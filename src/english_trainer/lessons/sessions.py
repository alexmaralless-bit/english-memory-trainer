"""Session lifecycle over kernel CAS aggregates (lessons contract 0.5; roadmap 2.2).

A session is a revisioned operational aggregate with the contract lifecycle
``STARTED → IN_PROGRESS → FINISHED | ABANDONED`` (the direct jump
``STARTED → ABANDONED`` is allowed; ``STARTED → FINISHED`` is not -- a session
that recorded nothing is abandoned, never "finished"). At most one session is
active at a time; the singleton pointer aggregate enforces that under
compare-and-set, so two concurrent starts cannot both win.

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

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from english_trainer.adapters.errors import SkillUnavailable
from english_trainer.adapters.events import SKILL_REQUIRED
from english_trainer.adapters.skills import resolve as resolve_skill
from english_trainer.control.compose import compose_plan
from english_trainer.control.policy import CONTROL_KIND, require_valid
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError, NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

# The default required skill (adapters 2), wired in only when the caller
# names an `agent_skills_dir` AND that skill actually resolves there -- a
# caller that passes neither (every pre-existing caller and test) keeps
# `required_skills: []` (see `_resolve_required_skills`).
_DEFAULT_REQUIRED_SKILL: tuple[str, str] = ("run-english-session", "1")

SESSION_AGGREGATE = "session"
PLAN_AGGREGATE = "session_plan"
POINTER_AGGREGATE = "session_pointer"
POINTER_ID = "active"

EVENT_STARTED = "session.started"
EVENT_FINISHED = "session.finished"
EVENT_ABANDONED = "session.abandoned"
EVENT_COMPOSED = "session.composed"
EVENT_STEP_PRESENTED = "session.step_presented"
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


def review_candidates_for(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
    program: dict[str, Any],
    control_policy: dict[str, Any],
    clock: Clock,
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
    )
    return classify_review_candidates(backlog, program, control_policy)


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
            "presented": step["presented_at"] is not None,
        }
        for step in plan_state["steps"]
    ]


def _resolve_required_skills(
    agent_skills_dir: Path | str | None,
    required_skills: Sequence[tuple[str, str]] | None,
) -> list[dict[str, str]]:
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
            resolve_skill(*_DEFAULT_REQUIRED_SKILL, agent_skills_dir)
        except SkillUnavailable:
            return []
        pairs = (_DEFAULT_REQUIRED_SKILL,)
    else:
        return []

    resolved: list[dict[str, str]] = []
    for name, version in pairs:
        try:
            skill = resolve_skill(name, version, agent_skills_dir)
        except SkillUnavailable as exc:
            raise SessionPrecondition(
                f"required skill {name}@{version} is unavailable: {exc}; run `trainer skills sync` first"
            ) from exc
        resolved.append({"skill_name": skill.name, "version": skill.version})
    return resolved


def start_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    provider: str,
    mode: str = "balanced",
    duration_minutes: int | None = None,
    actor: str = "engine",
    agent_skills_dir: Path | str | None = None,
    required_skills: Sequence[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Open a session, compose its plan, and return the immutable manifest plus a
    tutor ``briefing`` (continuation flow: one CLI call is enough to run the
    session). The briefing is a computed view riding the response only -- the
    persisted manifest stays immutable.

    Preconditions: active curriculum, control and generation policies must
    exist (composition is executed by control@1 and every step carries a
    generation directive under the pinned generation policy), and no other
    session may be active -- the contract decomposes "start with abandon" into
    two idempotent commands, so the caller abandons explicitly first
    (foundation 3.4, C-1).

    The budget precedence is ``--duration-minutes`` -> policy default
    (control 4.7a); the declared/observed AvailabilityProfile slots in between
    once the availability increment lands.

    ``agent_skills_dir``/``required_skills`` wire the manifest's
    ``required_skills`` (adapters 4.2, lessons 4b [P0-Q1]); see
    :func:`_resolve_required_skills` for the exact defaulting rule.
    """
    pinned = _pin_versions(registry)
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
    total_seconds = (
        duration_minutes if duration_minutes is not None else int(policy["budget"]["default_total_minutes"])
    ) * 60

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
        )

    # Required skills resolve synchronously here, before any session aggregate
    # exists (adapters 4.2; lessons 4b [P0-Q1]): an unresolvable pin raises and
    # `start` creates nothing.
    resolved_required_skills = _resolve_required_skills(agent_skills_dir, required_skills)

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
    }

    composed = compose_plan(
        program=program,
        policy=policy,
        generation_version=pinned["generation"],
        mode=mode,
        total_seconds=total_seconds,
        presented_targets=presented_targets(store),
        review_candidates=review_candidates_for(store, registry, pinned, program, policy, clock),
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
        **composed,
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            SESSION_AGGREGATE,
            session_id,
            {"status": STARTED, "manifest": manifest},
            expected_revision=0,
        )
        uow.save_aggregate(PLAN_AGGREGATE, manifest["session_plan_id"], plan_state, expected_revision=0)
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

    # `start` returns the tutor briefing too, not only the manifest: an agent
    # needs a single CLI call to run the session (continuation flow "Правила" --
    # `resume` и `start` возвращают tutor briefing). It is built from committed
    # engine state via the SAME builder `resume` uses (one source of truth), and
    # rides the START RESPONSE only -- never baked into the immutable Session
    # Manifest that was already persisted above (lessons 4b: manifest неизменяем;
    # continuation §2 trust boundary: computed state stays separate). Imported
    # locally to avoid a start-time import cycle (resume imports this module).
    from english_trainer.lessons.resume import build_briefing

    briefing = build_briefing(store, registry, clock, session_id, manifest)
    return {**manifest, "briefing": briefing}


def mark_in_progress(store: EventStore, clock: Clock, session_id: str) -> None:
    """STARTED → IN_PROGRESS: the first real work arrived (a presented step or
    a recorded attempt flips this in later increments)."""
    found = get_session(store, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    state, revision = found
    if state.get("status") != STARTED:
        if state.get("status") == IN_PROGRESS:
            return  # already there; idempotent
        raise SessionPrecondition(f"session {session_id} is {state.get('status')}, not {STARTED}")
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            SESSION_AGGREGATE, session_id, {**state, "status": IN_PROGRESS}, expected_revision=revision
        )


def _close_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    target_status: str,
    event_type: str,
    allowed_from: tuple[str, ...],
    refusal: str,
    actor: str,
    require_empty_pending: bool = False,
    close_pending_reason: str | None = None,
) -> DomainEvent:
    from english_trainer.evidence.attempts import close_pending_attempts, pending_attempts
    from english_trainer.evidence.reviews import close_pending_assignments, pending_assignments

    found = get_session(store, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    state, revision = found
    status = state.get("status")
    if status not in allowed_from:
        raise SessionPrecondition(refusal.format(session_id=session_id, status=status))

    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        # Pending-set rules run inside the transaction so the decision and the
        # terminalization see one consistent state (lessons 0.5).
        if require_empty_pending:
            pending = pending_attempts(store, session_id)
            open_reviews = pending_assignments(store, session_id)
            if pending or open_reviews:
                parts = []
                if pending:
                    names = ", ".join(str(a.get("attempt_id")) for a in pending[:3])
                    parts.append(f"{len(pending)} unassessed attempt(s) ({names})")
                if open_reviews:
                    names = ", ".join(str(a.get("review_id")) for a in open_reviews[:3])
                    parts.append(
                        f"{len(open_reviews)} open review assignment(s) ({names}) -- "
                        "`trainer review close` each one"
                    )
                raise SessionPrecondition(
                    f"session {session_id} has a non-empty pending set: {'; '.join(parts)}. "
                    "Finish REQUIRES an empty pending set and never auto-closes [P0-2]; "
                    "use `trainer session abandon` to close without contribution."
                )
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
        uow.save_aggregate(
            SESSION_AGGREGATE,
            session_id,
            {**state, "status": target_status, "closed_at": clock.now().isoformat()},
            expected_revision=revision,
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("session_id") == session_id:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"session_id": None}, expected_revision=pointer[1]
            )
        payload: dict[str, Any] = {"session_id": session_id, "from_status": status}
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


def finish_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    actor: str = "engine",
) -> DomainEvent:
    """IN_PROGRESS → FINISHED. A session that recorded nothing cannot finish:
    the contract lifecycle has no ``STARTED → FINISHED`` edge -- abandon it.

    FINISHED *requires* an already-empty pending set and refuses otherwise --
    it never closes goals itself [P0-2]: auto-closing would let a session end
    without outcomes, bypassing exactly the evidence persistence finish exists
    to guarantee. Review assignments join the pending set with the scheduler.
    """
    return _close_session(
        store,
        clock,
        random_source,
        session_id,
        target_status=FINISHED,
        event_type=EVENT_FINISHED,
        allowed_from=(IN_PROGRESS,),
        refusal=(
            "session {session_id} is {status}: a session that recorded nothing cannot finish; "
            "use `trainer session abandon` instead"
        ),
        actor=actor,
        require_empty_pending=True,
    )


def abandon_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
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
        target_status=ABANDONED,
        event_type=EVENT_ABANDONED,
        allowed_from=_ACTIVE_STATES,
        refusal="session {session_id} is already {status}",
        actor=actor,
        close_pending_reason="abandoned",
    )
