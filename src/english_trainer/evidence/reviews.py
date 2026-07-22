"""ReviewAssignment closure (evidence 4.3; roadmap 2.3 increment 3).

An assignment gets EXACTLY ONE terminal disposition, by the first trigger that
fires: explicit ``trainer review close`` (the engine computes the outcome from
the assignment's assessed attempts -- the agent marks done, never grades),
session abandon (pending assignments become ``INSUFFICIENT_EVIDENCE(reason=
abandoned)`` -- the scheduler holds the interval and books a short retry, no
punishment), or a replan that dropped the unpresented step (``CANCELLED`` --
NOT a learning outcome: the system withdrew the goal itself, so scoring and
the scheduler both treat it as a terminal no-op [RR2-4]).

The v1 outcome computation: the latest assessed attempt against the
assignment's step decides -- correct → CONFIRMED, incorrect → REGRESSION; no
assessed attempt → INSUFFICIENT_EVIDENCE(reason=not_attempted). RECOVERED is
never emitted separately: the scoring transition table already restores the
remembered steady state when CONFIRMED lands on AT_RISK. Mastery-criteria
gating of CONFIRMED (thresholds, independence across sessions) refines this
in the criteria increment; the outcome channel and its consumers stay as-is.

Re-closing a closed assignment is idempotent and returns the prior outcome; a
correction of a terminal outcome goes ONLY through the kernel correction
envelope, never a second REVIEW_OUTCOME.
"""

from __future__ import annotations

from typing import Any

from english_trainer.evidence.attempts import (
    EVENT_ATTEMPT_RECORDED,
    EvidencePrecondition,
    _session_manifest,
)
from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

REVIEW_AGGREGATE = "review_assignment"

EVENT_REVIEW_OUTCOME = "review.outcome"
EVENT_REVIEW_CANCELLED = "review.assignment_cancelled"

PENDING = "pending"
CLOSED = "closed"
CANCELLED = "cancelled"


def pending_assignments(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """The session's assignments still awaiting a terminal disposition."""
    out: list[dict[str, Any]] = []
    for _, state, _ in list_aggregates(store._conn, REVIEW_AGGREGATE):
        if state.get("session_id") == session_id and state.get("status") == PENDING:
            out.append(dict(state))
    return out


def _latest_assessed_attempt(store: EventStore, session_id: str, step_id: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for event in store.read():
        if (
            event.type == EVENT_ATTEMPT_RECORDED
            and event.correlation_id == session_id
            and str(event.payload.get("step_id")) == step_id
            and event.payload.get("status") == "assessed"
        ):
            found = dict(event.payload)
    return found


def close_review(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    review_id: str,
    *,
    actor: str = "agent",
) -> dict[str, Any]:
    """Compute and record the single terminal ReviewOutcome for an assignment."""
    manifest = _session_manifest(store, session_id)
    found = read_aggregate(store._conn, REVIEW_AGGREGATE, review_id)
    if found is None:
        raise EvidencePrecondition(f"review assignment {review_id} does not exist")
    state, revision = found
    if str(state.get("session_id")) != session_id:
        raise EvidencePrecondition(
            f"review assignment {review_id} belongs to session {state.get('session_id')}, not {session_id}"
        )
    if state.get("status") == CLOSED:
        # Idempotent re-close: the prior outcome, no second REVIEW_OUTCOME.
        return {
            "review_id": review_id,
            "outcome": state.get("outcome"),
            "reason": state.get("reason"),
            "already": True,
        }
    if state.get("status") == CANCELLED:
        raise EvidencePrecondition(
            f"review assignment {review_id} was cancelled by the system; there is nothing to close"
        )

    attempt = _latest_assessed_attempt(store, session_id, str(state.get("step_id")))
    reason: str | None = None
    if attempt is None:
        outcome = "INSUFFICIENT_EVIDENCE"
        reason = "not_attempted"
    elif attempt.get("assessment", {}).get("correct"):
        outcome = "CONFIRMED"
    else:
        outcome = "REGRESSION"

    closed_at = clock.now().isoformat()
    pinned = dict(manifest.get("pinned_versions") or {})
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            REVIEW_AGGREGATE,
            review_id,
            {**state, "status": CLOSED, "outcome": outcome, "reason": reason, "closed_at": closed_at},
            expected_revision=revision,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_REVIEW_OUTCOME,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload={
                        "review_id": review_id,
                        "target_ref": state.get("target_ref"),
                        "dimension": state.get("dimension"),
                        "outcome": outcome,
                        "reason": reason,
                        "origin": "session",
                        "session_id": session_id,
                        "step_id": state.get("step_id"),
                        "schedule_epoch": state.get("schedule_epoch"),
                        "attempt_id": attempt.get("attempt_id") if attempt else None,
                    },
                    pinned_versions=pinned,
                )
            ]
        )
    return {"review_id": review_id, "outcome": outcome, "reason": reason, "already": False}


def cancel_assignment(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    review_id: str,
    *,
    reason: str,
    actor: str = "engine",
) -> None:
    """Terminal system cancellation inside the caller's UoW (replan, control
    4.2): closes the assignment for the finish gate WITHOUT a learning outcome."""
    found = uow.get_aggregate(REVIEW_AGGREGATE, review_id)
    if found is None:
        return
    state, revision = found
    if state.get("status") != PENDING:
        return
    uow.save_aggregate(
        REVIEW_AGGREGATE,
        review_id,
        {**state, "status": CANCELLED, "reason": reason, "closed_at": clock.now().isoformat()},
        expected_revision=revision,
    )
    uow.append(
        [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_REVIEW_CANCELLED,
                occurred_at=clock.now(),
                actor=actor,
                correlation_id=str(state.get("session_id") or review_id),
                payload={
                    "review_id": review_id,
                    "target_ref": state.get("target_ref"),
                    "dimension": state.get("dimension"),
                    "reason": reason,
                },
            )
        ]
    )


def close_pending_assignments(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    reason: str,
    actor: str = "engine",
) -> list[str]:
    """ABANDONED converts pending assignments to INSUFFICIENT_EVIDENCE (0.5):
    the scheduler holds the interval and books a short retry -- no punishment.
    Runs inside the session-terminalization UoW, atomically with it."""
    closed: list[str] = []
    for state in pending_assignments(store, session_id):
        review_id = str(state["review_id"])
        found = uow.get_aggregate(REVIEW_AGGREGATE, review_id)
        if found is None:
            continue
        current, revision = found
        uow.save_aggregate(
            REVIEW_AGGREGATE,
            review_id,
            {
                **current,
                "status": CLOSED,
                "outcome": "INSUFFICIENT_EVIDENCE",
                "reason": reason,
                "closed_at": clock.now().isoformat(),
            },
            expected_revision=revision,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_REVIEW_OUTCOME,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=session_id,
                    payload={
                        "review_id": review_id,
                        "target_ref": current.get("target_ref"),
                        "dimension": current.get("dimension"),
                        "outcome": "INSUFFICIENT_EVIDENCE",
                        "reason": reason,
                        "origin": "session",
                        "session_id": session_id,
                        "step_id": current.get("step_id"),
                        "schedule_epoch": current.get("schedule_epoch"),
                        "attempt_id": None,
                    },
                )
            ]
        )
        closed.append(review_id)
    return closed
