"""Pinned evidence-policy decisions shared by objective, rubric and tutor-verdict attempts.

Two schema versions validate side by side (a session pins one and replays by
it forever):

- ``evidence@1`` -- multi-target credit allocation only;
- ``evidence@2`` -- the same allocation plus the tutor-verdict leaves of the
  lesson report [PD-2026-09-23]: ``verdict_scale`` (verdict -> ``score_ppm``),
  ``review_outcome_by_verdict`` (verdict -> ReviewOutcome), ``report_limits``
  and the policy-owned severity of tutor-reported errors.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.policy import PolicyRegistry

EVIDENCE_KIND = "evidence"
EVIDENCE_VERSION = "evidence@1"
EVIDENCE_VERSION_V2 = "evidence@2"
# policy_id -> schema_version: the versions ``require_valid`` knows how to check.
EVIDENCE_SCHEMAS: dict[str, int] = {EVIDENCE_VERSION: 1, EVIDENCE_VERSION_V2: 2}

# The tutor's verdict vocabulary (lesson_report@1), in canonical order.
VERDICTS: tuple[str, ...] = ("correct", "partial", "incorrect")
# Outcomes a verdict may map to. RECOVERED is never emitted directly: the
# scoring transition table restores the steady state when CONFIRMED lands on
# AT_RISK (evidence.reviews).
VERDICT_REVIEW_OUTCOMES = frozenset({"CONFIRMED", "PROGRESS", "REGRESSION", "INSUFFICIENT_EVIDENCE"})
# The rubric catalogue's severity vocabulary; tutor errors reuse it.
ERROR_SEVERITIES = frozenset({"minor", "major", "blocking"})
REPORT_LIMIT_KEYS: tuple[str, ...] = ("max_items", "max_answer_chars", "max_errors_per_item")
PPM_SCALE = 1_000_000


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


def _positive_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidencePolicyInvalid(f"{path}: must be a positive integer")
    return value


def require_valid_verdict_leaves(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the evidence@2 tutor-verdict leaves.

    Returns ``{verdict_scale, review_outcome_by_verdict, report_limits,
    tutor_errors}``. The scale is integer ppm, monotone in verdict order
    (``correct >= partial >= incorrect``) and tops out at the full scale for
    ``correct``: a fully correct answer that scored less than full quality
    would silently rescale every tutor-verdict evidence.
    """
    scale = payload.get("verdict_scale")
    if not isinstance(scale, dict) or set(scale) != set(VERDICTS):
        raise EvidencePolicyInvalid(f"evidence.verdict_scale: must map exactly {list(VERDICTS)}")
    normalized_scale: dict[str, int] = {}
    for verdict in VERDICTS:
        value = scale[verdict]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= PPM_SCALE:
            raise EvidencePolicyInvalid(
                f"evidence.verdict_scale.{verdict}: must be an integer in 0..{PPM_SCALE}"
            )
        normalized_scale[verdict] = value
    if normalized_scale["correct"] != PPM_SCALE:
        raise EvidencePolicyInvalid(f"evidence.verdict_scale.correct: must be {PPM_SCALE}")
    if not normalized_scale["correct"] >= normalized_scale["partial"] >= normalized_scale["incorrect"]:
        raise EvidencePolicyInvalid(
            "evidence.verdict_scale: must be monotone (correct >= partial >= incorrect)"
        )

    outcomes = payload.get("review_outcome_by_verdict")
    if not isinstance(outcomes, dict) or set(outcomes) != set(VERDICTS):
        raise EvidencePolicyInvalid(f"evidence.review_outcome_by_verdict: must map exactly {list(VERDICTS)}")
    for verdict in VERDICTS:
        if outcomes[verdict] not in VERDICT_REVIEW_OUTCOMES:
            raise EvidencePolicyInvalid(
                f"evidence.review_outcome_by_verdict.{verdict}: "
                f"must be one of {sorted(VERDICT_REVIEW_OUTCOMES)}"
            )

    limits = payload.get("report_limits")
    if not isinstance(limits, dict):
        raise EvidencePolicyInvalid("evidence.report_limits: must be an object")
    normalized_limits = {
        key: _positive_int(limits.get(key), f"evidence.report_limits.{key}") for key in REPORT_LIMIT_KEYS
    }

    tutor_errors = payload.get("tutor_errors")
    if not isinstance(tutor_errors, dict) or tutor_errors.get("default_severity") not in ERROR_SEVERITIES:
        raise EvidencePolicyInvalid(
            f"evidence.tutor_errors.default_severity: must be one of {sorted(ERROR_SEVERITIES)}"
        )
    return {
        "verdict_scale": normalized_scale,
        "review_outcome_by_verdict": {verdict: str(outcomes[verdict]) for verdict in VERDICTS},
        "report_limits": normalized_limits,
        "tutor_errors": {"default_severity": str(tutor_errors["default_severity"])},
    }


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an evidence policy of any known schema version (evidence@1, @2)."""
    policy_id = payload.get("policy_id")
    schema = EVIDENCE_SCHEMAS.get(str(policy_id))
    if schema is None:
        raise EvidencePolicyInvalid(f"evidence.policy_id must be one of {sorted(EVIDENCE_SCHEMAS)!r}")
    if payload.get("schema_version") != schema:
        raise EvidencePolicyInvalid(f"evidence.schema_version must be {schema} for {policy_id}")
    configured = payload.get("multi_credit")
    if not isinstance(configured, dict):
        raise EvidencePolicyInvalid("evidence.multi_credit: must be an object")
    require_valid_multi_credit(configured)
    if schema >= 2:
        require_valid_verdict_leaves(payload)
    return payload


def verdict_policy(registry: PolicyRegistry, pinned_versions: dict[str, str]) -> dict[str, Any]:
    """The pinned tutor-verdict leaves, validated (evidence@2 and later).

    A session that pinned no evidence version, or a version without the
    verdict leaves (evidence@1), cannot accept a tutor-verdict report: the
    scale that turns a verdict into ``score_ppm`` is a pinned decision, never
    a code default.
    """
    if EVIDENCE_KIND not in pinned_versions:
        raise EvidencePolicyInvalid("the session pinned no evidence policy; a tutor verdict has no scale")
    payload = registry.resolve_pinned(EVIDENCE_KIND, pinned_versions[EVIDENCE_KIND])
    if "verdict_scale" not in payload:
        raise EvidencePolicyInvalid(
            f"evidence policy {pinned_versions[EVIDENCE_KIND]} has no verdict_scale; "
            "a tutor-verdict report needs evidence@2 or later"
        )
    return require_valid_verdict_leaves(payload)


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
