"""Accepted exercise-bank reuse across composition, claim and evidence."""

from __future__ import annotations

import copy

import pytest

from english_trainer.evidence.attempts import record_attempt
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.sessions import (
    EVENT_EXERCISE_USED,
    EVENT_STEP_PRESENTED,
    SessionPrecondition,
    start_session,
)
from tests.lessons.conftest import PROGRAM


def _seed_accepted_item(store: EventStore, clock, rnd) -> str:
    instance_id = "bank-001"
    content_hash = "sha256:" + "1" * 64
    state = {
        "exercise_instance_id": instance_id,
        "status": "accepted",
        "content_hash": content_hash,
        "step_type": "new_material_intro",
        "target_refs": ["grammar.be.identity"],
        "dimensions": ["recognition"],
        "context_id": "team-introduction|new_material_intro",
        "lexicon_refs": ["role.engineer"],
        "source_session_id": "source-session",
    }
    rendered = {
        "session_id": "source-session",
        "step_id": "source-step",
        "exercise_instance_id": instance_id,
        "content_hash": content_hash,
        "target_refs": state["target_refs"],
        "dimensions": state["dimensions"],
        "context_id": state["context_id"],
        "lexicon_refs": state["lexicon_refs"],
        "prompt": "Complete: I ___ an engineer.",
        "answer_key": ["am"],
        "rubric_ref": None,
        "provenance": {"origin": "authored"},
    }
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("bank_item", instance_id, state, expected_revision=0)
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type="exercise.rendered",
                    occurred_at=clock.now(),
                    actor="maintainer",
                    correlation_id="source-session",
                    payload=rendered,
                )
            ]
        )
    return instance_id


def test_bank_item_is_reused_and_use_is_atomic_with_delivery(store, registry, clock, random_source) -> None:
    instance_id = _seed_accepted_item(store, clock, random_source)
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])

    claimed = next_step(
        store,
        registry,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    assert claimed["step"]["bank_item_id"] == instance_id
    assert claimed["step"]["generation_directive"] is None
    assert claimed["bank_item"]["prompt"] == "Complete: I ___ an engineer."
    uses = [event for event in store.read() if event.type == EVENT_EXERCISE_USED]
    presented = [event for event in store.read() if event.type == EVENT_STEP_PRESENTED]
    assert len(uses) == 1 and uses[0].causation_id == presented[-1].id
    assert uses[0].payload["active_safety_version"] == "v-test"
    assert [event for event in store.read() if event.type == "evidence.added"] == []

    attempt = record_attempt(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        step_id=str(claimed["step"]["step_id"]),
        exercise_instance_id=instance_id,
        raw_answer="am",
    )
    assert attempt["status"] == "assessed"
    assert len([event for event in store.read() if event.type == "evidence.added"]) == 1


def test_claim_revalidates_bank_item_against_active_safety(store, registry, clock, random_source) -> None:
    _seed_accepted_item(store, clock, random_source)
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    unsafe = copy.deepcopy(PROGRAM)
    unsafe["topics"] = [topic for topic in unsafe["topics"] if topic["id"] != "grammar.be.identity"]
    registry.register("curriculum", "v-unsafe", unsafe)
    registry.activate("curriculum", "v-unsafe")

    with pytest.raises(SessionPrecondition, match="safety_changed"):
        next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            expected_plan_version=1,
        )
    assert [event for event in store.read() if event.type == EVENT_EXERCISE_USED] == []
    assert read_aggregate(store._conn, "session_plan", manifest["session_plan_id"])[0]["plan_version"] == 1
