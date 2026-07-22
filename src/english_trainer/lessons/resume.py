"""Resuming a session and attaching a tutor to it (lessons 4b, 5; roadmap 2.5).

``attach_agent`` is the single mechanism that records a tutor's connection to
a session -- never a standalone CLI command (lessons 5 [R-3]): a separate
``session attach`` would let an agent declare itself attached to a session
whose briefing it never actually read. ``--provider`` is mandatory on both
``session start`` and ``session resume``; changing tutor mid-stream is a cold
``resume`` with a new provider, not a second attach path.

``resume_session`` is the read side: full session state, a tutor briefing
built from the scoring/evidence folds (never mixed into ``state``, [P0-5]),
and the session's untrusted notes as their own block -- followed by the one
write ``resume`` performs, attaching the resuming agent.
"""

from __future__ import annotations

from typing import Any

from english_trainer.evidence.attempts import list_notes
from english_trainer.evidence.reviews import pending_assignments
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import peek_step
from english_trainer.lessons.sessions import (
    EVENT_AGENT_ATTACHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    get_session,
)
from english_trainer.scoring.aggregates import (
    learning_score,
    measured_working_level,
    working_levels,
    xp_ledger,
)
from english_trainer.scoring.engine import fold_scores

# ``EVENT_AGENT_ATTACHED`` now lives in sessions.py (both start and resume
# attach); it is imported above and stays importable from here for callers
# that use its historical home.

_ACTIVE_STATES = (STARTED, IN_PROGRESS)


def attach_agent(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    provider: str,
    skills: list[dict[str, str]],
    actor: str = "agent",
) -> DomainEvent:
    """Record a tutor's connection to ``session_id`` (lessons 5 [R-3]).

    ``session start`` and ``session resume`` are the only callers -- there is
    no separate ``session attach`` command, precisely because that would let
    an agent declare itself attached to a session whose briefing it never
    read. Runs in its own UnitOfWork, the same shape every other lessons
    lifecycle transition uses (``mark_in_progress``, ``finish_session``): for
    ``resume_session`` this is the ONLY write the operation performs, so it is
    -- in effect -- the same transaction as the operation itself.
    """
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, _ = found
    if state.get("status") not in _ACTIVE_STATES:
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; an agent attaches only to an active session"
        )
    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_AGENT_ATTACHED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "provider": provider,
                        "skills": skills,
                        "attached_at": clock.now().isoformat(),
                    },
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return event


def _build_briefing(
    store: EventStore, registry: PolicyRegistry, session_id: str, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Read-only aggregation for the tutor -- NEVER mixed into ``state``
    (lessons [P0-5]). Honest no-data (``None``) whenever the manifest pinned
    no scoring/curriculum policy yet, never a fabricated zero (scoring 4.10).
    """
    pinned = dict(manifest.get("pinned_versions") or {})
    measured: str | None = None
    score: str | None = None
    levels: dict[str, Any] = {}
    xp = {"total": 0, "practice_days": 0, "streak": 0}
    scoring_version = pinned.get("scoring")
    curriculum_version = pinned.get("curriculum")
    if scoring_version and curriculum_version:
        scoring_policy = registry.resolve_pinned("scoring", scoring_version)
        program = registry.resolve_pinned("curriculum", curriculum_version)
        scores = fold_scores(store, scoring_policy)
        levels = working_levels(scores, program, scoring_policy)
        measured = measured_working_level(levels)
        score = learning_score(scores, program, scoring_policy, measured)
        full_ledger = xp_ledger(store, scoring_policy)
        xp = {
            "total": full_ledger["total"],
            "practice_days": full_ledger["practice_days"],
            "streak": full_ledger["streak"],
        }
    next_step: dict[str, Any] | None = None
    try:
        next_step = peek_step(store, session_id).get("step")
    except SessionPrecondition:
        next_step = None
    return {
        "measured_working_level": measured,
        "learning_score": score,
        "skills": levels,
        "xp": xp,
        "pending_reviews": len(pending_assignments(store, session_id)),
        "next_step": next_step,
    }


def resume_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    provider: str,
    actor: str = "agent",
) -> dict[str, Any]:
    """Full session state + a tutor briefing + notes, attaching ``provider``.

    Terminal sessions refuse (lessons 2: ``resume`` on a terminal session is a
    stable error, not a way to peek at history). The briefing and notes ride
    as SEPARATE blocks from ``state`` -- never mixed in (lessons [P0-5]).
    """
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, _ = found
    if state.get("status") not in _ACTIVE_STATES:
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; resume works only on an active session "
            "(terminal sessions are final -- lessons 2)"
        )
    manifest = dict(state.get("manifest") or {})
    required_skills = list(manifest.get("required_skills") or [])

    event = attach_agent(
        store,
        clock,
        random_source,
        session_id,
        provider=provider,
        skills=required_skills,
        actor=actor,
    )

    briefing = _build_briefing(store, registry, session_id, manifest)
    notes = list_notes(store, session_id)
    return {
        "session_id": session_id,
        "status": state.get("status"),
        "manifest": manifest,
        "agent_attached_event_id": event.id,
        "briefing": briefing,
        "notes": notes,
    }
