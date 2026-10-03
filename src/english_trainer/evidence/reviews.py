"""ReviewAssignment closure (evidence 4.3; roadmap 2.3 increment 3).

An assignment gets EXACTLY ONE terminal disposition, by the first trigger that
fires:

- the lesson report [PD-2026-09-23]: a reported item that names the review
  closes it by the tutor's ``verdict``, mapped by the ENGINE through the pinned
  evidence@2 ``review_outcome_by_verdict`` table (:func:`closure_from_verdict`)
  -- the report carries a verdict, never an outcome; every review the report
  did not address closes ``INSUFFICIENT_EVIDENCE`` with ``not_attempted`` or
  the tutor's skip reason (:func:`close_insufficient`);
- session abandon (or the stale sweep): pending assignments become
  ``INSUFFICIENT_EVIDENCE(reason=abandoned|stale)`` -- the scheduler holds the
  interval and books a short retry, no punishment
  (:func:`close_pending_assignments`).

Historic logs also carry closures written by the removed per-step protocol
(``attempt record --close-review``, ``review close``) and system cancellations
by a replan (``review.assignment_cancelled`` -- NOT a learning outcome, a
terminal no-op for scoring and the scheduler [RR2-4]); every consumer keeps
reading them. :func:`_outcome_from_assessment` still maps all three assessment
bases (objective check, rubric, tutor verdict) so those facts keep their
meaning.

Re-closing a closed assignment is idempotent and returns the prior outcome; a
correction of a terminal outcome goes ONLY through the kernel correction
envelope, never a second REVIEW_OUTCOME.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from english_trainer.evidence.attempts import (
    EvidencePrecondition,
    _session_manifest,
)
from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.transitions import build_state_transition

REVIEW_AGGREGATE = "review_assignment"

EVENT_REVIEW_OUTCOME = "review.outcome"
# Written by the removed replan path; historic logs carry it.
EVENT_REVIEW_CANCELLED = "review.assignment_cancelled"

PENDING = "pending"
CLOSED = "closed"
CANCELLED = "cancelled"

# v1 default: a scored, contributing open (rubric) answer confirms at or above
# half the ppm scale (500000 = 0.5 of 1_000_000). Integer-thresholded and
# deterministic; the mastery-criteria increment refines it, the channel stays.
_RUBRIC_CONFIRMED_PPM = 500_000

# The evidence@2 verdict -> outcome table, used only when a caller hands in no
# pinned table. A report commit always passes the session's pinned table.
DEFAULT_REVIEW_OUTCOME_BY_VERDICT: dict[str, str] = {
    "correct": "CONFIRMED",
    "partial": "CONFIRMED",
    "incorrect": "REGRESSION",
}


def pending_assignments(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """The session's assignments still awaiting a terminal disposition."""
    out: list[dict[str, Any]] = []
    for _, state, _ in list_aggregates(store._conn, REVIEW_AGGREGATE):
        if state.get("session_id") == session_id and state.get("status") == PENDING:
            out.append(dict(state))
    return out


def _outcome_from_assessment(
    assessment: dict[str, Any], outcome_by_verdict: Mapping[str, str] | None = None
) -> tuple[str, str | None]:
    """Map a FINALIZED attempt assessment to a ``(review_outcome, reason)`` pair
    (v1 rule). Objective checks carry a boolean ``correct``; open (rubric)
    answers carry ``disposition``/``score_ppm``/``contributing``.

    - objective ``correct`` True -> CONFIRMED, else REGRESSION;
    - rubric ``scored`` + contributing + ``score_ppm`` >= ``_RUBRIC_CONFIRMED_PPM``
      -> CONFIRMED, a scored-but-weaker one -> REGRESSION;
    - tutor ``verdict`` -> ``outcome_by_verdict[verdict]`` (evidence@2), an
      unknown verdict -> INSUFFICIENT_EVIDENCE (never a guessed movement);
    - anything non-contributing / insufficient -> INSUFFICIENT_EVIDENCE.

    The rubric threshold is a documented v1 default; the mapping is fully
    integer-thresholded and deterministic."""
    if assessment.get("contributing") is False:
        # An assessment that states it contributes nothing settles the review
        # without moving it: today that is a drill block whose every answered
        # item repeated an already-credited span (evidence 4.6). `False` only
        # -- an objective single-attempt assessment carries no `contributing`
        # key at all, and must keep falling through to the rule below.
        return "INSUFFICIENT_EVIDENCE", "no_credited_span"
    if str(assessment.get("basis")) == "objective_check":
        return ("CONFIRMED", None) if bool(assessment.get("correct")) else ("REGRESSION", None)
    if str(assessment.get("basis")) == "tutor_verdict":
        table = outcome_by_verdict if outcome_by_verdict is not None else DEFAULT_REVIEW_OUTCOME_BY_VERDICT
        mapped = table.get(str(assessment.get("verdict")))
        if mapped is None:
            return "INSUFFICIENT_EVIDENCE", "unknown_verdict"
        return str(mapped), None
    if assessment.get("disposition") == "scored" and bool(assessment.get("contributing")):
        if int(assessment.get("score_ppm") or 0) >= _RUBRIC_CONFIRMED_PPM:
            return "CONFIRMED", None
        return "REGRESSION", None
    return "INSUFFICIENT_EVIDENCE", "insufficient_evidence"


@dataclass(frozen=True)
class ReviewClosure:
    """A resolved, not-yet-written terminal disposition for one assignment.

    Resolution is a pure read and settlement (:func:`apply_closure`) is a
    write into the UnitOfWork the caller owns -- the lesson report settles
    every review inside its one commit.
    """

    review_id: str
    state: dict[str, Any]
    revision: int
    outcome: str
    reason: str | None
    attempt: dict[str, Any] | None

    def as_result(self, *, already: bool = False) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "already": already,
        }


def _open_assignment(
    store: EventStore, session_id: str, review_id: str
) -> tuple[dict[str, Any], int] | dict[str, Any]:
    """The pending assignment and its revision, or the idempotent prior result.

    It must exist, belong to the session, and not be system-cancelled; an already-closed one returns its
    prior outcome (no second ``REVIEW_OUTCOME``).
    """
    found = read_aggregate(store._conn, REVIEW_AGGREGATE, review_id)
    if found is None:
        raise EvidencePrecondition(f"review assignment {review_id} does not exist")
    state, revision = found
    if str(state.get("session_id")) != session_id:
        raise EvidencePrecondition(
            f"review assignment {review_id} belongs to session {state.get('session_id')}, not {session_id}"
        )
    if state.get("status") == CLOSED:
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
    return state, revision


def closure_from_verdict(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    review_id: str,
    *,
    attempt: dict[str, Any],
    outcome_by_verdict: Mapping[str, str],
    pinned: dict[str, Any],
    provider: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Close one assignment by a tutor-verdict attempt, INSIDE the caller's UoW.

    ``attempt`` is the ``attempt.recorded`` payload the report just wrote for
    the review item (its ``assessment`` has ``basis: tutor_verdict``);
    ``outcome_by_verdict`` is the pinned evidence@2 ``review_outcome_by_verdict``
    table. The outcome is mapped by :func:`_outcome_from_assessment`, so a
    non-contributing attempt (a repeated span) settles INSUFFICIENT_EVIDENCE
    exactly as a repeated drill block does. Writes the assignment aggregate,
    ``REVIEW_OUTCOME`` and its ``scoring.state_transition`` (via
    :func:`apply_closure`); the attempt's own events must already be appended
    to this UoW so the transition fold sees them. Returns the closure result
    (``already: True`` for an idempotent re-close).
    """
    opened = _open_assignment(store, session_id, review_id)
    if isinstance(opened, dict):
        return opened
    state, revision = opened
    outcome, reason = _outcome_from_assessment(dict(attempt.get("assessment") or {}), outcome_by_verdict)
    closure = ReviewClosure(
        review_id=review_id,
        state=state,
        revision=revision,
        outcome=outcome,
        reason=reason,
        attempt=attempt,
    )
    apply_closure(
        store, uow, clock, random_source, session_id, closure, pinned=pinned, provider=provider, actor=actor
    )
    return closure.as_result()


def close_insufficient(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    review_id: str,
    *,
    reason: str,
    pinned: dict[str, Any],
    provider: str | None = None,
    actor: str = "engine",
) -> dict[str, Any]:
    """Close one still-pending assignment as ``INSUFFICIENT_EVIDENCE(reason)``.

    The lesson report's disposition for a review it did not address:
    ``not_attempted``, or the tutor's skip reason (``no_time``,
    ``learner_declined``). The scheduler holds the interval and books a short
    retry -- no punishment, exactly as for an abandoned session. Runs inside
    the caller's UoW through :func:`apply_closure`; idempotent on an already
    closed assignment.
    """
    if not reason:
        raise EvidencePrecondition("an INSUFFICIENT_EVIDENCE closure needs a reason")
    opened = _open_assignment(store, session_id, review_id)
    if isinstance(opened, dict):
        return opened
    state, revision = opened
    closure = ReviewClosure(
        review_id=review_id,
        state=state,
        revision=revision,
        outcome="INSUFFICIENT_EVIDENCE",
        reason=reason,
        attempt=None,
    )
    apply_closure(
        store, uow, clock, random_source, session_id, closure, pinned=pinned, provider=provider, actor=actor
    )
    return closure.as_result()


def apply_closure(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    closure: ReviewClosure,
    *,
    pinned: dict[str, Any],
    provider: str | None = None,
    actor: str = "agent",
) -> None:
    """Write one resolved closure INSIDE the caller's UnitOfWork."""
    uow.save_aggregate(
        REVIEW_AGGREGATE,
        closure.review_id,
        {
            **closure.state,
            "status": CLOSED,
            "outcome": closure.outcome,
            "reason": closure.reason,
            "closed_at": clock.now().isoformat(),
        },
        expected_revision=closure.revision,
    )
    outcome_event = make_event(
        id=new_ulid(clock, random_source),
        type=EVENT_REVIEW_OUTCOME,
        occurred_at=clock.now(),
        actor=actor,
        provider=provider,
        correlation_id=session_id,
        payload={
            "review_id": closure.review_id,
            "target_ref": closure.state.get("target_ref"),
            "dimension": closure.state.get("dimension"),
            "outcome": closure.outcome,
            "reason": closure.reason,
            "origin": "session",
            "session_id": session_id,
            "step_id": closure.state.get("step_id"),
            "schedule_epoch": closure.state.get("schedule_epoch"),
            "attempt_id": closure.attempt.get("attempt_id") if closure.attempt else None,
        },
        pinned_versions=pinned,
    )
    transition_event = build_state_transition(store, PolicyRegistry(store._conn, clock), outcome_event)
    uow.append([outcome_event, *([transition_event] if transition_event is not None else [])])


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
