"""Executable marker for the unresolved control 4.9 catalogue data contract."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def test_versioned_tunable_catalogue_exists_with_bidirectional_control_coverage() -> None:
    catalogue_path = REPO / "curriculum" / "policies" / "tunables-v1.yaml"
    catalogue = yaml.safe_load(catalogue_path.read_text("utf-8"))
    control = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(catalogue, dict) and isinstance(control, dict)

    def leaves(value: object, prefix: str) -> set[str]:
        if isinstance(value, dict):
            result: set[str] = set()
            for key, item in value.items():
                result |= leaves(item, f"{prefix}.{key}")
            return result
        return {prefix}

    ignored = {
        "control.policy_id",
        "control.schema_version",
        "control.status",
        "control.canonical_encoding",
        "control.numeric_value_rule",
    }
    control_parameters = leaves(control, "control") - ignored
    rows = catalogue.get("parameters") or []
    catalogued = {
        str(row["parameter_id"])
        for row in rows
        if isinstance(row, dict) and str(row.get("owner")) == "0.12 control"
    }
    assert catalogued == control_parameters
    assert all(
        isinstance(row.get("allowed_range"), list)
        and len(row["allowed_range"]) == 2
        and row.get("change_mode") == "propose_confirm"
        for row in rows
        if isinstance(row, dict)
    )
