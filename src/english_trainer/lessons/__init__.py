"""Lessons module: the session lifecycle and the step-delivery protocol
(contract 0.5; control 4.2; roadmap 2.2).

Sessions are free-form conversations, not school lessons: the lifecycle is
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` with mandatory evidence
persistence at finish; nothing here blocks learning. The plan is composed by
:mod:`english_trainer.control` inside the start transaction and delivered step
by step under CAS (``session next`` / ``peek`` / ``replan``).
"""

from __future__ import annotations

from english_trainer.lessons.delivery import (
    next_step,
    peek_step,
    production_eligible,
    replan_session,
)
from english_trainer.lessons.rendering import (
    EVENT_EXERCISE_RENDERED,
    find_presented_step,
    find_rendered_exercise,
    record_rendered_exercise,
)
from english_trainer.lessons.sessions import (
    ABANDONED,
    EVENT_ABANDONED,
    EVENT_COMPOSED,
    EVENT_FINISHED,
    EVENT_SAFETY_REJECTED,
    EVENT_STARTED,
    EVENT_STEP_PRESENTED,
    FINISHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    abandon_session,
    active_session_id,
    finish_session,
    get_plan,
    get_session,
    mark_in_progress,
    start_session,
)

__all__ = [
    "ABANDONED",
    "EVENT_ABANDONED",
    "EVENT_COMPOSED",
    "EVENT_EXERCISE_RENDERED",
    "EVENT_FINISHED",
    "EVENT_SAFETY_REJECTED",
    "EVENT_STARTED",
    "EVENT_STEP_PRESENTED",
    "FINISHED",
    "IN_PROGRESS",
    "STARTED",
    "SessionPrecondition",
    "abandon_session",
    "active_session_id",
    "find_presented_step",
    "find_rendered_exercise",
    "finish_session",
    "get_plan",
    "get_session",
    "mark_in_progress",
    "next_step",
    "peek_step",
    "production_eligible",
    "record_rendered_exercise",
    "replan_session",
    "start_session",
]
