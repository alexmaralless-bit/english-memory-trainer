"""Fixtures for memory tests: a store with all learning policies active and a
tiny program, so the projection has real state to render."""

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
REPO = Path(__file__).resolve().parents[2]

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": "grammar.be.identity",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "State identity with forms of be.",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.pronouns.possessives",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "Use possessive pronouns.",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.basic-word-order",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "Order a simple statement.",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["status-update"],
            "lexicon": [],
        },
    ],
    "lexicon": [
        {
            "id": "reaction.no-way",
            "title": "no way",
            "type": "informal_chunk",
            "meaning_ru": "ни за что",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["conversation"],
        }
    ],
}


def _payload(name: str) -> dict[str, Any]:
    return yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text("utf-8"))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260722)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "memory.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", PROGRAM)
    reg.activate("curriculum", "v-test")
    reg.register("generation", "generation@1", {"policy_id": "generation@1"})
    reg.activate("generation", "generation@1")
    for name, kind, version in (
        ("control-v1.yaml", "control", "control@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("rubric-v1.yaml", "rubric", "rubric@1"),
    ):
        reg.register(kind, version, _payload(name))
        reg.activate(kind, version)
    return reg
