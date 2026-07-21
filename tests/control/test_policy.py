"""control@1 validation: total, executable, integer-only (control 3)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.errors import ControlPolicyInvalid
from english_trainer.control.policy import require_valid, validate_control_policy

REPO = Path(__file__).resolve().parents[2]


def payload() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_shipped_policy_is_valid() -> None:
    assert validate_control_policy(payload()) == []


def test_floats_are_refused_anywhere_in_the_payload() -> None:
    broken = copy.deepcopy(payload())
    broken["budget"]["shares_bp_by_mode"]["balanced"]["review_max"] = 0.45
    errors = validate_control_policy(broken)
    assert any("float" in error for error in errors)


def test_infeasible_shares_are_refused_per_mode() -> None:
    broken = copy.deepcopy(payload())
    broken["budget"]["shares_bp_by_mode"]["balanced"]["growth_min"] = 9000
    errors = validate_control_policy(broken)
    # 9000 + 1500 + 1000 > 10000 and 4500 + 9000 > 10000 -- both named.
    assert any("growth_min + integration_min + choice_min" in error for error in errors)
    assert any("review_max + growth_min" in error for error in errors)


def test_unreachable_floor_is_refused() -> None:
    broken = copy.deepcopy(payload())
    # No growth step type fits even the default session: the floor is a
    # guaranteed *attempt*, so this version must never activate [RR2-5].
    broken["budget"]["expected_seconds_by_step_type"]["new_material_intro"] = 99999
    broken["budget"]["expected_seconds_by_step_type"]["controlled_production"] = 99999
    errors = validate_control_policy(broken)
    assert any("unreachable" in error for error in errors)
    with pytest.raises(ControlPolicyInvalid):
        require_valid(broken)
