"""Fixtures for lessons tests: deterministic clock/randomness, migrated store,
and a policy registry with active curriculum + control + generation policies
(a session needs a program to compose from and control@1 to compose with)."""

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

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]

# A miniature but structurally faithful program snapshot: three topics in
# authored (= priority) order and one safe, unlinked CORE unit that the
# lexicon-first micro lane should pick up (generation@1 PD-5 D).
PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": "grammar.be.identity",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": ["role.engineer"],
        },
        {
            "id": "grammar.pronouns.possessives",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.basic-word-order",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["status-update"],
            "lexicon": [],
        },
    ],
    "lexicon": [
        {
            "id": "role.engineer",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
        },
        {
            "id": "reaction.no-way",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["conversation"],
        },
    ],
}


def control_payload() -> dict[str, Any]:
    """The real control@1 payload -- tests run against the shipped values."""
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


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
def program_payload() -> dict[str, Any]:
    return PROGRAM


@pytest.fixture
def full_registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    """Everything the review loop needs: curriculum + generation + control +
    scheduler + scoring (the review bucket lives only with the last two)."""
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", PROGRAM)
    reg.activate("curriculum", "v-test")
    reg.register("generation", "generation@1", {"policy_id": "generation@1"})
    reg.activate("generation", "generation@1")
    reg.register("control", "control@1", control_payload())
    reg.activate("control", "control@1")
    for name, kind, version in (
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
    ):
        payload = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text("utf-8"))
        reg.register(kind, version, payload)
        reg.activate(kind, version)
    return reg


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", PROGRAM)
    reg.activate("curriculum", "v-test")
    reg.register("generation", "generation@1", {"policy_id": "generation@1"})
    reg.activate("generation", "generation@1")
    reg.register("control", "control@1", control_payload())
    reg.activate("control", "control@1")
    return reg
