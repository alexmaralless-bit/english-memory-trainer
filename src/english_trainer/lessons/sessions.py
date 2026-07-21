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
(foundation 3.6). Plan composition inside the same start (control 4.2,
``SESSION_COMPOSED``) arrives with the control increment of 2.2; the manifest
already carries the ``session_plan_id`` and the initial plan snapshot so the
shape does not change later.

Everything commits through one UnitOfWork per command: the session aggregate,
the active-session pointer and the lifecycle event move together or not at all.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError, NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

SESSION_AGGREGATE = "session"
POINTER_AGGREGATE = "session_pointer"
POINTER_ID = "active"

EVENT_STARTED = "session.started"
EVENT_FINISHED = "session.finished"
EVENT_ABANDONED = "session.abandoned"

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


def start_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    provider: str,
    mode: str = "balanced",
    actor: str = "engine",
) -> dict[str, Any]:
    """Open a session and return its immutable manifest.

    Preconditions: an active curriculum version must exist (a session without a
    program has nothing to teach), and no other session may be active -- the
    contract decomposes "start with abandon" into two idempotent commands, so
    the caller abandons explicitly first (foundation 3.4, C-1).
    """
    if "curriculum" not in _pin_versions(registry):
        raise SessionPrecondition("no active curriculum version; run `trainer curriculum activate` first")
    current = active_session_id(store)
    if current is not None:
        raise SessionPrecondition(
            f"session {current} is still active; finish or abandon it first "
            "(start does not implicitly abandon -- contract C-1)"
        )

    session_id = new_ulid(clock, random_source)
    manifest: dict[str, Any] = {
        "session_id": session_id,
        "provider": provider,
        "mode": mode,
        "started_at": clock.now().isoformat(),
        "pinned_versions": _pin_versions(registry),
        "required_skills": [],
        "session_plan_id": new_ulid(clock, random_source),
        "plan": {"composition_revision": 1, "plan_version": 1},
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            SESSION_AGGREGATE,
            session_id,
            {"status": STARTED, "manifest": manifest},
            expected_revision=0,
        )
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
                    pinned_versions=manifest["pinned_versions"],
                )
            ]
        )
    return manifest


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
) -> DomainEvent:
    found = get_session(store, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    state, revision = found
    status = state.get("status")
    if status not in allowed_from:
        raise SessionPrecondition(refusal.format(session_id=session_id, status=status))

    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
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
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload={"session_id": session_id, "from_status": status},
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

    Evidence-completeness requirements (empty pending review set, 0.5 closure
    rules) attach here in the evidence increment of 2.2.
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
    )


def abandon_session(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    actor: str = "engine",
) -> DomainEvent:
    """STARTED | IN_PROGRESS → ABANDONED. Keeps everything already recorded."""
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
    )
