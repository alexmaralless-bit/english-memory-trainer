"""Finish requires an empty pending set and never auto-closes [P0-2];
abandon converts the pending set without scoring contribution (0.5)."""

from __future__ import annotations

import pytest

from english_trainer.evidence.attempts import (
    CLOSED_UNASSESSED,
    EVENT_ATTEMPT_STATE_CHANGED,
    pending_attempts,
    record_attempt,
)
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    finish_session,
    get_session,
    start_session,
)

EXERCISE = {
    "prompt": "Complete: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}


def _present(store: EventStore, registry: PolicyRegistry, clock, rnd) -> tuple[str, str]:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    result = next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    return session_id, str(result["step"]["step_id"])


def test_unassessed_attempt_blocks_finish(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    record_attempt(
        store, clock, random_source, session_id, step_id=step_id, raw_answer="I am an engineer."
    )  # open answer: stays `recorded` until scoring exists
    with pytest.raises(SessionPrecondition, match="pending"):
        finish_session(store, clock, random_source, session_id)
    state, _ = get_session(store, session_id)
    assert state["status"] == "IN_PROGRESS"  # the refusal wrote nothing


def test_assessed_attempts_allow_finish(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    rendered = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="am",
        exercise_instance_id=rendered["exercise_instance_id"],
    )
    assert pending_attempts(store, session_id) == []
    event = finish_session(store, clock, random_source, session_id)
    assert event.payload == {"session_id": session_id, "from_status": "IN_PROGRESS"}


def test_abandon_closes_pending_without_contribution(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    open_attempt = record_attempt(
        store, clock, random_source, session_id, step_id=step_id, raw_answer="I am an engineer."
    )
    rendered = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    assessed = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="am",
        exercise_instance_id=rendered["exercise_instance_id"],
    )

    event = abandon_session(store, clock, random_source, session_id)
    assert event.payload["closed_attempts"] == [open_attempt["attempt_id"]]

    closed_state = read_aggregate(store._conn, "attempt", open_attempt["attempt_id"])
    assert closed_state is not None
    assert closed_state[0]["status"] == CLOSED_UNASSESSED
    assert closed_state[0]["non_contributing"] is True
    assert closed_state[0]["close_reason"] == "abandoned"
    # The assessed attempt keeps its disposition -- everything recorded stays.
    kept = read_aggregate(store._conn, "attempt", assessed["attempt_id"])
    assert kept is not None and kept[0]["status"] == "assessed"

    changes = [e for e in store.read() if e.type == EVENT_ATTEMPT_STATE_CHANGED]
    assert len(changes) == 1
    assert changes[0].payload["to_status"] == CLOSED_UNASSESSED
    assert changes[0].payload["non_contributing"] is True
    assert pending_attempts(store, session_id) == []
