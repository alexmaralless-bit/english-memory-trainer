"""Fixtures for lessons tests: deterministic clock/randomness, migrated store,
and a policy registry with an active curriculum (a session needs a program)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260721)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "lessons.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", {"schema_version": 1, "topics": []})
    reg.activate("curriculum", "v-test")
    reg.register("generation", "generation@1", {"policy_id": "generation@1"})
    reg.activate("generation", "generation@1")
    return reg
