"""The full review loop across sessions (2.3 increment 3) on the brief/report
protocol [PD-2026-09-23]: reported evidence opens a schedule, the next
session composes a review with its assignment and lists it in the brief, the
report's review item closes it by the tutor's verdict (the engine maps the
outcome), and scoring and the scheduler both move."""

from __future__ import annotations

from pathlib import Path

from english_trainer.evidence.reviews import pending_assignments
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.report import commit_report
from english_trainer.lessons.sessions import FINISHED, abandon_session, get_plan, get_session
from english_trainer.scheduler.engine import fold_schedules
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.transitions import EVENT_STATE_TRANSITION, transition_coverage
from tests.lessons.report_support import EPOCH, item, report, report_registry, start_with_review


def _open(tmp_path: Path) -> tuple[EventStore, PolicyRegistry, FixedClock, SeededRandomSource]:
    conn = connect(tmp_path / "review-loop.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    return EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(20260923)


def _policies(registry: PolicyRegistry) -> tuple[dict, dict]:
    return (
        registry.resolve_pinned("scoring", registry.active_version("scoring")),
        registry.resolve_pinned("scheduler", registry.active_version("scheduler")),
    )


def test_review_loop_closes_end_to_end(tmp_path: Path) -> None:
    store, registry, clock, rnd = _open(tmp_path)
    started, review = start_with_review(store, registry, clock, rnd)
    session_id = str(started["session_id"])
    review_id = str(review["review_id"])
    target, dimension = str(review["target_ref"]), str(review["dimension"])

    # The brief's review is the session's composed review step and its
    # pending assignment -- one goal, one id.
    _, plan, _ = get_plan(store, session_id)
    (step,) = [s for s in plan["steps"] if s.get("review_assignment_id") == review_id]
    assert (step["target_ref"], step["dimension"]) == (target, dimension)
    assignments = pending_assignments(store, session_id)
    assert review_id in {a["review_id"] for a in assignments}

    scoring, scheduler = _policies(registry)
    before = fold_schedules(store, scheduler, registry=registry)[(target, dimension)]
    state_before = fold_scores(store, scoring)[target].knowledge_state

    body = report(
        session_id,
        started["brief"],
        [
            item(
                "rv",
                "I am a quality engineer.",
                target_ref=target,
                dimension=dimension,
                kind="review",
                review_id=review_id,
            )
        ],
    )
    clock.advance(seconds=20 * 60)
    result = commit_report(
        store, registry, clock, rnd, session_id, body, provider="claude-code", idempotency_key="lesson-2"
    )
    assert result["cached"] is False

    outcomes = [e for e in store.read() if e.type == "review.outcome" and e.payload["review_id"] == review_id]
    assert len(outcomes) == 1 and outcomes[0].payload["outcome"] == "CONFIRMED"
    # Every other pending assignment settled INSUFFICIENT_EVIDENCE in the same commit.
    assert pending_assignments(store, session_id) == []

    # The outcome moved BOTH consumers: scoring state and the schedule.
    (transition,) = [
        e for e in store.read() if e.type == EVENT_STATE_TRANSITION and e.causation_id == outcomes[0].id
    ]
    assert transition.payload["from_state"] == state_before
    assert transition.payload["to_state"] == fold_scores(store, scoring)[target].knowledge_state
    after = fold_schedules(store, scheduler, registry=registry)[(target, dimension)]
    assert after.schedule_epoch > before.schedule_epoch
    assert after.interval_days >= before.interval_days and after.last_outcome == "CONFIRMED"
    assert transition_coverage(store)["complete"] is True

    state, _ = get_session(store, session_id)
    assert state["status"] == FINISHED

    # A retried commit with the same key returns the one outcome, no second one.
    again = commit_report(
        store, registry, clock, rnd, session_id, body, provider="claude-code", idempotency_key="lesson-2"
    )
    assert again["cached"] is True
    assert (
        len([e for e in store.read() if e.type == "review.outcome" and e.payload["review_id"] == review_id])
        == 1
    )


def test_abandon_converts_open_assignments(tmp_path: Path) -> None:
    store, registry, clock, rnd = _open(tmp_path)
    started, review = start_with_review(store, registry, clock, rnd)
    session_id = str(started["session_id"])
    open_ids = sorted(a["review_id"] for a in pending_assignments(store, session_id))
    assert review["review_id"] in open_ids

    event = abandon_session(
        store,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert sorted(event.payload["closed_assignments"]) == open_ids
    assert pending_assignments(store, session_id) == []

    outcomes = [e for e in store.read() if e.type == "review.outcome" and e.correlation_id == session_id]
    assert {o.payload["outcome"] for o in outcomes} == {"INSUFFICIENT_EVIDENCE"}
    assert {o.payload["reason"] for o in outcomes} == {"abandoned"}
    transitions = [e for e in store.read() if e.type == EVENT_STATE_TRANSITION]
    assert transitions[-1].causation_id == outcomes[-1].id
    assert transitions[-1].payload["from_state"] == transitions[-1].payload["to_state"]
    assert transition_coverage(store)["missing"] == 0
    assert transition_coverage(store)["complete"] is True
    # The scheduler holds the interval and books the short retry -- no punishment.
    _, scheduler = _policies(registry)
    schedule = fold_schedules(store, scheduler, registry=registry)[
        (review["target_ref"], review["dimension"])
    ]
    assert schedule.last_outcome == "INSUFFICIENT_EVIDENCE"
