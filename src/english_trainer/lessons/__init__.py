"""Lessons module: the session lifecycle and the brief/report protocol
[PD-2026-09-23] (contract 0.5; control 4.2; roadmap 2.2).

``start_session`` returns the lesson brief (:func:`build_brief`); the tutor
runs the lesson and files one report, checked by :func:`check_report` and
written atomically -- finishing the session -- by :func:`commit_report`.

Sessions are free-form conversations, not school lessons: the lifecycle is
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` with mandatory evidence
persistence at finish; nothing here blocks learning. The plan is composed by
:mod:`english_trainer.control` inside the start transaction and rides the brief
as ADVISORY steps -- the tutor runs the lesson without calling the engine and
reports what happened once. The per-step delivery protocol (``session next``,
``exercise rendered``, ``attempt record``, ...) was removed [PD-2026-09-23];
the events it wrote stay readable by every consumer.
"""

from __future__ import annotations

from english_trainer.lessons.brief import (
    BRIEF_SCHEMA,
    EVENT_LESSON_REPORTED,
    REPORT_SCHEMA,
    brief_hash_of,
    build_brief,
)
from english_trainer.lessons.forms import (
    AUTOMATICITY_STEP_TYPES,
    DRILL_BLOCK,
    RECONSTRUCTION,
    TIMED_WRITING,
    choose_reconstruction_text,
    directive_view,
    frames_for_target,
    generation_schema_version,
    supports_automaticity_forms,
)
from english_trainer.lessons.report import (
    EncounterBuilder,
    EncounterLookup,
    ReportRejected,
    check_report,
    commit_report,
)
from english_trainer.lessons.resume import (
    attach_agent,
    resume_session,
)
from english_trainer.lessons.sessions import (
    ABANDONED,
    EVENT_ABANDONED,
    EVENT_AGENT_ATTACHED,
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
    close_reported_session,
    get_plan,
    get_session,
    start_session,
    uses_report_protocol,
)

__all__ = [
    "ABANDONED",
    "AUTOMATICITY_STEP_TYPES",
    "BRIEF_SCHEMA",
    "DRILL_BLOCK",
    "EVENT_ABANDONED",
    "EVENT_AGENT_ATTACHED",
    "EVENT_COMPOSED",
    "EVENT_FINISHED",
    "EVENT_LESSON_REPORTED",
    "EVENT_SAFETY_REJECTED",
    "EVENT_STARTED",
    "EVENT_STEP_PRESENTED",
    "FINISHED",
    "IN_PROGRESS",
    "RECONSTRUCTION",
    "REPORT_SCHEMA",
    "STARTED",
    "TIMED_WRITING",
    "EncounterBuilder",
    "EncounterLookup",
    "ReportRejected",
    "SessionPrecondition",
    "abandon_session",
    "active_session_id",
    "attach_agent",
    "brief_hash_of",
    "build_brief",
    "check_report",
    "choose_reconstruction_text",
    "close_reported_session",
    "commit_report",
    "directive_view",
    "frames_for_target",
    "generation_schema_version",
    "get_plan",
    "get_session",
    "resume_session",
    "start_session",
    "supports_automaticity_forms",
    "uses_report_protocol",
]
