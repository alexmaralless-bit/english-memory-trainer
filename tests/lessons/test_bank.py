"""The exercise bank: earned admission, closed reason enums, terminal states,
near-duplicate refusal (generation@1 bank_lifecycle, PD-2 A)."""

from __future__ import annotations

import pytest

from english_trainer.evidence.attempts import record_attempt
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.bank import (
    EVENT_EXERCISE_ACCEPTED,
    BankPrecondition,
    accept_exercise,
    bank_items,
    reject_exercise,
    retire_exercise,
)
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import start_session

EXERCISE = {
    "prompt": "Complete: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}


def _present(store: EventStore, registry: PolicyRegistry, clock, rnd) -> tuple[str, str]:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    result = next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    return session_id, str(result["step"]["step_id"])


def _render(store, registry, clock, rnd, session_id, step_id, exercise=None) -> str:
    result = record_rendered_exercise(
        store, registry, clock, rnd, session_id, step_id=step_id, exercise=dict(exercise or EXERCISE)
    )
    return str(result["exercise_instance_id"])


def test_admission_requires_an_assessed_attempt(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    instance = _render(store, registry, clock, random_source, session_id, step_id)
    with pytest.raises(BankPrecondition, match="assessed attempt"):
        accept_exercise(store, registry, clock, random_source, instance)
    assert bank_items(store) == []  # the refusal banked nothing

    record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer="am",
        exercise_instance_id=instance,
    )
    result = accept_exercise(store, registry, clock, random_source, instance)
    assert result["status"] == "accepted"

    (item,) = bank_items(store, status="accepted")
    assert item["exercise_instance_id"] == instance
    assert item["admission_basis"] == "assessed_attempt"
    assert item["step_type"] == "new_material_intro"
    assert item["target_refs"] == ["grammar.be.identity"]
    (event,) = [e for e in store.read() if e.type == EVENT_EXERCISE_ACCEPTED]
    assert event.payload["exercise_instance_id"] == instance

    # Idempotent re-accept: already banked, no second event.
    again = accept_exercise(store, registry, clock, random_source, instance)
    assert again.get("already") is True
    assert len([e for e in store.read() if e.type == EVENT_EXERCISE_ACCEPTED]) == 1


def test_maintainer_fast_path_needs_its_reason(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    instance = _render(store, registry, clock, random_source, session_id, step_id)
    result = accept_exercise(
        store,
        registry,
        clock,
        random_source,
        instance,
        maintainer_reason="reviewed schema, safety, answer key; text is authored",
    )
    assert result["status"] == "accepted"
    (item,) = bank_items(store)
    assert item["admission_basis"] == "maintainer_fast_path"


def test_near_duplicate_of_an_accepted_item_is_refused(store, registry, clock, random_source) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    first = _render(store, registry, clock, random_source, session_id, step_id)
    accept_exercise(store, registry, clock, random_source, first, maintainer_reason="reviewed")
    # Same prompt modulo whitespace/case => same canonical dedup key.
    twin = _render(
        store,
        registry,
        clock,
        random_source,
        session_id,
        step_id,
        {**EXERCISE, "prompt": "  complete:   I ___ an ENGINEER.  "},
    )
    with pytest.raises(BankPrecondition, match="near-duplicate"):
        accept_exercise(store, registry, clock, random_source, twin, maintainer_reason="reviewed")
    # A genuinely different exercise for the same target is fine.
    other = _render(
        store,
        registry,
        clock,
        random_source,
        session_id,
        step_id,
        {
            **EXERCISE,
            "prompt": "Fill in the missing form of be: my manager ___ in the office today.",
            "answer_key": ["is"],
        },
    )
    accepted = accept_exercise(store, registry, clock, random_source, other, maintainer_reason="reviewed")
    assert accepted["status"] == "accepted"


def test_reject_and_retire_enforce_closed_enums_and_transitions(
    store, registry, clock, random_source
) -> None:
    session_id, step_id = _present(store, registry, clock, random_source)
    instance = _render(store, registry, clock, random_source, session_id, step_id)

    with pytest.raises(BankPrecondition, match="unknown rejection reason"):
        reject_exercise(store, clock, random_source, instance, reason="did not like it")
    rejected = reject_exercise(store, clock, random_source, instance, reason="ambiguous_answer_key")
    assert rejected["status"] == "rejected"
    with pytest.raises(BankPrecondition, match="terminal"):
        accept_exercise(store, registry, clock, random_source, instance, maintainer_reason="r")
    with pytest.raises(BankPrecondition, match="only an accepted item"):
        retire_exercise(store, clock, random_source, instance, reason="target_retired")

    second = _render(store, registry, clock, random_source, session_id, step_id)
    accept_exercise(store, registry, clock, random_source, second, maintainer_reason="reviewed")
    with pytest.raises(BankPrecondition, match="unknown retirement reason"):
        retire_exercise(store, clock, random_source, second, reason="tired")
    retired = retire_exercise(store, clock, random_source, second, reason="target_retired")
    assert retired["status"] == "retired"
    statuses = {i["exercise_instance_id"]: i["status"] for i in bank_items(store)}
    assert statuses[instance] == "rejected" and statuses[second] == "retired"
