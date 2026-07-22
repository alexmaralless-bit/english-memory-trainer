"""Pinned evidence-policy decisions shared by objective and rubric attempts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.policy import PolicyRegistry

EVIDENCE_KIND = "evidence"
EVIDENCE_VERSION = "evidence@1"


class EvidencePolicyInvalid(KernelError):
    code = "EVIDENCE_POLICY_INVALID"


_DEFAULT_MULTI_CREDIT = {
    "primary_weight": "1.0",
    "secondary_weight": "0.5",
    "total_weight_cap": "2.0",
}


def _decimal(value: object, path: str) -> Decimal:
    if not isinstance(value, str):
        raise EvidencePolicyInvalid(f"{path}: must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise EvidencePolicyInvalid(f"{path}: invalid decimal string") from None
    if not parsed.is_finite() or parsed < 0:
        raise EvidencePolicyInvalid(f"{path}: must be finite and non-negative")
    return parsed


def multi_credit_policy(registry: PolicyRegistry | None, pinned_versions: dict[str, str]) -> dict[str, str]:
    if registry is None or EVIDENCE_KIND not in pinned_versions:
        return dict(_DEFAULT_MULTI_CREDIT)
    payload = registry.resolve_pinned(EVIDENCE_KIND, pinned_versions[EVIDENCE_KIND])
    configured = payload.get("multi_credit")
    if not isinstance(configured, dict):
        raise EvidencePolicyInvalid("evidence.multi_credit: must be an object")
    result = {key: configured.get(key) for key in _DEFAULT_MULTI_CREDIT}
    return require_valid_multi_credit(result)


def require_valid_multi_credit(configured: dict[str, object]) -> dict[str, str]:
    """Validate and normalize the decision-bearing multi-credit leaf."""
    result = {key: configured.get(key) for key in _DEFAULT_MULTI_CREDIT}
    for key, value in result.items():
        _decimal(value, f"evidence.multi_credit.{key}")
    primary = _decimal(result["primary_weight"], "primary_weight")
    cap = _decimal(result["total_weight_cap"], "total_weight_cap")
    if primary <= 0 or cap < primary:
        raise EvidencePolicyInvalid("evidence.multi_credit: cap must cover a positive primary weight")
    secondary = _decimal(result["secondary_weight"], "secondary_weight")
    if secondary > cap:
        raise EvidencePolicyInvalid("evidence.multi_credit: secondary weight must not exceed the cap")
    return {key: str(value) for key, value in result.items()}


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("policy_id") != EVIDENCE_VERSION:
        raise EvidencePolicyInvalid(f"evidence.policy_id must be {EVIDENCE_VERSION!r}")
    configured = payload.get("multi_credit")
    if not isinstance(configured, dict):
        raise EvidencePolicyInvalid("evidence.multi_credit: must be an object")
    require_valid_multi_credit(configured)
    return payload


def allocate_credit(
    targets: list[dict[str, Any]],
    primary_target: dict[str, Any] | None,
    policy: dict[str, str],
) -> list[dict[str, Any]]:
    """Allocate one answer span across distinct targets in canonical order."""
    if primary_target is None or not primary_target.get("target_ref"):
        return []
    primary_key = (
        str(primary_target["target_ref"]),
        str(primary_target.get("dimension") or "recognition"),
    )
    unique = {
        (str(item.get("target_ref")), str(item.get("dimension") or "recognition"))
        for item in targets
        if item.get("target_ref")
    }
    unique.add(primary_key)
    ordered = [primary_key, *sorted(unique - {primary_key})]
    primary_weight = _decimal(policy["primary_weight"], "primary_weight")
    secondary_weight = _decimal(policy["secondary_weight"], "secondary_weight")
    cap = _decimal(policy["total_weight_cap"], "total_weight_cap")
    used_total = Decimal(0)
    allocations: list[dict[str, Any]] = []
    for index, (target_ref, dimension) in enumerate(ordered):
        weight = primary_weight if index == 0 else secondary_weight
        used = weight > 0 and used_total + weight <= cap
        if used:
            used_total += weight
        allocations.append(
            {
                "target_ref": target_ref,
                "dimension": dimension,
                "contribution": str(weight) if used else "0",
                "used": used,
                "reason": "primary" if index == 0 else ("secondary" if used else "total_cap"),
            }
        )
    return allocations
