"""The automaticity axis (scoring 3d, [PD-2026-09-22]).

Covered here: policy activation (floats and drift refused), every row of the
transition table, the "no baseline => no automatic" rule, regression back to
proceduralized, lower-median determinism, replay byte-stability including the
``AUTOMATICITY_UPDATED`` facts, and the load-bearing negative: the axis leaves
Mastery / Stability / knowledge state / CEFR / Learning Score / XP untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import derived_ulid, new_ulid
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.automaticity import (
    AUTOMATIC,
    AUTOMATICITY_KIND,
    DELIBERATE,
    EVENT_AUTOMATICITY_UPDATED,
    NOT_MEASURED,
    PROCEDURALIZED,
    AutomaticityPolicyInvalid,
    automaticity_snapshot,
    backfill_automaticity_updates,
    build_automaticity_update,
    fold_automaticity,
    parse_automaticity_policy,
    validate_automaticity_policy,
)
from english_trainer.scoring.engine import fold_scores, snapshot
from english_trainer.scoring.replay import replay_scores

REPO = Path(__file__).resolve().parents[2]
POLICY_FILE = REPO / "curriculum" / "policies" / "automaticity-v1.yaml"
VERSION = "automaticity@1"


@pytest.fixture
def automaticity_policy() -> dict[str, Any]:
    loaded = yaml.safe_load(POLICY_FILE.read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _registry(store: EventStore, clock, automaticity_policy, scoring_policy=None) -> PolicyRegistry:
    registry = PolicyRegistry(store._conn, clock)
    registry.register(AUTOMATICITY_KIND, VERSION, automaticity_policy)
    registry.activate(AUTOMATICITY_KIND, VERSION)
    if scoring_policy is not None:
        registry.register("scoring", "scoring@1", scoring_policy)
        registry.activate("scoring", "scoring@1")
    return registry


def _append(store: EventStore, clock, rnd, event_type: str, payload: dict[str, Any], *, pin=True):
    event = make_event(
        id=new_ulid(clock, rnd),
        type=event_type,
        occurred_at=clock.now(),
        actor="engine",
        correlation_id=str(payload.get("session_id") or "corr"),
        payload=payload,
        pinned_versions={AUTOMATICITY_KIND: VERSION} if pin else {},
    )
    with UnitOfWork(store, clock) as uow:
        uow.append([event])
    return event


def _block(
    *,
    target: str = "grammar.be.identity",
    session: str = "s1",
    correct: int = 6,
    total: int = 6,
    latency: int | None = 1000,
    unpresented: int = 0,
) -> dict[str, Any]:
    """A drill-block ``evidence.added`` payload in the shape evidence 4.6 emits."""
    items: list[dict[str, Any]] = []
    for index in range(total):
        answered = index < total - unpresented
        items.append(
            {
                "index": index,
                "prompt_ref": f"x#item:{index}",
                "raw_answer": "a" if answered else None,
                "presented": answered,
                "objective_correct": (index < correct) if answered else None,
                "latency_ms": latency if answered else None,
                "self_repaired": False,
            }
        )
    answered_count = total - unpresented
    return {
        "evidence_id": target + session + str(correct),
        "session_id": session,
        "form": "drill_block",
        "mode": "controlled_production",
        "origin": "session",
        "assessment_basis": "objective_check",
        "primary_target": {"target_ref": target, "dimension": "controlled_production"},
        "credit_allocations": [
            {"target_ref": target, "dimension": "controlled_production", "contribution": "1.0", "used": True}
        ],
        "correct": True,
        "score_ppm": 1_000_000,
        "block_score_ppm": (correct * 1_000_000 // answered_count) if answered_count else 0,
        "hints": 0,
        "response_latency_ms": None,
        "items": items,
    }


def _confirmation(
    *, target: str = "grammar.be.identity", session: str = "s1", latency: int = 1200
) -> dict[str, Any]:
    """A spontaneous-form attempt outside the drill (canon 3d input (c))."""
    return {
        "evidence_id": f"conf-{session}-{target}",
        "session_id": session,
        "mode": "spontaneous_production",
        "origin": "session",
        "assessment_basis": "rubric",
        "primary_target": {"target_ref": target, "dimension": "spontaneous_production"},
        "correct": True,
        "score_ppm": 1_000_000,
        "hints": 0,
        "response_latency_ms": latency,
    }


def _active(target: str = "grammar.be.identity") -> dict[str, Any]:
    return {"target_ref": target, "from_state": "LEARNING", "to_state": "ACTIVE", "trigger": "CONFIRMED"}


# -- policy ---------------------------------------------------------------


def test_the_shipped_policy_is_exactly_the_canon_defaults(automaticity_policy) -> None:
    assert validate_automaticity_policy(automaticity_policy) == []
    assert automaticity_policy == {
        "policy_id": "automaticity@1",
        "schema_version": 1,
        "status": "accepted",
        "decision_record": "PD-2026-09-22",
        "canonical_encoding": "kernel.canonical_json_v1",
        "numeric_value_rule": "integers_and_decimal_strings_only",
        "proceduralized_accuracy_ppm": 900000,
        "automatic_accuracy_ppm": 950000,
        "min_blocks": 3,
        "min_sessions": 2,
        "latency_factor": "1.5",
        "baseline_window_sessions": 10,
    }
    # A separate KIND beside scoring@1, so the Session Manifest pins it.
    assert AUTOMATICITY_KIND in KNOWN_KINDS


def test_activation_refuses_a_yaml_float(automaticity_policy) -> None:
    broken = {**automaticity_policy, "latency_factor": 1.5}
    errors = validate_automaticity_policy(broken)
    assert any("float" in error for error in errors)
    with pytest.raises(AutomaticityPolicyInvalid):
        parse_automaticity_policy(POLICY_FILE.read_text("utf-8").replace('"1.5"', "1.5"))


def test_activation_refuses_duplicate_keys_and_unknown_keys(automaticity_policy) -> None:
    text = POLICY_FILE.read_text("utf-8")
    with pytest.raises(AutomaticityPolicyInvalid, match="duplicate key"):
        parse_automaticity_policy(text + "\nmin_blocks: 9\n")
    assert any("unknown key" in e for e in validate_automaticity_policy({**automaticity_policy, "x": 1}))
    assert any("missing" in e for e in validate_automaticity_policy({}))
    # The shipped file still parses under the strict loader.
    assert parse_automaticity_policy(text) == automaticity_policy


# -- transition table -----------------------------------------------------


def test_first_block_moves_not_measured_to_deliberate(store, clock, random_source, automaticity_policy):
    _append(store, clock, random_source, "evidence.added", _block(correct=6))
    states = fold_automaticity(store, automaticity_policy)
    axis = states["grammar.be.identity"]
    assert axis.state == DELIBERATE
    assert axis.blocks_observed == 1
    assert axis.accuracy_ppm == 1_000_000
    assert fold_automaticity(store, automaticity_policy) == states  # pure fold


def test_no_block_means_not_measured(store, clock, random_source, automaticity_policy):
    _append(store, clock, random_source, "evidence.added", _confirmation())
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == NOT_MEASURED
    assert axis.confirmations == 1


def test_min_blocks_at_threshold_promotes_to_proceduralized(store, clock, random_source, automaticity_policy):
    for index in range(3):
        _append(store, clock, random_source, "evidence.added", _block(session=f"s{index}", correct=6))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == PROCEDURALIZED
    assert axis.blocks_observed == 3
    assert axis.sessions_observed == 3


def test_accuracy_below_the_threshold_keeps_deliberate(store, clock, random_source, automaticity_policy):
    # 5/6 = 833333 ppm < 900000: three blocks, still deliberate.
    for index in range(3):
        _append(store, clock, random_source, "evidence.added", _block(session=f"s{index}", correct=5))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == DELIBERATE
    assert axis.accuracy_ppm == 833333  # floored integer ppm, no float


def test_unanswered_items_are_not_failures(store, clock, random_source, automaticity_policy):
    # 6 prompts, 2 never presented, 4/4 correct -> 100%, not 66%.
    _append(store, clock, random_source, "evidence.added", _block(correct=4, total=6, unpresented=2))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.accuracy_ppm == 1_000_000


def _promote_to_automatic(store, clock, rnd, *, latency: int = 1000) -> None:
    """ACTIVE target + three clean blocks over two sessions + a confirmation."""
    _append(store, clock, rnd, "scoring.state_transition", _active(), pin=False)
    for index, session in enumerate(("s1", "s1", "s2")):
        _append(store, clock, rnd, "evidence.added", _block(session=session, latency=latency + index * 0))
    _append(store, clock, rnd, "evidence.added", _confirmation(session="s2"))


def test_proceduralized_becomes_automatic_on_the_full_conjunction(
    store, clock, random_source, automaticity_policy
):
    _promote_to_automatic(store, clock, random_source)
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == AUTOMATIC
    assert axis.confirmations == 1
    assert axis.median_latency_ms == 1000
    assert axis.baseline_latency_ms == 1000


def test_without_a_confirmation_the_axis_stops_at_proceduralized(
    store, clock, random_source, automaticity_policy
):
    _append(store, clock, random_source, "scoring.state_transition", _active(), pin=False)
    for session in ("s1", "s1", "s2"):
        _append(store, clock, random_source, "evidence.added", _block(session=session))
    assert fold_automaticity(store, automaticity_policy)["grammar.be.identity"].state == PROCEDURALIZED


def test_one_session_is_not_enough_for_automatic(store, clock, random_source, automaticity_policy):
    _append(store, clock, random_source, "scoring.state_transition", _active(), pin=False)
    for _ in range(3):
        _append(store, clock, random_source, "evidence.added", _block(session="s1"))
    _append(store, clock, random_source, "evidence.added", _confirmation(session="s1"))
    assert fold_automaticity(store, automaticity_policy)["grammar.be.identity"].state == PROCEDURALIZED


def test_no_baseline_makes_automatic_unreachable(store, clock, random_source, automaticity_policy):
    """Everything holds except the baseline: the target was never ACTIVE, so no
    baseline sample exists and there is NO absolute fallback threshold."""
    for session in ("s1", "s1", "s2"):
        _append(store, clock, random_source, "evidence.added", _block(session=session))
    _append(store, clock, random_source, "evidence.added", _confirmation(session="s2"))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.baseline_latency_ms is None
    assert axis.state == PROCEDURALIZED


def test_a_slow_median_relative_to_the_baseline_blocks_automatic(
    store, clock, random_source, automaticity_policy
):
    # The baseline is the learner's own: another, already ACTIVE target answered
    # at 100ms. The drilled target is not ACTIVE yet, so its own slow latencies
    # do not pollute the baseline -- and 1000 > 1.5 x 100 blocks `automatic`.
    _append(store, clock, random_source, "scoring.state_transition", _active("other.target"), pin=False)
    _append(store, clock, random_source, "evidence.added", _block(target="other.target", latency=100))
    for session in ("s1", "s1", "s2"):
        _append(store, clock, random_source, "evidence.added", _block(session=session, latency=1000))
    _append(store, clock, random_source, "evidence.added", _confirmation(session="s2"))
    states = fold_automaticity(store, automaticity_policy)
    assert states["grammar.be.identity"].baseline_latency_ms == 100
    assert states["grammar.be.identity"].median_latency_ms == 1000
    assert states["grammar.be.identity"].state == PROCEDURALIZED


def test_the_baseline_window_forgets_older_sessions(store, clock, random_source, automaticity_policy):
    """Only the last ``baseline_window_sessions`` sessions feed the baseline."""
    narrow = {**automaticity_policy, "baseline_window_sessions": 1}
    _append(store, clock, random_source, "scoring.state_transition", _active("other.target"), pin=False)
    _append(
        store, clock, random_source, "evidence.added", _block(target="other.target", session="s0", latency=50)
    )
    _append(store, clock, random_source, "evidence.added", _block(session="s1", latency=900))
    assert fold_automaticity(store, automaticity_policy)["grammar.be.identity"].baseline_latency_ms == 50
    # With a one-session window, session s0's samples have fallen out entirely.
    assert fold_automaticity(store, narrow)["grammar.be.identity"].baseline_latency_ms is None


def test_an_unsuccessful_block_demotes_automatic_to_proceduralized(
    store, clock, random_source, automaticity_policy
):
    _promote_to_automatic(store, clock, random_source)
    assert fold_automaticity(store, automaticity_policy)["grammar.be.identity"].state == AUTOMATIC
    # 3/6 = 500000 ppm in the newest block drags the 3-block window under 900000.
    for session in ("s3", "s3", "s3"):
        _append(store, clock, random_source, "evidence.added", _block(session=session, correct=3))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == PROCEDURALIZED


def test_the_axis_never_falls_back_to_not_measured(store, clock, random_source, automaticity_policy):
    _append(store, clock, random_source, "evidence.added", _block(correct=0))
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    assert axis.state == DELIBERATE  # measured once, measured forever
    assert axis.accuracy_ppm == 0


def test_unknown_pairs_are_no_ops(store, clock, random_source, automaticity_policy):
    """Teaching, target-less evidence and a latency-free attempt move nothing."""
    _append(store, clock, random_source, "session.step_presented", {"session_id": "s1"})
    _append(store, clock, random_source, "evidence.added", {"session_id": "s1", "primary_target": {}})
    _append(
        store,
        clock,
        random_source,
        "evidence.added",
        {**_confirmation(), "response_latency_ms": None},
    )
    assert fold_automaticity(store, automaticity_policy) == {}


# -- determinism ----------------------------------------------------------


def test_the_median_is_the_lower_median_of_an_even_sample(store, clock, random_source, automaticity_policy):
    _append(store, clock, random_source, "evidence.added", _block(total=2, correct=2, latency=100))
    _append(
        store, clock, random_source, "evidence.added", _block(session="s2", total=2, correct=2, latency=300)
    )
    axis = fold_automaticity(store, automaticity_policy)["grammar.be.identity"]
    # Sample [100, 100, 300, 300]: the lower median is an observed value, 100.
    assert axis.median_latency_ms == 100


def test_the_fold_is_byte_stable(store, clock, random_source, automaticity_policy):
    _promote_to_automatic(store, clock, random_source)
    first = automaticity_snapshot(fold_automaticity(store, automaticity_policy))
    second = automaticity_snapshot(fold_automaticity(store, automaticity_policy))
    assert payload_hash(first) == payload_hash(second)


# -- the AUTOMATICITY_UPDATED producer + replay ---------------------------


def test_updates_are_derived_idempotent_and_replay_stable(
    store, clock, random_source, automaticity_policy, policy
):
    registry = _registry(store, clock, automaticity_policy, policy)
    _promote_to_automatic(store, clock, random_source)
    sources = [event for event in store.read() if event.type == "evidence.added"]

    with UnitOfWork(store, clock) as uow:
        first = backfill_automaticity_updates(store, registry, uow)
    assert first == {"scanned": 4, "created": 4}
    updates = [event for event in store.read() if event.type == EVENT_AUTOMATICITY_UPDATED]
    assert [event.id for event in updates] == [
        derived_ulid(source.id, EVENT_AUTOMATICITY_UPDATED) for source in sources
    ]
    assert [event.causation_id for event in updates] == [source.id for source in sources]
    assert [event.payload["to_state"] for event in updates] == [
        DELIBERATE,
        DELIBERATE,
        PROCEDURALIZED,
        AUTOMATIC,
    ]
    assert updates[-1].payload["pinned_automaticity_policy"] == VERSION
    assert updates[-1].payload["causation_id"] == sources[-1].id
    assert updates[-1].pinned_versions == {AUTOMATICITY_KIND: VERSION}

    with UnitOfWork(store, clock) as uow:
        assert backfill_automaticity_updates(store, registry, uow)["created"] == 0

    report = replay_scores(store, registry)
    assert report["consistent"] is True
    assert report["automaticity"]["status"] == "measured"
    assert report["automaticity"]["mismatches"] == []
    assert report["automaticity"]["unrecorded"] == []
    assert report["automaticity"]["targets"]["grammar.be.identity"]["state"] == AUTOMATIC
    assert report["automaticity"]["snapshot_hash"] == payload_hash(
        automaticity_snapshot(fold_automaticity(store, automaticity_policy))
    )


def test_a_tampered_recorded_fact_is_a_replay_error(store, clock, random_source, automaticity_policy, policy):
    registry = _registry(store, clock, automaticity_policy, policy)
    _promote_to_automatic(store, clock, random_source)
    with UnitOfWork(store, clock) as uow:
        backfill_automaticity_updates(store, registry, uow)
    _append(
        store,
        clock,
        random_source,
        EVENT_AUTOMATICITY_UPDATED,
        {
            "target_ref": "grammar.be.identity",
            "from_state": PROCEDURALIZED,
            "to_state": DELIBERATE,  # a lie about the saved axis
            "accuracy_ppm": 1,
            "median_latency_ms": None,
            "baseline_latency_ms": None,
            "pinned_automaticity_policy": VERSION,
            "causation_id": None,
        },
    )
    report = replay_scores(store, registry)
    assert report["automaticity"]["consistent"] is False
    assert report["consistent"] is False


def test_the_builder_mints_nothing_when_no_number_moves(
    store, clock, random_source, automaticity_policy, policy
):
    registry = _registry(store, clock, automaticity_policy, policy)
    teaching = make_event(
        id=new_ulid(clock, random_source),
        type="session.step_presented",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="s1",
        payload={"session_id": "s1"},
        pinned_versions={AUTOMATICITY_KIND: VERSION},
    )
    assert build_automaticity_update(store, registry, teaching) is None
    unpinned = make_event(
        id=new_ulid(clock, random_source),
        type="evidence.added",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="s1",
        payload=_block(),
        pinned_versions={},
    )
    assert build_automaticity_update(store, registry, unpinned) is None


def test_the_builder_sees_an_event_not_yet_in_the_store(
    store, clock, random_source, automaticity_policy, policy
):
    """It is called inside the evidence UoW, before the source is committed."""
    registry = _registry(store, clock, automaticity_policy, policy)
    source = make_event(
        id=new_ulid(clock, random_source),
        type="evidence.added",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="s1",
        payload=_block(),
        pinned_versions={AUTOMATICITY_KIND: VERSION},
    )
    built = build_automaticity_update(store, registry, source)
    assert built is not None
    assert built.payload["from_state"] == NOT_MEASURED
    assert built.payload["to_state"] == DELIBERATE
    with UnitOfWork(store, clock) as uow:
        uow.append([source, built])
    # Committed: the same source now resolves to the same, single fact.
    assert build_automaticity_update(store, registry, source).id == built.id


# -- the axis changes nothing outside itself ------------------------------


def test_the_axis_leaves_every_other_score_byte_identical(
    store, clock, random_source, automaticity_policy, policy
):
    """Replay the same log with and without the reducer's own events and compare
    Mastery / Stability / knowledge state / CEFR / Learning Score / XP."""
    registry = _registry(store, clock, automaticity_policy, policy)
    _promote_to_automatic(store, clock, random_source)
    _append(
        store,
        clock,
        random_source,
        "review.outcome",
        {"target_ref": "grammar.be.identity", "dimension": "controlled_production", "outcome": "CONFIRMED"},
    )
    before = snapshot(fold_scores(store, policy))
    before_report = replay_scores(store, registry)

    with UnitOfWork(store, clock) as uow:
        assert backfill_automaticity_updates(store, registry, uow)["created"] > 0

    after = snapshot(fold_scores(store, policy))
    after_report = replay_scores(store, registry)
    assert payload_hash(after) == payload_hash(before)
    assert after_report["snapshot_hash"] == before_report["snapshot_hash"]
    assert after_report["scores"] == before_report["scores"]
    # And the axis itself did move, so the comparison is not vacuous.
    assert after_report["automaticity"]["targets"]["grammar.be.identity"]["state"] == AUTOMATIC


def test_replay_reports_no_policy_without_an_active_automaticity(store, clock, policy):
    registry = PolicyRegistry(store._conn, clock)
    registry.register("scoring", "scoring@1", policy)
    registry.activate("scoring", "scoring@1")
    report = replay_scores(store, registry)
    assert report["automaticity"] == {"status": "no-policy", "policy_version": None, "targets": {}}
    assert report["consistent"] is True
