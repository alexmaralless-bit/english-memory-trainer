"""Fixtures for learner tests: deterministic clock/randomness, a migrated
store, a tiny curriculum program, and a helper that stands up a bare session
aggregate (so session-bound lexicon writes have a fence to advance)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

EPOCH = datetime(2026, 7, 22, 9, 0, 0, tzinfo=UTC)

# A minimal but faithful program: one topic and one lexical item the encounter
# path can link to. ``word.feasible`` is a real curriculum LexicalItem; a
# personal entry may reference it. ``role.engineer`` is a second lexical item.
PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {"id": "grammar.be.identity", "cefr": "A1", "track": "grammar-engine", "lexicon": ["word.feasible"]},
    ],
    "lexicon": [
        {
            "id": "word.feasible",
            "type": "word",
            "title": "feasible",
            "cefr": "A2",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "meaning_ru": "осуществимый; выполнимый",
        },
        {
            "id": "role.engineer",
            "type": "word",
            "title": "engineer",
            "cefr": "A1",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "meaning_ru": "инженер",
        },
    ],
}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260722)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "learner.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def program() -> dict[str, Any]:
    return PROGRAM


def make_session(store: EventStore, clock: FixedClock, session_id: str = "SESSION-1") -> str:
    """Persist a bare STARTED session aggregate at revision 1."""
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            "session",
            session_id,
            {
                "status": "STARTED",
                "manifest": {"session_id": session_id, "pinned_versions": {"curriculum": "v-test"}},
                "last_activity_at": clock.now().isoformat(),
            },
            expected_revision=0,
        )
    return session_id
