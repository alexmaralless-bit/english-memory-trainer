"""Fixtures for assessments tests: a deterministic migrated store, an empty
policy registry (placement self-registers assessments@1), and the shipped
scoring@1 for the fold assertions."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate

EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
SEED = 20260722
REPO = Path(__file__).resolve().parents[2]


def scoring_payload() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "scoring-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(SEED)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "assessments.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    return PolicyRegistry(store._conn, clock)


@pytest.fixture
def scoring_policy() -> dict[str, Any]:
    return scoring_payload()
