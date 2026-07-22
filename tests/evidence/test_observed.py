"""Observed errors: trusted facts, engine classifications, recurring risk."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from english_trainer.control.classify import IMPORTANT, classify_review_candidates
from english_trainer.control.saturation import recurring_error_keys
from english_trainer.evidence.assessment import span_hash
from english_trainer.evidence.attempts import EvidencePrecondition, record_attempt
from english_trainer.evidence.observed import EVENT_ERROR_OBSERVED, record_observed
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import start_session
from tests.evidence.conftest import PROGRAM

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def observed_registry(store: EventStore, clock) -> PolicyRegistry:
    registry = PolicyRegistry(store._conn, clock)
    registry.register("curriculum", "v-test", PROGRAM)
    registry.activate("curriculum", "v-test")
    registry.register("generation", "generation@1", {"policy_id": "generation@1"})
    registry.activate("generation", "generation@1")
    for filename, kind, version in (
        ("control-v1.yaml", "control", "control@1"),
        ("rubric-v1.yaml", "rubric", "rubric@1"),
    ):
        payload = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
        registry.register(kind, version, payload)
        registry.activate(kind, version)
    return registry


def _objective_context(store, registry, clock, rnd) -> tuple[str, str, str]:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    claimed = next_step(
        store,
        registry,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    rendered = record_rendered_exercise(
        store,
        registry,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=str(claimed["step"]["step_id"]),
        exercise={
            "prompt": "Complete: I ___ an engineer.",
            "answer_key": ["am"],
            "provenance": {"origin": "authored"},
        },
    )
    return session_id, str(claimed["step"]["step_id"]), str(rendered["exercise_instance_id"])


def _objective_attempt(store, clock, rnd, context: tuple[str, str, str], answer: str) -> str:
    session_id, step_id, instance_id = context
    attempt = record_attempt(
        store,
        clock,
        rnd,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=step_id,
        exercise_instance_id=instance_id,
        raw_answer=answer,
    )
    return str(attempt["attempt_id"])


def _negative_observation(answer: str) -> dict[str, object]:
    end = len(answer.encode("utf-8"))
    return {
        "rubric_criterion_ref": "rubric:conversation.free#criterion:target-control",
        "finding_code": "target_form_is_incorrect",
        "span_ref": {"start_utf8": 0, "end_utf8": end, "span_hash": span_hash(answer, 0, end)},
    }


def test_real_observed_events_activate_recurring_error_risk(
    store, observed_registry, clock, random_source
) -> None:
    context = _objective_context(store, observed_registry, clock, random_source)
    session_id = context[0]
    for answer in ("are", "is"):
        attempt_id = _objective_attempt(store, clock, random_source, context, answer)
        result = record_observed(
            store,
            observed_registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            kind="error",
            attempt_id=attempt_id,
            observation=_negative_observation(answer),
        )
        assert result["already"] is False

    events = [event for event in store.read() if event.type == EVENT_ERROR_OBSERVED]
    assert len(events) == 2
    assert all(event.payload["severity"] == "major" for event in events)
    policy = observed_registry.resolve_pinned("control", "control@1")
    recurring = recurring_error_keys(store.read(), policy)
    assert ("grammar.be.identity", "recognition") in recurring
    classified = classify_review_candidates(
        [
            {
                "target_ref": "grammar.be.identity",
                "dimension": "recognition",
                "knowledge_state": "ACTIVE",
                "retrievability": "0.900000",
                "schedule_epoch": 1,
            }
        ],
        PROGRAM,
        policy,
        recurring_errors=recurring,
    )
    assert classified[0]["urgency_class"] == IMPORTANT
    assert classified[0]["classification_trace"]["risk_factors"]["recurring_error"] is True


def test_observed_error_that_contradicts_objective_result_is_rejected(
    store, observed_registry, clock, random_source
) -> None:
    context = _objective_context(store, observed_registry, clock, random_source)
    session_id = context[0]
    attempt_id = _objective_attempt(store, clock, random_source, context, "am")
    with pytest.raises(EvidencePrecondition, match="contradicts_machine_result"):
        record_observed(
            store,
            observed_registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            kind="error",
            attempt_id=attempt_id,
            observation=_negative_observation("am"),
        )
    assert [event for event in store.read() if event.type == EVENT_ERROR_OBSERVED] == []
