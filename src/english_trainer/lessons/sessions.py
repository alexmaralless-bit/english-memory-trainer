"""Session lifecycle over kernel CAS aggregates (lessons contract 0.5; roadmap 2.2).

A session is a revisioned operational aggregate with the contract lifecycle
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` (the direct jump
``STARTED → ABANDONED`` is allowed; ``STARTED → FINISHED`` is not -- a session
that recorded nothing is abandoned, never "finished"). At most one session is
active at a time; the singleton pointer aggregate enforces that under
compare-and-set, so two concurrent starts cannot both win.

The brief/report protocol [PD-2026-09-23] closes a session with ONE
committed lesson report (``lessons.report.commit_report``): inside that single
transaction the session moves ``STARTED → IN_PROGRESS`` (the reported work)
and then ``IN_PROGRESS → FINISHED`` (:func:`close_reported_session`), so the
lifecycle still has no direct ``STARTED → FINISHED`` edge.

``start`` writes the immutable Session Manifest: provider, mode, and the
**pinned versions** of every policy kind registered at that moment -- replay
and resume resolve those exact versions, never the later active ones
(foundation 3.6). Composition happens *inside the start UnitOfWork* (control
4.2): ``compose_plan`` builds the ``SessionPlan`` with ``composition_revision
= 1`` and ``plan_version = 1``, the plan is saved as its own revisioned
aggregate (the live plan/ledger is never embedded in the immutable manifest),
and ``SESSION_COMPOSED`` rides the same transactional outbox as
``SESSION_STARTED``.

Everything commits through one UnitOfWork per command: the session aggregate,
the plan, the active-session pointer and the lifecycle events move together or
not at all.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from english_trainer.adapters.errors import SkillUnavailable
from english_trainer.adapters.events import SKILL_REQUIRED
from english_trainer.adapters.skills import resolve as resolve_skill
from english_trainer.control.availability import availability_get, resolve_total_seconds
from english_trainer.control.compose import compose_plan
from english_trainer.control.deferral import qualified_candidates, reduce_deferrals
from english_trainer.control.lesson_profiles import build_lesson_arc, build_lesson_proposal
from english_trainer.control.policy import CONTROL_KIND, require_valid
from english_trainer.control.saturation import recurring_error_keys, reduce_saturation
from english_trainer.control.signals import (
    EVENT_PROBE_REQUESTED,
    EVENT_SIGNAL_CONSUMED,
    active_signals,
    build_probe_candidate,
)
from english_trainer.control.trace import save_decision_traces
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError, NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.forms import generation_schema_version

# The default required skill (adapters 2), wired in only when the caller
# names an `agent_skills_dir` AND that skill actually resolves there -- a
# caller that passes neither (every pre-existing caller and test) keeps
# `required_skills: []` (see `_resolve_required_skills`).
_DEFAULT_REQUIRED_SKILL: tuple[str, str] = ("run-english-session", "1")
# Legacy pedagogy-v2 default (generation@2 pinned, but not the brief/report
# protocol -- see `_REPORT_REQUIRED_SKILL` below). Kept exactly as before:
# `run-english-session@2` is not archived under agent-skills/run-english-
# session/versions, so a caller relying on this default (with no explicit
# `required_skills`) resolves `[]`, same as always -- this constant is not
# the bug fixed here, only the third default (below) is [PD-2026-09-23].
_PEDAGOGY_REQUIRED_SKILL: tuple[str, str] = ("run-english-session", "2")
# The brief/report protocol's default (`uses_report_protocol`): the current
# canonical `run-english-session` version (its SKILL.md frontmatter), so
# `--agent-skills agent-skills` with no explicit `--required-skill` actually
# pins something instead of silently resolving `[]` -- the stale-skill bug
# this constant replaces pinned `@2`, which is neither current nor archived.
# Bump this alongside the skill's own version bump.
_REPORT_REQUIRED_SKILL: tuple[str, str] = ("run-english-session", "10")

SESSION_AGGREGATE = "session"
PLAN_AGGREGATE = "session_plan"
POINTER_AGGREGATE = "session_pointer"
POINTER_ID = "active"

# Consumed from the learner module via the event log (events are the module
# boundary; lessons must not import learner -- tests/architecture allowlist).
# Literal on purpose, mirroring how evidence/scoring consume published events.
LEARNER_LEXICON_ENTRY_ADDED = "learner.lexicon_entry_added"
LEARNER_PREFERENCES_UPDATED = "learner.preferences_updated"

# Mirrors learner.preferences.DEFAULT_PREFERENCES's round_size/timed_limit_
# seconds (learner 4a) -- duplicated on purpose, exactly like the lexicon
# constant above; lessons must not import learner. Control reads only these
# two fields at composition time and keeps no copy of its own.
_DEFAULT_LEARNER_PREFERENCES: dict[str, int] = {"round_size": 6, "timed_limit_seconds": 240}

#: Injected classifier for the permanent interleaved tier (scheduler 3a,
#: [PD-2026-09-22] PD-F). ``lessons`` must not import ``curriculum`` (layer
#: allowlist), yet every scheduler call site here resolves a curriculum
#: snapshot of its own -- so the EDGE passes
#: ``curriculum.service.permanent_interleave_targets`` itself and the call site
#: applies it to the snapshot it pinned. ``None`` -- the default every existing
#: caller uses -- means an empty set, i.e. exactly today's behaviour.
PermanentInterleave = Callable[[Mapping[str, Any]], frozenset[str]]


EVENT_STARTED = "session.started"
EVENT_FINISHED = "session.finished"
EVENT_ABANDONED = "session.abandoned"
EVENT_STALE_ABANDONED = "session.stale_abandoned"
EVENT_COMPOSED = "session.composed"
EVENT_STEP_PRESENTED = "session.step_presented"
# Written by the removed step-delivery protocol; historic logs carry it and
# audit/metrics folds still read it.
EVENT_SAFETY_REJECTED = "session.step_safety_rejected"
# Owned by lessons (lessons 5): both `session start` and `session resume`
# attach the tutor in the same UoW as the operation. Defined here so both call
# sites (start below, resume via import) share one source of truth.
EVENT_AGENT_ATTACHED = "session.agent_attached"

STARTED = "STARTED"
IN_PROGRESS = "IN_PROGRESS"
FINISHED = "FINISHED"
ABANDONED = "ABANDONED"
_ACTIVE_STATES = (STARTED, IN_PROGRESS)


class SessionPrecondition(KernelError):
    """The action is not allowed in the current state -- do something else.

    Maps to the CLI's PRECONDITION_FAILED (exit 6), distinct from CONFLICT:
    retrying the same call will not help.
    """

    code = "SESSION_PRECONDITION"


def _pin_versions(registry: PolicyRegistry) -> dict[str, str]:
    """Pin the active version of every policy kind that has one right now."""
    pinned: dict[str, str] = {}
    for kind in sorted(KNOWN_KINDS):
        try:
            pinned[kind] = registry.active_version(kind)
        except NoActivePolicy:
            continue
    return pinned


def lessons_schema_version(pinned: Mapping[str, Any]) -> int:
    """The integer after ``@`` of the pinned lessons policy, or 0."""
    _, _, suffix = str(pinned.get("lessons") or "").partition("@")
    try:
        return int(suffix)
    except ValueError:
        return 0


def uses_report_protocol(pinned: Mapping[str, Any]) -> bool:
    """Whether a session runs the brief/report protocol [PD-2026-09-23].

    Decided by the session's own pins: lessons@2 (brief/report schemas) with
    evidence@2 (the verdict scale). Such a session is closed by ONE
    ``lesson_report@1`` (``lessons.report.commit_report``), never step by step.
    """
    _, _, evidence = str(pinned.get("evidence") or "").partition("@")
    return lessons_schema_version(pinned) >= 2 and evidence.isdigit() and int(evidence) >= 2


def _session_pins(registry: PolicyRegistry) -> dict[str, str]:
    """The pins of a NEW lesson session.

    Every active policy kind, except that a brief/report session does not pin
    ``rubric``: its correctness is the tutor's verdict (evidence@2), and no
    step of it is rubric-assessed. Placement pins its own set, rubric included
    (``assessments.placement``), and a legacy session keeps pinning it.
    """
    pinned = _pin_versions(registry)
    if uses_report_protocol(pinned):
        pinned.pop("rubric", None)
    return pinned


def active_session_id(store: EventStore) -> str | None:
    from english_trainer.kernel.aggregates import read_aggregate

    row = read_aggregate(store._conn, POINTER_AGGREGATE, POINTER_ID)
    if row is None:
        return None
    state, _ = row
    value = state.get("session_id")
    return str(value) if value else None


def get_session(store: EventStore, session_id: str) -> tuple[dict[str, Any], int] | None:
    from english_trainer.kernel.aggregates import read_aggregate

    return read_aggregate(store._conn, SESSION_AGGREGATE, session_id)


def get_plan(store: EventStore, session_id: str) -> tuple[str, dict[str, Any], int]:
    """Return ``(session_plan_id, plan_state, revision)`` for a session."""
    from english_trainer.kernel.aggregates import read_aggregate

    found = get_session(store, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    plan_id = str((found[0].get("manifest") or {}).get("session_plan_id"))
    plan = read_aggregate(store._conn, PLAN_AGGREGATE, plan_id)
    if plan is None:
        raise KernelError(f"session {session_id} has no plan aggregate {plan_id}")
    state, revision = plan
    return plan_id, state, revision


def sweep_stale_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    actor: str = "engine",
) -> DomainEvent | None:
    """Abandon the one active session at its deterministic stale boundary.

    The session's pinned ``lessons`` policy supplies the threshold. Legacy
    sessions without that pin use the accepted v1 default of seven elapsed
    days. Repeated sweeps are no-ops because terminalization clears the active
    pointer in the same transaction.
    """
    session_id = active_session_id(store)
    if session_id is None:
        return None
    found = get_session(store, session_id)
    if found is None:
        raise KernelError(f"active-session pointer names missing session {session_id}")
    state, revision = found
    if state.get("status") not in _ACTIVE_STATES:
        return None
    manifest = dict(state.get("manifest") or {})
    pinned = dict(manifest.get("pinned_versions") or {})
    threshold_days = 7
    lessons_version = pinned.get("lessons")
    if lessons_version is not None:
        policy = registry.resolve_pinned("lessons", lessons_version)
        threshold_days = int(policy["stale_session_days"])
    last_activity = datetime.fromisoformat(str(state.get("last_activity_at") or manifest.get("started_at")))
    boundary_at = last_activity + timedelta(days=threshold_days)
    if clock.now() < boundary_at:
        return None

    from english_trainer.evidence.attempts import close_pending_attempts
    from english_trainer.evidence.reviews import close_pending_assignments

    with UnitOfWork(store, clock) as uow:
        closed_attempts = close_pending_attempts(
            store, uow, clock, random_source, session_id, reason="stale", actor=actor
        )
        closed_assignments = close_pending_assignments(
            store, uow, clock, random_source, session_id, reason="stale", actor=actor
        )
        new_revision = bump_session(
            uow,
            session_id,
            state,
            revision,
            boundary_at,
            changes={"status": ABANDONED, "closed_at": boundary_at.isoformat()},
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("session_id") == session_id:
            uow.save_aggregate(
                POINTER_AGGREGATE,
                POINTER_ID,
                {"session_id": None},
                expected_revision=pointer[1],
            )
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_STALE_ABANDONED,
                    occurred_at=boundary_at,
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "from_status": state.get("status"),
                        "boundary_at": boundary_at.isoformat(),
                        "stale_session_days": threshold_days,
                        "closed_attempts": closed_attempts,
                        "closed_assignments": closed_assignments,
                        "session_revision": new_revision,
                    },
                    pinned_versions=pinned,
                )
            ]
        )
    return event


def review_candidates_for(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
    program: dict[str, Any],
    control_policy: dict[str, Any],
    clock: Clock,
    *,
    saturation: dict[tuple[str, str], Any] | None = None,
    recurring_errors: frozenset[tuple[str, str]] | None = None,
    deferrals: dict[tuple[str, str], Any] | None = None,
    permanent_interleave: PermanentInterleave | None = None,
) -> list[dict[str, Any]]:
    """Classified due/overdue review candidates for composition (control 4.4
    step 1: due backlog from the scheduler, classified per 4.5). Empty when
    the scheduler or scoring policy is not registered yet -- the review bucket
    then stays honestly empty."""
    if "scheduler" not in pinned or "scoring" not in pinned:
        return []
    from english_trainer.control.classify import classify_review_candidates
    from english_trainer.scheduler.engine import due_backlog

    backlog = due_backlog(
        store,
        registry.resolve_pinned("scheduler", pinned["scheduler"]),
        registry.resolve_pinned("scoring", pinned["scoring"]),
        program,
        clock.now(),
        # Each event under its OWN pinned scheduler version (scheduler 3a);
        # the article tier is classified from the session's pinned snapshot.
        registry=registry,
        permanent_interleave_targets=(
            permanent_interleave(program) if permanent_interleave is not None else None
        ),
    )
    return classify_review_candidates(
        backlog,
        program,
        control_policy,
        saturation=saturation,
        recurring_errors=recurring_errors,
        deferrals=deferrals,
        now=clock.now(),
    )


def save_new_review_assignments(uow: Any, plan_state: dict[str, Any], session_id: str, now_iso: str) -> None:
    """Create the pending ReviewAssignment aggregate for every review step of
    the plan that does not have one yet (start and replan UoWs)."""
    from english_trainer.evidence.reviews import REVIEW_AGGREGATE

    for step in plan_state["steps"]:
        if step.get("kind") != "review":
            continue
        review_id = str(step["review_assignment_id"])
        if uow.get_aggregate(REVIEW_AGGREGATE, review_id) is not None:
            continue
        uow.save_aggregate(
            REVIEW_AGGREGATE,
            review_id,
            {
                "review_id": review_id,
                "session_id": session_id,
                "step_id": step["step_id"],
                "target_ref": step["target_ref"],
                "dimension": step["dimension"],
                "urgency_class": step.get("urgency_class"),
                "criteria_ref": step.get("criteria_ref"),
                "schedule_epoch": step.get("schedule_epoch"),
                "status": "pending",
                "created_at": now_iso,
            },
            expected_revision=0,
        )


def presented_targets(store: EventStore) -> frozenset[str]:
    """Every target that has EVER had a ``STEP_PRESENTED`` (control 4.3):
    ``is_first_exposure`` is defined by the fact of delivery, not by knowledge
    state -- presentation is not evidence, so a shown target can stay NEW."""
    seen: set[str] = set()
    for event in store.read():
        if event.type != EVENT_STEP_PRESENTED:
            continue
        for target in event.payload.get("targets", []):
            ref = target.get("target_ref")
            if ref:
                seen.add(str(ref))
    return frozenset(seen)


def live_composition_inputs(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
    program: dict[str, Any],
    policy: dict[str, Any],
    clock: Clock,
    *,
    starting_new_session: bool,
    permanent_interleave: PermanentInterleave | None = None,
) -> dict[str, Any]:
    """Fold every live control input from the authoritative event stream.

    All helpers are pure/read-only. The caller later saves the resulting plan,
    traces, assignments and any one-shot signal consumption in one lessons UoW.
    """
    events = list(store.read())
    session_seq = sum(1 for event in events if event.type == EVENT_STARTED)
    if starting_new_session:
        session_seq += 1
    signals = active_signals(store, session_seq, clock.now())
    saturation = reduce_saturation(events, policy)
    recurring = recurring_error_keys(events, policy)
    deferrals = reduce_deferrals(events, policy)
    review_candidates = review_candidates_for(
        store,
        registry,
        pinned,
        program,
        policy,
        clock,
        saturation=saturation,
        recurring_errors=recurring,
        deferrals=deferrals,
        permanent_interleave=permanent_interleave,
    )

    requests: dict[str, tuple[int, dict[str, Any]]] = {}
    for event in events:
        if event.type != EVENT_PROBE_REQUESTED:
            continue
        signal_id = str(event.payload.get("signal_id") or "")
        requests[signal_id] = (int(event.sequence or 0), dict(event.payload))
    probe: dict[str, Any] | None = None
    for signal in signals:
        if signal.get("kind") != "too_easy":
            continue
        request = requests.get(str(signal["signal_id"]))
        if request is None:
            continue
        payload = request[1]
        probe = build_probe_candidate(
            policy,
            probe_id=str(payload["probe_id"]),
            signal_id=str(payload["signal_id"]),
            target_ref=str(payload["target_ref"]),
            dimension=(str(payload["dimension"]) if payload.get("dimension") is not None else None),
            requested_difficulty=str(payload["requested_difficulty"]),
            avoid_context=(
                str(payload["avoid_context"]) if payload.get("avoid_context") is not None else None
            ),
        )
        break

    # Personal-lexicon relevance (learner 4 -> control 4.5): the linked_item_id
    # of every linked entry raises learner_relevance and may pull a
    # learner-requested LexicalItem into the lexicon-first micro lane. Folded
    # here (lessons must not import learner); unlinked entries contribute
    # nothing, and an encounter never touches scoring.
    seen_lexicon: set[str] = set()
    relevant_targets: set[str] = set()
    for event in events:
        if event.type != LEARNER_LEXICON_ENTRY_ADDED:
            continue
        key = str(event.payload.get("identity_key"))
        if key in seen_lexicon:
            continue
        seen_lexicon.add(key)
        linked_item_id = event.payload.get("linked_item_id")
        if linked_item_id:
            relevant_targets.add(str(linked_item_id))

    # LearnerPreferences (learner 4a): the drill profile reads round_size for
    # its rounds and timed_writing reads timed_limit_seconds for its default
    # limit. The newest LEARNER_PREFERENCES_UPDATED full snapshot wins (folded
    # here -- lessons must not import learner); the documented defaults apply
    # before the first `learner preferences set`.
    learner_preferences = dict(_DEFAULT_LEARNER_PREFERENCES)
    for event in events:
        if event.type != LEARNER_PREFERENCES_UPDATED:
            continue
        learner_preferences = {
            "round_size": event.payload.get("round_size", _DEFAULT_LEARNER_PREFERENCES["round_size"]),
            "timed_limit_seconds": event.payload.get(
                "timed_limit_seconds", _DEFAULT_LEARNER_PREFERENCES["timed_limit_seconds"]
            ),
        }

    return {
        "signals": signals,
        "review_candidates": review_candidates,
        "starvation_candidates": qualified_candidates(review_candidates, deferrals),
        "probe": probe,
        "relevant_targets": frozenset(relevant_targets),
        "learner_preferences": learner_preferences,
    }


def plan_summary(plan_state: dict[str, Any]) -> list[dict[str, Any]]:
    """The compact step list carried by ``SESSION_COMPOSED`` (the directive
    itself is hashed at presentation time, not duplicated into every event)."""
    return [
        {
            "step_id": step["step_id"],
            "kind": step["kind"],
            "bucket": step["bucket"],
            "step_type": step["step_type"],
            "expected_seconds": step["expected_seconds"],
            "order_index": step["order_index"],
            "target_ref": step.get("target_ref"),
            "dimension": step.get("dimension"),
            "lesson_profile": step.get("lesson_profile"),
            "lesson_arc_id": step.get("lesson_arc_id"),
            "arc_phase": step.get("arc_phase"),
            "primary_role": step.get("primary_role"),
            "presented": step["presented_at"] is not None,
        }
        for step in plan_state["steps"]
    ]


def _resolve_required_skills(
    agent_skills_dir: Path | str | None,
    required_skills: Sequence[tuple[str, str]] | None,
    *,
    default_required_skill: tuple[str, str] = _DEFAULT_REQUIRED_SKILL,
) -> list[dict[str, Any]]:
    """Resolve every required skill synchronously, before any session
    aggregate is written (adapters 4.2; lessons 4b [P0-Q1]): an unresolvable
    pin fails ``start`` outright, with no session created.

    Defaults to the canonical ``run-english-session@1`` skill only when
    ``agent_skills_dir`` is given AND that skill actually resolves there.
    Callers that pass neither argument -- every pre-existing caller, and any
    test that does not set up an ``agent-skills/`` directory -- keep
    ``required_skills: []``: the engine never invents a dependency on a
    directory the caller never named.
    """
    if required_skills is not None:
        if agent_skills_dir is None:
            raise SessionPrecondition(
                "required_skills was given without agent_skills_dir: nothing to resolve them against"
            )
        pairs: Sequence[tuple[str, str]] = required_skills
    elif agent_skills_dir is not None and Path(agent_skills_dir).is_dir():
        try:
            resolve_skill(*default_required_skill, agent_skills_dir)
        except SkillUnavailable:
            return []
        pairs = (default_required_skill,)
    else:
        return []

    resolved: list[dict[str, Any]] = []
    for name, version in pairs:
        try:
            skill = resolve_skill(name, version, agent_skills_dir)
        except SkillUnavailable as exc:
            raise SessionPrecondition(
                f"required skill {name}@{version} is unavailable: {exc}; run `trainer skills sync` first"
            ) from exc
        resolved.append(
            {
                "skill_name": skill.name,
                "version": skill.version,
                "content_hash": skill.content_hash,
                "cli_calls": list(skill.cli_calls),
            }
        )
    return resolved


def known_target_refs(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
) -> frozenset[str]:
    """Targets backed by at least one scoring observation.

    ``STEP_PRESENTED`` means "the tutor received a step", not "the learner
    knows this language".  Conversation constraints therefore use scored
    learner state when available and fall back to an empty set honestly.
    """
    if "scoring" not in pinned:
        return frozenset()
    from english_trainer.scoring.engine import fold_scores

    policy = registry.resolve_pinned("scoring", pinned["scoring"])
    scores = fold_scores(store, policy)
    return frozenset(target_ref for target_ref, state in scores.items() if int(state.evidence_count) > 0)


def _propose_session_with_pins(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    *,
    pinned: dict[str, str],
    duration_minutes: int | None = None,
    lesson_profile: str | None = None,
    target_ref: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """Build a preview against one already-resolved active-policy snapshot."""
    for kind in ("curriculum", CONTROL_KIND):
        if kind not in pinned:
            raise SessionPrecondition(
                f"no active {kind} policy version; run `trainer curriculum activate` first"
            )
    if generation_schema_version(pinned) < 2:
        raise SessionPrecondition(
            "lesson proposals require active generation@2; "
            "run `trainer curriculum activate` with the updated policy set first"
        )
    program = registry.resolve_pinned("curriculum", pinned["curriculum"])
    policy = require_valid(registry.resolve_pinned(CONTROL_KIND, pinned[CONTROL_KIND]))
    availability = availability_get(store, policy, clock)
    total_seconds, budget_source = resolve_total_seconds(
        policy,
        duration_minutes=duration_minutes,
        declared=dict(availability["declared"]),
        observed=dict(availability["observed"]),
    )
    presented = presented_targets(store)
    profile = lesson_profile or "program_lesson"
    explicit = lesson_profile is not None or target_ref is not None or bool(theme and theme.strip())
    proposal = build_lesson_proposal(
        program=program,
        duration_minutes=total_seconds // 60,
        profile=profile,
        target_ref=target_ref,
        theme=theme,
        presented_targets=presented,
        known_targets=known_target_refs(store, registry, pinned),
        explicit_request=explicit,
    )
    # Budget provenance is part of the proposal the learner accepts, therefore
    # recompute the final hash after adding it.
    proposal.pop("proposal_hash")
    proposal["budget_source"] = budget_source
    proposal["proposal_hash"] = payload_hash(proposal)
    return proposal


def propose_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    *,
    duration_minutes: int | None = None,
    lesson_profile: str | None = None,
    target_ref: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """Read-only lesson preview used for announcement and informed consent."""
    return _propose_session_with_pins(
        store,
        registry,
        clock,
        pinned=_pin_versions(registry),
        duration_minutes=duration_minutes,
        lesson_profile=lesson_profile,
        target_ref=target_ref,
        theme=theme,
    )


def start_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    provider: str,
    mode: str = "balanced",
    duration_minutes: int | None = None,
    lesson_profile: str | None = None,
    target_ref: str | None = None,
    theme: str | None = None,
    actor: str = "engine",
    agent_skills_dir: Path | str | None = None,
    required_skills: Sequence[tuple[str, str]] | None = None,
    permanent_interleave: PermanentInterleave | None = None,
) -> dict[str, Any]:
    """Open a session, compose its plan, and return the immutable manifest plus
    the lesson ``brief`` (``lesson_brief@1``, :func:`lessons.brief.build_brief`):
    ``{session_id, brief, session_revision, ...manifest}``. The brief is a
    computed view riding the response only -- the persisted manifest stays
    immutable.

    Explicit ``lesson_profile``/``target_ref``/``duration_minutes``/``theme``
    are the learner's consent: no proposal hash is compared [PD-2026-09-23].
    With lessons@2 + evidence@2 active the session runs the brief/report
    protocol and pins no ``rubric``. The plan never reuses exercise-bank items:
    the bank belonged to the removed step-delivery protocol.

    Preconditions: active curriculum, control and generation policies must
    exist (composition is executed by control@1 and every step carries a
    generation directive under the pinned generation policy), and no other
    session may be active -- the contract decomposes "start with abandon" into
    two idempotent commands, so the caller abandons explicitly first
    (foundation 3.4, C-1).

    The budget precedence is ``--duration-minutes`` -> declared profile ->
    observed rhythm -> policy default (control 4.7a).

    ``agent_skills_dir``/``required_skills`` wire the manifest's
    ``required_skills`` (adapters 4.2, lessons 4b [P0-Q1]); see
    :func:`_resolve_required_skills` for the exact defaulting rule.
    """
    sweep_stale_session(store, registry, clock, random_source, actor=actor)
    pinned = _session_pins(registry)
    for kind, hint in (
        ("curriculum", "run `trainer curriculum activate` first"),
        (CONTROL_KIND, "register and activate control@1 (curriculum activate does this)"),
        ("generation", "register and activate generation@1 (curriculum activate does this)"),
    ):
        if kind not in pinned:
            raise SessionPrecondition(f"no active {kind} policy version; {hint}")
    current = active_session_id(store)
    if current is not None:
        raise SessionPrecondition(
            f"session {current} is still active; finish or abandon it first "
            "(start does not implicitly abandon -- contract C-1)"
        )

    program = registry.resolve_pinned("curriculum", pinned["curriculum"])
    policy = require_valid(registry.resolve_pinned(CONTROL_KIND, pinned[CONTROL_KIND]))
    availability = availability_get(store, policy, clock)
    total_seconds, budget_source = resolve_total_seconds(
        policy,
        duration_minutes=duration_minutes,
        declared=dict(availability["declared"]),
        observed=dict(availability["observed"]),
    )

    # "generation@2 or later" (generation@3 keeps the whole pedagogy contract).
    pedagogy_v2 = generation_schema_version(pinned) >= 2
    proposal: dict[str, Any] = {}
    lesson_arc: dict[str, Any] = {}
    if pedagogy_v2:
        proposal = _propose_session_with_pins(
            store,
            registry,
            clock,
            pinned=pinned,
            duration_minutes=duration_minutes,
            lesson_profile=lesson_profile,
            target_ref=target_ref,
            theme=theme,
        )
        # No proposal-hash comparison any more [PD-2026-09-23]: the explicit
        # profile/topic/duration/theme ARE the learner's consent, and a hash
        # taken at `session propose` went stale on any unrelated learner fact.
        lesson_arc = build_lesson_arc(proposal)
    elif any((lesson_profile is not None, target_ref is not None, bool(theme and theme.strip()))):
        raise SessionPrecondition("lesson profile/topic/theme proposals require active generation@2")

    if "scheduler" in pinned:
        # The overdue sweep runs before composition so AT_RISK facts exist
        # before any plan is built on them (scheduler 4). Idempotent by
        # (target, dimension, schedule_epoch): a crash between sweep and start
        # leaves committed facts, and the retried start mints no duplicates.
        from english_trainer.scheduler.engine import sweep_overdue

        sweep_overdue(
            store,
            pinned["scheduler"],
            registry.resolve_pinned("scheduler", pinned["scheduler"]),
            clock,
            random_source,
            actor=actor,
            permanent_interleave_targets=(
                permanent_interleave(registry.resolve_pinned("curriculum", pinned["curriculum"]))
                if permanent_interleave is not None and "curriculum" in pinned
                else None
            ),
            registry=registry,
        )

    # Required skills resolve synchronously here, before any session aggregate
    # exists (adapters 4.2; lessons 4b [P0-Q1]): an unresolvable pin raises and
    # `start` creates nothing. A report-protocol session (`uses_report_
    # protocol`) defaults to the current canonical skill version regardless of
    # the pinned generation version [PD-2026-09-23]; a pedagogy-v2 session that
    # is NOT report-protocol keeps the old `@2` default; everything else keeps
    # `@1`.
    if uses_report_protocol(pinned):
        default_skill = _REPORT_REQUIRED_SKILL
    elif generation_schema_version(pinned) >= 2:
        default_skill = _PEDAGOGY_REQUIRED_SKILL
    else:
        default_skill = _DEFAULT_REQUIRED_SKILL
    resolved_required_skills = _resolve_required_skills(
        agent_skills_dir,
        required_skills,
        default_required_skill=default_skill,
    )

    session_id = new_ulid(clock, random_source)
    manifest: dict[str, Any] = {
        "session_id": session_id,
        "provider": provider,
        "mode": mode,
        "started_at": clock.now().isoformat(),
        "pinned_versions": pinned,
        "required_skills": resolved_required_skills,
        "session_plan_id": new_ulid(clock, random_source),
        "plan": {"composition_revision": 1, "plan_version": 1},
        **({"lesson_profile": proposal["profile"], "lesson_arc": lesson_arc} if pedagogy_v2 else {}),
    }

    live = live_composition_inputs(
        store,
        registry,
        pinned,
        program,
        policy,
        clock,
        starting_new_session=True,
        permanent_interleave=permanent_interleave,
    )
    known = known_target_refs(store, registry, pinned)
    central = proposal.get("central_topic") or {}
    composed = compose_plan(
        program=program,
        policy=policy,
        generation_version=pinned["generation"],
        mode=mode,
        total_seconds=total_seconds,
        presented_targets=presented_targets(store),
        review_candidates=live["review_candidates"],
        signals=live["signals"],
        probe=live["probe"],
        starvation_candidates=live["starvation_candidates"],
        relevant_targets=live["relevant_targets"],
        availability_long_break=bool(availability["long_break"]),
        # No exercise bank: the tutor builds the items itself and reports them
        # (the bank belonged to the removed step-delivery protocol).
        bank_items=[],
        pinned_versions=pinned,
        active_safety_version=pinned["curriculum"],
        lesson_profile=str(proposal["profile"]) if pedagogy_v2 else None,
        lesson_arc=lesson_arc if pedagogy_v2 else None,
        central_target_ref=(str(central["target_ref"]) if central.get("target_ref") is not None else None),
        lesson_theme=(str(proposal["theme"]) if proposal.get("theme") is not None else None),
        known_targets=known,
        learner_preferences=live["learner_preferences"],
        new_id=lambda: new_ulid(clock, random_source),
    )
    plan_state: dict[str, Any] = {
        "session_id": session_id,
        "mode": mode,
        "total_seconds": total_seconds,
        "composition_revision": 1,
        "plan_version": 1,
        # The safety overlay stays *active*, never pinned (OPEN-14): record
        # which version did the excluding, which at start equals the pin.
        "active_safety_version": pinned["curriculum"],
        "availability": {
            "budget_source": budget_source,
            "long_break": availability["long_break"],
            "trace": availability["trace"],
        },
        **({"lesson_profile": proposal["profile"], "lesson_arc": lesson_arc} if pedagogy_v2 else {}),
        **composed,
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            SESSION_AGGREGATE,
            session_id,
            {
                "status": STARTED,
                "manifest": manifest,
                "last_activity_at": clock.now().isoformat(),
            },
            expected_revision=0,
        )
        uow.save_aggregate(PLAN_AGGREGATE, manifest["session_plan_id"], plan_state, expected_revision=0)
        save_decision_traces(uow, plan_state)
        save_new_review_assignments(uow, plan_state, session_id, clock.now().isoformat())
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is None:
            uow.save_aggregate(POINTER_AGGREGATE, POINTER_ID, {"session_id": session_id}, expected_revision=0)
        else:
            state, revision = pointer
            if state.get("session_id"):
                # A concurrent start slipped in between our check and this
                # transaction; the CAS family refuses it deterministically.
                raise SessionPrecondition("another session became active concurrently")
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"session_id": session_id}, expected_revision=revision
            )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_STARTED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=session_id,
                    payload={"manifest": manifest},
                    pinned_versions=pinned,
                ),
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_COMPOSED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "session_plan_id": manifest["session_plan_id"],
                        "composition_revision": 1,
                        "plan_version": 1,
                        "budget": {"total_seconds": total_seconds, **plan_state["budget"]},
                        "steps": plan_summary(plan_state),
                        "eligible_review": plan_state["eligible_review"],
                        "excluded_review": plan_state["excluded_review"],
                        "waivers": plan_state["waivers"],
                        "active_safety_version": plan_state["active_safety_version"],
                    },
                    pinned_versions=pinned,
                ),
                *(
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=SKILL_REQUIRED,
                        occurred_at=clock.now(),
                        actor=actor,
                        provider=provider,
                        correlation_id=session_id,
                        payload={"session_id": session_id, **item},
                        pinned_versions=pinned,
                    )
                    for item in resolved_required_skills
                ),
                *(
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=EVENT_SIGNAL_CONSUMED,
                        occurred_at=clock.now(),
                        actor=actor,
                        provider=provider,
                        correlation_id=session_id,
                        payload={
                            "signal_id": signal_id,
                            "session_id": session_id,
                            "composition_revision": 1,
                            "reason": "probe_admitted",
                            "consumed_at": clock.now().isoformat(),
                        },
                        pinned_versions=pinned,
                    )
                    for signal_id in plan_state["consumed"]
                ),
                # `--provider` is mandatory at start too, and `attach_agent`
                # runs in the same UoW as the operation (lessons 5 [R-3]): start
                # attaches the starting tutor, alongside the start events, so an
                # AGENT_ATTACHED fact exists from the first connection -- resume
                # is not the only path that attaches.
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_AGENT_ATTACHED,
                    occurred_at=clock.now(),
                    actor="agent",
                    provider=provider,
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "provider": provider,
                        "skills": resolved_required_skills,
                        "attached_at": clock.now().isoformat(),
                    },
                    pinned_versions=pinned,
                ),
            ]
        )

    # `start` returns the lesson brief (lesson_brief@1): everything the tutor
    # needs to run the lesson without calling the engine again. It is built
    # from committed engine state and rides the START RESPONSE only -- never
    # baked into the immutable manifest persisted above (lessons 4b). Imported
    # locally to avoid an import cycle (brief imports this module).
    from english_trainer.lessons.brief import build_brief

    brief = build_brief(store, registry, session_id, permanent_interleave=permanent_interleave)
    return {**manifest, "session_id": session_id, "brief": brief, "session_revision": 1}


def _close_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    expected_session_revision: int,
    target_status: str,
    event_type: str,
    allowed_from: tuple[str, ...],
    refusal: str,
    actor: str,
    close_pending_reason: str | None = None,
) -> DomainEvent:
    from english_trainer.evidence.attempts import close_pending_attempts
    from english_trainer.evidence.reviews import close_pending_assignments

    state, revision = load_session_for_update(store, session_id, expected_session_revision)
    status = state.get("status")
    if status not in allowed_from:
        raise SessionPrecondition(refusal.format(session_id=session_id, status=status))

    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        closed_attempts: list[str] = []
        closed_assignments: list[str] = []
        if close_pending_reason is not None:
            # ABANDONED converts the pending set (0.5): recorded attempts close
            # without scoring contribution, pending review assignments become
            # INSUFFICIENT_EVIDENCE(reason=abandoned) -- the scheduler holds
            # the interval and books a retry, never a punishment. Atomic with
            # the terminalization.
            closed_attempts = close_pending_attempts(
                store, uow, clock, random_source, session_id, reason=close_pending_reason, actor=actor
            )
            closed_assignments = close_pending_assignments(
                store, uow, clock, random_source, session_id, reason=close_pending_reason, actor=actor
            )
        new_session_revision = bump_session(
            uow,
            session_id,
            state,
            revision,
            clock.now(),
            changes={"status": target_status, "closed_at": clock.now().isoformat()},
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("session_id") == session_id:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"session_id": None}, expected_revision=pointer[1]
            )
        payload: dict[str, Any] = {
            "session_id": session_id,
            "from_status": status,
            "session_revision": new_session_revision,
        }
        if close_pending_reason is not None:
            payload["closed_attempts"] = closed_attempts
            payload["closed_assignments"] = closed_assignments
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload=payload,
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return event


def abandon_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    expected_session_revision: int,
    actor: str = "engine",
) -> DomainEvent:
    """STARTED | IN_PROGRESS → ABANDONED. Keeps everything already recorded;
    pending attempts close without scoring contribution in the same
    transaction (0.5: the learner is not punished for a lost chat)."""
    return _close_session(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=expected_session_revision,
        target_status=ABANDONED,
        event_type=EVENT_ABANDONED,
        allowed_from=_ACTIVE_STATES,
        refusal="session {session_id} is already {status}",
        actor=actor,
        close_pending_reason="abandoned",
    )


def close_reported_session(
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    state: dict[str, Any],
    revision: int,
    *,
    report_hash: str,
    actor: str = "agent",
) -> tuple[DomainEvent, int]:
    """Terminalize a session INSIDE the lesson-report transaction.

    The report is the lesson's work, so a ``STARTED`` session first moves to
    ``IN_PROGRESS`` (the edge the first delivered step used to take) and then
    to ``FINISHED`` -- two revision bumps in one UnitOfWork, never the illegal
    direct ``STARTED → FINISHED`` edge. There is no pending-set gate: the same
    transaction has already closed every review assignment (addressed ones by
    verdict, the rest INSUFFICIENT_EVIDENCE with a reason), which is exactly
    the evidence persistence ``finish`` exists to guarantee.

    Returns ``(session.finished event, new session revision)``.
    """
    status = state.get("status")
    if status not in _ACTIVE_STATES:
        raise SessionPrecondition(f"session {session_id} is {status}; only an active session can be reported")
    manifest = dict(state.get("manifest") or {})
    pinned = dict(manifest.get("pinned_versions") or {})
    current_state, current_revision = dict(state), revision
    if status == STARTED:
        current_revision = bump_session(
            uow, session_id, current_state, current_revision, clock.now(), changes={"status": IN_PROGRESS}
        )
        current_state = {**current_state, "status": IN_PROGRESS, "last_activity_at": clock.now().isoformat()}
    new_revision = bump_session(
        uow,
        session_id,
        current_state,
        current_revision,
        clock.now(),
        changes={"status": FINISHED, "closed_at": clock.now().isoformat()},
    )
    pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
    if pointer is not None and pointer[0].get("session_id") == session_id:
        uow.save_aggregate(POINTER_AGGREGATE, POINTER_ID, {"session_id": None}, expected_revision=pointer[1])
    (event,) = uow.append(
        [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_FINISHED,
                occurred_at=clock.now(),
                actor=actor,
                provider=manifest.get("provider"),
                correlation_id=session_id,
                payload={
                    "session_id": session_id,
                    "from_status": IN_PROGRESS,
                    "reported_from_status": status,
                    "closed_by": "lesson_report",
                    "report_hash": report_hash,
                    "session_revision": new_revision,
                },
                pinned_versions=pinned,
            )
        ]
    )
    return event, new_revision
