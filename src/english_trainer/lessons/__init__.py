"""Lessons module: the session lifecycle and the step-delivery protocol
(contract 0.5; control 4.2; roadmap 2.2).

Sessions are free-form conversations, not school lessons: the lifecycle is
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` with mandatory evidence
persistence at finish; nothing here blocks learning. The plan is composed by
:mod:`english_trainer.control` inside the start transaction and delivered step
by step under CAS (``session next`` / ``peek`` / ``replan``).
"""

from __future__ import annotations

from english_trainer.lessons.bank import (
    BankPrecondition,
    accept_exercise,
    bank_items,
    reject_exercise,
    retire_exercise,
)
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
from english_trainer.lessons.resume import (
    EVENT_AGENT_ATTACHED,
    attach_agent,
    resume_session,
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
    "EVENT_AGENT_ATTACHED",
    "EVENT_COMPOSED",
    "EVENT_EXERCISE_RENDERED",
    "EVENT_FINISHED",
    "EVENT_SAFETY_REJECTED",
    "EVENT_STARTED",
    "EVENT_STEP_PRESENTED",
    "FINISHED",
    "IN_PROGRESS",
    "STARTED",
    "BankPrecondition",
    "SessionPrecondition",
    "abandon_session",
    "accept_exercise",
    "active_session_id",
    "attach_agent",
    "bank_items",
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
    "reject_exercise",
    "replan_session",
    "resume_session",
    "retire_exercise",
    "start_session",
]
