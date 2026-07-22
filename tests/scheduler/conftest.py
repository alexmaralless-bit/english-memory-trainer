"""Fixtures for scheduler tests: deterministic store + the shipped policies."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.store import EventStore, connect, migrate

EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


def _payload(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def scheduler_policy() -> dict[str, Any]:
    return _payload("scheduler-v1.yaml")


@pytest.fixture
def scoring_policy() -> dict[str, Any]:
    return _payload("scoring-v1.yaml")


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260723)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "scheduler.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()
