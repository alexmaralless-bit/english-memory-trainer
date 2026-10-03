"""Shipped engine policies activate together, in file order (control 3, 4.9).

``curriculum activate`` registers and activates every ``curriculum/policies/
*.yaml`` in sorted filename order, so the highest-numbered file of a kind ends
up active: ``control-v3.yaml`` selects ``control@3`` and ``tunables-v2.yaml``
selects ``tunables@2``. The catalogue check is bidirectional and runs only after
every owner policy is active, which is what makes the pairing testable at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from english_trainer.control.tunables import (
    TunableCatalogueInvalid,
    list_tunables,
    require_valid_catalogue,
    validate_catalogue,
)
from english_trainer.curriculum.loader import load_policies
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

REPO = Path(__file__).resolve().parents[2]
POLICIES = REPO / "curriculum" / "policies"


def _payload(filename: str) -> dict[str, object]:
    loaded = yaml.safe_load((POLICIES / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    shipped = PolicyRegistry(store._conn, clock)
    for kind, version, payload in load_policies(REPO / "curriculum"):
        shipped.register(kind, version, payload)
        shipped.activate(kind, version)
    return shipped


def test_the_shipped_files_leave_control_v3_and_tunables_v2_active(registry: PolicyRegistry) -> None:
    assert registry.active_version("control") == "control@3"
    assert registry.active_version("tunables") == "tunables@2"
    # Every earlier version stays resolvable for replay of the sessions pinned
    # to it -- activation picks a default, it does not retire history.
    for version in ("control@1", "control@2", "control@3"):
        assert registry.resolve_pinned("control", version)["policy_id"] == version


def test_the_active_catalogue_covers_active_control_in_both_directions(
    registry: PolicyRegistry,
) -> None:
    rows = list_tunables(registry, owner="0.12 control")
    assert len(rows) == 51
    priced = {
        row["parameter_id"]
        for row in rows
        if str(row["parameter_id"]).startswith("control.budget.expected_seconds_by_step_type.")
    }
    assert priced >= {
        "control.budget.expected_seconds_by_step_type.drill_block",
        "control.budget.expected_seconds_by_step_type.timed_writing",
        "control.budget.expected_seconds_by_step_type.reconstruction",
    }


def test_the_previous_catalogue_no_longer_covers_control_v3(registry: PolicyRegistry) -> None:
    # The reason tunables@2 had to exist: with control@3 active, tunables@1 is
    # incomplete and the validator names exactly the three missing leaves.
    errors = validate_catalogue(
        _payload("tunables-v1.yaml"),
        {
            kind: registry.resolve_active(kind)[1]
            for kind in (
                "control",
                "lessons",
                "evidence",
                "scoring",
                "scheduler",
                "assessments",
                "obligations",
            )
        },
    )
    missing = [error for error in errors if error.startswith("control catalogue missing")]
    assert len(missing) == 1
    for step_type in ("drill_block", "timed_writing", "reconstruction"):
        assert f"expected_seconds_by_step_type.{step_type}" in missing[0]
    with pytest.raises(TunableCatalogueInvalid):
        require_valid_catalogue(registry, _payload("tunables-v1.yaml"))
