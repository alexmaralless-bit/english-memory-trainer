"""Fixtures for scoring tests: deterministic store + the shipped scoring@1."""

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


def scoring_payload() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "scoring-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def policy() -> dict[str, Any]:
    return scoring_payload()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260722)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "scoring.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()
