"""rubric@1 policy validation (evidence-owned consumer; P.5 [PD-2026-07-22]).

The rubric policy is data the ENGINE executes: criterion levels and
``score_ppm`` are computed here (in the assessment increment), never accepted
from a client. This module holds the total structural validator the
activation hook runs before the payload may register -- mirroring the rules
canon now names (curriculum enforcement patch): no floats, resolvable refs,
profile weights summing to exactly 10000 units, one score-bearing criterion
per error family, unique exact defaults compatible with their profiles, and
the complete four-level scale of PD-2 B.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.errors import KernelError

RUBRIC_KIND = "rubric"

WEIGHT_TOTAL_UNITS = 10000
LEVEL_PPM = {"0": 0, "1": 333333, "2": 666667, "3": 1000000}


class RubricPolicyInvalid(KernelError):
    """The rubric policy violates its own contract; it must never activate."""

    code = "RUBRIC_POLICY_INVALID"


def _walk_floats(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        errors.append(f"{path}: float {value!r} is banned; use integers or decimal strings")
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk_floats(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_floats(item, f"{path}[{index}]", errors)


def validate_rubric_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid). Total over the contract."""
    errors: list[str] = []
    _walk_floats(payload, "rubric", errors)

    criteria = payload.get("criterion_catalog")
    profiles = payload.get("rubric_profiles")
    operations = payload.get("machine_operations")
    families = payload.get("error_families")
    if not isinstance(criteria, dict) or not criteria:
        errors.append("rubric.criterion_catalog: missing")
        return errors
    if not isinstance(profiles, dict) or not profiles:
        errors.append("rubric.rubric_profiles: missing")
        return errors
    operations = operations if isinstance(operations, dict) else {}
    families = families if isinstance(families, dict) else {}

    scale = payload.get("level_scale")
    if not isinstance(scale, dict) or set(scale) != set(LEVEL_PPM):
        errors.append("rubric.level_scale: must define exactly levels 0..3 (PD-2 B)")
    else:
        for level, expected_ppm in LEVEL_PPM.items():
            if int(scale[level].get("level_ppm", -1)) != expected_ppm:
                errors.append(f"rubric.level_scale.{level}: level_ppm must be {expected_ppm}")

    for criterion_id, criterion in criteria.items():
        for op in criterion.get("allowed_machine_operations") or []:
            if op not in operations:
                errors.append(f"criterion {criterion_id}: unknown machine operation {op!r}")
        for finding_id, finding in (criterion.get("negative_findings") or {}).items():
            family = finding.get("error_family")
            if family is not None:
                bound = (families.get(family) or {}).get("score_criterion_id")
                if family not in families:
                    errors.append(f"criterion {criterion_id}.{finding_id}: unknown error family {family!r}")
                elif bound != criterion_id:
                    errors.append(
                        f"criterion {criterion_id}.{finding_id}: error family {family!r} is score-bound "
                        f"to {bound!r} -- exactly one score-bearing criterion per family (PD-4 C)"
                    )

    for family_id, family in families.items():
        if family.get("severity") not in ("minor", "major", "blocking"):
            errors.append(f"error family {family_id}: severity must be minor|major|blocking")
        if family.get("score_criterion_id") not in criteria:
            errors.append(f"error family {family_id}: dangling score_criterion_id")

    profile_refs: set[str] = set()
    for profile_id, profile in profiles.items():
        ref = str(profile.get("rubric_ref") or "")
        if ref != f"rubric:{profile_id}":
            errors.append(f"profile {profile_id}: rubric_ref must be rubric:{profile_id} (PD-5 A)")
        profile_refs.add(ref)
        selected = profile.get("criteria") or []
        total = 0
        for item in selected:
            if item.get("criterion_id") not in criteria:
                errors.append(f"profile {profile_id}: dangling criterion {item.get('criterion_id')!r}")
            total += int(item.get("weight_units", 0))
        if total != WEIGHT_TOTAL_UNITS:
            errors.append(f"profile {profile_id}: weights sum to {total}, must be {WEIGHT_TOTAL_UNITS}")

    default_map = payload.get("default_rubric_map") or {}
    seen: set[tuple[str, str]] = set()
    profiles_by_ref = {str(p.get("rubric_ref")): p for p in profiles.values()}
    for entry in default_map.get("entries") or []:
        key = (str(entry.get("step_type")), str(entry.get("dimension")))
        if key in seen:
            errors.append(f"default {key}: duplicate (the exact table must be unambiguous, PD-6 B)")
        seen.add(key)
        ref = str(entry.get("rubric_ref") or "")
        profile = profiles_by_ref.get(ref)
        if profile is None:
            errors.append(f"default {key}: dangling rubric_ref {ref!r}")
            continue
        if key[0] not in (profile.get("allowed_step_types") or []):
            errors.append(f"default {key}: step_type not allowed by profile {ref}")
        if key[1] not in (profile.get("dimensions") or []):
            errors.append(f"default {key}: dimension not allowed by profile {ref}")
    return errors


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_rubric_policy(payload)
    if errors:
        raise RubricPolicyInvalid("; ".join(errors))
    return payload
