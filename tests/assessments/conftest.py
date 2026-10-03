"""Fixtures for assessments tests: a deterministic migrated store, a policy
registry holding the fixture curriculum (forms are curriculum data now, so the
legacy stub form is loaded explicitly through it), and the shipped scoring
policies for the fold assertions."""

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
from tests.assessments.fixtures import full_program, policy, stub_program

CURRICULUM_KIND = "curriculum"
STUB_VERSION = "placement-stub@1"
FULL_VERSION = "placement-fixture@1"

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
    """A registry with the STUB form active as the curriculum snapshot.

    ``placement start`` resolves its form from the active curriculum; the
    lifecycle/exposure/ceiling tests keep using the six-item stub, now loaded
    explicitly as a fixture instead of being embedded in the engine.
    """
    registry = PolicyRegistry(store._conn, clock)
    registry.register(CURRICULUM_KIND, STUB_VERSION, stub_program())
    registry.activate(CURRICULUM_KIND, STUB_VERSION)
    return registry


@pytest.fixture
def full_registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    """The measurable fixture form plus scoring@2 and rubric@1."""
    registry = PolicyRegistry(store._conn, clock)
    registry.register(CURRICULUM_KIND, FULL_VERSION, full_program())
    registry.activate(CURRICULUM_KIND, FULL_VERSION)
    for kind, filename in (("scoring", "scoring-v2.yaml"), ("rubric", "rubric-v1.yaml")):
        payload = policy(filename)
        registry.register(kind, str(payload["policy_id"]), payload)
        registry.activate(kind, str(payload["policy_id"]))
    return registry


@pytest.fixture
def scoring_policy() -> dict[str, Any]:
    return scoring_payload()
