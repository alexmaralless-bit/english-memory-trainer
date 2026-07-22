"""Tutor Compliance uses observed effects, never self-report alone."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from english_trainer.audit import obligations
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.compliance import tutor_compliance

REPO = Path(__file__).resolve().parents[2]


def test_obligations_separate_self_report_and_effect_and_are_read_only(tmp_path: Path) -> None:
    conn = connect(tmp_path / "audit.db")
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(datetime(2026, 7, 22, 14, 0, tzinfo=UTC))
    random_source = SeededRandomSource(33)
    registry = PolicyRegistry(conn, clock)
    policy = yaml.safe_load(
        (REPO / "curriculum" / "policies" / "obligations-v1.yaml").read_text(encoding="utf-8")
    )
    registry.register("obligations", "obligations@1", policy)
    registry.activate("obligations", "obligations@1")
    session_id = new_ulid(clock, random_source)
    invoked_id = new_ulid(clock, random_source)
    events = [
        make_event(
            id=new_ulid(clock, random_source),
            type="session.started",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id=session_id,
            payload={"manifest": {"pinned_versions": {"obligations": "obligations@1"}}},
        ),
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
                "cli_calls": ["session.finish"],
            },
        ),
        make_event(
            id=new_ulid(clock, random_source),
            type="skill.completed",
            occurred_at=clock.now(),
            actor="agent",
            correlation_id=session_id,
            payload={"skill_name": "run-english-session", "version": "1"},
        ),
        make_event(
            id=invoked_id,
            type="cli.command_invoked",
            occurred_at=clock.now(),
            actor="cli-transport",
            correlation_id="call-1",
            payload={"command": "session.finish"},
        ),
        make_event(
            id=new_ulid(clock, random_source),
            type="cli.command_terminated",
            occurred_at=clock.now(),
            actor="cli-transport",
            correlation_id="call-1",
            causation_id=invoked_id,
            payload={
                "command": "session.finish",
                "outcome": "success",
                "exit_code": 0,
                "session_id": session_id,
            },
        ),
        make_event(
            id=new_ulid(clock, random_source),
            type="session.finished",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id=session_id,
            payload={"session_id": session_id},
        ),
    ]
    with UnitOfWork(store, clock) as uow:
        uow.append(events)
    before = len(list(store.read()))
    first = obligations(store, registry, session_id)
    second = obligations(store, registry, session_id)
    assert first == second
    assert len(list(store.read())) == before
    required = first["observations"][0]
    assert required["satisfied"] is True
    assert required["self_report_events"][0]["type"] == "skill.completed"
    assert required["observed_effects"][0]["type"] == "cli.command_terminated"
    assert tutor_compliance(store, registry) == {
        "status": "measured",
        "score": 100,
        "sessions": 1,
        "satisfied": 2,
        "applicable": 2,
    }
