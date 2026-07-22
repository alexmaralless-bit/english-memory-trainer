"""Untrusted adapter ingress is immutable, fenced, and audit-only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.adapters import (
    ProviderMessageConflict,
    SkillReportInvalid,
    UserTurnInvalid,
    capture_user_turn,
    report_skill,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import SessionRevisionConflict
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork


def _session(tmp_path: Path) -> tuple[EventStore, FixedClock, SeededRandomSource, str]:
    conn = connect(tmp_path / "ingress.db")
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(datetime(2026, 7, 22, 12, 0, tzinfo=UTC))
    random_source = SeededRandomSource(29)
    session_id = new_ulid(clock, random_source)
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            "session",
            session_id,
            {
                "status": "IN_PROGRESS",
                "manifest": {"provider": "codex", "pinned_versions": {}},
                "last_activity_at": clock.now().isoformat(),
            },
            expected_revision=0,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="skill.required",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "skill_name": "run-english-session",
                        "version": "1",
                        "content_hash": "sha256:skill",
                        "cli_calls": ["session.finish"],
                    },
                )
            ]
        )
    return store, clock, random_source, session_id


def test_capture_keeps_exact_text_hash_span_and_provider_global_identity(tmp_path: Path) -> None:
    store, clock, random_source, session_id = _session(tmp_path)
    result = capture_user_turn(
        store,
        clock,
        random_source,
        session_id,
        provider="codex",
        provider_message_id="message-1",
        content="Привет, write this.",
        byte_start=0,
        byte_end=12,
        expected_session_revision=1,
    )
    event = next(event for event in store.read() if event.type == "adapter.user_turn_captured")
    assert event.payload["content"] == "Привет, write this."
    assert event.payload["content_hash"].startswith("sha256:")
    assert event.payload["trust"] == "untrusted_user_input"
    assert result["session_revision"] == 2

    replay = capture_user_turn(
        store,
        clock,
        random_source,
        session_id,
        provider="codex",
        provider_message_id="message-1",
        content="Привет, write this.",
        byte_start=0,
        byte_end=12,
        expected_session_revision=1,
    )
    assert replay["cached"] is True and replay["event_id"] == result["event_id"]
    with pytest.raises(ProviderMessageConflict):
        capture_user_turn(
            store,
            clock,
            random_source,
            session_id,
            provider="codex",
            provider_message_id="message-1",
            content="changed",
            expected_session_revision=2,
        )
    with pytest.raises(UserTurnInvalid, match="code-point"):
        capture_user_turn(
            store,
            clock,
            random_source,
            session_id,
            provider="codex",
            provider_message_id="message-2",
            content="Я",
            byte_start=1,
            byte_end=2,
            expected_session_revision=2,
        )


def test_skill_report_is_untrusted_and_shares_the_session_fence(tmp_path: Path) -> None:
    store, clock, random_source, session_id = _session(tmp_path)
    result = report_skill(
        store,
        clock,
        random_source,
        session_id,
        skill_name="run-english-session",
        version="1",
        status="completed",
        expected_session_revision=1,
        provider="codex",
    )
    event = next(event for event in store.read() if event.type == "skill.completed")
    assert event.payload["trust"] == "untrusted_agent_self_report"
    assert event.payload["content_hash"] == "sha256:skill"
    assert result["session_revision"] == 2
    with pytest.raises(SessionRevisionConflict):
        report_skill(
            store,
            clock,
            random_source,
            session_id,
            skill_name="run-english-session",
            version="1",
            status="started",
            expected_session_revision=1,
            provider="codex",
        )
    with pytest.raises(SkillReportInvalid):
        report_skill(
            store,
            clock,
            random_source,
            session_id,
            skill_name="other",
            version="1",
            status="completed",
            expected_session_revision=2,
            provider="codex",
        )
