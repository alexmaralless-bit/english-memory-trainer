"""Validation for the versioned Tutor Compliance obligation registry."""

from __future__ import annotations

from typing import Any

from english_trainer.audit.views import ObligationPolicyInvalid

OBLIGATIONS_KIND = "obligations"
OBLIGATIONS_VERSION = "obligations@1"
_SUPPORTED_V1 = {"required_skill_effect", "correction_protocol", "forbidden_action_absence"}
_SUPPORTED_V2 = {
    *_SUPPORTED_V1,
    "lesson_preflight",
    "teaching_snapshot",
    "delivery_protocol",
}
# obligations@3 observes the SAME six obligations as v2; what changed is how
# two of them are satisfied (rendered-before-attempt, assessed attempt +
# review closed through either trigger) -- the registry shape is unchanged.
_SUPPORTED_V3 = set(_SUPPORTED_V2)
# obligations@4 [PD-2026-09-23] observes the brief/report protocol: it drops
# `teaching_snapshot`, `delivery_protocol` and `correction_protocol` (there is
# no more per-step rendering or engine-graded correction to police) and adds
# two outcome-shaped obligations in their place -- `report_committed` and
# `reviews_addressed`. `required_skill_effect`, `lesson_preflight` and
# `forbidden_action_absence` carry over.
_SUPPORTED_V4 = {
    "required_skill_effect",
    "lesson_preflight",
    "report_committed",
    "reviews_addressed",
    "forbidden_action_absence",
}
_KNOWN_VERSIONS = (OBLIGATIONS_VERSION, "obligations@2", "obligations@3", "obligations@4")
_SUPPORTED_BY_VERSION = {
    OBLIGATIONS_VERSION: _SUPPORTED_V1,
    "obligations@2": _SUPPORTED_V2,
    "obligations@3": _SUPPORTED_V3,
    "obligations@4": _SUPPORTED_V4,
}


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    policy_id = payload.get("policy_id")
    if policy_id not in _KNOWN_VERSIONS:
        raise ObligationPolicyInvalid(
            "obligations.policy_id must be one of " + ", ".join(repr(name) for name in _KNOWN_VERSIONS)
        )
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
    supported = _SUPPORTED_BY_VERSION[str(policy_id)]
    if len(ids) != len(obligations) or set(ids) != supported or order != ids:
        raise ObligationPolicyInvalid(
            f"obligations and matching_order must contain the supported ids for {policy_id} in policy order"
        )
    return payload
