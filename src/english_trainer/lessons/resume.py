"""Resuming a session and attaching a tutor to it (lessons 4b, 5; roadmap 2.5).

``attach_agent`` is the single mechanism that records a tutor's connection to
a session -- never a standalone CLI command (lessons 5 [R-3]): a separate
``session attach`` would let an agent declare itself attached to a session
whose brief it never actually read. ``--provider`` is mandatory on both
``session start`` and ``session resume``; changing tutor mid-stream is a cold
``resume`` with a new provider, not a second attach path.

``resume_session`` is the read side: the session state and the rebuilt lesson
``brief`` (``lessons.brief``; the same brief and ``brief_hash`` the start
returned while no learner fact landed in between) -- followed by the one write
``resume`` performs, attaching the resuming agent. The legacy step-protocol
``briefing`` (with its ``next_step`` peek) and the untrusted per-attempt notes
went away with that protocol [PD-2026-09-23]; the brief carries everything a
resuming tutor needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from english_trainer.adapters.errors import SkillUnavailable
from english_trainer.adapters.skills import resolve as resolve_skill
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.brief import (
    LEARNER_LEXICON_ENTRY_ADDED,
    LEARNER_PREFERENCES_UPDATED,
    build_brief,
)
from english_trainer.lessons.sessions import (
    EVENT_AGENT_ATTACHED,
    IN_PROGRESS,
    STARTED,
    PermanentInterleave,
    SessionPrecondition,
    get_plan,
    get_session,
    sweep_stale_session,
)

# ``EVENT_AGENT_ATTACHED`` now lives in sessions.py (both start and resume
# attach); it is imported above and stays importable from here for callers
# that use its historical home.

_ACTIVE_STATES = (STARTED, IN_PROGRESS)

# Re-exported from their new home (lessons.brief) for historical importers.
__all__ = [
    "EVENT_AGENT_ATTACHED",
    "LEARNER_LEXICON_ENTRY_ADDED",
    "LEARNER_PREFERENCES_UPDATED",
    "attach_agent",
    "resume_session",
]


def attach_agent(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    provider: str,
    skills: list[dict[str, Any]],
    expected_session_revision: int,
    actor: str = "agent",
) -> tuple[DomainEvent, int]:
    """Record a tutor's connection to ``session_id`` (lessons 5 [R-3]).

    ``session start`` and ``session resume`` are the only callers -- there is
    no separate ``session attach`` command, precisely because that would let
    an agent declare itself attached to a session whose briefing it never
    read. Runs in its own UnitOfWork, the same shape every other lessons
    lifecycle transition uses (``abandon_session``): for
    ``resume_session`` this is the ONLY write the operation performs, so it is
    -- in effect -- the same transaction as the operation itself.
    """
    state, session_revision = load_session_for_update(store, session_id, expected_session_revision)
    if state.get("status") not in _ACTIVE_STATES:
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; an agent attaches only to an active session"
        )
    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        new_session_revision = bump_session(uow, session_id, state, session_revision, clock.now())
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
    return event, new_session_revision


def resume_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    provider: str,
    actor: str = "agent",
    agent_skills_dir: Path | str | None = None,
    permanent_interleave: PermanentInterleave | None = None,
) -> dict[str, Any]:
    """Session state + the rebuilt lesson brief, attaching ``provider``.

    Terminal sessions refuse (lessons 2: ``resume`` on a terminal session is a
    stable error, not a way to peek at history). The brief rides as its own
    block, computed from engine state -- never mixed into ``state`` (lessons
    [P0-5]).
    """
    sweep_stale_session(store, registry, clock, random_source, actor=actor)
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, session_revision = found
    if state.get("status") not in _ACTIVE_STATES:
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; resume works only on an active session "
            "(terminal sessions are final -- lessons 2)"
        )
    manifest = dict(state.get("manifest") or {})
    required_skills = list(manifest.get("required_skills") or [])
    if agent_skills_dir is not None:
        for required in required_skills:
            try:
                resolve_skill(
                    str(required["skill_name"]),
                    str(required["version"]),
                    agent_skills_dir,
                    content_hash=str(required["content_hash"]),
                )
            except SkillUnavailable as exc:
                raise SessionPrecondition(
                    "pinned tutor skill snapshot is unavailable: "
                    f"{required.get('skill_name')}@{required.get('version')} "
                    f"({required.get('content_hash')}); run `trainer skills sync`"
                ) from exc

    event, new_session_revision = attach_agent(
        store,
        clock,
        random_source,
        session_id,
        provider=provider,
        skills=required_skills,
        expected_session_revision=session_revision,
        actor=actor,
    )

    # The lesson brief (brief/report protocol [PD-2026-09-23]): rebuilt from
    # state, evaluated at the session's own start instant, so a resumed tutor
    # receives the same brief -- and brief_hash -- the starting one did.
    brief = build_brief(store, registry, session_id, permanent_interleave=permanent_interleave)
    _, plan_state, _ = get_plan(store, session_id)
    return {
        "session_id": session_id,
        "session_revision": new_session_revision,
        "status": state.get("status"),
        "manifest": manifest,
        "lesson_arc": plan_state.get("lesson_arc") or manifest.get("lesson_arc"),
        "agent_attached_event_id": event.id,
        "brief": brief,
    }
