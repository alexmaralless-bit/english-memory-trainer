"""Validation for the versioned lessons lifecycle policy."""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.errors import KernelError

LESSONS_KIND = "lessons"
LESSONS_VERSION = "lessons@1"


class LessonsPolicyInvalid(KernelError):
    code = "LESSONS_POLICY_INVALID"


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("policy_id") != LESSONS_VERSION:
        raise LessonsPolicyInvalid(f"lessons.policy_id must be {LESSONS_VERSION!r}")
    days = payload.get("stale_session_days")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise LessonsPolicyInvalid("lessons.stale_session_days must be a positive integer")
    return payload
