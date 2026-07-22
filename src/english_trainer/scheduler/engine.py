"""The review scheduler: when to repeat (scheduler 2-5; roadmap 2.3).

Schedules are a pure fold over the event log, like scores: the first
admissible evidence for a (target, dimension) opens its ``ReviewSchedule``
(epoch 1, first interval), and every ``REVIEW_OUTCOME`` adapts it --
CONFIRMED/RECOVERED step forward, REGRESSION steps back, PROGRESS holds,
INSUFFICIENT_EVIDENCE holds the interval index and books a short retry (for
ANY reason, including ``abandoned`` -- the learner is not punished for a lost
chat). ``REVIEW_ASSIGNMENT_CANCELLED`` is an explicit terminal no-op: the
system withdrew the goal itself, so neither the schedule nor a retry moves.
Intervals are elapsed time (24h), never calendar days.

``review_status`` (not_due / due / overdue) is COMPUTED from the schedule and
the clock -- an operational axis, never knowledge state, and never persisted
as truth. ``OVERDUE_AT_RISK_TRIGGERED``, by contrast, IS a fact: crossing the
at-risk boundary changes knowledge state, so the sweep emits it append-only
with a deterministic ``boundary_at`` (derived from ``next_review_at``, never
the sweep's wall clock) and an idempotency key of (target, dimension,
schedule_epoch) -- re-running the sweep can never mint a second fact, while a
legitimately new schedule epoch can.

The due backlog orders by LOSS RISK, not by idle time (canonical tuple,
scheduler 5): retrievability ascending leads; overdue days only separate near
ties. ``is_prereq_of_next`` and ``weakest_dimension_gap`` are honest zeros
until the learner model and per-dimension gap data exist; the tuple keeps
their slots so the order is stable when they arrive.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.policy import scoring_context
from english_trainer.scoring.transitions import build_state_transition

# Consumed event contracts; literals on purpose -- events are the boundary.
EVIDENCE_ADDED_EVENT = "evidence.added"
REVIEW_OUTCOME_EVENT = "review.outcome"
CANCELLED_EVENT = "review.assignment_cancelled"

EVENT_OVERDUE_AT_RISK = "review.overdue_at_risk"

NOT_DUE = "not_due"
DUE = "due"
OVERDUE = "overdue"

_DAY_SECONDS = Decimal(86400)


@dataclass
class ScheduleState:
    """One (target, dimension) review schedule -- the fold's unit."""

    schedule_epoch: int
    interval_index: int
    interval_days: int
    next_review_at: datetime
    last_outcome: str | None
    last_activity_at: datetime


def fold_schedules(store: EventStore, policy: dict[str, Any]) -> dict[tuple[str, str], ScheduleState]:
    """Fold the event log into review schedules (deterministic)."""
    intervals: list[int] = list(policy["intervals_days"])
    retry_days = int(policy["retry_days"])
    schedules: dict[tuple[str, str], ScheduleState] = {}

    for event in store.read():
        if event.type == EVIDENCE_ADDED_EVENT:
            primary = event.payload.get("primary_target") or {}
            ref = primary.get("target_ref")
            if not ref:
                continue
            key = (str(ref), str(primary.get("dimension") or "recognition"))
            if key in schedules:
                continue  # intervals adapt only through review outcomes
            schedules[key] = ScheduleState(
                schedule_epoch=1,
                interval_index=0,
                interval_days=intervals[0],
                next_review_at=event.occurred_at + timedelta(days=intervals[0]),
                last_outcome=None,
                last_activity_at=event.occurred_at,
            )
        elif event.type == REVIEW_OUTCOME_EVENT:
            payload = event.payload
            ref = payload.get("target_ref")
            if not ref:
                continue
            key = (str(ref), str(payload.get("dimension") or "recognition"))
            state = schedules.get(key)
            if state is None:
                # An outcome for a never-scheduled pair: open a schedule so the
                # fact is not lost (hidden/conversation review, canon 5).
                state = schedules[key] = ScheduleState(
                    1, 0, intervals[0], event.occurred_at, None, event.occurred_at
                )
            outcome = str(payload.get("outcome") or "")
            index = state.interval_index
            if outcome in ("CONFIRMED", "RECOVERED"):
                index = min(index + 1, len(intervals) - 1)
                days = intervals[index]
            elif outcome == "REGRESSION":
                index = max(index - 1, 0)
                days = intervals[index]
            elif outcome == "PROGRESS":
                days = intervals[index]  # hold
            elif outcome == "INSUFFICIENT_EVIDENCE":
                days = retry_days  # hold the index, book a short retry (any reason)
            else:
                continue  # unknown outcome: audited by scoring, no scheduler branch
            state.interval_index = index
            state.interval_days = days
            state.next_review_at = event.occurred_at + timedelta(days=days)
            state.last_outcome = outcome
            state.last_activity_at = event.occurred_at
            state.schedule_epoch += 1
        elif event.type == CANCELLED_EVENT:
            continue  # explicit terminal no-op: no reschedule, no retry [RR2-4]

    return schedules


def review_status(state: ScheduleState, now: datetime, policy: dict[str, Any]) -> str:
    """``not_due / due / overdue`` -- computed, never persisted as truth."""
    if now < state.next_review_at:
        return NOT_DUE
    lateness_days = Decimal((now - state.next_review_at).total_seconds()) / _DAY_SECONDS
    threshold = Decimal(str(policy["overdue_factor"])) * Decimal(state.interval_days)
    return OVERDUE if lateness_days > threshold else DUE


def at_risk_boundary(state: ScheduleState, policy: dict[str, Any]) -> datetime:
    """The deterministic AT_RISK crossing instant -- from the schedule, never
    from the sweep's wall clock."""
    factor = Decimal(str(policy["at_risk_overdue_factor"]))
    seconds = int(factor * Decimal(state.interval_days) * _DAY_SECONDS)
    return state.next_review_at + timedelta(seconds=seconds)


def due_backlog(
    store: EventStore,
    scheduler_policy: dict[str, Any],
    scoring_policy: dict[str, Any],
    program: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """Due/overdue candidates in the canonical priority order (scheduler 5).

    Loss risk leads: retrievability ascending, then curriculum priority, then
    the reserved slots, then overdue days as a near-tie separator, then the
    stable (target_id, dimension_id) tie-breaker.
    """
    context = scoring_context(scoring_policy)
    schedules = fold_schedules(store, scheduler_policy)
    scores = fold_scores(store, scoring_policy)
    priority_rank = {str(t.get("id")): rank for rank, t in enumerate(program.get("topics", []))}

    out: list[dict[str, Any]] = []
    for (target_ref, dimension), state in schedules.items():
        status = review_status(state, now, scheduler_policy)
        if status == NOT_DUE:
            continue
        stability = None
        target_scores = scores.get(target_ref)
        if target_scores is not None and target_scores.stability_days is not None:
            stability = target_scores.stability_days
        if stability is None or stability <= 0:
            retriev = Decimal(0)
        else:
            elapsed = context.divide(
                context.create_decimal(int((now - state.last_activity_at).total_seconds())), _DAY_SECONDS
            )
            with decimal.localcontext(context):
                retriev = (-context.divide(elapsed, stability)).exp()
        overdue_days = int(Decimal((now - state.next_review_at).total_seconds()) / _DAY_SECONDS)
        out.append(
            {
                "target_ref": target_ref,
                "dimension": dimension,
                "status": status,
                "retrievability": str(retriev),
                "overdue_days": overdue_days,
                "schedule_epoch": state.schedule_epoch,
                "interval_days": state.interval_days,
                "next_review_at": state.next_review_at.isoformat(),
                "first_due_at": state.next_review_at.isoformat(),
                "curriculum_priority_rank": priority_rank.get(target_ref, 10_000_000),
                "knowledge_state": target_scores.knowledge_state if target_scores else "NEW",
            }
        )
    out.sort(
        key=lambda c: (
            Decimal(c["retrievability"]),  # risk of loss leads (asc)
            c["curriculum_priority_rank"],
            0,  # is_prereq_of_next desc -- honest zero until the learner model
            0,  # weakest_dimension_gap desc -- honest zero until per-dimension gaps
            -c["overdue_days"],  # desc: separates near ties only
            c["target_ref"],
            c["dimension"],
        )
    )
    return out


def _already_triggered(store: EventStore) -> set[tuple[str, str, int]]:
    seen: set[tuple[str, str, int]] = set()
    for event in store.read():
        if event.type == EVENT_OVERDUE_AT_RISK:
            payload = event.payload
            seen.add(
                (
                    str(payload.get("target_ref")),
                    str(payload.get("dimension")),
                    int(payload.get("schedule_epoch") or 0),
                )
            )
    return seen


def sweep_overdue(
    store: EventStore,
    scheduler_version: str,
    scheduler_policy: dict[str, Any],
    clock: Clock,
    random_source: RandomSource,
    *,
    actor: str = "engine",
) -> list[str]:
    """Emit ``OVERDUE_AT_RISK_TRIGGERED`` for every new boundary crossing.

    Append-only and idempotent by (target, dimension, schedule_epoch): a
    re-run mints nothing, a legitimately new epoch mints a new fact. Returns
    the target refs that crossed. One UnitOfWork for the whole batch.
    """
    schedules = fold_schedules(store, scheduler_policy)
    triggered = _already_triggered(store)
    now = clock.now()
    crossings: list[tuple[tuple[str, str], ScheduleState, datetime]] = []
    for key in sorted(schedules):
        state = schedules[key]
        boundary = at_risk_boundary(state, scheduler_policy)
        if now >= boundary and (key[0], key[1], state.schedule_epoch) not in triggered:
            crossings.append((key, state, boundary))
    if not crossings:
        return []
    registry = PolicyRegistry(store._conn, clock)
    try:
        scoring_version = registry.active_version("scoring")
    except NoActivePolicy:
        scoring_version = None
    source_events = []
    transition_events = []
    state_overrides: dict[str, tuple[str, str | None]] = {}
    for key, state, boundary in crossings:
        pins = {"scheduler": scheduler_version}
        if scoring_version is not None:
            pins["scoring"] = scoring_version
        source = make_event(
            id=new_ulid(clock, random_source),
            type=EVENT_OVERDUE_AT_RISK,
            occurred_at=boundary,
            actor=actor,
            correlation_id=new_ulid(clock, random_source),
            payload={
                "target_ref": key[0],
                "dimension": key[1],
                "schedule_epoch": state.schedule_epoch,
                "boundary_at": boundary.isoformat(),
                "next_review_at": state.next_review_at.isoformat(),
            },
            pinned_versions=pins,
        )
        source_events.append(source)
        transition_event = build_state_transition(
            store,
            registry,
            source,
            before_override=state_overrides.get(key[0]),
        )
        if transition_event is not None:
            transition_events.append(transition_event)
            state_overrides[key[0]] = (
                str(transition_event.payload["to_state"]),
                str(transition_event.payload["from_state"]),
            )
    with UnitOfWork(store, clock) as uow:
        uow.append([*source_events, *transition_events])
    return [key[0] for key, _, _ in crossings]
