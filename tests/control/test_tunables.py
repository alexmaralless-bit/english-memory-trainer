from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from english_trainer.control.tunables import (
    EVENT_CALIBRATION_APPLIED,
    EVENT_POLICY_ACTIVATED,
    confirm_calibration,
    list_calibrations,
    list_tunables,
    propose_calibration,
    validate_catalogue,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 7, 22, 12, 0, tzinfo=UTC))


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260722)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    connection = connect(tmp_path / "tunables.db")
    migrate(connection)
    try:
        yield EventStore(connection)
    finally:
        connection.close()


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    return PolicyRegistry(store._conn, clock)


def _payload(filename: str) -> dict[str, object]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _activate(registry: PolicyRegistry) -> None:
    for filename, kind, version in (
        ("control-v1.yaml", "control", "control@1"),
        ("lessons-v1.yaml", "lessons", "lessons@1"),
        ("evidence-v1.yaml", "evidence", "evidence@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("assessments-v1.yaml", "assessments", "assessments@1"),
        ("obligations-v1.yaml", "obligations", "obligations@1"),
        ("tunables-v1.yaml", "tunables", "tunables@1"),
    ):
        registry.register(kind, version, _payload(filename))
        registry.activate(kind, version)


def test_shipped_catalogue_resolves_every_owner_leaf(store, registry) -> None:
    _activate(registry)
    catalogue = registry.resolve_pinned("tunables", "tunables@1")
    owners = {
        kind: registry.resolve_active(kind)[1]
        for kind in ("control", "lessons", "evidence", "scoring", "scheduler", "assessments", "obligations")
    }
    assert validate_catalogue(catalogue, owners) == []
    assert len(list_tunables(registry, owner="0.12 control")) == 48


def test_confirm_activates_owner_successor_and_causally_records_application(
    store, registry, clock, random_source
) -> None:
    _activate(registry)
    proposal = propose_calibration(
        store,
        registry,
        clock,
        random_source,
        "control.budget.shares_bp_by_mode.balanced.review_max",
        5000,
        rationale="measured review pressure",
    )
    applied = confirm_calibration(store, registry, clock, random_source, str(proposal["proposal_id"]))
    version, active = registry.resolve_active("control")
    assert version == applied["owner_policy_version"]
    assert active["budget"]["shares_bp_by_mode"]["balanced"]["review_max"] == 5000
    assert len(list_calibrations(store)) == 1

    activation, application = [
        event for event in store.read() if event.type in {EVENT_POLICY_ACTIVATED, EVENT_CALIBRATION_APPLIED}
    ]
    assert application.causation_id == activation.id
    assert application.payload["activation_event_id"] == activation.id

    # Confirmation is domain-idempotent even without relying on the CLI cache.
    assert confirm_calibration(store, registry, clock, random_source, str(proposal["proposal_id"])) == applied
