"""Attempt admissibility and capture (0.4): the engine derives the facts, the
event carries everything scoring will need, semantic identity holds."""

from __future__ import annotations

import pytest

from english_trainer.evidence.attempts import (
    ASSESSED,
    EVENT_ATTEMPT_RECORDED,
    RECORDED,
    STEP_PRESENTED_EVENT,
    EvidencePrecondition,
    list_notes,
    record_attempt,
    session_attempts,
)
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import abandon_session, start_session

EXERCISE = {
    "prompt": "Complete: I ___ an engineer.",
    "answer_key": ["am", "I am"],
    "provenance": {"origin": "authored"},
}


def _present(store: EventStore, registry: PolicyRegistry, clock, rnd) -> tuple[str, str]:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    result = next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    return session_id, str(result["step"]["step_id"])


def _fabricate_step(
    store: EventStore, clock, rnd, session_id: str, *, step_id: str, step_type: str, kind: str
) -> None:
    """Seed a STEP_PRESENTED fact directly: evidence trusts the event log, so
    tests can exercise step types the current composer does not emit yet."""
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=STEP_PRESENTED_EVENT,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=session_id,
                    payload={
                        "step_id": step_id,
                        "session_id": session_id,
                        "step_type": step_type,
                        "kind": kind,
                        "targets": [{"target_ref": "grammar.be.identity", "dimension": "recognition"}],
                        "context_id": "team-introduction|" + step_type,
                    },
                )
            ]
        )


def test_open_attempt_records_with_derived_facts(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    result = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="I am an engineer at Vercel.",
        note="learner asked to focus on work vocabulary",
    )
    assert result["status"] == RECORDED and result["assessment"] is None
    assert result["origin"] == "session"
    assert result["primary_target"] == {"target_ref": "grammar.be.identity", "dimension": "recognition"}

    (event,) = [e for e in store.read() if e.type == EVENT_ATTEMPT_RECORDED]
    assert event.correlation_id == session_id
    assert event.payload["raw_answer"] == "I am an engineer at Vercel."
    assert event.payload["selection_basis"] == "canonical_order"
    assert event.payload["mode"] == "new_material_intro"
    assert event.pinned_versions["curriculum"] == "v-test"  # capture-into-event
    aggregate = read_aggregate(store._conn, "attempt", result["attempt_id"])
    assert aggregate is not None and aggregate[0]["status"] == RECORDED

    notes = list_notes(store, session_id)
    assert len(notes) == 1
    assert notes[0]["author_provider"] == "claude-code"
    assert notes[0]["text"] == "learner asked to focus on work vocabulary"


def test_objective_check_assesses_against_the_stored_snapshot(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    rendered = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    instance = rendered["exercise_instance_id"]

    correct = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="  AM ",  # normalization: NFC + casefold + whitespace collapse
        exercise_instance_id=instance,
    )
    assert correct["status"] == ASSESSED
    assert correct["assessment"]["correct"] is True
    assert correct["assessment"]["score_ppm"] == 1_000_000
    assert correct["assessment"]["checked_against_content_hash"] == rendered["content_hash"]
    assert correct["primary_target"]["target_ref"] == "grammar.be.identity"
    assert correct["selection_basis"] == "declared_item_target"

    wrong = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="is",
        exercise_instance_id=instance,
    )
    assert wrong["assessment"]["correct"] is False and wrong["assessment"]["score_ppm"] == 0


def test_structured_step_requires_the_snapshot(store, registry, clock, random_source) -> None:
    session_id, _ = _present(store, registry, clock, random_source)
    _fabricate_step(
        store, clock, random_source, session_id, step_id="rc-1", step_type="recognition_check", kind="review"
    )
    with pytest.raises(EvidencePrecondition, match="structured check"):
        record_attempt(store, clock, random_source, session_id, step_id="rc-1", raw_answer="b")


def test_probe_origin_is_derived_never_claimed(store, registry, clock, random_source) -> None:
    session_id, _ = _present(store, registry, clock, random_source)
    _fabricate_step(
        store, clock, random_source, session_id, step_id="pr-1", step_type="transfer_task", kind="probe"
    )
    result = record_attempt(
        store, clock, random_source, session_id, step_id="pr-1", raw_answer="I have been an engineer."
    )
    assert result["origin"] == "control_probe"  # no CLI flag can produce this


def test_attempt_requires_a_delivered_step_and_an_active_session(
    store, registry, clock, random_source
) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    with pytest.raises(EvidencePrecondition, match="STEP_PRESENTED"):
        record_attempt(store, clock, random_source, session_id, step_id="ghost", raw_answer="x")
    with pytest.raises(EvidencePrecondition, match="empty"):
        record_attempt(store, clock, random_source, session_id, step_id=step_id, raw_answer="   ")

    abandon_session(store, clock, random_source, session_id)
    with pytest.raises(EvidencePrecondition, match="closed"):
        record_attempt(store, clock, random_source, session_id, step_id=step_id, raw_answer="I am here.")


def test_exercise_instance_must_match_the_step(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    rendered = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    result = next_step(store, registry, clock, random_source, session_id, expected_plan_version=2)
    other_step = str(result["step"]["step_id"])
    with pytest.raises(EvidencePrecondition, match="rendered for step"):
        record_attempt(
            store,
            clock,
            random_source,
            session_id,
            step_id=other_step,
            raw_answer="am",
            exercise_instance_id=rendered["exercise_instance_id"],
        )


def test_same_span_same_target_is_refused(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    record_attempt(store, clock, random_source, session_id, step_id=step_id, raw_answer="I am an engineer.")
    with pytest.raises(EvidencePrecondition, match="already recorded"):
        record_attempt(
            store, clock, random_source, session_id, step_id=step_id, raw_answer="I am an engineer."
        )
    # The same words aimed at a DIFFERENT target are a new fact, not a replay.
    result = next_step(store, registry, clock, random_source, session_id, expected_plan_version=2)
    other = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=str(result["step"]["step_id"]),
        raw_answer="I am an engineer.",
    )
    assert other["primary_target"]["target_ref"] == "grammar.pronouns.possessives"
    assert len(session_attempts(store, session_id)) == 2
