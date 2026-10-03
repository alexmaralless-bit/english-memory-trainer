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


def _validate_relearning_ladder(payload: dict[str, Any], intervals: Any, errors: list[str]) -> None:
    """``relearning_ladder_days`` (scheduler@2, wiki/modules/scheduler.md 3a).

    Absent key is valid (scheduler@1: no ladder, base table only). When
    present it must be a strictly increasing list of positive integers whose
    last rung is smaller than at least one base ``intervals_days`` rung -- the
    ladder must actually hand off into the base table, never dangle past it.
    """
    if "relearning_ladder_days" not in payload:
        return
    ladder = payload["relearning_ladder_days"]
    if (
        not isinstance(ladder, list)
        or not ladder
        or not all(isinstance(day, int) and day > 0 for day in ladder)
    ):
        errors.append("scheduler.relearning_ladder_days: must be a non-empty list of positive integers")
        return
    if ladder != sorted(ladder) or len(set(ladder)) != len(ladder):
        errors.append("scheduler.relearning_ladder_days: must be strictly increasing")
        return
    if isinstance(intervals, list) and intervals and not any(day > ladder[-1] for day in intervals):
        errors.append(
            "scheduler.relearning_ladder_days: last rung must be smaller than a base "
            "intervals_days rung that follows it"
        )


def _validate_permanent_interleave(payload: dict[str, Any], intervals: Any, errors: list[str]) -> None:
    """``permanent_interleave_interval_days`` (scheduler@2, wiki/modules/scheduler.md 3a).

    Absent key is valid (scheduler@1, or any future policy that does not offer
    the permanent-interleave tier). When present it must be a positive integer
    equal to the LAST rung of the base ``intervals_days`` table: the canon
    names the permanent-interleave interval as literally "the last base
    interval (180 days)", not an independently tunable number, so this is not
    a ``>=`` floor -- it is the same rung, named. Letting the two config knobs
    diverge would silently desynchronize them the moment either one is edited
    without the other.
    """
    if "permanent_interleave_interval_days" not in payload:
        return
    value = payload["permanent_interleave_interval_days"]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append("scheduler.permanent_interleave_interval_days: must be a positive integer")
        return
    if isinstance(intervals, list) and intervals and value != intervals[-1]:
        errors.append(
            "scheduler.permanent_interleave_interval_days: must equal the last intervals_days rung "
            f"({intervals[-1]!r}), not {value!r} -- it names the base table's last interval, never "
            "an independent number"
        )


def effective_intervals_days(payload: dict[str, Any]) -> list[int]:
    """The interval table the fold actually uses (wiki/modules/scheduler.md 3a).

    ``scheduler@1`` carries no ``relearning_ladder_days`` key and returns the
    base table unchanged -- byte-identical to today. ``scheduler@2`` prepends
    the short relearning ladder and keeps only the base rungs strictly greater
    than its last rung, so ``[1, 2, 4]`` in front of
    ``[1, 3, 7, 14, 30, 60, 120, 180]`` becomes
    ``[1, 2, 4, 7, 14, 30, 60, 120, 180]``.
    """
    base = [int(day) for day in payload["intervals_days"]]
    ladder = payload.get("relearning_ladder_days")
    if not ladder:
        return base
    last_rung = int(ladder[-1])
    return [*(int(day) for day in ladder), *(day for day in base if day > last_rung)]


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

    _validate_relearning_ladder(payload, intervals, errors)
    _validate_permanent_interleave(payload, intervals, errors)

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
