"""Lessons module: the session lifecycle and (in later 2.2 increments) the
step/attempt protocol (contract 0.5; roadmap 2.2).

Sessions are free-form conversations, not school lessons: the lifecycle is
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` with mandatory evidence
persistence at finish; nothing here blocks learning.
"""

from __future__ import annotations

from english_trainer.lessons.sessions import (
    ABANDONED,
    EVENT_ABANDONED,
    EVENT_FINISHED,
    EVENT_STARTED,
    FINISHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    abandon_session,
    active_session_id,
    finish_session,
    get_session,
    mark_in_progress,
    start_session,
)

__all__ = [
    "ABANDONED",
    "EVENT_ABANDONED",
    "EVENT_FINISHED",
    "EVENT_STARTED",
    "FINISHED",
    "IN_PROGRESS",
    "STARTED",
    "SessionPrecondition",
    "abandon_session",
    "active_session_id",
    "finish_session",
    "get_session",
    "mark_in_progress",
    "start_session",
]
