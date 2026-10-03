"""Validation for the versioned lessons lifecycle policy."""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.errors import KernelError

LESSONS_KIND = "lessons"
LESSONS_VERSION = "lessons@1"
# lessons@2 [PD-2026-09-23] layers the brief/report protocol's schema ids and
# advisory requirements onto lessons@1's `stale_session_days` (unchanged in
# meaning); see curriculum/policies/lessons-v2.yaml.
LESSONS_VERSION_2 = "lessons@2"
_KNOWN_VERSIONS = (LESSONS_VERSION, LESSONS_VERSION_2)
_BRIEF_SCHEMA = "lesson_brief@1"
_REPORT_SCHEMA = "lesson_report@1"
# The concept is explicit that a brief's requirements are warnings the tutor
# sees, never grounds to reject a report: this policy has no vocabulary for a
# blocking requirement, so "warning" is the only severity it accepts.
_ADVISORY_SEVERITIES = {"warning"}


class LessonsPolicyInvalid(KernelError):
    code = "LESSONS_POLICY_INVALID"


def require_valid(payload: dict[str, Any]) -> dict[str, Any]:
    policy_id = payload.get("policy_id")
    if policy_id not in _KNOWN_VERSIONS:
        raise LessonsPolicyInvalid(f"lessons.policy_id must be one of {_KNOWN_VERSIONS!r}")
    days = payload.get("stale_session_days")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise LessonsPolicyInvalid("lessons.stale_session_days must be a positive integer")
    if policy_id == LESSONS_VERSION_2:
        _require_valid_v2_fields(payload)
    return payload


def _require_valid_v2_fields(payload: dict[str, Any]) -> None:
    if payload.get("brief_schema") != _BRIEF_SCHEMA:
        raise LessonsPolicyInvalid(f"lessons.brief_schema must be {_BRIEF_SCHEMA!r}")
    if payload.get("report_schema") != _REPORT_SCHEMA:
        raise LessonsPolicyInvalid(f"lessons.report_schema must be {_REPORT_SCHEMA!r}")
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise LessonsPolicyInvalid("lessons.requirements must be a non-empty mapping")
    severity = requirements.get("severity")
    if severity not in _ADVISORY_SEVERITIES:
        raise LessonsPolicyInvalid(
            "lessons.requirements.severity must be advisory only: one of "
            + ", ".join(sorted(_ADVISORY_SEVERITIES))
        )
    min_items = requirements.get("central_topic_min_items")
    if min_items is not None and (
        isinstance(min_items, bool) or not isinstance(min_items, int) or min_items < 0
    ):
        raise LessonsPolicyInvalid(
            "lessons.requirements.central_topic_min_items must be a non-negative integer"
        )
    must_address = requirements.get("reviews_must_be_addressed")
    if must_address is not None and not isinstance(must_address, bool):
        raise LessonsPolicyInvalid("lessons.requirements.reviews_must_be_addressed must be a boolean")
