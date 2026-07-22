"""The canonical composition pipeline (control 4.3-4.4; roadmap 2.2).

Fully deterministic: two correct executions over the same inputs produce a
byte-identical ``SessionPlan`` (the aggregate state is canonically encoded, so
"identical" is checkable as a hash). The pipeline follows control 4.4:
candidates -> safety exclusion -> canonical sort -> floor reservation in the
fixed order growth -> integration -> choice (a floor is reserved capacity, not
mandatory load [R-2]; the step that first reaches or crosses a non-zero floor
may exceed it whole [RR2-5]) -> review by class -> top-up passes -> diversity
quotas as an *admission filter*, not post-processing. First-fit, never
best-fit.

What this increment can honestly feed the pipeline:

- ``review``: **empty**. Due/overdue candidates come from the scheduler, which
  does not exist yet; an empty review bucket is the true state of the world,
  not a stub. Classification (4.5), starvation reserve, saturation (4.6),
  signals (4.7) and availability (4.7a) attach when their inputs exist.
- ``growth``: curriculum recommendations = the authored topic order of the
  pinned program (rank = position), filtered by ``is_first_exposure`` -- a
  target is new only while it has **no** ``STEP_PRESENTED`` at all (4.3);
  plus the lexicon-first micro lane of generation@1 (PD-5 D): at most one
  safe, unlinked CORE/HIGH lexical unit per balanced session.
- ``integration``: empty until scoring can name a *learned* target for the
  (new, learned) pair -- the waiver ``NO_INTEGRATION_CANDIDATE`` is recorded,
  and its reserve passes to the next bucket, exactly the first-session case
  the canon designed the waiver for (4.4 step 5).
- ``choice``: free conversation is an unconditional candidate [RR2-14], so
  ``NO_CHOICE_CANDIDATE`` cannot occur; ``topic_hint`` comes from an active
  goal once the learner module exists.

"Mode" in ``max_consecutive_same_mode`` is read as the step type (v1); the
interleaving of step 10 falls out of admission order, which the quota already
shapes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from english_trainer.control.errors import BudgetTooSmall, NoCandidates
from english_trainer.control.policy import (
    FLOOR_ORDER,
    STEP_TYPE_RANK,
    mode_shares,
    step_cost,
)
from english_trainer.control.signals import apply_signals, is_excluded
from english_trainer.control.trace import build_decision_trace

Candidate = dict[str, Any]
NewId = Callable[[], str]


# -- candidate discovery -----------------------------------------------------


def growth_candidates(
    program: dict[str, Any],
    presented_targets: frozenset[str],
    policy: dict[str, Any],
    relevant_targets: frozenset[str] = frozenset(),
) -> list[Candidate]:
    """Growth candidates in canonical order (control 4.4 step 4).

    Topic rank is the authored program order -- the curriculum's own priority
    sequence (``curriculum_priority_rank``). ``learner_relevance`` is the
    secondary key: a target the personal lexicon marks relevant (``goals`` join
    later) sorts ahead of an equal-rank neighbour and, for a learner-requested
    curriculum LexicalItem, enters the lexicon-first micro lane below. It never
    lifts a lexical item above a topic (rank is primary), and it never touches
    scoring. With ``relevant_targets`` empty the result is byte-identical to
    before (the default composition path).
    """
    cost = step_cost(policy, "new_material_intro")
    out: list[Candidate] = []
    for rank, topic in enumerate(program.get("topics", [])):
        topic_id = str(topic.get("id"))
        if topic_id in presented_targets:
            continue  # has a STEP_PRESENTED somewhere => not first exposure
        dimensions = topic.get("dimensions") or ["recognition"]
        contexts = topic.get("contexts") or ["general"]
        out.append(
            {
                "candidate_id": f"growth:topic:{topic_id}",
                "kind": "growth",
                "bucket": "growth",
                "step_type": "new_material_intro",
                "expected_seconds": cost,
                "target_ref": topic_id,
                "dimension": str(dimensions[0]),
                "context_id": f"{contexts[0]}|new_material_intro",
                "lexicon_first": False,
                "lexicon_refs": [str(ref) for ref in (topic.get("lexicon") or [])],
                "learner_relevance": 1 if topic_id in relevant_targets else 0,
                "sort_rank": rank,
            }
        )
    out.extend(_micro_lane_candidates(program, presented_targets, policy, relevant_targets))
    return out


def _lexicon_growth_candidate(
    unit: dict[str, Any], policy: dict[str, Any], *, learner_relevance: int
) -> Candidate:
    unit_id = str(unit.get("id"))
    domains = unit.get("domains") or ["general"]
    return {
        "candidate_id": f"growth:lexicon:{unit_id}",
        "kind": "growth",
        "bucket": "growth",
        "step_type": "new_material_intro",
        "expected_seconds": step_cost(policy, "new_material_intro"),
        "target_ref": unit_id,
        "dimension": "recognition",
        "context_id": f"{domains[0]}|new_material_intro",
        "lexicon_first": True,
        "lexicon_refs": [unit_id],
        "learner_relevance": learner_relevance,
        # After every topic candidate: the micro lane supplements growth, it
        # never displaces the curriculum's own recommendations.
        "sort_rank": 10_000_000,
    }


def _is_safe_current(unit: dict[str, Any]) -> bool:
    return (
        str(unit.get("usage_policy", "safe_to_use")) == "safe_to_use"
        and str(unit.get("currency", "current")) == "current"
    )


def _micro_lane_candidates(
    program: dict[str, Any],
    presented_targets: frozenset[str],
    policy: dict[str, Any],
    relevant_targets: frozenset[str],
) -> list[Candidate]:
    """The lexicon-first micro lane (generation@1, PD-5 D; control 4.4 step 1).

    Two arms, both safe + current only:

    - **learner-requested** (``relevant_targets``): a curriculum LexicalItem the
      personal lexicon linked to -- an explicit vocabulary request, so it is
      admitted even when it is attached to a topic (which the default cap
      excludes). ``learner_relevance = 1``.
    - the historical **fallback**: at most one safe, unlinked CORE/HIGH unit per
      session (``learner_relevance = 0``), skipped when it is already emitted as
      a learner request.

    With ``relevant_targets`` empty the first arm is empty and the result is
    exactly the single fallback candidate (or none) -- byte-identical to before.
    """
    by_id = {str(unit.get("id")): unit for unit in program.get("lexicon", [])}
    out: list[Candidate] = []
    emitted: set[str] = set()
    # Learner-requested arm, in canonical id order for determinism.
    for unit_id in sorted(relevant_targets):
        unit = by_id.get(unit_id)
        if unit is None or unit_id in presented_targets or not _is_safe_current(unit):
            continue
        out.append(_lexicon_growth_candidate(unit, policy, learner_relevance=1))
        emitted.add(unit_id)

    # Fallback arm: unchanged selection of one unlinked CORE/HIGH unit.
    linked: set[str] = set()
    for topic in program.get("topics", []):
        linked.update(str(ref) for ref in (topic.get("lexicon") or []))
    band_rank = {"CORE": 0, "HIGH": 1}
    eligible: list[tuple[int, str, dict[str, Any]]] = []
    for unit in program.get("lexicon", []):
        unit_id = str(unit.get("id"))
        band = str(unit.get("curriculum_priority_band", ""))
        if unit_id in linked or unit_id in presented_targets or unit_id in emitted or band not in band_rank:
            continue
        if not _is_safe_current(unit):
            continue  # avoid/caution/recognition_only or dated units never enter production lanes
        eligible.append((band_rank[band], unit_id, unit))
    if eligible:
        _, _, unit = min(eligible)
        out.append(_lexicon_growth_candidate(unit, policy, learner_relevance=0))
    return out


def choice_candidates(policy: dict[str, Any]) -> list[Candidate]:
    """Free conversation, unconditionally [RR2-14]. ``topic_hint`` stays empty
    until the learner module contributes goals."""
    return [
        {
            "candidate_id": "choice:free-conversation",
            "kind": "choice",
            "bucket": "choice",
            "step_type": "free_conversation",
            "expected_seconds": step_cost(policy, "free_conversation"),
            "target_ref": None,
            "dimension": None,
            "context_id": "conversation|free_conversation",
            "lexicon_first": False,
            "lexicon_refs": [],
            "topic_hint": None,
            "sort_rank": 5,  # source_rank: free conversation is 5 (4.4 step 4)
        }
    ]


def _canonical_sort(candidates: list[Candidate]) -> list[Candidate]:
    # (curriculum_priority_rank asc, learner_relevance desc, target_id asc,
    # dimension asc, step_type_rank asc, candidate_id asc) -- control 4.4 step 4.
    # ``learner_relevance`` defaults to 0 (choice candidates, and every candidate
    # when no personal-lexicon relevance exists), so the order is unchanged for
    # the default path.
    return sorted(
        candidates,
        key=lambda c: (
            c["sort_rank"],
            -int(c.get("learner_relevance", 0)),
            str(c.get("target_ref") or ""),
            str(c.get("dimension") or ""),
            STEP_TYPE_RANK[c["step_type"]],
            c["candidate_id"],
        ),
    )


_MAX_SEQ = 1 << 62  # an unqualified candidate sorts last (defensive; reserve is qualified)


def _reserve_sort(candidates: list[Candidate]) -> list[Candidate]:
    """The starvation reserve order (control 4.5 [R-6, RR2-8]): oldest
    qualification episode first, so a younger episode never overtakes an open one.
    """
    return sorted(
        candidates,
        key=lambda c: (
            int(c["qualified_at_session_seq"]) if c.get("qualified_at_session_seq") is not None else _MAX_SEQ,
            -int(c.get("deferral_count", 0)),
            int(c.get("retrievability_ppm", 0)),
            str(c.get("target_ref") or ""),
            str(c.get("dimension") or ""),
        ),
    )


# -- the pipeline ------------------------------------------------------------


def compose_plan(
    *,
    program: dict[str, Any],
    policy: dict[str, Any],
    generation_version: str,
    mode: str,
    total_seconds: int,
    presented_targets: frozenset[str] = frozenset(),
    presented_by_bucket: dict[str, int] | None = None,
    presented_steps: list[dict[str, Any]] | None = None,
    keep_step_ids: dict[str, str] | None = None,
    review_candidates: list[Candidate] | None = None,
    keep_review_ids: dict[str, str] | None = None,
    signals: list[dict[str, Any]] | None = None,
    probe: dict[str, Any] | None = None,
    starvation_candidates: list[Candidate] | None = None,
    relevant_targets: frozenset[str] = frozenset(),
    availability_long_break: bool = False,
    bank_items: list[dict[str, Any]] | None = None,
    pinned_versions: dict[str, str] | None = None,
    active_safety_version: str | None = None,
    new_id: NewId,
) -> dict[str, Any]:
    """Compose the plan slice of the ``session_plan`` aggregate state.

    First composition: ``presented_*`` empty. Replan: the new revision gets
    only the remainder [RR2-6] -- residual floors are
    ``max(0, floor(total * min_bp / 10000) - presented[bucket])`` and overall
    capacity is ``total_seconds - presented_seconds``; already-presented steps
    are passed through verbatim and surviving candidates keep their step ids
    via ``keep_step_ids`` (``step_id`` is stable across revisions, 4.2).

    ``signals`` are the active learner control signals (control 4.7): applied
    after classification (step 3a) they exclude or reshuffle review candidates
    and exclude growth candidates, all deterministically. ``probe`` is a
    pre-built ``kind=probe`` candidate for a ``too_easy`` target; it is first-fit
    into the remainder (step 6a). When it is admitted its signal id appears in
    the returned ``consumed`` list so the caller can retire the signal
    (``SIGNAL_CONSUMED``) in the same UnitOfWork that saves this plan; when it
    does not fit, ``PROBE_BUDGET_UNAVAILABLE`` is waived and the signal is NOT
    consumed. Both default empty -- the pipeline is byte-identical without them.

    ``bank_items`` is the already-accepted, caller-revalidated exercise-bank
    view. Matching is deterministic and conservative: step type, target,
    dimension and context must agree exactly, and an item already presented in
    this session is not selected again. The default empty view preserves the
    original generation-directive path byte-for-byte.

    ``starvation_candidates`` are the qualified review candidates (control 4.5
    [CTRL-7], a subset of ``review_candidates`` by ``candidate_id``, each carrying
    ``qualified_at_session_seq``). Before review fills by class (step 6) up to
    ``reserved_steps_per_session`` of them are admitted UNCONDITIONALLY -- bypassing
    ``review_max``; only the overall remainder and the already-secured non-zero
    floors bound them -- in the reserve order (qualified_at_session_seq asc,
    deferral_count desc, retrievability asc, target_id asc, dimension_id asc). A
    step that does not fit records ``STARVATION_STEP_DOES_NOT_FIT`` and stops the
    reserve, so a younger episode never overtakes an older one (the FIFO the
    waiting bound needs). Default ``None`` -- the pipeline is byte-identical
    without it.

    ``relevant_targets`` are the curriculum targets the personal lexicon marks
    relevant (learner 4; control 4.5): they raise ``learner_relevance`` in the
    growth sort and let a learner-requested LexicalItem enter the lexicon-first
    micro lane. Default empty -- the pipeline is byte-identical without it, and
    it never touches scoring (an encounter is enrollment, not evidence).
    """
    minimum = int(policy["budget"]["min_total_minutes"]) * 60
    if total_seconds < minimum:
        raise BudgetTooSmall(
            f"total budget {total_seconds}s is below the policy minimum {minimum}s; ask for a longer session"
        )

    presented_by_bucket = presented_by_bucket or {}
    presented_steps = presented_steps or []
    keep_step_ids = keep_step_ids or {}
    keep_review_ids = keep_review_ids or {}
    presented_seconds = sum(presented_by_bucket.values())
    capacity = total_seconds - presented_seconds  # DeliveryLedger.remaining_seconds

    shares = mode_shares(policy, mode)
    floors = {
        "growth": shares["growth_min"],
        "integration": shares["integration_min"],
        "choice": shares["choice_min"],
    }
    residual_floor = {
        bucket: max(0, (total_seconds * bp) // 10000 - presented_by_bucket.get(bucket, 0))
        for bucket, bp in floors.items()
    }
    # review_max is a CAP on the effective total, not a floor (4.2 [RR2-6]).
    review_cap = max(
        0, (total_seconds * shares["review_max"]) // 10000 - presented_by_bucket.get("review", 0)
    )

    def _review_sort(candidates: list[Candidate]) -> list[Candidate]:
        # Canonical order within a class (4.4 step 4): risk first, then stake,
        # then deferral age, then cost, then the stable tie-breakers.
        return sorted(
            candidates,
            key=lambda c: (
                int(c.get("retrievability_ppm", 0)),
                int(c.get("stake_rank", 2)),
                -int(c.get("deferral_count", 0)),
                int(c["expected_seconds"]),
                str(c.get("target_ref") or ""),
                str(c.get("dimension") or ""),
                c["candidate_id"],
            ),
        )

    # Step 3a: apply active learner signals after base classification (4.7).
    # Precedence reshapes the review candidates and can exclude growth targets;
    # both are deterministic, so the plan stays byte-identical.
    active = list(signals or [])
    signal_waivers: list[str] = []
    review_list = list(review_candidates or [])
    eligible_review = sorted(
        {
            (str(candidate.get("target_ref")), str(candidate.get("dimension")))
            for candidate in review_list
            if candidate.get("target_ref") is not None and candidate.get("dimension") is not None
        }
    )
    excluded_review = sorted(
        {
            (str(candidate.get("target_ref")), str(candidate.get("dimension")))
            for candidate in review_list
            if candidate.get("target_ref") is not None
            and candidate.get("dimension") is not None
            and bool(active)
            and is_excluded(candidate, active)
        }
    )
    growth_list = growth_candidates(program, presented_targets, policy, relevant_targets)
    if active:
        review_list, signal_waivers = apply_signals(review_list, active)
        growth_list = [candidate for candidate in growth_list if not is_excluded(candidate, active)]

    pool: dict[str, list[Candidate]] = {
        "review": _review_sort(review_list),
        "growth": _canonical_sort(growth_list),
        "integration": [],  # needs a learned target from scoring
        "choice": _canonical_sort(choice_candidates(policy)),
    }

    admitted: list[Candidate] = []
    planned = {"review": 0, "growth": 0, "integration": 0, "choice": 0}
    waivers: list[str] = list(signal_waivers)
    consumed: list[str] = []
    starvation_admitted: list[str] = []
    admission_occupancy: dict[str, tuple[dict[str, int], dict[str, int]]] = {}
    diversity = policy["diversity"]
    max_consecutive = int(diversity["max_consecutive_same_mode"])
    max_per_topic = int(diversity["max_steps_per_topic"])

    def planned_total() -> int:
        return sum(planned.values())

    def quota_allows(candidate: Candidate) -> bool:
        # max_consecutive_same_mode: refuse the step that would make
        # (max_consecutive + 1) same-typed steps in a row of admission order.
        tail = admitted[-max_consecutive:]
        if len(tail) == max_consecutive and all(s["step_type"] == candidate["step_type"] for s in tail):
            return False
        # max_steps_per_topic: growth is one step per target already [R-13];
        # this guards the general case once review/integration exist.
        target = candidate.get("target_ref")
        if target is not None:
            same_topic = sum(1 for s in admitted if s.get("target_ref") == target)
            if same_topic >= max_per_topic:
                return False
        return True

    def admit(candidate: Candidate) -> None:
        before = dict(planned)
        planned[candidate["bucket"]] += candidate["expected_seconds"]
        admitted.append(candidate)
        pool[candidate["bucket"]].remove(candidate)
        admission_occupancy[str(candidate["candidate_id"])] = (before, dict(planned))

    # Step 5: reserve residual floors, growth -> integration -> choice. The
    # step that first reaches or crosses a non-zero floor is admitted whole if
    # it fits the overall remainder; after it the floor counts as closed.
    for bucket in FLOOR_ORDER:
        floor = residual_floor[bucket]
        if floor <= 0:
            continue
        if not pool[bucket]:
            waivers.append(f"NO_{bucket.upper()}_CANDIDATE")
            continue
        admitted_any = False
        for candidate in list(pool[bucket]):
            if planned[bucket] >= floor:
                break
            if candidate["expected_seconds"] + planned_total() > capacity:
                continue  # first-fit: skip, try the next candidate
            if not quota_allows(candidate):
                continue
            admit(candidate)
            admitted_any = True
        if planned[bucket] < floor:
            waivers.append(
                f"{bucket.upper()}_CANDIDATES_EXHAUSTED" if admitted_any else f"NO_{bucket.upper()}_STEP_FITS"
            )

    # Step 6: starvation reserve (4.4 step 6 / 4.5 [CTRL-7]). Before review fills
    # by class, admit up to reserved_steps_per_session qualified review candidates
    # UNCONDITIONALLY -- bypassing review_cap; only the overall remainder bounds
    # them, and the non-zero floors were already secured in step 5. In the reserve
    # order; a step that does not fit stops the reserve so a younger episode never
    # overtakes an older open one (the FIFO the waiting bound depends on).
    if starvation_candidates:
        reserve_limit = int(policy["starvation"]["reserved_steps_per_session"])
        by_id = {c["candidate_id"]: c for c in pool["review"]}
        reserve = _reserve_sort(
            [by_id[c["candidate_id"]] for c in starvation_candidates if c["candidate_id"] in by_id]
        )
        seen_reserved: set[str] = set()
        reserved_admitted = 0
        for candidate in reserve:
            candidate_id = candidate["candidate_id"]
            if candidate_id in seen_reserved:
                continue
            seen_reserved.add(candidate_id)
            if reserved_admitted >= reserve_limit:
                break
            if candidate["expected_seconds"] + planned_total() > capacity:
                # The session is too short for the oldest reserved step: the
                # episode is not consumed and stays open for the next composition.
                waivers.append("STARVATION_STEP_DOES_NOT_FIT")
                break
            admit(candidate)  # into the review bucket, above review_cap by design
            starvation_admitted.append(str(candidate["candidate_id"]))
            reserved_admitted += 1

    # Step 6/Availability: after residual floors and the starvation reserve,
    # a long break may spend a small, bounded slice on critical review. It
    # never crosses review_max, never overshoots its own capacity, and runs
    # before ordinary review and growth top-up (control 4.7a).
    if availability_long_break:
        residual_review_capacity = max(0, review_cap - planned["review"])
        unplanned_remaining = max(0, capacity - planned_total())
        boost_capacity = min(
            total_seconds * int(policy["availability"]["reentry_critical_boost_bp"]) // 10000,
            residual_review_capacity,
            unplanned_remaining,
        )
        boosted = False
        if boost_capacity > 0:
            boost_used = 0
            for candidate in [c for c in list(pool["review"]) if c.get("urgency_class") == "critical"]:
                cost = int(candidate["expected_seconds"])
                if boost_used + cost > boost_capacity:
                    continue
                if cost + planned_total() > capacity or not quota_allows(candidate):
                    continue
                admit(candidate)
                boost_used += cost
                boosted = True
        if not boosted:
            waivers.append("NO_CRITICAL_AVAILABILITY_CANDIDATE")

    # Step 6a: first-fit the pending probe into the remainder (4.7). The probe
    # is a choice-bucket step (source_rank 0). On admission its signal id is
    # returned in ``consumed`` so the caller retires the too_easy signal
    # (SIGNAL_CONSUMED) in the same UoW that saves this plan; if it does not fit,
    # the per-target probe budget is spent, or an exclusion applies, the trace
    # gets PROBE_BUDGET_UNAVAILABLE and the signal survives (NOT consumed).
    if probe is not None:
        already = any(
            step.get("kind") == "probe" and step.get("target_ref") == probe["target_ref"]
            for step in presented_steps
        )
        blocked = already or (bool(active) and is_excluded(probe, active))
        fits = probe["expected_seconds"] + planned_total() <= capacity and quota_allows(probe)
        if blocked or not fits:
            waivers.append("PROBE_BUDGET_UNAVAILABLE")
        else:
            before = dict(planned)
            planned[probe["bucket"]] += int(probe["expected_seconds"])
            admitted.append(probe)
            admission_occupancy[str(probe["candidate_id"])] = (before, dict(planned))
            consumed.append(str(probe["signal_id"]))

    # Step 7: review by urgency class, critical -> important -> normal ->
    # maintenance, until review_max or the budget stops it. First-fit; the
    # empty backlog is recorded, not silently skipped.
    if not pool["review"]:
        waivers.append("NO_REVIEW_CANDIDATE")
    else:
        admitted_review = False
        for klass in ("critical", "important", "normal", "maintenance"):
            for candidate in [c for c in list(pool["review"]) if c.get("urgency_class") == klass]:
                cost = candidate["expected_seconds"]
                if planned["review"] + cost > review_cap:
                    continue  # the cap bounds effective review share [RR2-6]
                if cost + planned_total() > capacity:
                    continue
                if not quota_allows(candidate):
                    continue
                admit(candidate)
                admitted_review = True
        if not admitted_review:
            waivers.append("NO_REVIEW_STEP_FITS")

    # Step 8: top-up passes in the fixed order, one pass each, first-fit.
    for bucket in FLOOR_ORDER:
        for candidate in list(pool[bucket]):
            if candidate["expected_seconds"] + planned_total() > capacity:
                continue
            if not quota_allows(candidate):
                continue
            admit(candidate)

    if not admitted:
        raise NoCandidates(
            "composition admitted zero steps: every candidate was presented, skipped or did not fit; "
            "finish or abandon the session"
        )

    # Materialize steps: admission order IS the presentation order (step 10's
    # interleaving is produced by the consecutive-mode quota at admission).
    next_index = max((int(s["order_index"]) for s in presented_steps), default=-1) + 1
    steps: list[dict[str, Any]] = [dict(s) for s in presented_steps]
    available_bank = sorted(
        [item for item in (bank_items or []) if item.get("status") == "accepted"],
        key=lambda item: str(item.get("exercise_instance_id") or ""),
    )
    used_bank_ids = {
        str(step["bank_item_id"]) for step in presented_steps if step.get("bank_item_id") is not None
    }

    def matching_bank_item(candidate: Candidate) -> dict[str, Any] | None:
        target = candidate.get("target_ref")
        expected_targets = [str(target)] if target is not None else []
        dimension = candidate.get("dimension")
        expected_dimensions = [str(dimension)] if dimension is not None else []
        for item in available_bank:
            item_id = str(item.get("exercise_instance_id") or "")
            if not item_id or item_id in used_bank_ids:
                continue
            if str(item.get("step_type") or "") != str(candidate["step_type"]):
                continue
            if sorted(str(ref) for ref in item.get("target_refs") or []) != expected_targets:
                continue
            if sorted(str(dim) for dim in item.get("dimensions") or []) != expected_dimensions:
                continue
            if str(item.get("context_id") or "") != str(candidate.get("context_id") or ""):
                continue
            used_bank_ids.add(item_id)
            return item
        return None

    for offset, candidate in enumerate(admitted):
        decision_id = new_id()
        occupancy = admission_occupancy[str(candidate["candidate_id"])]
        directive = {
            "schema_version": 1,
            "generation_policy": generation_version,
            "kind": candidate["kind"],
            "step_type": candidate["step_type"],
            "target_ref": candidate.get("target_ref"),
            "dimension": candidate.get("dimension"),
            "context_id": candidate["context_id"],
            "lexicon_refs": candidate["lexicon_refs"],
            "topic_hint": candidate.get("topic_hint"),
        }
        if candidate["kind"] == "probe":
            # The probe tells the tutor which context to steer clear of (4.7).
            directive["avoid_context"] = candidate.get("avoid_context")
        bank_item = matching_bank_item(candidate)
        step = {
            "step_id": keep_step_ids.get(candidate["candidate_id"]) or new_id(),
            "decision_id": decision_id,
            "candidate_id": candidate["candidate_id"],
            "kind": candidate["kind"],
            "bucket": candidate["bucket"],
            "step_type": candidate["step_type"],
            "expected_seconds": candidate["expected_seconds"],
            "order_index": next_index + offset,
            "presented_at": None,
            "context_id": candidate["context_id"],
            "lexicon_first": candidate["lexicon_first"],
            "bank_item_id": (str(bank_item["exercise_instance_id"]) if bank_item is not None else None),
            "generation_directive": None if bank_item is not None else directive,
            "decision_trace": build_decision_trace(
                candidate,
                decision_id=decision_id,
                policy=policy,
                generation_version=generation_version,
                pinned_versions=pinned_versions,
                active_safety_version=active_safety_version,
                bucket_before=occupancy[0],
                bucket_after=occupancy[1],
            ),
        }
        if candidate["kind"] == "growth":
            step["target_ref"] = candidate["target_ref"]
            step["dimension"] = candidate["dimension"]
            step["is_first_exposure"] = True
        elif candidate["kind"] == "review":
            # A review step MUST carry its assignment id (4.3a) -- without it
            # the delivered task cannot be closed through `trainer review
            # close` and finish cannot check the pending set. Stable across
            # revisions for surviving candidates, like step_id.
            step["target_ref"] = candidate["target_ref"]
            step["dimension"] = candidate["dimension"]
            step["review_assignment_id"] = keep_review_ids.get(candidate["candidate_id"]) or new_id()
            step["urgency_class"] = candidate["urgency_class"]
            step["criteria_ref"] = candidate.get("criteria_ref")
            step["schedule_epoch"] = candidate.get("schedule_epoch")
        elif candidate["kind"] == "choice":
            step["target_ref"] = candidate.get("target_ref")
            step["topic_hint"] = candidate.get("topic_hint")
        elif candidate["kind"] == "probe":
            # A probe carries its engine id, dimension, requested difficulty and
            # the context to avoid; step_targets exposes (target, dimension) so
            # its STEP_PRESENTED derives origin=control_probe downstream (4.7).
            step["target_ref"] = candidate["target_ref"]
            step["dimension"] = candidate.get("dimension")
            step["probe_id"] = candidate["probe_id"]
            step["requested_difficulty"] = candidate["requested_difficulty"]
            step["avoid_context"] = candidate.get("avoid_context")
        steps.append(step)

    result: dict[str, Any] = {
        "steps": steps,
        "consumed": consumed,
        "budget": {"planned": planned},
        "ledger": {
            "presented": {b: presented_by_bucket.get(b, 0) for b in planned},
            "presented_seconds": presented_seconds,
            "remaining_seconds": capacity,
        },
        "waivers": waivers,
        "allocations": {
            "review_cap": (total_seconds * shares["review_max"]) // 10000,
            "floors": {b: (total_seconds * bp) // 10000 for b, bp in floors.items()},
        },
    }
    # New live-fold facts are present only when their optional inputs were
    # supplied. Calls using the historical/default surface retain the exact
    # canonical result shape (control 4.4 determinism compatibility).
    if review_candidates is not None:
        result["eligible_review"] = [
            {"target_ref": target_ref, "dimension": dimension} for target_ref, dimension in eligible_review
        ]
        result["excluded_review"] = [
            {"target_ref": target_ref, "dimension": dimension} for target_ref, dimension in excluded_review
        ]
    if starvation_candidates is not None:
        result["starvation_admitted"] = starvation_admitted
    return result


def step_targets(step: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``targets[]`` of a step for ``STEP_PRESENTED`` (control 4.6): every
    (target_ref, dimension) pair; empty only for target-less choice."""
    if step["kind"] in ("growth", "review", "probe"):
        return [{"target_ref": step["target_ref"], "dimension": step["dimension"]}]
    if step["kind"] == "choice" and step.get("target_ref"):
        return [{"target_ref": step["target_ref"], "dimension": None}]
    return []
