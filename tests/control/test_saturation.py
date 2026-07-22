"""Saturation reducer + predicate and recurring-error detection (control 4.6, 4.5).

Covers: the per-dimension key, the max-exposure branch, the transfer-staleness
branch (fresh vs stale vs null ``last_transfer_check_at``), recurring-error
recency, and byte-determinism of the fold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.saturation import (
    EVENT_ERROR_OBSERVED,
    EVENT_REVIEW_OUTCOME,
    EVENT_SESSION_STARTED,
    EVENT_STEP_PRESENTED,
    SaturationState,
    is_saturated,
    recurring_error_keys,
    reduce_saturation,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
BASE = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def store() -> EventStore:
    conn = connect(":memory:")
    migrate(conn)
    return EventStore(conn)


def emit(
    evt_store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    type_: str,
    payload: dict[str, Any],
    correlation: str = "S1",
) -> None:
    with UnitOfWork(evt_store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=type_,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=correlation,
                    payload=payload,
                )
            ]
        )


def presented(target: str, dimension: str, *, step_type: str, context: str) -> dict[str, Any]:
    return {
        "targets": [{"target_ref": target, "dimension": dimension}],
        "step_type": step_type,
        "context_id": context,
    }


def outcome(target: str, dimension: str, *, result: str, independent: bool) -> dict[str, Any]:
    return {"target_ref": target, "dimension": dimension, "outcome": result, "independent": independent}


# -- the max-exposure branch, per-dimension (control 4.6) --------------------


def test_max_exposures_saturates_only_the_exposed_dimension() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(1)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    for i in range(3):  # max_exposures_in_window = 3
        emit(
            evt_store,
            clock,
            rnd,
            EVENT_STEP_PRESENTED,
            presented("grammar.x", "recognition", step_type="recognition_check", context=f"c{i}"),
        )

    states = reduce_saturation(evt_store.read(), policy())
    recognition = states[("grammar.x", "recognition")]
    assert recognition.exposures_in_window == 3
    assert is_saturated(recognition, policy(), BASE) is True
    # A different dimension of the same target was never exposed: not tracked,
    # and a missing key is not saturated (the per-dimension key, RR2-13).
    assert ("grammar.x", "controlled_production") not in states
    assert is_saturated(SaturationState(), policy(), BASE) is False


# -- the transfer-staleness branch (control 4.6) -----------------------------


def _streak_state(
    evt_store: EventStore, clock: FixedClock, rnd: SeededRandomSource, *, transfer: bool
) -> SaturationState:
    """Three independent successes on (grammar.x, spontaneous_production) in ONE
    context; the single exposure is a transfer_task (or not, for the null case)."""
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    step_type = "transfer_task" if transfer else "recognition_check"
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_STEP_PRESENTED,
        presented("grammar.x", "spontaneous_production", step_type=step_type, context="familiar"),
    )
    for _ in range(3):  # consecutive_success_threshold = 3
        emit(
            evt_store,
            clock,
            rnd,
            EVENT_REVIEW_OUTCOME,
            outcome("grammar.x", "spontaneous_production", result="CONFIRMED", independent=True),
        )
    return reduce_saturation(evt_store.read(), policy())[("grammar.x", "spontaneous_production")]


def test_narrow_success_saturates_only_with_a_fresh_transfer_check() -> None:
    state = _streak_state(store(), FixedClock(BASE), SeededRandomSource(2), transfer=True)
    # Below the max-exposure branch; the second conjunction carries it.
    assert state.exposures_in_window == 1
    assert state.consecutive_independent_successes == 3
    assert state.distinct_contexts == 1  # < min_distinct_contexts (2)
    assert state.last_transfer_check_at == BASE.isoformat()
    # Fresh transfer check (<= 30 days): saturated.
    assert is_saturated(state, policy(), BASE + timedelta(days=10)) is True
    # Stale transfer check (> 30 days): not saturated -- drilling may resume.
    assert is_saturated(state, policy(), BASE + timedelta(days=40)) is False


def test_narrow_success_is_not_saturation_without_any_transfer_check() -> None:
    state = _streak_state(store(), FixedClock(BASE), SeededRandomSource(3), transfer=False)
    assert state.consecutive_independent_successes == 3 and state.distinct_contexts == 1
    assert state.last_transfer_check_at is None
    # Null last_transfer_check_at makes the second conjunction false (control 4.6).
    assert is_saturated(state, policy(), BASE + timedelta(days=1)) is False


def test_a_failure_and_a_hinted_success_break_the_independent_streak() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(4)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_REVIEW_OUTCOME,
        outcome("g.y", "recognition", result="CONFIRMED", independent=True),
    )
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_REVIEW_OUTCOME,
        outcome("g.y", "recognition", result="REGRESSION", independent=True),
    )  # failure resets
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_REVIEW_OUTCOME,
        outcome("g.y", "recognition", result="CONFIRMED", independent=True),
    )
    # A scaffolded (hinted) success does not extend the independent run.
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_REVIEW_OUTCOME,
        {"target_ref": "g.y", "dimension": "recognition", "outcome": "CONFIRMED", "hints": ["a"]},
    )
    state = reduce_saturation(evt_store.read(), policy())[("g.y", "recognition")]
    assert state.consecutive_independent_successes == 0


# -- recurring-error detection (control 4.5) ---------------------------------


def test_two_recent_errors_recur_and_a_single_one_does_not() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(5)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    emit(evt_store, clock, rnd, EVENT_ERROR_OBSERVED, {"target_ref": "g.x", "dimension": "recognition"})
    emit(evt_store, clock, rnd, EVENT_ERROR_OBSERVED, {"target_ref": "g.x", "dimension": "recognition"})
    emit(evt_store, clock, rnd, EVENT_ERROR_OBSERVED, {"target_ref": "g.z", "dimension": "recognition"})
    keys = recurring_error_keys(evt_store.read(), policy())
    assert ("g.x", "recognition") in keys  # >= recurring_error_min_occurrences (2)
    assert ("g.z", "recognition") not in keys  # only one


def test_no_error_events_means_no_recurring_error() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(6)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    assert recurring_error_keys(evt_store.read(), policy()) == frozenset()


def test_errors_outside_the_session_window_do_not_recur() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(7)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1}, "S1")
    emit(evt_store, clock, rnd, EVENT_ERROR_OBSERVED, {"target_ref": "g.x", "dimension": "recognition"}, "S1")
    emit(evt_store, clock, rnd, EVENT_ERROR_OBSERVED, {"target_ref": "g.x", "dimension": "recognition"}, "S1")
    # Three more sessions pass -> the window (recurring_error_window_sessions = 3)
    # has moved past session 1, so the two errors no longer recur.
    for seq in range(2, 5):
        emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": seq}, f"S{seq}")
    assert recurring_error_keys(evt_store.read(), policy()) == frozenset()


# -- byte-determinism (control determinism) ----------------------------------


def test_reduce_is_deterministic_over_the_same_log() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(8)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_STEP_PRESENTED,
        presented("grammar.x", "recognition", step_type="transfer_task", context="email"),
    )
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_REVIEW_OUTCOME,
        outcome("grammar.x", "recognition", result="PROGRESS", independent=True),
    )
    assert reduce_saturation(list(evt_store.read()), policy()) == reduce_saturation(
        list(evt_store.read()), policy()
    )
