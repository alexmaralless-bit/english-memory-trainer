"""Session lifecycle (2.2 increment 1): manifest pinning, the single active
session invariant, and the contract state machine STARTED → IN_PROGRESS →
FINISHED | ABANDONED (no STARTED → FINISHED edge). A session finishes only
through its committed lesson report [PD-2026-09-23], which walks
STARTED → IN_PROGRESS → FINISHED inside one transaction."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.errors import SessionRevisionConflict
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.report import check_report, commit_report
from english_trainer.lessons.resume import resume_session
from english_trainer.lessons.sessions import (
    ABANDONED,
    EVENT_ABANDONED,
    EVENT_AGENT_ATTACHED,
    EVENT_COMPOSED,
    EVENT_FINISHED,
    EVENT_STALE_ABANDONED,
    EVENT_STARTED,
    FINISHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    abandon_session,
    active_session_id,
    get_session,
    start_session,
    sweep_stale_session,
)
from tests.lessons.report_support import EPOCH, item, report, report_registry
from tests.lessons.report_support import start as start_report_session

REPO = Path(__file__).resolve().parents[2]

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

    # start returns the lesson brief in one call, but the persisted,
    # immutable manifest never carries that computed view.
    assert manifest["brief"]["schema"] == "lesson_brief@1"
    assert "briefing" not in manifest
    session_id = manifest["session_id"]
    assert active_session_id(store) == session_id
    state, revision = get_session(store, session_id)
    assert state["status"] == STARTED and revision == 1
    assert "brief" not in state["manifest"]

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


def test_started_session_is_abandoned_and_frees_the_slot(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    event = abandon_session(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert event.type == EVENT_ABANDONED
    assert event.payload["from_status"] == STARTED
    assert active_session_id(store) is None
    state, _ = get_session(store, session_id)
    assert state["status"] == ABANDONED


def test_a_reported_session_walks_in_progress_to_finished_and_frees_the_slot(tmp_path: Path) -> None:
    conn = connect(tmp_path / "reported.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    rnd = SeededRandomSource(20260923)
    store = EventStore(conn)
    registry = report_registry(conn, clock)
    started = start_report_session(store, registry, clock, rnd)
    session_id = str(started["session_id"])
    body = report(session_id, started["brief"], [item("i1", "I am a data engineer.")])
    result = commit_report(
        store, registry, clock, rnd, session_id, body, provider="claude-code", idempotency_key="k1"
    )
    assert result["cached"] is False
    finished = [event for event in store.read() if event.type == EVENT_FINISHED]
    assert len(finished) == 1
    payload = finished[0].payload
    # Never the illegal direct STARTED → FINISHED edge: the report moves the
    # session through IN_PROGRESS inside the same transaction.
    assert payload["from_status"] == IN_PROGRESS and payload["reported_from_status"] == STARTED
    assert payload["closed_by"] == "lesson_report"
    state, revision = get_session(store, session_id)
    assert state["status"] == FINISHED and revision == 3
    assert active_session_id(store) is None
    second = start_report_session(store, registry, clock, rnd)
    assert active_session_id(store) == second["session_id"]


def test_report_protocol_session_defaults_to_the_canonical_skill_version(tmp_path: Path) -> None:
    # `uses_report_protocol(pinned)` (lessons@2 + evidence@2, report_registry)
    # must default to the CURRENT canonical `run-english-session` version, not
    # the stale, unarchived `@2` [PD-2026-09-23] -- resolved against the real
    # agent-skills/ directory, exactly as `--agent-skills agent-skills` does.
    conn = connect(tmp_path / "reported-skill.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    rnd = SeededRandomSource(20260923)
    store = EventStore(conn)
    registry = report_registry(conn, clock)
    started = start_report_session(store, registry, clock, rnd, agent_skills_dir=REPO / "agent-skills")
    required = started["required_skills"]
    assert required, "a report-protocol session with a real agent-skills dir must pin a skill"
    assert required[0]["skill_name"] == "run-english-session"
    assert required[0]["version"] == "10"
    assert required[0]["content_hash"]
    events = [event for event in store.read() if event.type == "skill.required"]
    assert len(events) == 1 and events[0].payload["version"] == "10"


def test_closed_session_cannot_close_again(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    abandon_session(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    with pytest.raises(SessionPrecondition, match="already"):
        abandon_session(
            store,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
        )
    # A terminal session takes no report either (checked before any policy).
    with pytest.raises(SessionPrecondition, match="only for an active session"):
        check_report(store, registry, session_id, {})


def test_lifecycle_events_and_outbox_stay_paired(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    abandon_session(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert store.count() == 4  # started + composed + agent_attached + abandoned
    outbox = store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"]
    assert outbox == 4  # every lifecycle event rode the transactional outbox


def test_coarse_session_fence_allows_one_writer_and_rejects_the_stale_one(
    store, registry, clock, random_source
) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="codex")
    session_id = str(manifest["session_id"])
    before = store.count()
    winner = resume_session(store, registry, clock, random_source, session_id, provider="claude-code")
    assert winner["session_revision"] == 2
    after_winner = store.count()
    assert after_winner > before
    with pytest.raises(SessionRevisionConflict) as caught:
        abandon_session(store, clock, random_source, session_id, expected_session_revision=1)
    assert caught.value.code == "SESSION_REVISION_CONFLICT"
    assert caught.value.current_session_revision == 2
    assert store.count() == after_winner


def test_stale_sweep_uses_pinned_boundary_is_idempotent_and_frees_slot(
    store, registry, clock, random_source
) -> None:
    lessons = yaml.safe_load(
        (REPO / "curriculum" / "policies" / "lessons-v1.yaml").read_text(encoding="utf-8")
    )
    registry.register("lessons", "lessons@1", lessons)
    registry.activate("lessons", "lessons@1")
    manifest = start_session(store, registry, clock, random_source, provider="codex")
    session_id = str(manifest["session_id"])
    started_at = clock.now()
    clock.advance(seconds=7 * 24 * 60 * 60)

    event = sweep_stale_session(store, registry, clock, random_source)
    assert event is not None and event.type == EVENT_STALE_ABANDONED
    assert event.occurred_at == started_at + timedelta(days=7)
    assert event.payload["boundary_at"] == event.occurred_at.isoformat()
    state, revision = get_session(store, session_id)
    assert state["status"] == ABANDONED and revision == 2
    count = store.count()
    assert sweep_stale_session(store, registry, clock, random_source) is None
    assert store.count() == count

    replacement = start_session(store, registry, clock, random_source, provider="codex")
    assert replacement["session_id"] != session_id
