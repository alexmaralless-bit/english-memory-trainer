"""Scheduler-policy access and validation (scheduler 3; roadmap 2.3).

The interval table is the v1 formula behind the interface: replacing it (FSRS
is a MAY) means a new policy version, never a different domain model. Days are
integers, ratios are decimal strings; floats are refused everywhere.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

from english_trainer.kernel.errors import KernelError

SCHEDULER_KIND = "scheduler"


class SchedulerPolicyInvalid(KernelError):
    """The scheduler policy violates its own contract; it must never activate."""

    code = "SCHEDULER_POLICY_INVALID"


def _walk_floats(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        errors.append(f"{path}: float {value!r} is banned on the decision path; use a decimal string")
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk_floats(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_floats(item, f"{path}[{index}]", errors)


def _decimal_or_error(value: Any, path: str, errors: list[str]) -> None:
    try:
        Decimal(str(value))
    except decimal.InvalidOperation:
        errors.append(f"{path}: {value!r} is not a parseable decimal string")


def validate_scheduler_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid)."""
    errors: list[str] = []
    _walk_floats(payload, "scheduler", errors)

    intervals = payload.get("intervals_days")
    if (
        not isinstance(intervals, list)
        or not intervals
        or not all(isinstance(day, int) and day > 0 for day in intervals)
    ):
        errors.append("scheduler.intervals_days: must be a non-empty list of positive integers")
    elif intervals != sorted(intervals) or len(set(intervals)) != len(intervals):
        errors.append("scheduler.intervals_days: must be strictly increasing")

    if not isinstance(payload.get("retry_days"), int) or payload.get("retry_days", 0) <= 0:
        errors.append("scheduler.retry_days: must be a positive integer")
    for key in ("target_recall", "overdue_factor", "at_risk_overdue_factor"):
        if key not in payload:
            errors.append(f"scheduler.{key}: missing")
        else:
            _decimal_or_error(payload[key], f"scheduler.{key}", errors)

    re_entry = payload.get("re_entry")
    if not isinstance(re_entry, dict):
        errors.append("scheduler.re_entry: missing")
    else:
        if not isinstance(re_entry.get("gap_threshold_days"), int):
            errors.append("scheduler.re_entry.gap_threshold_days: must be an integer")
        if "retrievability_floor" not in re_entry:
            errors.append("scheduler.re_entry.retrievability_floor: missing")
        else:
            _decimal_or_error(
                re_entry["retrievability_floor"], "scheduler.re_entry.retrievability_floor", errors
            )
    return errors


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_scheduler_policy(payload)
    if errors:
        raise SchedulerPolicyInvalid("; ".join(errors))
    return payload
