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

Candidate = dict[str, Any]
NewId = Callable[[], str]


# -- candidate discovery -----------------------------------------------------


def growth_candidates(
    program: dict[str, Any],
    presented_targets: frozenset[str],
    policy: dict[str, Any],
) -> list[Candidate]:
    """Growth candidates in canonical order (control 4.4 step 4).

    Topic rank is the authored program order -- the curriculum's own priority
    sequence; ``learner_relevance`` is constant until the learner module
    exists, so the canonical sort degenerates to (rank, target_id, ...).
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
                "sort_rank": rank,
            }
        )
    micro = _micro_lane_candidate(program, presented_targets, policy)
    if micro is not None:
        out.append(micro)
    return out


def _micro_lane_candidate(
    program: dict[str, Any],
    presented_targets: frozenset[str],
    policy: dict[str, Any],
) -> Candidate | None:
    """The lexicon-first micro lane (generation@1, PD-5 D): at most one safe,
    unlinked CORE/HIGH unit per balanced session, ranked after every topic."""
    linked: set[str] = set()
    for topic in program.get("topics", []):
        linked.update(str(ref) for ref in (topic.get("lexicon") or []))
    band_rank = {"CORE": 0, "HIGH": 1}
    eligible: list[tuple[int, str, dict[str, Any]]] = []
    for unit in program.get("lexicon", []):
        unit_id = str(unit.get("id"))
        band = str(unit.get("curriculum_priority_band", ""))
        if unit_id in linked or unit_id in presented_targets or band not in band_rank:
            continue
        if str(unit.get("usage_policy", "safe_to_use")) != "safe_to_use":
            continue  # avoid/caution/recognition_only units never enter production lanes
        if str(unit.get("currency", "current")) != "current":
            continue  # dated/expired units are not introduced as new material
        eligible.append((band_rank[band], unit_id, unit))
    if not eligible:
        return None
    _, unit_id, unit = min(eligible)
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
        # After every topic candidate: the micro lane supplements growth, it
        # never displaces the curriculum's own recommendations (advisory cap
        # of one is enforced by emitting a single candidate).
        "sort_rank": 10_000_000,
    }


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
    return sorted(
        candidates,
        key=lambda c: (
            c["sort_rank"],
            str(c.get("target_ref") or ""),
            str(c.get("dimension") or ""),
            STEP_TYPE_RANK[c["step_type"]],
            c["candidate_id"],
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
    new_id: NewId,
) -> dict[str, Any]:
    """Compose the plan slice of the ``session_plan`` aggregate state.

    First composition: ``presented_*`` empty. Replan: the new revision gets
    only the remainder [RR2-6] -- residual floors are
    ``max(0, floor(total * min_bp / 10000) - presented[bucket])`` and overall
    capacity is ``total_seconds - presented_seconds``; already-presented steps
    are passed through verbatim and surviving candidates keep their step ids
    via ``keep_step_ids`` (``step_id`` is stable across revisions, 4.2).
    """
    minimum = int(policy["budget"]["min_total_minutes"]) * 60
    if total_seconds < minimum:
        raise BudgetTooSmall(
            f"total budget {total_seconds}s is below the policy minimum {minimum}s; ask for a longer session"
        )

    presented_by_bucket = presented_by_bucket or {}
    presented_steps = presented_steps or []
    keep_step_ids = keep_step_ids or {}
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

    pool: dict[str, list[Candidate]] = {
        "review": [],  # scheduler-owned; empty is the honest current state
        "growth": _canonical_sort(growth_candidates(program, presented_targets, policy)),
        "integration": [],  # needs a learned target from scoring
        "choice": _canonical_sort(choice_candidates(policy)),
    }

    admitted: list[Candidate] = []
    planned = {"review": 0, "growth": 0, "integration": 0, "choice": 0}
    waivers: list[str] = []
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
        planned[candidate["bucket"]] += candidate["expected_seconds"]
        admitted.append(candidate)
        pool[candidate["bucket"]].remove(candidate)

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

    # Step 7: review by class up to review_max. No scheduler yet => nothing to
    # classify; the empty backlog is recorded, not silently skipped.
    if not pool["review"]:
        waivers.append("NO_REVIEW_CANDIDATE")

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
    for offset, candidate in enumerate(admitted):
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
        step = {
            "step_id": keep_step_ids.get(candidate["candidate_id"]) or new_id(),
            "decision_id": new_id(),
            "candidate_id": candidate["candidate_id"],
            "kind": candidate["kind"],
            "bucket": candidate["bucket"],
            "step_type": candidate["step_type"],
            "expected_seconds": candidate["expected_seconds"],
            "order_index": next_index + offset,
            "presented_at": None,
            "context_id": candidate["context_id"],
            "lexicon_first": candidate["lexicon_first"],
            "bank_item_id": None,
            "generation_directive": directive,
        }
        if candidate["kind"] == "growth":
            step["target_ref"] = candidate["target_ref"]
            step["dimension"] = candidate["dimension"]
            step["is_first_exposure"] = True
        elif candidate["kind"] == "choice":
            step["target_ref"] = candidate.get("target_ref")
            step["topic_hint"] = candidate.get("topic_hint")
        steps.append(step)

    return {
        "steps": steps,
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


def step_targets(step: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``targets[]`` of a step for ``STEP_PRESENTED`` (control 4.6): every
    (target_ref, dimension) pair; empty only for target-less choice."""
    if step["kind"] == "growth":
        return [{"target_ref": step["target_ref"], "dimension": step["dimension"]}]
    if step["kind"] == "choice" and step.get("target_ref"):
        return [{"target_ref": step["target_ref"], "dimension": None}]
    return []
