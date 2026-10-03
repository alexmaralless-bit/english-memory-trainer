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
from typing import Any, cast

from english_trainer.control.errors import BudgetTooSmall, NoCandidates
from english_trainer.control.lesson_profiles import phase_for_step
from english_trainer.control.policy import (
    CONTRAST_MAX,
    CONTRAST_MIN,
    DRILL_BLOCK,
    FLOOR_ORDER,
    RECONSTRUCTION,
    STEP_TYPE_RANK,
    TIMED_WRITING,
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


def _profile_growth_candidates(
    program: dict[str, Any],
    policy: dict[str, Any],
    *,
    target_ref: str,
    is_first_exposure: bool,
    profile: str,
) -> list[Candidate]:
    """A coherent activity sequence around one central target.

    This is the generation@2 path.  It intentionally creates several
    *different retrieval conditions* for one topic rather than treating four
    unrelated topic introductions as a complete lesson.
    """
    topics = list(program.get("topics", []))
    lexical_items = list(program.get("lexicon", []))
    target = next(
        (item for item in [*topics, *lexical_items] if str(item.get("id")) == target_ref),
        None,
    )
    if target is None:
        return []
    is_lexical = any(str(item.get("id")) == target_ref for item in lexical_items)
    dimensions = [
        str(value)
        for value in (
            target.get("dimensions")
            or (
                ["recognition", "controlled_production", "spontaneous_production"]
                if is_lexical
                else ["recognition"]
            )
        )
    ]
    contexts = [str(value) for value in (target.get("contexts") or target.get("domains") or ["general"])]
    lexicon_refs = [str(ref) for ref in (target.get("lexicon") or [])]
    if is_lexical:
        lexicon_refs = sorted({*lexicon_refs, target_ref})

    if profile == "vocabulary_lesson":
        sequence = (
            ("new_material_intro", "recognition"),
            ("recognition_check", "recognition"),
            ("controlled_production", "controlled_production"),
            ("spontaneous_production", "spontaneous_production"),
        )
    else:
        sequence = (
            ("new_material_intro", dimensions[0]),
            ("recognition_check", "recognition"),
            ("controlled_production", "controlled_production"),
            ("spontaneous_production", "spontaneous_production"),
        )

    out: list[Candidate] = []
    for rank, (step_type, preferred_dimension) in enumerate(sequence):
        dimension = (
            preferred_dimension
            if preferred_dimension in dimensions
            else dimensions[min(rank, len(dimensions) - 1)]
        )
        context = contexts[rank % len(contexts)]
        out.append(
            {
                "candidate_id": f"profile:{profile}:{target_ref}:{step_type}",
                "kind": "growth",
                "bucket": "growth",
                "step_type": step_type,
                "expected_seconds": step_cost(policy, step_type),
                "target_ref": target_ref,
                "dimension": dimension,
                "context_id": f"{context}|{step_type}",
                "lexicon_first": False,
                "lexicon_refs": lexicon_refs,
                "learner_relevance": 1,
                "sort_rank": rank,
                "is_first_exposure": is_first_exposure,
            }
        )
    return out


# -- the automaticity loop (control 4.3a, 4.6 [PD-2026-09-22]) ---------------

# The canonical drill agenda runs two rounds (the contract allows 2-3): one
# blocked, one interleaved. A third round would be a policy decision, not an
# implementation detail, so it is not invented here.
DRILL_ROUNDS = 2

# LearnerPreferences (learner 4a) owns ``round_size`` and ``timed_limit_seconds``.
# Control *reads* them and keeps no copy of its own; these are the fallbacks used
# only while no preferences have been recorded, and they mirror the documented
# learner defaults so the two can never disagree silently.
DEFAULT_ROUND_SIZE = 6
DEFAULT_TIMED_LIMIT_SECONDS = 240

# Agenda slots of the `drill` profile; the admitted steps are re-ordered by this
# key before materialization so the plan's presentation order is the canonical
# agenda rather than the bucket order the generic pipeline admits in.
AGENDA_RANK_WARMUP = 0
AGENDA_RANK_FRAME_SET = 1
AGENDA_RANK_DRILL_BLOCKED = 2
AGENDA_RANK_DRILL_INTERLEAVED = 3
AGENDA_RANK_RECONSTRUCTION = 4
AGENDA_RANK_TIMED_WRITING = 5
_AGENDA_RANK_OTHER = 8  # anything the agenda does not name sorts after it


def _preference(preferences: dict[str, Any] | None, key: str, fallback: int) -> int:
    value = (preferences or {}).get(key)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else fallback


def _program_targets(program: dict[str, Any]) -> list[dict[str, Any]]:
    """Topics then lexical units, in authored order -- the canonical pool."""
    return [cast(dict[str, Any], item) for item in [*program.get("topics", []), *program.get("lexicon", [])]]


def _family_key(item: dict[str, Any]) -> tuple[str, str]:
    """The (track, CEFR) family a contrast set is drawn from.

    A topic carries ``track``; a lexical unit has no track, so its ``type``
    (chunk / word / collocation) plays that role. Both carry ``cefr``.
    """
    return (
        str(item.get("track") or item.get("type") or ""),
        str(item.get("cefr") or ""),
    )


def contrast_targets(
    program: dict[str, Any],
    target_ref: str,
    *,
    dimension: str | None = None,
    limit: int = CONTRAST_MAX,
) -> list[dict[str, Any]]:
    """The deterministic contrast set of an interleaved drill block (control 4.6).

    Two branches, in this order:

    (a) **authored contrasts as target ids** -- ``contrast_refs``, or a
        ``contrasts`` entry that is itself a known target id. Today the authored
        ``contrasts`` field holds prose lines, not ids, so this branch is
        normally empty; it exists so that curriculum which *does* expose ids
        wins over the structural fallback without a code change.
    (b) **same family from the candidate pool** -- every other target of the
        same ``(track, CEFR)`` family, in canonical order (authored program
        position, then target id), safe and current only.

    At most ``limit`` (4) are returned. Fewer than ``CONTRAST_MIN`` (2) means the
    caller must record ``NO_CONTRAST_CANDIDATE``: two competing forms is the
    smallest set that is interleaving rather than decoration.
    """
    pool = _program_targets(program)
    by_id = {str(item.get("id")): item for item in pool}
    order = {str(item.get("id")): rank for rank, item in enumerate(pool)}
    primary = by_id.get(target_ref)
    if primary is None:
        return []

    def _entry(item: dict[str, Any]) -> dict[str, Any]:
        dims = [str(value) for value in (item.get("dimensions") or [])]
        chosen = dimension if dimension in dims else (dims[0] if dims else dimension)
        return {"target_ref": str(item.get("id")), "dimension": chosen, "role": "contrast"}

    authored: list[str] = [str(ref) for ref in (primary.get("contrast_refs") or [])]
    authored += [str(ref) for ref in (primary.get("contrasts") or []) if str(ref) in by_id]
    picked = [ref for ref in dict.fromkeys(authored) if ref in by_id and ref != target_ref]
    if len(picked) >= CONTRAST_MIN:
        picked.sort(key=lambda ref: (order[ref], ref))
        return [_entry(by_id[ref]) for ref in picked[:limit]]

    family = _family_key(primary)
    siblings = [
        item
        for item in pool
        if str(item.get("id")) != target_ref and _family_key(item) == family and _is_safe_current(item)
    ]
    siblings.sort(key=lambda item: (order[str(item.get("id"))], str(item.get("id"))))
    return [_entry(item) for item in siblings[:limit]]


def drill_block_mode(
    target_ref: str,
    presented_targets: frozenset[str],
    *,
    round_index: int,
) -> str:
    """``blocked`` or ``interleaved`` for one drill block (control 4.6).

    A block is ``blocked`` **only** on the pattern's very first exposure: the
    target has no ``STEP_PRESENTED`` at all and this is the first round of the
    plan. Any later block -- a second round in the same lesson, or any block for
    a target that was already delivered once -- is ``interleaved`` and must carry
    contrast targets. Blocked practice is what makes the pattern form at all;
    only mixing it with the forms it competes against makes it survive.
    """
    first_exposure = target_ref not in presented_targets
    return "blocked" if first_exposure and round_index == 0 else "interleaved"


def _drill_growth_candidates(
    program: dict[str, Any],
    policy: dict[str, Any],
    *,
    target_ref: str,
    is_first_exposure: bool,
    presented_targets: frozenset[str],
    round_size: int,
) -> list[Candidate]:
    """Frame set + two drill rounds for the `drill` profile (control 4.2a)."""
    target = next(
        (item for item in _program_targets(program) if str(item.get("id")) == target_ref),
        None,
    )
    if target is None:
        return []
    dimensions = [str(value) for value in (target.get("dimensions") or ["controlled_production"])]
    contexts = [str(value) for value in (target.get("contexts") or target.get("domains") or ["general"])]
    lexicon_refs = [str(ref) for ref in (target.get("lexicon") or [])]
    if any(str(item.get("id")) == target_ref for item in program.get("lexicon", [])):
        lexicon_refs = sorted({*lexicon_refs, target_ref})
    drill_dimension = "controlled_production" if "controlled_production" in dimensions else dimensions[0]

    out: list[Candidate] = [
        {
            "candidate_id": f"profile:drill:{target_ref}:new_material_intro",
            "kind": "growth",
            "bucket": "growth",
            "step_type": "new_material_intro",
            "expected_seconds": step_cost(policy, "new_material_intro"),
            "target_ref": target_ref,
            "dimension": dimensions[0],
            "context_id": f"{contexts[0]}|new_material_intro",
            "lexicon_first": False,
            "lexicon_refs": lexicon_refs,
            "learner_relevance": 1,
            "sort_rank": 0,
            "agenda_rank": AGENDA_RANK_FRAME_SET,
            "is_first_exposure": is_first_exposure,
        }
    ]
    for round_index in range(DRILL_ROUNDS):
        mode = drill_block_mode(target_ref, presented_targets, round_index=round_index)
        contrasts: list[dict[str, Any]] = []
        if mode == "interleaved":
            contrasts = contrast_targets(program, target_ref, dimension=drill_dimension)
        waived = mode == "interleaved" and len(contrasts) < CONTRAST_MIN
        if waived:
            # Not enough competing forms exist: the block falls back to blocked
            # practice and says so in the trace instead of pretending to
            # interleave against one distractor.
            mode, contrasts = "blocked", []
        out.append(
            {
                "candidate_id": f"profile:drill:{target_ref}:drill_block:{round_index + 1}",
                "kind": "growth",
                "bucket": "growth",
                "step_type": DRILL_BLOCK,
                "expected_seconds": step_cost(policy, DRILL_BLOCK),
                "target_ref": target_ref,
                "dimension": drill_dimension,
                "context_id": f"{contexts[round_index % len(contexts)]}|{DRILL_BLOCK}",
                "lexicon_first": False,
                "lexicon_refs": lexicon_refs,
                "learner_relevance": 1,
                "sort_rank": round_index + 1,
                "agenda_rank": (
                    AGENDA_RANK_DRILL_BLOCKED if round_index == 0 else AGENDA_RANK_DRILL_INTERLEAVED
                ),
                # Growth is claimed once per target; the second round revisits a
                # target the plan has already introduced, so it is not a new one.
                "is_first_exposure": is_first_exposure and round_index == 0,
                "drill_mode": mode,
                "rounds": DRILL_ROUNDS,
                "round_size": round_size,
                "contrast_targets": contrasts,
                "contrast_waiver": waived,
                "targets": [
                    {"target_ref": target_ref, "dimension": drill_dimension, "role": "target"},
                    *contrasts,
                ],
            }
        )
    return out


def with_drill_fields(
    candidate: Candidate,
    program: dict[str, Any],
    presented_targets: frozenset[str],
    *,
    round_size: int = DEFAULT_ROUND_SIZE,
) -> Candidate:
    """Complete a ``drill_block`` candidate the composer did not build itself.

    The interleaving rule is a property of the STEP TYPE, not of the `drill`
    profile: a due review that the scheduler hands over as a drill block obeys
    it too. A candidate that already carries ``drill_mode`` (the profile lane
    decided it with its round index) and any candidate of another step type are
    returned unchanged -- identity included, so every historical composition
    stays byte-identical.
    """
    if candidate.get("step_type") != DRILL_BLOCK or "drill_mode" in candidate:
        return candidate
    target_ref = str(candidate.get("target_ref") or "")
    mode = drill_block_mode(target_ref, presented_targets, round_index=0)
    contrasts: list[dict[str, Any]] = []
    if mode == "interleaved":
        contrasts = contrast_targets(
            program, target_ref, dimension=str(candidate.get("dimension") or "") or None
        )
    waived = mode == "interleaved" and len(contrasts) < CONTRAST_MIN
    if waived:
        mode, contrasts = "blocked", []
    return {
        **candidate,
        "drill_mode": mode,
        "rounds": int(candidate.get("rounds") or DRILL_ROUNDS),
        "round_size": int(candidate.get("round_size") or round_size),
        "contrast_targets": contrasts,
        "contrast_waiver": waived,
        "targets": candidate.get("targets")
        or [
            {
                "target_ref": target_ref,
                "dimension": candidate.get("dimension"),
                "role": "target",
            },
            *contrasts,
        ],
    }


def _drill_integration_candidates(
    program: dict[str, Any],
    policy: dict[str, Any],
    *,
    target_ref: str,
    known_targets: frozenset[str],
) -> list[Candidate]:
    """The reconstruction step: integration needs the (new, learned) pair.

    Without a learned target there is no pair, so no reconstruction candidate
    exists and the ordinary ``NO_INTEGRATION_CANDIDATE`` waiver applies -- the
    first-ever drill lesson honestly has nothing to reconstruct against.
    """
    learned = sorted(ref for ref in known_targets if ref != target_ref)
    if not learned:
        return []
    pool = {str(item.get("id")): item for item in _program_targets(program)}
    target = pool.get(target_ref)
    if target is None:
        return []
    learned_ref = learned[0]
    learned_item = pool.get(learned_ref, {})
    dimensions = [str(value) for value in (target.get("dimensions") or ["controlled_production"])]
    learned_dimensions = [str(value) for value in (learned_item.get("dimensions") or dimensions)]
    contexts = [str(value) for value in (target.get("contexts") or target.get("domains") or ["general"])]
    return [
        {
            "candidate_id": f"profile:drill:{target_ref}:reconstruction",
            "kind": "integration",
            "bucket": "integration",
            "step_type": RECONSTRUCTION,
            "expected_seconds": step_cost(policy, RECONSTRUCTION),
            "target_ref": target_ref,
            "dimension": dimensions[0],
            "context_id": f"{contexts[0]}|{RECONSTRUCTION}",
            "lexicon_first": False,
            "lexicon_refs": [str(ref) for ref in (target.get("lexicon") or [])],
            "learner_relevance": 1,
            "sort_rank": 0,
            "agenda_rank": AGENDA_RANK_RECONSTRUCTION,
            # The authored text (curriculum 2d) once the text bank exists; the
            # tutor renders from the directive until then.
            "text_ref": target.get("text_ref"),
            "targets": [
                {"target_ref": target_ref, "dimension": dimensions[0], "role": "new"},
                {"target_ref": learned_ref, "dimension": learned_dimensions[0], "role": "learned"},
            ],
        }
    ]


def _profile_choice_candidates(
    policy: dict[str, Any],
    *,
    profile: str,
    target_ref: str | None,
    target_dimension: str | None,
    theme: str | None,
    timed_limit_seconds: int = DEFAULT_TIMED_LIMIT_SECONDS,
) -> list[Candidate]:
    """A targeted learner-choice activity for non-program profiles."""
    step_type = {
        "transfer_simulation": "transfer_task",
        "writing_workshop": "transfer_task",
        "reading_workshop": "transfer_task",
        "diagnostic": "gate_item",
        "practice": "controlled_production",
        "error_clinic": "controlled_production",
        "spaced_review": "recognition_check",
        # The drill lesson closes with writing against the clock; ``choice``
        # admits timed_writing (control 4.3a) and needs no (new, learned) pair.
        "drill": TIMED_WRITING,
    }.get(profile, "free_conversation")
    candidate: Candidate = {
        "candidate_id": f"profile:{profile}:choice:{target_ref or 'open'}",
        "kind": "choice",
        "bucket": "choice",
        "step_type": step_type,
        "expected_seconds": step_cost(policy, step_type),
        "target_ref": target_ref,
        "dimension": target_dimension,
        "context_id": f"{theme or profile}|{step_type}",
        "lexicon_first": False,
        "lexicon_refs": [],
        "topic_hint": theme,
        "sort_rank": 0,
    }
    if step_type == TIMED_WRITING:
        # The tutor MUST announce the limit before the learner starts (lessons 5).
        candidate["declared_limit_seconds"] = timed_limit_seconds
        candidate["agenda_rank"] = AGENDA_RANK_TIMED_WRITING
    return [candidate]


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


def _agenda_rank(candidate: Candidate) -> int:
    """The `drill` agenda slot of an admitted candidate (control 4.2a).

    Total by construction: a candidate the agenda names carries its own rank, a
    review step is the retrieval warm-up, and anything else sorts after the
    agenda rather than silently displacing it.
    """
    rank = candidate.get("agenda_rank")
    if rank is not None:
        return int(rank)
    return AGENDA_RANK_WARMUP if candidate.get("kind") == "review" else _AGENDA_RANK_OTHER


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
    lesson_profile: str | None = None,
    lesson_arc: dict[str, Any] | None = None,
    central_target_ref: str | None = None,
    lesson_theme: str | None = None,
    known_targets: frozenset[str] = frozenset(),
    learner_preferences: dict[str, Any] | None = None,
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
    round_size = _preference(learner_preferences, "round_size", DEFAULT_ROUND_SIZE)
    timed_limit_seconds = _preference(learner_preferences, "timed_limit_seconds", DEFAULT_TIMED_LIMIT_SECONDS)
    integration_list: list[Candidate] = []
    profile_growth = lesson_profile in ("program_lesson", "vocabulary_lesson")
    if lesson_profile == "drill" and central_target_ref is not None:
        growth_list = _drill_growth_candidates(
            program,
            policy,
            target_ref=central_target_ref,
            is_first_exposure=central_target_ref not in presented_targets,
            presented_targets=presented_targets,
            round_size=round_size,
        )
        integration_list = _drill_integration_candidates(
            program,
            policy,
            target_ref=central_target_ref,
            known_targets=known_targets,
        )
    elif profile_growth and central_target_ref is not None:
        growth_list = _profile_growth_candidates(
            program,
            policy,
            target_ref=central_target_ref,
            is_first_exposure=central_target_ref not in presented_targets,
            profile=str(lesson_profile),
        )
    elif lesson_profile is not None:
        # Practice, conversation and diagnostic profiles do not smuggle a new
        # curriculum topic into the plan merely to fill the growth floor.
        growth_list = []
    else:
        growth_list = growth_candidates(program, presented_targets, policy, relevant_targets)
    if active:
        review_list, signal_waivers = apply_signals(review_list, active)
        growth_list = [candidate for candidate in growth_list if not is_excluded(candidate, active)]

    if lesson_profile is not None:
        choice_target = central_target_ref
        if lesson_profile == "free_conversation" and choice_target is None and known_targets:
            choice_target = sorted(known_targets)[0]
        choice_dimension: str | None = None
        if choice_target is not None:
            choice_item = next(
                (
                    item
                    for item in [*program.get("topics", []), *program.get("lexicon", [])]
                    if str(item.get("id")) == choice_target
                ),
                None,
            )
            dimensions = (
                [str(value) for value in choice_item.get("dimensions") or []]
                if choice_item is not None
                else []
            )
            preferred = {
                "free_conversation": "spontaneous_production",
                "practice": "controlled_production",
                "error_clinic": "controlled_production",
                "transfer_simulation": "transfer",
                "writing_workshop": "transfer",
                "reading_workshop": "recognition",
                "spaced_review": "recognition",
                "diagnostic": "recognition",
                "drill": "controlled_production",
            }.get(lesson_profile)
            if lesson_profile == "free_conversation":
                # Conversation is assessed against its dedicated exact rubric.
                # A topic may list recognition first, but that must not turn a
                # free utterance into an unresolvable recognition attempt.
                choice_dimension = "spontaneous_production"
            elif preferred in dimensions:
                choice_dimension = preferred
            elif dimensions:
                choice_dimension = dimensions[0]
        profiled_choice = _profile_choice_candidates(
            policy,
            profile=lesson_profile,
            target_ref=choice_target,
            target_dimension=choice_dimension,
            theme=lesson_theme,
            timed_limit_seconds=timed_limit_seconds,
        )
    else:
        profiled_choice = choice_candidates(policy)

    def _complete(candidates: list[Candidate]) -> list[Candidate]:
        return [with_drill_fields(c, program, presented_targets, round_size=round_size) for c in candidates]

    pool: dict[str, list[Candidate]] = {
        "review": _complete(_review_sort(review_list)),
        "growth": _canonical_sort(growth_list),
        # Empty unless a profile can name the (new, learned) pair; the drill
        # profile's reconstruction step is the first that can.
        "integration": _canonical_sort(integration_list),
        "choice": _canonical_sort(profiled_choice),
    }

    admitted: list[Candidate] = []
    planned = {"review": 0, "growth": 0, "integration": 0, "choice": 0}
    waivers: list[str] = list(signal_waivers)
    consumed: list[str] = []
    starvation_admitted: list[str] = []
    admission_occupancy: dict[str, tuple[dict[str, int], dict[str, int]]] = {}
    diversity = policy["diversity"]
    max_consecutive = int(diversity["max_consecutive_same_mode"])
    # A coherent generation@2 lesson deliberately revisits its single central
    # target under several retrieval conditions.  The historical quota still
    # governs every v1/default composition.
    # A drill lesson IS massed practice on one pattern: frame set, two blocks,
    # reconstruction and the timed text all sit on the central target. The quota
    # that stops a general lesson from accidentally repeating a topic does not
    # govern the profile whose whole purpose is repetition -- and a drill_block
    # still counts as exactly ONE step here, whatever its round size (4.6).
    max_per_topic = (
        6
        if lesson_profile == "drill"
        else 4
        if lesson_profile is not None
        else int(diversity["max_steps_per_topic"])
    )

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

    if lesson_profile == "drill":
        # Admission order is bucket order; the drill agenda is normative
        # (control 4.2a: warm-up -> frame set -> blocked round -> interleaved
        # round -> reconstruction -> timed writing). Re-ordering the admitted
        # set onto it keeps the budget arithmetic untouched and is stable.
        admitted.sort(key=lambda c: (_agenda_rank(c), str(c["candidate_id"])))
    for candidate in admitted:
        if candidate.get("contrast_waiver"):
            # Fewer than two competing forms exist for this target: the block is
            # delivered blocked and the trace says why (control 4.6).
            waivers.append("NO_CONTRAST_CANDIDATE")

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
        # A step with an explicit ``targets[]`` (a drill block, a reconstruction
        # pair) is matched against ALL of them, exactly as the delivery boundary
        # revalidates it -- otherwise composition would attach a bank item that
        # delivery then rejects.
        listed = candidate.get("targets")
        if listed:
            expected_targets = sorted(str(item["target_ref"]) for item in listed)
            expected_dimensions = sorted(
                str(item["dimension"]) for item in listed if item.get("dimension") is not None
            )
        else:
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
            "schema_version": 2 if lesson_profile is not None else 1,
            "generation_policy": generation_version,
            "kind": candidate["kind"],
            "step_type": candidate["step_type"],
            "target_ref": candidate.get("target_ref"),
            "dimension": candidate.get("dimension"),
            "context_id": candidate["context_id"],
            "lexicon_refs": candidate["lexicon_refs"],
            "topic_hint": candidate.get("topic_hint"),
        }
        if lesson_profile is not None:
            directive["lesson_profile"] = lesson_profile
            directive["lesson_arc_id"] = lesson_arc.get("arc_id") if lesson_arc else None
            directive["lesson_theme"] = lesson_theme
        if candidate["kind"] == "probe":
            # The probe tells the tutor which context to steer clear of (4.7).
            directive["avoid_context"] = candidate.get("avoid_context")
        if candidate["step_type"] == DRILL_BLOCK:
            # ``mode`` is the tutor-visible half of the interleaving rule (4.6):
            # a blocked round shows one pattern, an interleaved round mixes in
            # the contrast targets listed beside it.
            directive["mode"] = candidate["drill_mode"]
            directive["rounds"] = int(candidate["rounds"])
            directive["round_size"] = int(candidate["round_size"])
            directive["contrast_targets"] = [dict(item) for item in candidate["contrast_targets"]]
        elif candidate["step_type"] == TIMED_WRITING:
            directive["declared_limit_seconds"] = int(candidate["declared_limit_seconds"])
        elif candidate["step_type"] == RECONSTRUCTION:
            directive["text_ref"] = candidate.get("text_ref")
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
        if candidate.get("targets"):
            # control 4.3a: the roles travel with the step, so STEP_PRESENTED can
            # list them and evidence can tell a drilled target from a distractor.
            step["targets"] = [dict(item) for item in candidate["targets"]]
        if candidate["step_type"] == DRILL_BLOCK:
            step["drill_mode"] = candidate["drill_mode"]
            step["rounds"] = int(candidate["rounds"])
            step["round_size"] = int(candidate["round_size"])
        elif candidate["step_type"] == TIMED_WRITING:
            step["declared_limit_seconds"] = int(candidate["declared_limit_seconds"])
        elif candidate["step_type"] == RECONSTRUCTION:
            step["text_ref"] = candidate.get("text_ref")
        if candidate["kind"] == "growth":
            step["target_ref"] = candidate["target_ref"]
            step["dimension"] = candidate["dimension"]
            step["is_first_exposure"] = bool(candidate.get("is_first_exposure", True))
        elif candidate["kind"] == "integration":
            step["target_ref"] = candidate.get("target_ref")
            step["dimension"] = candidate.get("dimension")
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
            step["dimension"] = candidate.get("dimension")
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
        if lesson_profile is not None:
            step["lesson_profile"] = lesson_profile
            step["lesson_arc_id"] = lesson_arc.get("arc_id") if lesson_arc else None
            step["arc_phase"] = phase_for_step(
                lesson_arc or {},
                offset,
                len(admitted),
                str(candidate["step_type"]),
                # The drill agenda is normative, so its steps name their phase
                # instead of being slotted proportionally (control 4.2a).
                agenda_slot=(_agenda_rank(candidate) if lesson_profile == "drill" else None),
            )
            step["primary_role"] = (
                "central"
                if central_target_ref is not None and candidate.get("target_ref") == central_target_ref
                else "support"
            )
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
    if lesson_arc is not None:
        result["lesson_arc"] = dict(lesson_arc)
    return result


def step_targets(step: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``targets[]`` of a step for ``STEP_PRESENTED`` (control 4.6): every
    (target_ref, dimension) pair; empty only for target-less choice.

    A step that carries its own ``targets[]`` -- an interleaved drill block, an
    integration pair -- publishes them verbatim, roles included. ``role:
    contrast`` declares that the unit was shown as a competing choice, not as a
    checked target: it earns no evidence credit from control, which keeps
    attributing evidence in the evidence/scoring modules by source span.
    """
    listed = step.get("targets")
    if listed:
        return [dict(item) for item in listed]
    if step["kind"] in ("growth", "review", "probe"):
        return [{"target_ref": step["target_ref"], "dimension": step["dimension"]}]
    if step["kind"] == "choice" and step.get("target_ref"):
        return [{"target_ref": step["target_ref"], "dimension": step.get("dimension")}]
    return []
