"""Scoring-policy access and validation (scoring 2; roadmap 2.3).

Every formula input is a concrete value of a versioned policy: decimal-bearing
numbers are *strings* parsed under the fixed Decimal context (precision 28,
ROUND_HALF_EVEN -- canon 2.1, review 0.4-8), counters and caps are integers.
IEEE floats are refused anywhere in the payload: on a boundary value two float
paths could round a Mastery differently and replay would stop being bitwise.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

from english_trainer.kernel.errors import KernelError

SCORING_KIND = "scoring"

DIMENSIONS = ("recognition", "controlled_production", "spontaneous_production", "transfer")
OUTCOME_QUALITIES = ("PROGRESS", "CONFIRMED", "RECOVERED")


class ScoringPolicyInvalid(KernelError):
    """The scoring policy violates its own contract; it must never activate."""

    code = "SCORING_POLICY_INVALID"


def scoring_context(payload: dict[str, Any]) -> decimal.Context:
    """The fixed Decimal context the policy pins (part of the pinned policy)."""
    section = payload.get("decimal_context") or {}
    return decimal.Context(
        prec=int(section.get("precision", 28)),
        rounding=getattr(decimal, str(section.get("rounding", "ROUND_HALF_EVEN"))),
    )


def _walk_floats(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        errors.append(f"{path}: float {value!r} is banned on the scoring path; use a decimal string")
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk_floats(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_floats(item, f"{path}[{index}]", errors)


def _decimal_or_error(value: Any, path: str, errors: list[str]) -> Decimal | None:
    try:
        return Decimal(str(value))
    except decimal.InvalidOperation:
        errors.append(f"{path}: {value!r} is not a parseable decimal string")
        return None


def validate_scoring_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid)."""
    errors: list[str] = []
    _walk_floats(payload, "scoring", errors)

    context = payload.get("decimal_context") or {}
    if context.get("precision") != 28 or context.get("rounding") != "ROUND_HALF_EVEN":
        errors.append("scoring.decimal_context: must pin precision 28 and ROUND_HALF_EVEN (canon 2.1)")

    mastery = payload.get("mastery")
    if not isinstance(mastery, dict):
        errors.append("scoring.mastery: missing")
        return errors
    weights: dict[str, Decimal] = {}
    for dimension in DIMENSIONS:
        value = (mastery.get("mode_weights") or {}).get(dimension)
        if value is None:
            errors.append(f"scoring.mastery.mode_weights.{dimension}: missing")
            continue
        parsed = _decimal_or_error(value, f"scoring.mastery.mode_weights.{dimension}", errors)
        if parsed is not None:
            weights[dimension] = parsed
    if len(weights) == len(DIMENSIONS):
        # The canonical ordering: recognition < controlled < spontaneous (2.1);
        # transfer confirms ownership across contexts and must not be free.
        if not (
            weights["recognition"] < weights["controlled_production"] < weights["spontaneous_production"]
        ):
            errors.append(
                "scoring.mastery.mode_weights: must increase recognition < controlled < spontaneous"
            )
        if weights["transfer"] <= 0:
            errors.append("scoring.mastery.mode_weights.transfer: must be positive")
    for key in ("base_delta", "hint_penalty_per_hint", "hint_penalty_floor", "regression_penalty"):
        if key not in mastery:
            errors.append(f"scoring.mastery.{key}: missing")
        else:
            _decimal_or_error(mastery[key], f"scoring.mastery.{key}", errors)
    for key in ("session_cap", "rubric_cap"):
        if not isinstance(mastery.get(key), int) or mastery.get(key, 0) <= 0:
            errors.append(f"scoring.mastery.{key}: must be a positive integer")

    stability = payload.get("stability")
    if not isinstance(stability, dict):
        errors.append("scoring.stability: missing")
        return errors
    for key in (
        "initial_stability_days",
        "success_growth_base",
        "growth_damping_days",
        "regression_shrink_factor",
    ):
        if key not in stability:
            errors.append(f"scoring.stability.{key}: missing")
        else:
            _decimal_or_error(stability[key], f"scoring.stability.{key}", errors)
    qualities = stability.get("outcome_quality") or {}
    for outcome in OUTCOME_QUALITIES:
        if outcome not in qualities:
            errors.append(f"scoring.stability.outcome_quality.{outcome}: missing")
        else:
            _decimal_or_error(qualities[outcome], f"scoring.stability.outcome_quality.{outcome}", errors)

    origin = payload.get("origin_rules") or {}
    if origin.get("placement_state_ceiling") != "ACTIVE":
        errors.append("scoring.origin_rules.placement_state_ceiling: must be ACTIVE (canon 4b)")
    if origin.get("control_probe_no_negative") is not True:
        errors.append("scoring.origin_rules.control_probe_no_negative: must be true (canon 4b)")

    skill_map = payload.get("core_skill_map")
    if not isinstance(skill_map, dict) or not skill_map:
        errors.append("scoring.core_skill_map: missing")
    else:
        for track, row in skill_map.items():
            if not isinstance(row, dict):
                errors.append(f"scoring.core_skill_map.{track}: not a mapping")
                continue
            for dimension in DIMENSIONS:
                if dimension not in row:
                    errors.append(f"scoring.core_skill_map.{track}.{dimension}: missing (map must be total)")
                    continue
                cell = row[dimension]
                if cell is None:
                    continue
                if not isinstance(cell, dict) or not cell.get("skill"):
                    errors.append(f"scoring.core_skill_map.{track}.{dimension}: needs skill + weight")
                else:
                    _decimal_or_error(
                        cell.get("weight"), f"scoring.core_skill_map.{track}.{dimension}.weight", errors
                    )
    return errors


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_scoring_policy(payload)
    if errors:
        raise ScoringPolicyInvalid("; ".join(errors))
    return payload
