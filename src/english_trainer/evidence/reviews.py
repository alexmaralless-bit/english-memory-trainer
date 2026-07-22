"""ReviewAssignment closure (evidence 4.3; roadmap 2.3 increment 3).

An assignment gets EXACTLY ONE terminal disposition, by the first trigger that
fires: explicit ``trainer review close`` (the engine computes the outcome from
the assignment's assessed attempts -- the agent marks done, never grades),
session abandon (pending assignments become ``INSUFFICIENT_EVIDENCE(reason=
abandoned)`` -- the scheduler holds the interval and books a short retry, no
punishment), or a replan that dropped the unpresented step (``CANCELLED`` --
NOT a learning outcome: the system withdrew the goal itself, so scoring and
the scheduler both treat it as a terminal no-op [RR2-4]).

The v1 outcome computation: the latest attempt that reached the terminal
``assessed`` state against the assignment's step decides, read from the attempt
aggregate so BOTH assessment paths count. An objective check maps by its
``correct`` boolean (True → CONFIRMED, False → REGRESSION); an open (rubric)
answer maps by its finalized disposition -- a scored, contributing answer at or
above the v1 ppm threshold → CONFIRMED, a scored-but-weaker one → REGRESSION,
and a non-contributing / insufficient one → INSUFFICIENT_EVIDENCE. No assessed
attempt at all → INSUFFICIENT_EVIDENCE(reason=not_attempted). RECOVERED is
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
    ASSESSED,
    ATTEMPT_AGGREGATE,
    EVENT_ATTEMPT_RECORDED,
    EvidencePrecondition,
    _session_manifest,
)
from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.transitions import build_state_transition

REVIEW_AGGREGATE = "review_assignment"

EVENT_REVIEW_OUTCOME = "review.outcome"
EVENT_REVIEW_CANCELLED = "review.assignment_cancelled"

PENDING = "pending"
CLOSED = "closed"
CANCELLED = "cancelled"

# v1 default: a scored, contributing open (rubric) answer confirms at or above
# half the ppm scale (500000 = 0.5 of 1_000_000). Integer-thresholded and
# deterministic; the mastery-criteria increment refines it, the channel stays.
_RUBRIC_CONFIRMED_PPM = 500_000


def pending_assignments(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """The session's assignments still awaiting a terminal disposition."""
    out: list[dict[str, Any]] = []
    for _, state, _ in list_aggregates(store._conn, REVIEW_AGGREGATE):
        if state.get("session_id") == session_id and state.get("status") == PENDING:
            out.append(dict(state))
    return out


def _latest_assessed_attempt(store: EventStore, session_id: str, step_id: str) -> dict[str, Any] | None:
    """The step's most recent attempt that reached the terminal ``assessed``
    state, read from the attempt AGGREGATE (the authoritative lifecycle status).

    Objective checks are recorded already-assessed; an open answer is recorded
    as ``recorded`` and only later finalized to ``assessed`` via
    ``attempt.state_changed`` (``finalize_attempt``). Both settle in the attempt
    aggregate, so reading it covers BOTH paths -- matching only
    ``attempt.recorded(status=assessed)`` would miss every rubric finalization
    (finding 2). The ``attempt.recorded`` event supplies the step -> attempt_id
    link (the state-change fact carries no ``step_id``)."""
    found: dict[str, Any] | None = None
    for event in store.read():
        if (
            event.type == EVENT_ATTEMPT_RECORDED
            and event.correlation_id == session_id
            and str(event.payload.get("step_id")) == step_id
        ):
            aggregate = read_aggregate(store._conn, ATTEMPT_AGGREGATE, str(event.payload.get("attempt_id")))
            if aggregate is None:
                continue
            state, _ = aggregate
            if state.get("status") == ASSESSED:
                found = dict(state)
    return found


def _outcome_from_assessment(assessment: dict[str, Any]) -> tuple[str, str | None]:
    """Map a FINALIZED attempt assessment to a ``(review_outcome, reason)`` pair
    (v1 rule). Objective checks carry a boolean ``correct``; open (rubric)
    answers carry ``disposition``/``score_ppm``/``contributing``.

    - objective ``correct`` True -> CONFIRMED, else REGRESSION;
    - rubric ``scored`` + contributing + ``score_ppm`` >= ``_RUBRIC_CONFIRMED_PPM``
      -> CONFIRMED, a scored-but-weaker one -> REGRESSION;
    - anything non-contributing / insufficient -> INSUFFICIENT_EVIDENCE.

    The rubric threshold is a documented v1 default; the mapping is fully
    integer-thresholded and deterministic."""
    if str(assessment.get("basis")) == "objective_check":
        return ("CONFIRMED", None) if bool(assessment.get("correct")) else ("REGRESSION", None)
    if assessment.get("disposition") == "scored" and bool(assessment.get("contributing")):
        if int(assessment.get("score_ppm") or 0) >= _RUBRIC_CONFIRMED_PPM:
            return "CONFIRMED", None
        return "REGRESSION", None
    return "INSUFFICIENT_EVIDENCE", "insufficient_evidence"


def close_review(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    review_id: str,
    *,
    expected_session_revision: int,
    actor: str = "agent",
) -> dict[str, Any]:
    """Compute and record the single terminal ReviewOutcome for an assignment."""
    session_state, session_revision = load_session_for_update(store, session_id, expected_session_revision)
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

    outcome: str
    reason: str | None
    attempt = _latest_assessed_attempt(store, session_id, str(state.get("step_id")))
    if attempt is None:
        # No assessed attempt at all (never answered, or answered open and not
        # yet finalized): hold the interval, book a short retry -- no movement.
        outcome, reason = "INSUFFICIENT_EVIDENCE", "not_attempted"
    else:
        outcome, reason = _outcome_from_assessment(attempt.get("assessment") or {})

    closed_at = clock.now().isoformat()
    pinned = dict(manifest.get("pinned_versions") or {})
    with UnitOfWork(store, clock) as uow:
        new_session_revision = bump_session(uow, session_id, session_state, session_revision, clock.now())
        uow.save_aggregate(
            REVIEW_AGGREGATE,
            review_id,
            {**state, "status": CLOSED, "outcome": outcome, "reason": reason, "closed_at": closed_at},
            expected_revision=revision,
        )
        outcome_event = make_event(
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
        transition_event = build_state_transition(store, PolicyRegistry(store._conn, clock), outcome_event)
        uow.append([outcome_event, *([transition_event] if transition_event is not None else [])])
    return {
        "review_id": review_id,
        "outcome": outcome,
        "reason": reason,
        "already": False,
        "session_revision": new_session_revision,
    }


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
    pinned = dict(_session_manifest(store, session_id).get("pinned_versions") or {})
    registry = PolicyRegistry(store._conn, clock)
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
        outcome_event = make_event(
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
            pinned_versions=pinned,
        )
        transition_event = build_state_transition(store, registry, outcome_event)
        uow.append([outcome_event, *([transition_event] if transition_event is not None else [])])
        closed.append(review_id)
    return closed
