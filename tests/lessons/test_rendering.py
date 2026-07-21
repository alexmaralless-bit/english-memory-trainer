"""EXERCISE_RENDERED: the snapshot commits before the learner sees the prompt
(P.3 PD-1 A), anchored to a delivered step, authored-text only."""

from __future__ import annotations

import pytest

from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.delivery import next_step
from english_trainer.lessons.rendering import (
    EVENT_EXERCISE_RENDERED,
    find_rendered_exercise,
    record_rendered_exercise,
)
from english_trainer.lessons.sessions import SessionPrecondition, abandon_session, start_session

EXERCISE = {
    "prompt": "Complete the sentence: I ___ an engineer.",
    "answer_key": ["am"],
    "distractor_error_refs": ["be.omission"],
    "lexicon_refs": [],
    "provenance": {"origin": "authored", "provider": "claude-code"},
}


def _start_and_present(store: EventStore, registry: PolicyRegistry, clock, rnd) -> tuple[str, str]:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    result = next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    return session_id, str(result["step"]["step_id"])


def test_rendered_snapshot_is_complete_and_hashed(store, registry, clock, random_source) -> None:
    session_id, step_id = _start_and_present(store, registry, clock, random_source)
    result = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    stored = find_rendered_exercise(store, session_id, result["exercise_instance_id"])
    assert stored is not None
    # The snapshot carries everything replay needs (generation@1 minimum payload).
    assert stored["step_id"] == step_id
    assert stored["target_refs"] == ["grammar.be.identity"]
    assert stored["dimensions"] == ["recognition"]
    assert stored["prompt"] == EXERCISE["prompt"]
    assert stored["answer_key"] == ["am"] and stored["rubric_ref"] is None
    assert stored["generation_policy_version"] == "generation@1"
    assert stored["pinned_curriculum_version"] == "v-test"
    assert stored["active_safety_version"] == "v-test"
    assert stored["provider"] == "claude-code"
    # The engine owns content identity: the hash covers what the learner faces.
    assert result["content_hash"] == payload_hash(
        {
            "prompt": EXERCISE["prompt"],
            "answer_key": ["am"],
            "rubric_ref": None,
            "distractor_error_refs": ["be.omission"],
            "lexicon_refs": [],
        }
    )


def test_same_content_same_hash_new_instance(store, registry, clock, random_source) -> None:
    session_id, step_id = _start_and_present(store, registry, clock, random_source)
    first = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    second = record_rendered_exercise(
        store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
    )
    assert first["content_hash"] == second["content_hash"]
    assert first["exercise_instance_id"] != second["exercise_instance_id"]
    rendered = [e for e in store.read() if e.type == EVENT_EXERCISE_RENDERED]
    assert len(rendered) == 2


def test_render_requires_a_presented_step(store, registry, clock, random_source) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    with pytest.raises(SessionPrecondition, match="STEP_PRESENTED"):
        record_rendered_exercise(
            store,
            registry,
            clock,
            random_source,
            str(manifest["session_id"]),
            step_id="nonexistent-step",
            exercise=dict(EXERCISE),
        )


def test_render_refuses_a_closed_session(store, registry, clock, random_source) -> None:
    session_id, step_id = _start_and_present(store, registry, clock, random_source)
    abandon_session(store, clock, random_source, session_id)
    with pytest.raises(SessionPrecondition, match="active"):
        record_rendered_exercise(
            store, registry, clock, random_source, session_id, step_id=step_id, exercise=dict(EXERCISE)
        )


@pytest.mark.parametrize(
    ("broken", "complaint"),
    [
        ({"prompt": "   "}, "prompt"),
        ({"answer_key": None}, "exactly one"),  # neither key nor rubric
        ({"rubric_ref": "rubric:writing@1"}, "exactly one"),  # both
        ({"provenance": {"origin": "quoted"}}, "authored"),
        ({"provenance": None}, "authored"),
    ],
)
def test_invalid_exercises_are_refused(store, registry, clock, random_source, broken, complaint) -> None:
    session_id, step_id = _start_and_present(store, registry, clock, random_source)
    exercise = {**EXERCISE, **broken}
    with pytest.raises(SessionPrecondition, match=complaint):
        record_rendered_exercise(
            store, registry, clock, random_source, session_id, step_id=step_id, exercise=exercise
        )
    assert not [e for e in store.read() if e.type == EVENT_EXERCISE_RENDERED]  # nothing written
