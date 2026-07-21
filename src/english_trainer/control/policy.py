"""Control-policy access and total validation (control 3; roadmap 2.2).

The policy is *executable*: every branch of the composition pipeline reads a
concrete value from here -- there are no ranges and no implementation-chosen
defaults. Validation is total and runs before registration:

- **integer arithmetic on the whole decision path** [R-12, RR2-12]: every
  decision-bearing field must be an ``int`` (shares in basis points, ppm,
  seconds). A YAML float anywhere in the payload is refused with a readable
  message (the kernel's canonical encoding would refuse it anyway, later and
  more rudely).
- **share feasibility per mode**: ``growth_min + integration_min + choice_min
  <= 10000`` and ``review_max + growth_min <= 10000``.
- **discrete attainability of floors** [RR2-5]: for every mode, every non-zero
  floor and every whole-minute budget from ``min_total_minutes`` to
  ``default_total_minutes`` there must exist at least one step type admissible
  for that bucket with ``expected_seconds <= total_seconds`` -- the floor is a
  guaranteed *attempt*, so a step merely has to fit the session, not the floor.
"""

from __future__ import annotations

from typing import Any

from english_trainer.control.errors import ControlPolicyInvalid

CONTROL_KIND = "control"

BUCKETS = ("review", "growth", "integration", "choice")

# kind -> admissible step types (control 4.3a); the closed matrix that keeps
# two implementations from pricing the same plan differently [RR2-5].
STEP_TYPES_BY_KIND: dict[str, tuple[str, ...]] = {
    "review": ("recognition_check", "controlled_production", "spontaneous_production", "transfer_task"),
    "growth": ("new_material_intro", "controlled_production"),
    "integration": ("integration_task", "transfer_task"),
    "choice": ("free_conversation", "spontaneous_production"),
    "gate": ("gate_item",),
    "probe": ("transfer_task", "spontaneous_production"),
}

# kind -> bucket is total (control 4.3a): choice hosts gate and probe steps too.
BUCKET_BY_KIND: dict[str, str] = {
    "review": "review",
    "growth": "growth",
    "integration": "integration",
    "choice": "choice",
    "gate": "choice",
    "probe": "choice",
}

# Canonical step-type ranks for sorting (control 4.4 step 4).
STEP_TYPE_RANK: dict[str, int] = {
    "new_material_intro": 0,
    "recognition_check": 1,
    "controlled_production": 2,
    "spontaneous_production": 3,
    "transfer_task": 4,
    "integration_task": 5,
    "gate_item": 6,
    "free_conversation": 7,
}

# Step types whose delivery asks the learner to *produce* language -- the set
# the live production_eligible safety check applies to (control 4.2 [П.3]).
PRODUCTION_STEP_TYPES = frozenset(
    {"controlled_production", "spontaneous_production", "transfer_task", "integration_task"}
)

# Buckets whose floors are reserved, in the fixed reservation order (4.4 step 5).
FLOOR_ORDER = ("growth", "integration", "choice")


def _walk_numbers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        errors.append(f"{path}: float {value!r} is banned on the decision path; use integers")
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk_numbers(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_numbers(item, f"{path}[{index}]", errors)


def validate_control_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid). Total: checks all rules."""
    errors: list[str] = []
    _walk_numbers(payload, "control", errors)

    budget = payload.get("budget")
    if not isinstance(budget, dict):
        errors.append("control.budget: missing or not a mapping")
        return errors

    costs = budget.get("expected_seconds_by_step_type")
    if not isinstance(costs, dict):
        errors.append("control.budget.expected_seconds_by_step_type: missing")
        costs = {}
    for step_type in STEP_TYPE_RANK:
        if not isinstance(costs.get(step_type), int):
            errors.append(f"control.budget.expected_seconds_by_step_type.{step_type}: missing integer cost")

    minimum = budget.get("min_total_minutes")
    default = budget.get("default_total_minutes")
    if not isinstance(minimum, int) or not isinstance(default, int) or minimum <= 0 or default < minimum:
        errors.append(
            "control.budget: min_total_minutes/default_total_minutes must be ints with 0 < min <= default"
        )
        return errors

    shares = budget.get("shares_bp_by_mode")
    if not isinstance(shares, dict) or not shares:
        errors.append("control.budget.shares_bp_by_mode: missing")
        return errors

    floor_keys = {"growth": "growth_min", "integration": "integration_min", "choice": "choice_min"}
    for mode, table in sorted(shares.items()):
        if not isinstance(table, dict):
            errors.append(f"control.budget.shares_bp_by_mode.{mode}: not a mapping")
            continue
        review_max = table.get("review_max", 0)
        floors = {bucket: table.get(key, 0) for bucket, key in floor_keys.items()}
        # Feasibility of the share algebra (control 3).
        if sum(floors.values()) > 10000:
            errors.append(f"{mode}: growth_min + integration_min + choice_min > 10000 bp")
        if review_max + floors["growth"] > 10000:
            errors.append(f"{mode}: review_max + growth_min > 10000 bp")
        # Discrete attainability [RR2-5]: some admissible step must fit the
        # *session* for every whole-minute budget in [min, default].
        for bucket, floor_bp in floors.items():
            if floor_bp == 0:
                continue
            step_costs = [costs[t] for t in STEP_TYPES_BY_KIND[bucket] if isinstance(costs.get(t), int)]
            if not step_costs:
                errors.append(f"{mode}.{bucket}: no admissible step type has a cost")
                continue
            for minutes in range(minimum, default + 1):
                if min(step_costs) > minutes * 60:
                    errors.append(
                        f"{mode}.{bucket}: floor {floor_bp} bp unreachable at {minutes} min -- "
                        f"cheapest admissible step costs {min(step_costs)}s"
                    )
                    break
    return errors


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate or raise :class:`ControlPolicyInvalid` with every violation."""
    errors = validate_control_policy(payload)
    if errors:
        raise ControlPolicyInvalid("; ".join(errors))
    return payload


def step_cost(policy: dict[str, Any], step_type: str) -> int:
    return int(policy["budget"]["expected_seconds_by_step_type"][step_type])


def mode_shares(policy: dict[str, Any], mode: str) -> dict[str, int]:
    """``{review_max, growth_min, integration_min, choice_min}`` for ``mode``."""
    table = policy["budget"]["shares_bp_by_mode"].get(mode)
    if table is None:
        raise ControlPolicyInvalid(f"mode {mode!r} is not defined by the control policy")
    return {key: int(value) for key, value in table.items()}
