"""The scheduler fold: interval adaptation, computed statuses, the canonical
backlog order, and the replayable AT_RISK sweep (canon 0.4 part 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scheduler.engine import (
    DUE,
    EVENT_OVERDUE_AT_RISK,
    NOT_DUE,
    OVERDUE,
    at_risk_boundary,
    due_backlog,
    fold_schedules,
    review_status,
    sweep_overdue,
)
from english_trainer.scheduler.policy import validate_scheduler_policy
from english_trainer.scoring.engine import AT_RISK, fold_scores

EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


def _emit(store: EventStore, clock, rnd, event_type: str, payload: dict[str, Any]) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="corr",
                    payload=payload,
                )
            ]
        )


def _evidence(store, clock, rnd, target="t.a", dimension="recognition") -> None:
    _emit(
        store,
        clock,
        rnd,
        "evidence.added",
        {
            "evidence_id": new_ulid(clock, rnd),
            "session_id": "s1",
            "primary_target": {"target_ref": target, "dimension": dimension},
            "origin": "session",
            "assessment_basis": "objective_check",
            "correct": True,
            "hints": 0,
        },
    )


def _outcome(store, clock, rnd, target="t.a", outcome="CONFIRMED", dimension="recognition") -> None:
    _emit(
        store,
        clock,
        rnd,
        "review.outcome",
        {"target_ref": target, "dimension": dimension, "outcome": outcome, "origin": "session"},
    )


def test_the_shipped_policy_is_valid(scheduler_policy) -> None:
    assert validate_scheduler_policy(scheduler_policy) == []


def test_first_evidence_opens_the_schedule(store, clock, random_source, scheduler_policy) -> None:
    _evidence(store, clock, random_source)
    _evidence(store, clock, random_source)  # more evidence does not reschedule
    schedules = fold_schedules(store, scheduler_policy)
    state = schedules[("t.a", "recognition")]
    assert state.schedule_epoch == 1 and state.interval_index == 0
    assert state.next_review_at == EPOCH + timedelta(days=1)


def test_outcomes_adapt_the_interval(store, clock, random_source, scheduler_policy) -> None:
    _evidence(store, clock, random_source)
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # 1 -> 3 days
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # 3 -> 7 days
    schedules = fold_schedules(store, scheduler_policy)
    state = schedules[("t.a", "recognition")]
    assert state.interval_days == 7 and state.schedule_epoch == 3

    _outcome(store, clock, random_source, outcome="REGRESSION")  # step back -> 3
    _outcome(store, clock, random_source, outcome="PROGRESS")  # hold -> 3
    _outcome(store, clock, random_source, outcome="INSUFFICIENT_EVIDENCE")  # hold index, retry 1d
    schedules = fold_schedules(store, scheduler_policy)
    state = schedules[("t.a", "recognition")]
    assert state.interval_index == 1  # held through PROGRESS and INSUFFICIENT
    assert state.interval_days == 1  # the short retry
    assert state.next_review_at == EPOCH + timedelta(days=1)

    # CANCELLED is an explicit terminal no-op: nothing moves [RR2-4].
    before = state.schedule_epoch
    _emit(store, clock, random_source, "review.assignment_cancelled", {"target_ref": "t.a"})
    assert fold_schedules(store, scheduler_policy)[("t.a", "recognition")].schedule_epoch == before


def test_review_status_is_computed_not_stored(store, clock, random_source, scheduler_policy) -> None:
    _evidence(store, clock, random_source)
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]
    assert review_status(state, EPOCH, scheduler_policy) == NOT_DUE
    assert review_status(state, EPOCH + timedelta(days=1, hours=1), scheduler_policy) == DUE
    # overdue when lateness > 0.5 * interval (interval 1d => boundary at +1.5d)
    assert review_status(state, EPOCH + timedelta(days=2, hours=13), scheduler_policy) == OVERDUE


def test_backlog_orders_by_loss_risk_not_idle_time(
    store, clock, random_source, scheduler_policy, scoring_policy
) -> None:
    _evidence(store, clock, random_source, target="t.peripheral")
    _evidence(store, clock, random_source, target="t.core")
    # t.core gains high stability (short elapsed decay), t.peripheral stays at
    # the initial 2 days -- its retrievability collapses over the same gap.
    for _ in range(3):
        _outcome(store, clock, random_source, target="t.core", outcome="CONFIRMED")
    program = {"topics": [{"id": "t.core"}, {"id": "t.peripheral"}]}
    now = EPOCH + timedelta(days=40)
    backlog = due_backlog(store, scheduler_policy, scoring_policy, program, now)
    assert [c["target_ref"] for c in backlog] == ["t.peripheral", "t.core"]
    # ...even though t.core is "more overdue" by schedule bookkeeping is irrelevant:
    # risk of loss leads the canonical tuple, idle time only separates near ties.
    assert all(c["status"] in (DUE, OVERDUE) for c in backlog)


def test_sweep_is_idempotent_and_boundary_deterministic(
    store, clock, random_source, scheduler_policy, scoring_policy
) -> None:
    _evidence(store, clock, random_source)
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]
    boundary = at_risk_boundary(state, scheduler_policy)
    assert boundary == EPOCH + timedelta(days=2)  # next_review (+1d) + 1.0 * interval (1d)

    late = FixedClock(EPOCH + timedelta(days=5))
    crossed = sweep_overdue(store, "scheduler@1", scheduler_policy, late, random_source)
    assert crossed == ["t.a"]
    (event,) = [e for e in store.read() if e.type == EVENT_OVERDUE_AT_RISK]
    assert event.payload["boundary_at"] == boundary.isoformat()  # never the sweep's wall clock
    assert event.occurred_at == boundary
    assert event.pinned_versions == {"scheduler": "scheduler@1"}

    # Re-running the sweep (even later) mints nothing: same (target, dim, epoch).
    again = sweep_overdue(
        store, "scheduler@1", scheduler_policy, FixedClock(EPOCH + timedelta(days=9)), random_source
    )
    assert again == []
    assert len([e for e in store.read() if e.type == EVENT_OVERDUE_AT_RISK]) == 1


def test_swept_fact_flips_scoring_to_at_risk(
    store, clock, random_source, scheduler_policy, scoring_policy
) -> None:
    _evidence(store, clock, random_source)
    _outcome(store, clock, random_source, outcome="PROGRESS")  # NEW -> LEARNING
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # LEARNING -> ACTIVE
    late = FixedClock(EPOCH + timedelta(days=30))
    sweep_overdue(store, "scheduler@1", scheduler_policy, late, random_source)
    scores = fold_scores(store, scoring_policy)
    assert scores["t.a"].knowledge_state == AT_RISK  # the event, not a clock, moved it
    assert scores["t.a"].prior_steady_state == "ACTIVE"
