"""The full review loop across sessions (2.3 increment 3): evidence opens a
schedule, the next session composes a review step with its assignment, close
computes the outcome, scoring and the scheduler both move."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from english_trainer.evidence.attempts import record_attempt
from english_trainer.evidence.reviews import close_review, pending_assignments
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.lessons.delivery import next_step, replan_session
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    finish_session,
    get_plan,
    start_session,
)
from english_trainer.scheduler.engine import fold_schedules
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.transitions import EVENT_STATE_TRANSITION, transition_coverage

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)  # matches the conftest clock

EXERCISE = {
    "prompt": "Choose the form of be: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}


def _first_session_with_evidence(store, full_registry, clock, rnd) -> str:
    """Day 0: deliver the first growth step, answer it correctly, finish."""
    manifest = start_session(store, full_registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    assert manifest["pinned_versions"]["scheduler"] == "scheduler@1"
    result = next_step(
        store,
        full_registry,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    step_id = str(result["step"]["step_id"])
    rendered = record_rendered_exercise(
        store,
        full_registry,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step_id,
        exercise=dict(EXERCISE),
    )
    record_attempt(
        store,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step_id,
        raw_answer="am",
        exercise_instance_id=rendered["exercise_instance_id"],
    )
    finish_session(
        store,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    return session_id


def _next_until_review(store, registry, clock, rnd, session_id) -> dict:
    version = 1
    while True:
        result = next_step(
            store,
            registry,
            clock,
            rnd,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            expected_plan_version=version,
        )
        version = result["plan_version"]
        if result["step"]["kind"] == "review":
            return result["step"]


def test_review_loop_closes_end_to_end(store, full_registry, clock, random_source) -> None:
    _first_session_with_evidence(store, full_registry, clock, random_source)

    # Two days later the schedule (first interval: 1 day) is overdue.
    later = FixedClock(EPOCH + timedelta(days=2))
    manifest = start_session(store, full_registry, later, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    _, plan, _ = get_plan(store, session_id)
    review_steps = [s for s in plan["steps"] if s["kind"] == "review"]
    assert len(review_steps) == 1
    review = review_steps[0]
    assert review["target_ref"] == "grammar.be.identity"
    assert review["step_type"] == "recognition_check"
    assert review["urgency_class"] == "important"  # R ~ 0.37 < critical floor, no stake data
    review_id = str(review["review_assignment_id"])
    composition_prediction_ppm = int(review["decision_trace"]["computed_inputs"]["retrievability_ppm"])
    (assignment,) = pending_assignments(store, session_id)
    assert assignment["review_id"] == review_id and assignment["step_id"] == review["step_id"]

    # Deliver up to the review step; the open assignment now gates finish (0.5).
    later.advance(seconds=86_400)  # delivery is a day after composition
    step = _next_until_review(store, full_registry, later, random_source, session_id)
    presented = [
        event
        for event in store.read()
        if event.type == "session.step_presented" and event.payload.get("step_id") == step["step_id"]
    ]
    assert presented[-1].payload["review_assignment_id"] == review_id
    issued_prediction_ppm = int(Decimal(presented[-1].payload["predicted_retrievability"]) * 1_000_000)
    assert issued_prediction_ppm < composition_prediction_ppm
    with pytest.raises(SessionPrecondition, match="review assignment"):
        finish_session(
            store,
            later,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
        )
    rendered = record_rendered_exercise(
        store,
        full_registry,
        later,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step["step_id"],
        exercise=dict(EXERCISE),
    )
    record_attempt(
        store,
        later,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step["step_id"],
        raw_answer="AM",
        exercise_instance_id=rendered["exercise_instance_id"],
    )
    closed = close_review(
        store,
        later,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert closed["outcome"] == "CONFIRMED" and closed["already"] is False
    again = close_review(
        store,
        later,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert again["already"] is True and again["outcome"] == "CONFIRMED"  # idempotent, one outcome

    # The outcome moved BOTH consumers: scoring state and the schedule.
    scores = fold_scores(store, full_registry.resolve_pinned("scoring", "scoring@1"))
    assert scores["grammar.be.identity"].knowledge_state == "LEARNING"  # NEW + CONFIRMED
    schedules = fold_schedules(store, full_registry.resolve_pinned("scheduler", "scheduler@1"))
    schedule = schedules[("grammar.be.identity", "recognition")]
    assert schedule.interval_days == 3 and schedule.schedule_epoch == 2  # stepped forward

    # Pending set is empty now; finish succeeds.
    assert pending_assignments(store, session_id) == []
    finish_session(
        store,
        later,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )


def test_abandon_converts_open_assignments(store, full_registry, clock, random_source) -> None:
    _first_session_with_evidence(store, full_registry, clock, random_source)
    later = FixedClock(EPOCH + timedelta(days=2))
    manifest = start_session(store, full_registry, later, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    (assignment,) = pending_assignments(store, session_id)

    event = abandon_session(
        store,
        later,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert event.payload["closed_assignments"] == [assignment["review_id"]]
    assert pending_assignments(store, session_id) == []

    outcomes = [e for e in store.read() if e.type == "review.outcome"]
    assert outcomes[-1].payload["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert outcomes[-1].payload["reason"] == "abandoned"
    transitions = [e for e in store.read() if e.type == EVENT_STATE_TRANSITION]
    assert transitions[-1].causation_id == outcomes[-1].id
    assert transitions[-1].payload["from_state"] == transitions[-1].payload["to_state"]
    assert transition_coverage(store)["missing"] == 0
    assert transition_coverage(store)["complete"] is True
    # The scheduler holds the interval and books the short retry -- no punishment.
    schedules = fold_schedules(store, full_registry.resolve_pinned("scheduler", "scheduler@1"))
    schedule = schedules[("grammar.be.identity", "recognition")]
    assert schedule.interval_index == 0 and schedule.interval_days == 1


def test_replan_keeps_the_surviving_assignment_id(store, full_registry, clock, random_source) -> None:
    _first_session_with_evidence(store, full_registry, clock, random_source)
    later = FixedClock(EPOCH + timedelta(days=2))
    manifest = start_session(store, full_registry, later, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    _, plan, _ = get_plan(store, session_id)
    (before,) = [s for s in plan["steps"] if s["kind"] == "review"]

    replan_session(
        store,
        full_registry,
        later,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    _, plan2, _ = get_plan(store, session_id)
    (after,) = [s for s in plan2["steps"] if s["kind"] == "review"]
    # Still due, still the same goal: assignment and step ids are stable, no
    # cancellation event was minted.
    assert after["review_assignment_id"] == before["review_assignment_id"]
    assert after["step_id"] == before["step_id"]
    assert not [e for e in store.read() if e.type == "review.assignment_cancelled"]
    assert len(pending_assignments(store, session_id)) == 1
