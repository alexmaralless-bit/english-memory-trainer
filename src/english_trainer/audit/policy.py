"""Validation for the versioned Tutor Compliance obligation registry."""

from __future__ import annotations

from typing import Any

from english_trainer.audit.views import ObligationPolicyInvalid

OBLIGATIONS_KIND = "obligations"
OBLIGATIONS_VERSION = "obligations@1"
_SUPPORTED = {"required_skill_effect", "correction_protocol", "forbidden_action_absence"}


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("policy_id") != OBLIGATIONS_VERSION:
        raise ObligationPolicyInvalid(f"obligations.policy_id must be {OBLIGATIONS_VERSION!r}")
    window = payload.get("measurement_window_terminal_sessions")
    if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
        raise ObligationPolicyInvalid(
            "obligations.measurement_window_terminal_sessions must be a positive integer"
        )
    obligations = payload.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise ObligationPolicyInvalid("obligations.obligations must be a non-empty list")
    ids = [str(item.get("obligation_id")) for item in obligations if isinstance(item, dict)]
    order = [str(item) for item in payload.get("matching_order") or []]
    if len(ids) != len(obligations) or set(ids) != _SUPPORTED or order != ids:
        raise ObligationPolicyInvalid(
            "obligations and matching_order must contain the three supported ids in policy order"
        )
    return payload
