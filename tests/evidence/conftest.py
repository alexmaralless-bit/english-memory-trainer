"""Fixtures for evidence tests: the same deterministic store/registry shape as
the lessons suite -- evidence consumes the events lessons publishes, so its
tests drive a real session through lessons to produce honest inputs."""

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

EPOCH = datetime(2026, 7, 22, 9, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": "grammar.be.identity",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.pronouns.possessives",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
    ],
    "lexicon": [],
}


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260722)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "evidence.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    control = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", PROGRAM)
    reg.activate("curriculum", "v-test")
    reg.register("generation", "generation@1", {"policy_id": "generation@1"})
    reg.activate("generation", "generation@1")
    reg.register("control", "control@1", control)
    reg.activate("control", "control@1")
    return reg
