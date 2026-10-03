"""The automaticity loop of control@3 (PD-2026-09-22).

Covers the four things the contract added and nothing else can check for it:
the three new ``step_type``s and their prices, the `drill` profile's canonical
agenda as a byte-stable plan, the blocked/interleaved decision with its
deterministic contrast set, and the rule that a drill block is ONE exposure.
The last test is the regression guard: a control@2 session must compose exactly
as it did before, or replay of every recorded session breaks.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.compose import (
    DEFAULT_ROUND_SIZE,
    DRILL_ROUNDS,
    compose_plan,
    contrast_targets,
    drill_block_mode,
    step_targets,
)
from english_trainer.control.errors import ControlPolicyInvalid
from english_trainer.control.lesson_profiles import (
    LESSON_PROFILES,
    build_lesson_arc,
    build_lesson_proposal,
)
from english_trainer.control.policy import (
    CONTRAST_MAX,
    CONTRAST_MIN,
    MATRIX_STEP_TYPES,
    STEP_TYPE_RANK,
    STEP_TYPES_BY_KIND,
    require_valid,
    step_cost,
    validate_control_policy,
)
from english_trainer.control.saturation import (
    EVENT_EVIDENCE_ADDED,
    EVENT_SESSION_STARTED,
    EVENT_STEP_PRESENTED,
    reduce_saturation,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
BASE = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
CENTRAL = "grammar.articles.identity"


def policy(filename: str = "control-v3.yaml") -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def topic(topic_id: str, *, cefr: str = "A1", track: str = "grammar-engine") -> dict[str, Any]:
    return {
        "id": topic_id,
        "title": topic_id.rsplit(".", 1)[-1],
        "cefr": cefr,
        "track": track,
        "dimensions": ["recognition", "controlled_production"],
        "contexts": ["team-introduction"],
        "lexicon": [],
    }


PROGRAM: dict[str, Any] = {
    "topics": [
        topic(CENTRAL),
        topic("grammar.do-questions"),
        topic("grammar.past-simple"),
        topic("grammar.plurals"),
        topic("grammar.b1.conditionals", cefr="B1"),
        topic("writing.email", track="written-interaction"),
    ],
    "lexicon": [],
}


def ids() -> Any:
    counter = iter(f"id{index:04d}" for index in range(500))
    return lambda: next(counter)


def drill_plan(
    *,
    program: dict[str, Any] | None = None,
    presented: frozenset[str] = frozenset(),
    known: frozenset[str] = frozenset({"grammar.do-questions"}),
    total_seconds: int = 1800,
    review_candidates: list[dict[str, Any]] | None = None,
    control: dict[str, Any] | None = None,
    learner_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    used = program if program is not None else PROGRAM
    proposal = build_lesson_proposal(
        program=used,
        duration_minutes=total_seconds // 60,
        profile="drill",
        target_ref=CENTRAL,
        explicit_request=True,
    )
    return compose_plan(
        program=used,
        policy=control or policy(),
        generation_version="generation@2",
        mode="balanced",
        total_seconds=total_seconds,
        presented_targets=presented,
        known_targets=known,
        review_candidates=review_candidates,
        lesson_profile="drill",
        lesson_arc=build_lesson_arc(proposal),
        central_target_ref=CENTRAL,
        learner_preferences=learner_preferences,
        new_id=ids(),
    )


# -- the matrix, the ranks and the prices ------------------------------------


def test_the_three_new_step_types_are_admissible_exactly_where_the_matrix_says() -> None:
    assert "drill_block" in STEP_TYPES_BY_KIND["review"]
    assert "drill_block" in STEP_TYPES_BY_KIND["growth"]
    assert {"reconstruction", "timed_writing"} <= set(STEP_TYPES_BY_KIND["integration"])
    assert "timed_writing" in STEP_TYPES_BY_KIND["choice"]
    # The forbidden pairs are forbidden on purpose (control 4.3a).
    assert "drill_block" not in STEP_TYPES_BY_KIND["integration"]
    assert "reconstruction" not in STEP_TYPES_BY_KIND["growth"]
    assert "reconstruction" not in STEP_TYPES_BY_KIND["choice"]


def test_new_ranks_are_appended_so_existing_plans_keep_their_order() -> None:
    historical = {
        "new_material_intro": 0,
        "recognition_check": 1,
        "controlled_production": 2,
        "spontaneous_production": 3,
        "transfer_task": 4,
        "integration_task": 5,
        "gate_item": 6,
        "free_conversation": 7,
    }
    for step_type, rank in historical.items():
        assert STEP_TYPE_RANK[step_type] == rank, step_type
    assert STEP_TYPE_RANK["drill_block"] == 8
    assert STEP_TYPE_RANK["reconstruction"] == 9
    assert STEP_TYPE_RANK["timed_writing"] == 10
    assert set(STEP_TYPE_RANK) == set(MATRIX_STEP_TYPES)


def test_control_v3_prices_every_admissible_step_type() -> None:
    shipped = policy()
    assert validate_control_policy(shipped) == []
    for step_type in MATRIX_STEP_TYPES:
        assert isinstance(step_cost(shipped, step_type), int)
    for step_type in ("drill_block", "timed_writing", "reconstruction"):
        assert step_cost(shipped, step_type) == 300


def test_v3_without_a_new_price_does_not_activate() -> None:
    broken = copy.deepcopy(policy())
    del broken["budget"]["expected_seconds_by_step_type"]["drill_block"]
    errors = validate_control_policy(broken)
    assert any("drill_block" in error for error in errors)
    with pytest.raises(ControlPolicyInvalid):
        require_valid(broken)


def test_v3_refuses_a_float_price_like_every_other_decision_leaf() -> None:
    broken = copy.deepcopy(policy())
    broken["budget"]["expected_seconds_by_step_type"]["timed_writing"] = 300.0
    assert any("float" in error for error in validate_control_policy(broken))


def test_floor_reachability_covers_the_new_integration_step_types() -> None:
    broken = copy.deepcopy(policy())
    costs = broken["budget"]["expected_seconds_by_step_type"]
    for step_type in STEP_TYPES_BY_KIND["integration"]:
        costs[step_type] = 99999
    errors = validate_control_policy(broken)
    assert any("unreachable" in error and "integration" in error for error in errors)


def test_the_historical_versions_keep_validating_under_their_own_matrix() -> None:
    # control@1/@2 never priced the automaticity loop; judging them by the
    # control@3 matrix would retroactively invalidate a pinned, replayed version.
    assert validate_control_policy(policy("control-v1.yaml")) == []
    assert validate_control_policy(policy("control-v2.yaml")) == []


# -- the drill profile --------------------------------------------------------


def test_drill_is_the_eleventh_learner_facing_profile() -> None:
    assert "drill" in LESSON_PROFILES
    assert len(LESSON_PROFILES) == 11
    proposal = build_lesson_proposal(
        program=PROGRAM, duration_minutes=30, profile="drill", target_ref=CENTRAL, explicit_request=True
    )
    assert proposal["title"].startswith("Drill lesson:")
    assert [phase["phase_id"] for phase in proposal["agenda"]] == [
        "retrieval_warmup",
        "frame_set",
        "drill_blocked",
        "drill_interleaved",
        "reconstruction",
        "timed_writing",
        "debrief",
    ]


def test_drill_plan_follows_the_canonical_agenda_and_is_byte_stable() -> None:
    first = drill_plan()
    second = drill_plan()
    assert canonical_json(first) == canonical_json(second)

    steps = first["steps"]
    assert [step["step_type"] for step in steps] == [
        "new_material_intro",
        "drill_block",
        "drill_block",
        "reconstruction",
        "timed_writing",
    ]
    assert [step["arc_phase"]["phase_id"] for step in steps] == [
        "frame_set",
        "drill_blocked",
        "drill_interleaved",
        "reconstruction",
        "timed_writing",
    ]
    assert [step["bucket"] for step in steps] == [
        "growth",
        "growth",
        "growth",
        "integration",
        "choice",
    ]
    assert [step["order_index"] for step in steps] == [0, 1, 2, 3, 4]
    # The 30-minute drill lesson spends its whole budget: 900 growth + 300
    # integration + 300 choice.
    assert first["budget"]["planned"] == {
        "review": 0,
        "growth": 900,
        "integration": 300,
        "choice": 300,
    }


def test_the_retrieval_warmup_is_a_review_step_and_opens_the_agenda() -> None:
    warmup = {
        "candidate_id": "review:grammar.do-questions:controlled_production",
        "kind": "review",
        "bucket": "review",
        "step_type": "drill_block",
        "expected_seconds": 300,
        "target_ref": "grammar.do-questions",
        "dimension": "controlled_production",
        "context_id": "standup|drill_block",
        "lexicon_first": False,
        "lexicon_refs": [],
        "urgency_class": "normal",
        "retrievability_ppm": 600000,
    }
    plan = drill_plan(review_candidates=[warmup])
    steps = plan["steps"]
    assert steps[0]["kind"] == "review"
    assert steps[0]["arc_phase"]["phase_id"] == "retrieval_warmup"
    assert steps[0]["review_assignment_id"]
    assert [step["step_type"] for step in steps[1:]] == [
        "new_material_intro",
        "drill_block",
        "drill_block",
        "reconstruction",
        "timed_writing",
    ]


def test_timed_writing_declares_its_limit_and_reconstruction_carries_the_pair() -> None:
    steps = {step["step_type"]: step for step in drill_plan()["steps"]}
    timed = steps["timed_writing"]
    assert timed["declared_limit_seconds"] == 240
    assert timed["generation_directive"]["declared_limit_seconds"] == 240
    reconstruction = steps["reconstruction"]
    roles = [target["role"] for target in reconstruction["targets"]]
    assert roles == ["new", "learned"]
    assert "text_ref" in reconstruction


def test_without_a_learned_target_there_is_no_reconstruction_step() -> None:
    plan = drill_plan(known=frozenset())
    assert "reconstruction" not in {step["step_type"] for step in plan["steps"]}
    assert "NO_INTEGRATION_CANDIDATE" in plan["waivers"]


# -- blocked vs interleaved ---------------------------------------------------


def test_first_exposure_is_blocked_and_the_second_round_interleaves() -> None:
    blocks = [step for step in drill_plan()["steps"] if step["step_type"] == "drill_block"]
    assert len(blocks) == DRILL_ROUNDS
    assert blocks[0]["drill_mode"] == "blocked"
    assert blocks[0]["targets"] == [
        {"target_ref": CENTRAL, "dimension": "controlled_production", "role": "target"}
    ]
    assert blocks[0]["generation_directive"]["mode"] == "blocked"
    assert blocks[1]["drill_mode"] == "interleaved"
    contrasts = [t for t in blocks[1]["targets"] if t["role"] == "contrast"]
    assert CONTRAST_MIN <= len(contrasts) <= CONTRAST_MAX
    assert blocks[1]["generation_directive"]["mode"] == "interleaved"
    for block in blocks:
        assert block["rounds"] == DRILL_ROUNDS
        assert block["round_size"] == DEFAULT_ROUND_SIZE


def test_a_learner_round_size_preference_sizes_every_drill_block() -> None:
    # LearnerPreferences (learner 4a): control reads round_size from the
    # snapshot lessons folds off the event log and keeps no copy of its own
    # (compose.py DEFAULT_ROUND_SIZE comment) -- a `round_size: 8` preference
    # must size every drill block at 8, not the DEFAULT_ROUND_SIZE of 6.
    blocks = [
        step
        for step in drill_plan(learner_preferences={"round_size": 8})["steps"]
        if step["step_type"] == "drill_block"
    ]
    assert len(blocks) == DRILL_ROUNDS
    assert DEFAULT_ROUND_SIZE != 8  # the assertion below is not vacuously true
    for block in blocks:
        assert block["round_size"] == 8
        assert block["decision_trace"]["computed_inputs"]["automaticity"]["round_size"] == 8

    # A preference with no round_size key (e.g. only timed_limit_seconds was
    # set) falls back to the documented default -- the pipeline stays
    # byte-identical to no preferences at all.
    fallback = [
        step
        for step in drill_plan(learner_preferences={"timed_limit_seconds": 300})["steps"]
        if step["step_type"] == "drill_block"
    ]
    for block in fallback:
        assert block["round_size"] == DEFAULT_ROUND_SIZE


def test_a_target_with_a_prior_step_presented_never_gets_a_blocked_block() -> None:
    blocks = [
        step
        for step in drill_plan(presented=frozenset({CENTRAL}))["steps"]
        if step["step_type"] == "drill_block"
    ]
    assert [block["drill_mode"] for block in blocks] == ["interleaved", "interleaved"]
    for block in blocks:
        assert len([t for t in block["targets"] if t["role"] == "contrast"]) >= CONTRAST_MIN
    assert drill_block_mode(CENTRAL, frozenset({CENTRAL}), round_index=0) == "interleaved"
    assert drill_block_mode(CENTRAL, frozenset(), round_index=0) == "blocked"
    assert drill_block_mode(CENTRAL, frozenset(), round_index=1) == "interleaved"


def test_contrast_selection_is_deterministic_same_track_and_cefr() -> None:
    picked = contrast_targets(PROGRAM, CENTRAL, dimension="controlled_production")
    assert [entry["target_ref"] for entry in picked] == [
        "grammar.do-questions",
        "grammar.past-simple",
        "grammar.plurals",
    ]
    assert {entry["role"] for entry in picked} == {"contrast"}
    # Neither the B1 topic nor the other track is a contrast for an A1
    # grammar-engine pattern, and the primary never contrasts with itself.
    assert "grammar.b1.conditionals" not in {entry["target_ref"] for entry in picked}
    assert "writing.email" not in {entry["target_ref"] for entry in picked}
    assert contrast_targets(PROGRAM, CENTRAL, dimension="controlled_production") == picked
    assert len(picked) <= CONTRAST_MAX
    # Without a requested dimension each contrast falls back to its own first
    # authored dimension -- still total, still deterministic.
    assert [entry["dimension"] for entry in contrast_targets(PROGRAM, CENTRAL)] == ["recognition"] * 3


def test_authored_contrast_refs_win_over_the_structural_fallback() -> None:
    program = copy.deepcopy(PROGRAM)
    program["topics"][0]["contrast_refs"] = ["writing.email", "grammar.b1.conditionals"]
    picked = contrast_targets(program, CENTRAL, dimension="controlled_production")
    assert [entry["target_ref"] for entry in picked] == [
        "grammar.b1.conditionals",
        "writing.email",
    ]


def test_an_unfillable_interleave_falls_back_to_blocked_and_says_so() -> None:
    lonely = {"topics": [topic(CENTRAL), topic("writing.email", track="written-interaction")], "lexicon": []}
    plan = drill_plan(program=lonely, known=frozenset())
    blocks = [step for step in plan["steps"] if step["step_type"] == "drill_block"]
    assert [block["drill_mode"] for block in blocks] == ["blocked", "blocked"]
    assert "NO_CONTRAST_CANDIDATE" in plan["waivers"]
    trace = blocks[1]["decision_trace"]["computed_inputs"]["automaticity"]
    assert trace["waiver"] == "NO_CONTRAST_CANDIDATE"
    assert trace["contrast_targets"] == []


def test_the_decision_trace_names_mode_contrasts_and_block_accounting() -> None:
    blocks = [step for step in drill_plan()["steps"] if step["step_type"] == "drill_block"]
    trace = blocks[1]["decision_trace"]["computed_inputs"]["automaticity"]
    assert trace["mode"] == "interleaved"
    assert trace["exposure_accounting"] == "block_counts_as_one_exposure"
    assert [entry["target_ref"] for entry in trace["contrast_targets"]] == [
        "grammar.do-questions",
        "grammar.past-simple",
        "grammar.plurals",
    ]
    assert trace["round_size"] == DEFAULT_ROUND_SIZE
    assert "waiver" not in trace


def test_step_presented_targets_carry_the_contrast_role() -> None:
    blocks = [step for step in drill_plan()["steps"] if step["step_type"] == "drill_block"]
    published = step_targets(blocks[1])
    assert published[0]["role"] == "target"
    assert {entry["role"] for entry in published[1:]} == {"contrast"}
    # The primary is still first, so downstream code that reads targets[0]
    # reads the drilled pattern, never a distractor.
    assert published[0]["target_ref"] == CENTRAL


# -- saturation ---------------------------------------------------------------


def _store() -> EventStore:
    conn = connect(":memory:")
    migrate(conn)
    return EventStore(conn)


def _emit(
    store: EventStore, clock: FixedClock, rnd: SeededRandomSource, type_: str, payload: dict[str, Any]
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=type_,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="S1",
                    payload=payload,
                )
            ]
        )


def test_a_drill_block_is_one_exposure_and_one_success_whatever_its_size() -> None:
    store, clock, rnd = _store(), FixedClock(BASE), SeededRandomSource(20260922)
    _emit(store, clock, rnd, EVENT_SESSION_STARTED, {})
    _emit(
        store,
        clock,
        rnd,
        EVENT_STEP_PRESENTED,
        {
            "step_id": "STEP-1",
            "step_type": "drill_block",
            "context_id": "team-introduction|drill_block",
            "targets": [{"target_ref": CENTRAL, "dimension": "controlled_production", "role": "target"}],
        },
    )
    # Eight items inside one block: without the collapse this would be eight
    # exposures and eight successes, exhausting max_exposures_in_window (3)
    # inside the very first block.
    for _ in range(8):
        _emit(
            store,
            clock,
            rnd,
            EVENT_EVIDENCE_ADDED,
            {
                "step_id": "STEP-1",
                "target_ref": CENTRAL,
                "dimension": "controlled_production",
                "correct": True,
                "independent": True,
            },
        )
    state = reduce_saturation(store.read(), policy())[(CENTRAL, "controlled_production")]
    assert state.exposures_in_window == 1
    assert state.consecutive_independent_successes == 1


def test_one_failed_item_makes_the_whole_block_unsuccessful() -> None:
    store, clock, rnd = _store(), FixedClock(BASE), SeededRandomSource(20260922)
    _emit(store, clock, rnd, EVENT_SESSION_STARTED, {})
    _emit(
        store,
        clock,
        rnd,
        EVENT_STEP_PRESENTED,
        {
            "step_id": "STEP-1",
            "step_type": "drill_block",
            "context_id": "team-introduction|drill_block",
            "targets": [{"target_ref": CENTRAL, "dimension": "controlled_production"}],
        },
    )
    for correct in (True, False, True):
        _emit(
            store,
            clock,
            rnd,
            EVENT_EVIDENCE_ADDED,
            {
                "step_id": "STEP-1",
                "target_ref": CENTRAL,
                "dimension": "controlled_production",
                "correct": correct,
                "independent": True,
            },
        )
    state = reduce_saturation(store.read(), policy())[(CENTRAL, "controlled_production")]
    assert state.consecutive_independent_successes == 0


def test_max_steps_per_topic_counts_a_block_as_one_step() -> None:
    steps = drill_plan()["steps"]
    on_central = [step for step in steps if step.get("target_ref") == CENTRAL]
    # Frame set, two blocks, reconstruction and the timed text: five steps, and
    # each block counts once however many items it runs.
    assert len(on_central) == 5
    assert sum(1 for step in on_central if step["step_type"] == "drill_block") == DRILL_ROUNDS


# -- the regression guard -----------------------------------------------------


def test_a_control_v2_session_composes_exactly_as_before() -> None:
    def program_lesson(control: dict[str, Any]) -> dict[str, Any]:
        proposal = build_lesson_proposal(
            program=PROGRAM,
            duration_minutes=30,
            profile="program_lesson",
            target_ref=CENTRAL,
            explicit_request=True,
        )
        return compose_plan(
            program=PROGRAM,
            policy=control,
            generation_version="generation@2",
            mode="balanced",
            total_seconds=1800,
            lesson_profile="program_lesson",
            lesson_arc=build_lesson_arc(proposal),
            central_target_ref=CENTRAL,
            new_id=ids(),
        )

    under_v2 = program_lesson(policy("control-v2.yaml"))
    step_types = {step["step_type"] for step in under_v2["steps"]}
    assert step_types.isdisjoint({"drill_block", "timed_writing", "reconstruction"})
    # The same inputs under control@3 give the same plan apart from the pinned
    # policy id: the new step types never leak into an existing profile.
    under_v3 = program_lesson(policy())
    assert [step["step_type"] for step in under_v3["steps"]] == [
        step["step_type"] for step in under_v2["steps"]
    ]
    assert [step["order_index"] for step in under_v3["steps"]] == [
        step["order_index"] for step in under_v2["steps"]
    ]
    assert under_v3["budget"] == under_v2["budget"]


def test_a_default_v1_composition_is_untouched_by_the_new_step_types() -> None:
    def default_plan(control: dict[str, Any]) -> str:
        composed = compose_plan(
            program=PROGRAM,
            policy=control,
            generation_version="generation@1",
            mode="balanced",
            total_seconds=1800,
            new_id=ids(),
        )
        # The pinned policy id is the only legitimate difference.
        for step in composed["steps"]:
            step["decision_trace"]["facts"]["pinned_versions"].pop("control_policy", None)
        return canonical_json(composed)

    assert default_plan(policy("control-v1.yaml")) == default_plan(policy())
