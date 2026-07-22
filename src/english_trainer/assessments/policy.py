"""The assessments policy: resume window, cooldown, exposure down-weight
(assessments 2-3; roadmap 2.6).

Placement is a *timed* diagnostic, so two of its rules are tunables that must be
pinned like any other policy (foundation 3.6): the ``resume_window`` after which
a stalled placement expires, and the exposure ``reseen_exposure_weight`` applied
to items a learner has already been shown, so a memorized form cannot be re-sat
as fresh evidence. The values ship as an in-code default the module registers
and activates on demand; calibrating them (and the full authored form content)
is deferred to the content phase (П, OPEN-17).

Every number is an integer count or a decimal *string* parsed under the same
fixed context the scoring path uses -- no IEEE float ever enters a hashed
payload (foundation 5).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from english_trainer.kernel.errors import KernelError

ASSESSMENTS_KIND = "assessments"
ASSESSMENTS_VERSION = "assessments@1"

# The four core skills a placement measures and self-assessment reports against
# (assessments 5; scoring core_skill_map). Listening/speaking are out of scope
# (text-only modalities), so they are absent by construction, never "unknown".
CORE_SKILLS: tuple[str, ...] = ("grammar", "vocabulary", "reading", "writing")
CEFR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")


class AssessmentsPolicyInvalid(KernelError):
    """The assessments policy violates its own contract; it must never activate."""

    code = "ASSESSMENTS_POLICY_INVALID"


# The shipped default. `resume_window_hours` is the 48h tunable [PD-2026-07-20];
# `reseen_exposure_weight` "0" fully zeroes a re-seen item (a valid down-weight
# -- the spec allows "понижается или обнуляется"), captured into every evidence
# event so replay reproduces the contribution.
_DEFAULT_POLICY: dict[str, Any] = {
    "policy_id": ASSESSMENTS_VERSION,
    "schema_version": 1,
    "status": "accepted",
    "resume_window_hours": 48,
    "form_cooldown_days": 30,
    "reseen_exposure_weight": "0",
    "fresh_exposure_weight": "1",
    "core_skills": list(CORE_SKILLS),
    "cefr_levels": list(CEFR_LEVELS),
}


def default_policy() -> dict[str, Any]:
    """A fresh copy of the shipped assessments@1 content."""
    return {
        **_DEFAULT_POLICY,
        "core_skills": list(CORE_SKILLS),
        "cefr_levels": list(CEFR_LEVELS),
    }


def _positive_int(value: Any, path: str, errors: list[str], *, allow_zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path}: must be an integer")
        return
    if value < 0 or (value == 0 and not allow_zero):
        errors.append(f"{path}: must be {'non-negative' if allow_zero else 'positive'}")


def _weight(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{path}: must be a decimal string in [0, 1]")
        return
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{path}: {value!r} is not a parseable decimal string")
        return
    if not (Decimal(0) <= parsed <= Decimal(1)):
        errors.append(f"{path}: must be within [0, 1]")


def validate_assessments_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid)."""
    errors: list[str] = []
    _positive_int(payload.get("resume_window_hours"), "assessments.resume_window_hours", errors)
    _positive_int(
        payload.get("form_cooldown_days"), "assessments.form_cooldown_days", errors, allow_zero=True
    )
    _weight(payload.get("reseen_exposure_weight"), "assessments.reseen_exposure_weight", errors)
    _weight(payload.get("fresh_exposure_weight"), "assessments.fresh_exposure_weight", errors)
    skills = payload.get("core_skills")
    if not isinstance(skills, list) or not skills or not all(isinstance(s, str) for s in skills):
        errors.append("assessments.core_skills: must be a non-empty list of skill ids")
    levels = payload.get("cefr_levels")
    if not isinstance(levels, list) or not levels or not all(isinstance(s, str) for s in levels):
        errors.append("assessments.cefr_levels: must be a non-empty list of CEFR levels")
    return errors


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_assessments_policy(payload)
    if errors:
        raise AssessmentsPolicyInvalid("; ".join(errors))
    return payload


def resume_window(payload: dict[str, Any]) -> timedelta:
    """The tunable resume window as a ``timedelta`` (assessments 2 [PD-2026-07-20])."""
    return timedelta(hours=int(payload["resume_window_hours"]))
