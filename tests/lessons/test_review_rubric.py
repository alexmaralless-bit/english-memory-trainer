"""close_review over OPEN (rubric) review answers (finding 2 regression).

A review answered with an open attempt is recorded then finalized via
``attempt.state_changed`` (never ``attempt.recorded(assessed)``); the outcome
must be read from the FINALIZED assessment, so a strong answer CONFIRMS, a weak
one REGRESSES, and an unanswered step stays INSUFFICIENT_EVIDENCE. The objective
path (already covered by ``test_review_loop``) is unaffected.
"""

from __future__ import annotations

from typing import Any

import yaml

from english_trainer.evidence.assessment import finalize_attempt, span_hash
from english_trainer.evidence.attempts import record_attempt
from english_trainer.evidence.reviews import REVIEW_AGGREGATE, close_review
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.sessions import EVENT_STEP_PRESENTED, start_session
from english_trainer.scheduler.engine import fold_schedules
from english_trainer.scoring.engine import fold_scores
from tests.lessons.conftest import REPO

TARGET = "grammar.past-simple.narrative"
DIMENSION = "spontaneous_production"
ANSWER = (
    "Yesterday I fixed the broken deploy, then I wrote a short note so the team "
    "knew what changed and why it mattered for the release."
)


def _rubric_registry(full_registry: PolicyRegistry) -> PolicyRegistry:
    """The review-loop registry plus rubric@1 (needed to finalize open answers)."""
    payload = yaml.safe_load((REPO / "curriculum" / "policies" / "rubric-v1.yaml").read_text("utf-8"))
    full_registry.register("rubric", "rubric@1", payload)
    full_registry.activate("rubric", "rubric@1")
    return full_registry


def _obs(criterion: str, finding: str) -> dict[str, Any]:
    end = len(ANSWER.encode("utf-8"))
    return {
        "rubric_criterion_ref": f"rubric:production.spontaneous#criterion:{criterion}",
        "finding_code": finding,
        "span_ref": {"start_utf8": 0, "end_utf8": end, "span_hash": span_hash(ANSWER, 0, end)},
    }


# One finding per required criterion of production.spontaneous. Strong findings
# (units 2) land level 2; weak findings (units 1) land level 1.
_STRONG = [
    _obs("target-control", "target_used_in_required_function"),
    _obs("meaning-clarity", "main_message_is_recoverable"),
    _obs("context-adaptation", "target_is_adapted_to_new_context"),
    _obs("language-control", "well_formed_clause"),
    _obs("independent-expression", "learner_adds_independent_clause"),
]
_WEAK = [
    _obs("target-control", "target_surface_present"),
    _obs("meaning-clarity", "reference_is_clear"),
    _obs("context-adaptation", "context_specific_detail_is_relevant"),
    _obs("language-control", "well_formed_clause"),
    _obs("independent-expression", "learner_adds_relevant_detail"),
]


def _open_review(store: EventStore, registry: PolicyRegistry, clock, rnd) -> tuple[str, str]:
    """Start a session and present an OPEN (spontaneous_production) review step
    carrying a target; return ``(session_id, step_id)``."""
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    step_id = "open-review-step"
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=EVENT_STEP_PRESENTED,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "step_id": step_id,
                        "step_type": DIMENSION,
                        "kind": "review",
                        "targets": [{"target_ref": TARGET, "dimension": DIMENSION}],
                    },
                )
            ]
        )
    return session_id, step_id


def _assignment(store: EventStore, clock, session_id: str, step_id: str) -> str:
    review_id = "open-review-1"
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            REVIEW_AGGREGATE,
            review_id,
            {
                "review_id": review_id,
                "session_id": session_id,
                "step_id": step_id,
                "target_ref": TARGET,
                "dimension": DIMENSION,
                "schedule_epoch": 1,
                "status": "pending",
                "created_at": clock.now().isoformat(),
            },
            expected_revision=0,
        )
    return review_id


def test_strong_open_review_confirms_and_moves_both_consumers(
    store, full_registry, clock, random_source
) -> None:
    registry = _rubric_registry(full_registry)
    session_id, step_id = _open_review(store, registry, clock, random_source)
    recorded = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step_id,
        raw_answer=ANSWER,
        observations=_STRONG,
    )
    assert recorded["status"] == "recorded"  # open answer waits for the rubric
    result = finalize_attempt(
        store,
        registry,
        clock,
        random_source,
        session_id,
        recorded["attempt_id"],
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert result["disposition"] == "scored" and result["contributing"] and result["score_ppm"] >= 500_000

    review_id = _assignment(store, clock, session_id, step_id)
    closed = close_review(
        store,
        clock,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert closed["outcome"] == "CONFIRMED" and closed["reason"] is None

    # BOTH consumers moved: scoring state (NEW + CONFIRMED = LEARNING) and the
    # schedule (opened by EVIDENCE_ADDED, stepped forward by the outcome).
    scores = fold_scores(store, full_registry.resolve_pinned("scoring", "scoring@1"))
    assert scores[TARGET].knowledge_state == "LEARNING"
    schedules = fold_schedules(store, full_registry.resolve_pinned("scheduler", "scheduler@1"))
    schedule = schedules[(TARGET, DIMENSION)]
    assert schedule.schedule_epoch == 2 and schedule.interval_index == 1  # stepped forward

    # Idempotent re-close returns the same outcome, no second REVIEW_OUTCOME.
    again = close_review(
        store,
        clock,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert again["already"] is True and again["outcome"] == "CONFIRMED"
    assert len([e for e in store.read() if e.type == "review.outcome"]) == 1


def test_weak_open_review_regresses(store, full_registry, clock, random_source) -> None:
    registry = _rubric_registry(full_registry)
    session_id, step_id = _open_review(store, registry, clock, random_source)
    recorded = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step_id,
        raw_answer=ANSWER,
        observations=_WEAK,
    )
    result = finalize_attempt(
        store,
        registry,
        clock,
        random_source,
        session_id,
        recorded["attempt_id"],
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert result["disposition"] == "scored" and result["score_ppm"] < 500_000

    review_id = _assignment(store, clock, session_id, step_id)
    closed = close_review(
        store,
        clock,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert closed["outcome"] == "REGRESSION"  # scored, contributing, but below the v1 threshold


def test_unanswered_open_review_is_insufficient_evidence(store, full_registry, clock, random_source) -> None:
    registry = _rubric_registry(full_registry)
    session_id, step_id = _open_review(store, registry, clock, random_source)
    # No attempt recorded for the step at all.
    review_id = _assignment(store, clock, session_id, step_id)
    closed = close_review(
        store,
        clock,
        random_source,
        session_id,
        review_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
    assert closed["outcome"] == "INSUFFICIENT_EVIDENCE" and closed["reason"] == "not_attempted"
