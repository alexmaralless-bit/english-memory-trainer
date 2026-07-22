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

from datetime import datetime
from typing import Any

from english_trainer.evidence.attempts import EVENT_ATTEMPT_RECORDED, list_notes
from english_trainer.evidence.reviews import pending_assignments
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import peek_step
from english_trainer.lessons.sessions import (
    EVENT_AGENT_ATTACHED,
    EVENT_FINISHED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    get_plan,
    get_session,
)
from english_trainer.scheduler.engine import due_backlog
from english_trainer.scoring.aggregates import (
    learning_score,
    measured_working_level,
    working_levels,
    xp_ledger,
)
from english_trainer.scoring.engine import (
    ACTIVE,
    AT_RISK,
    EVIDENCE_ADDED_EVENT,
    MASTERED,
    REVIEW_OUTCOME_EVENT,
    TargetState,
    fold_scores,
)

# ``EVENT_AGENT_ATTACHED`` now lives in sessions.py (both start and resume
# attach); it is imported above and stays importable from here for callers
# that use its historical home.

_ACTIVE_STATES = (STARTED, IN_PROGRESS)

# Topics the learner has activated: ACTIVE state or beyond, plus AT_RISK -- a
# formerly-steady topic now decaying -- so the tutor sees the whole activated
# repertoire and which parts of it are slipping, not a silently dropped one.
_ACTIVE_PLUS = (ACTIVE, MASTERED, AT_RISK)

# Lexicon ``type``s that are multi-word chunks rather than single words. Mirrors
# ``curriculum.validate.MULTIWORD_TYPES``; duplicated here on purpose -- the
# lessons layer must not import curriculum (tests/architecture allowlist).
_MULTIWORD_TYPES = frozenset({"chunk", "idiom", "phrasal-verb", "informal_chunk"})

# Events that count as learner activity when measuring the re-entry gap.
_ACTIVITY_EVENTS = (EVENT_ATTEMPT_RECORDED, EVIDENCE_ADDED_EVENT, REVIEW_OUTCOME_EVENT)

# How many recent lexical items each briefing bucket carries.
_RECENT_LIMIT = 10


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


def _active_topics(scores: dict[str, TargetState], program: dict[str, Any]) -> list[dict[str, Any]]:
    """ACTIVE+ topics (incl. AT_RISK) with their state, in curriculum order."""
    out: list[dict[str, Any]] = []
    for topic in program.get("topics", []):
        topic_id = str(topic.get("id"))
        state = scores.get(topic_id)
        if state is None or state.knowledge_state not in _ACTIVE_PLUS:
            continue
        out.append(
            {
                "target_ref": topic_id,
                "knowledge_state": state.knowledge_state,
                "cefr": topic.get("cefr"),
                "evidence_count": state.evidence_count,
            }
        )
    return out


def _recent_lexicon(
    store: EventStore, program: dict[str, Any], scores: dict[str, TargetState]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Most-recently practised vocabulary and chunks, split by lexicon ``type``.

    A pure fold over ``EVIDENCE_ADDED``: a lexical unit becomes "recent" once an
    attempt scores against it (the lexicon-first micro lane makes a unit a
    ``target_ref``). Both buckets stay honestly empty until such evidence
    exists -- an empty list, never an invented item.
    """
    units = {str(unit.get("id")): unit for unit in program.get("lexicon", [])}
    last_seen: dict[str, int] = {}
    for index, event in enumerate(store.read()):
        if event.type != EVIDENCE_ADDED_EVENT:
            continue
        ref = str((event.payload.get("primary_target") or {}).get("target_ref") or "")
        if ref in units:
            last_seen[ref] = index
    vocabulary: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for ref in sorted(last_seen, key=lambda r: last_seen[r], reverse=True):
        unit = units[ref]
        state = scores.get(ref)
        entry = {
            "target_ref": ref,
            "title": unit.get("title"),
            "knowledge_state": state.knowledge_state if state is not None else "NEW",
            "evidence_count": state.evidence_count if state is not None else 0,
        }
        if str(unit.get("type", "word")) in _MULTIWORD_TYPES:
            chunks.append(entry)
        else:
            vocabulary.append(entry)
    return vocabulary[:_RECENT_LIMIT], chunks[:_RECENT_LIMIT]


def _last_activity_at(store: EventStore) -> datetime | None:
    """The most recent learner-activity event timestamp, or ``None`` if none."""
    latest: datetime | None = None
    for event in store.read():
        if event.type in _ACTIVITY_EVENTS and (latest is None or event.occurred_at > latest):
            latest = event.occurred_at
    return latest


def _re_entry(
    store: EventStore, now: datetime, at_risk_targets: list[str], backlog: list[dict[str, Any]]
) -> dict[str, Any]:
    """The break + dropped-Retrievability picture (continuation "re-entry").

    ``now`` is the injected clock, never wall-clock. ``lowest_retrievability`` is
    ``None`` when nothing is due -- honest no-data, never a fabricated ``0``.
    """
    last_activity = _last_activity_at(store)
    gap_days = (now - last_activity).days if last_activity is not None else None
    return {
        "last_activity_at": last_activity.isoformat() if last_activity is not None else None,
        "gap_days": gap_days,
        "at_risk_targets": list(at_risk_targets),
        "due_review_count": len(backlog),
        # ``due_backlog`` is sorted by Retrievability ascending, so the head is
        # the most decayed due review.
        "lowest_retrievability": backlog[0]["retrievability"] if backlog else None,
    }


def _plan_focus_targets(store: EventStore, session_id: str) -> list[str]:
    """Distinct still-unpresented target refs of the session plan, in order."""
    try:
        _, plan_state, _ = get_plan(store, session_id)
    except KernelError:
        return []
    ordered: list[str] = []
    for step in sorted(plan_state.get("steps", []), key=lambda s: int(s.get("order_index", 0))):
        if step.get("presented_at") is not None:
            continue
        ref = step.get("target_ref")
        if ref and str(ref) not in ordered:
            ordered.append(str(ref))
    return ordered


def _recommendations(store: EventStore, session_id: str, backlog: list[dict[str, Any]]) -> dict[str, Any]:
    """What to do next: due reviews to repeat + this plan's focus targets to learn."""
    due_reviews = [
        {
            "target_ref": item["target_ref"],
            "dimension": item["dimension"],
            "status": item["status"],
            "retrievability": item["retrievability"],
            "knowledge_state": item["knowledge_state"],
        }
        for item in backlog
    ]
    return {"due_reviews": due_reviews, "focus_targets": _plan_focus_targets(store, session_id)}


def _last_session_summary(store: EventStore) -> dict[str, Any] | None:
    """Computed itog of the last FINISHED session -- state only, never notes.

    Honest ``None`` until a session has finished. Session notes stay in their own
    untrusted block (lessons [P0-5]); this summary is a pure fold over the
    session's own lifecycle/evidence events.
    """
    events = list(store.read())
    finished = [event for event in events if event.type == EVENT_FINISHED]
    if not finished:
        return None
    last = finished[-1]
    session_id = last.correlation_id
    attempts = correct = evidence = 0
    outcomes: dict[str, int] = {}
    targets: set[str] = set()
    for event in events:
        if event.correlation_id != session_id:
            continue
        if event.type == EVENT_ATTEMPT_RECORDED:
            attempts += 1
            if (event.payload.get("assessment") or {}).get("correct"):
                correct += 1
        elif event.type == EVIDENCE_ADDED_EVENT:
            evidence += 1
            ref = str((event.payload.get("primary_target") or {}).get("target_ref") or "")
            if ref:
                targets.add(ref)
        elif event.type == REVIEW_OUTCOME_EVENT:
            outcome = str(event.payload.get("outcome") or "")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "session_id": session_id,
        "finished_at": last.occurred_at.isoformat(),
        "attempts": attempts,
        "correct_attempts": correct,
        "evidence_count": evidence,
        "review_outcomes": dict(sorted(outcomes.items())),
        "targets_practiced": sorted(targets),
    }


def build_briefing(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    session_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """The shared tutor briefing -- a pure function of engine state, NEVER of the
    untrusted notes (lessons [P0-5]; continuation §2 trust boundary).

    ``start`` and ``resume`` call this ONE builder, so both return the same
    briefing shape and an agent needs a single CLI call to run the session
    correctly (continuation "Правила": ``resume`` и ``start`` возвращают tutor
    briefing -- агенту достаточно одного вызова CLI).

    Every one of the seven contract sections is populated from an available fold
    or an HONEST no-data value (``None``/empty), never a fabricated zero
    (scoring 4.10; CLAUDE.md -- honest no-data is a legitimate result):

    - ``active_topics`` / ``recent_vocabulary`` / ``recent_chunks`` -- the scoring
      fold (ACTIVE+ topics; recent lexical targets split by ``type``);
    - ``re_entry`` -- the scheduler gap + the due-backlog Retrievability drop;
    - ``recommendations`` -- due backlog (repeat) + the plan's focus targets;
    - ``last_session_summary`` -- a fold over the last FINISHED session's events;
    - ``top_errors`` -- honestly EMPTY: ``ERROR_OBSERVED`` is a later evidence
      increment, so there are no error observations to rank yet -- the section is
      present but empty, never fabricated.

    Future work: this aggregation ideally belongs to a dedicated ``learner``
    module (continuation "Выведенные контракты"); it lives in the lessons facade
    for now because no ``learner`` module exists yet.
    """
    pinned = dict(manifest.get("pinned_versions") or {})
    scoring_version = pinned.get("scoring")
    curriculum_version = pinned.get("curriculum")
    scheduler_version = pinned.get("scheduler")

    measured: str | None = None
    score: str | None = None
    levels: dict[str, Any] = {}
    xp = {"total": 0, "practice_days": 0, "streak": 0}
    active_topics: list[dict[str, Any]] = []
    recent_vocabulary: list[dict[str, Any]] = []
    recent_chunks: list[dict[str, Any]] = []
    at_risk_targets: list[str] = []

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
        active_topics = _active_topics(scores, program)
        recent_vocabulary, recent_chunks = _recent_lexicon(store, program, scores)
        at_risk_targets = sorted(ref for ref, state in scores.items() if state.knowledge_state == AT_RISK)

    backlog: list[dict[str, Any]] = []
    if scheduler_version and scoring_version and curriculum_version:
        # Same due backlog control composes from (continuation "recommendations"
        # / "re-entry"); empty until the scheduler and scoring policies are pinned.
        backlog = due_backlog(
            store,
            registry.resolve_pinned("scheduler", scheduler_version),
            registry.resolve_pinned("scoring", scoring_version),
            registry.resolve_pinned("curriculum", curriculum_version),
            clock.now(),
        )

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
        "active_topics": active_topics,
        # ``ERROR_OBSERVED`` is not emitted yet (observed-record is a later
        # evidence increment), so there is nothing to rank: honestly empty, never
        # a fabricated error.
        "top_errors": [],
        "recent_vocabulary": recent_vocabulary,
        "recent_chunks": recent_chunks,
        "re_entry": _re_entry(store, clock.now(), at_risk_targets, backlog),
        "recommendations": _recommendations(store, session_id, backlog),
        "last_session_summary": _last_session_summary(store),
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

    briefing = build_briefing(store, registry, clock, session_id, manifest)
    notes = list_notes(store, session_id)
    return {
        "session_id": session_id,
        "status": state.get("status"),
        "manifest": manifest,
        "agent_attached_event_id": event.id,
        "briefing": briefing,
        "notes": notes,
    }
