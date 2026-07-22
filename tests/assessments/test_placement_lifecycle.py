"""Placement lifecycle: transitions, illegal-transition refusals, idempotent
terminal submit (assessments 2)."""

from __future__ import annotations

import pytest

from english_trainer.assessments.placement import (
    PlacementPrecondition,
    abandon_placement,
    active_placement_id,
    answer_placement,
    get_placement,
    start_placement,
    submit_placement,
)

GRAMMAR_ALL = {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}


def _event_count(store) -> int:
    return sum(1 for _ in store.read())


def test_start_answer_submit_happy_path(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    assert started["status"] == "STARTED"
    assert active_placement_id(store) == pid

    res = answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    assert res["status"] == "IN_PROGRESS"
    assert res["next_section"] == "vocabulary"
    answer_placement(store, clock, random_source, pid, section="vocabulary", answers={"v-greeting-1": "hi"})

    result = submit_placement(store, registry, clock, random_source, pid)
    assert result["status"] == "SCORED"
    assert result["already"] is False
    # 3 grammar + 1 vocabulary correct -> four contributing evidence + outcomes.
    assert result["evidence_count"] == 4
    assert result["outcome_count"] == 4
    # The active pointer is cleared on terminalization.
    assert active_placement_id(store) is None


def test_submit_requires_in_progress(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    # STARTED with no answers cannot be submitted (no STARTED -> SUBMITTED edge).
    with pytest.raises(PlacementPrecondition):
        submit_placement(store, registry, clock, random_source, started["placement_id"])


def test_submit_is_idempotent_and_terminal(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)

    first = submit_placement(store, registry, clock, random_source, pid)
    count_after_first = _event_count(store)

    second = submit_placement(store, registry, clock, random_source, pid)
    assert second["already"] is True
    assert second["evidence_count"] == first["evidence_count"]
    # A repeat submit mints no new events -- it is terminal and idempotent.
    assert _event_count(store) == count_after_first


def test_abandon_forbidden_after_submit(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    submit_placement(store, registry, clock, random_source, pid)
    with pytest.raises(PlacementPrecondition):
        abandon_placement(store, clock, random_source, pid)


def test_answer_forbidden_after_terminal(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    abandon_placement(store, clock, random_source, pid)
    with pytest.raises(PlacementPrecondition):
        answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)


def test_start_refuses_a_second_active_placement(store, registry, clock, random_source) -> None:
    start_placement(store, registry, clock, random_source)
    with pytest.raises(PlacementPrecondition):
        start_placement(store, registry, clock, random_source)


def test_abandon_frees_the_pointer_for_a_new_placement(store, registry, clock, random_source) -> None:
    first = start_placement(store, registry, clock, random_source)
    abandon_placement(store, clock, random_source, first["placement_id"])
    assert active_placement_id(store) is None
    second = start_placement(store, registry, clock, random_source)
    assert second["placement_id"] != first["placement_id"]
    state, _ = get_placement(store, first["placement_id"])
    assert state["status"] == "ABANDONED"


def test_answer_rejects_unknown_section_and_item(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    with pytest.raises(PlacementPrecondition):
        answer_placement(store, clock, random_source, pid, section="listening", answers={"x": "y"})
    with pytest.raises(PlacementPrecondition):
        answer_placement(store, clock, random_source, pid, section="grammar", answers={"v-greeting-1": "hi"})
