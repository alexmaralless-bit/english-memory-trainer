"""Session lifecycle (2.2 increment 1): manifest pinning, the single active
session invariant, and the contract state machine STARTED → IN_PROGRESS →
FINISHED | ABANDONED (no STARTED → FINISHED edge)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.sessions import (
    ABANDONED,
    EVENT_ABANDONED,
    EVENT_AGENT_ATTACHED,
    EVENT_COMPOSED,
    EVENT_FINISHED,
    EVENT_STARTED,
    FINISHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    abandon_session,
    active_session_id,
    finish_session,
    get_session,
    mark_in_progress,
    start_session,
)

PINNED = {"control": "control@1", "curriculum": "v-test", "generation": "generation@1"}


def _start(store: EventStore, registry: PolicyRegistry, clock, rnd) -> str:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    return str(manifest["session_id"])


def test_start_pins_active_policies_into_the_manifest(store, registry, clock, random_source) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="claude-code", mode="balanced")
    assert manifest["pinned_versions"] == PINNED
    assert manifest["provider"] == "claude-code"
    assert manifest["plan"] == {"composition_revision": 1, "plan_version": 1}
    assert manifest["required_skills"] == []

    session_id = manifest["session_id"]
    assert active_session_id(store) == session_id
    state, revision = get_session(store, session_id)
    assert state["status"] == STARTED and revision == 1

    events = list(store.read())
    # start attaches the starting tutor in the same UoW (lessons 5 [R-3]).
    assert [event.type for event in events] == [EVENT_STARTED, EVENT_COMPOSED, EVENT_AGENT_ATTACHED]
    assert events[0].pinned_versions == manifest["pinned_versions"]
    assert events[0].correlation_id == session_id
    assert events[1].payload["session_plan_id"] == manifest["session_plan_id"]
    assert events[2].provider == "claude-code" and events[2].payload["provider"] == "claude-code"


def test_start_without_active_curriculum_is_refused(store, clock, random_source) -> None:
    empty_registry = PolicyRegistry(store._conn, clock)  # nothing registered
    with pytest.raises(SessionPrecondition, match="no active curriculum"):
        start_session(store, empty_registry, clock, random_source, provider="claude-code")
    assert active_session_id(store) is None
    assert store.count() == 0


def test_second_start_requires_explicit_closure(store, registry, clock, random_source) -> None:
    first = _start(store, registry, clock, random_source)
    with pytest.raises(SessionPrecondition, match="still active"):
        _start(store, registry, clock, random_source)
    assert active_session_id(store) == first  # contract C-1: no implicit abandon
    assert store.count() == 3  # started + composed + agent_attached; the refused start wrote nothing


def test_started_session_cannot_finish_only_abandon(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    with pytest.raises(SessionPrecondition, match="cannot finish"):
        finish_session(store, clock, random_source, session_id)
    state, _ = get_session(store, session_id)
    assert state["status"] == STARTED  # refusal left no trace

    event = abandon_session(store, clock, random_source, session_id)
    assert event.type == EVENT_ABANDONED
    assert active_session_id(store) is None
    state, _ = get_session(store, session_id)
    assert state["status"] == ABANDONED


def test_in_progress_session_finishes_and_frees_the_slot(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    mark_in_progress(store, clock, session_id)
    mark_in_progress(store, clock, session_id)  # idempotent
    state, _ = get_session(store, session_id)
    assert state["status"] == IN_PROGRESS

    event = finish_session(store, clock, random_source, session_id)
    assert event.type == EVENT_FINISHED
    assert event.payload == {"session_id": session_id, "from_status": IN_PROGRESS}
    assert event.pinned_versions == PINNED
    state, _ = get_session(store, session_id)
    assert state["status"] == FINISHED
    assert active_session_id(store) is None

    # The slot is free: a new session starts cleanly.
    second = _start(store, registry, clock, random_source)
    assert active_session_id(store) == second


def test_closed_session_cannot_close_again(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    abandon_session(store, clock, random_source, session_id)
    with pytest.raises(SessionPrecondition, match="already"):
        abandon_session(store, clock, random_source, session_id)
    with pytest.raises(SessionPrecondition):
        finish_session(store, clock, random_source, session_id)
    with pytest.raises(SessionPrecondition):
        mark_in_progress(store, clock, session_id)


def test_lifecycle_events_and_outbox_stay_paired(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    mark_in_progress(store, clock, session_id)
    finish_session(store, clock, random_source, session_id)
    assert store.count() == 4  # started + composed + agent_attached + finished
    outbox = store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"]
    assert outbox == 4  # every lifecycle event rode the transactional outbox
