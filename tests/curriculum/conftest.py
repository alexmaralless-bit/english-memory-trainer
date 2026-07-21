"""Fixtures for curriculum tests: deterministic clock, seeded randomness, and a
fresh migrated store per test (same shape as the kernel fixtures)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
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
    conn = connect(tmp_path / "curriculum.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()
