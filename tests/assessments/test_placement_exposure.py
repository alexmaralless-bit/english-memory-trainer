"""Exposure history: re-seen items are down-weighted (zeroed) on re-take and
the applied weight is captured into the evidence event (assessments 3)."""

from __future__ import annotations

from english_trainer.assessments.placement import (
    answer_placement,
    start_placement,
    submit_placement,
)

GRAMMAR_ALL = {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}


def _run_take(store, registry, clock, random_source) -> tuple[str, dict]:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    result = submit_placement(store, registry, clock, random_source, pid)
    return pid, result


def _evidence_events(store) -> list:
    return [event for event in store.read() if event.type == "evidence.added"]


def test_first_take_is_fresh_and_contributing(store, registry, clock, random_source) -> None:
    _, result = _run_take(store, registry, clock, random_source)
    assert result["evidence_count"] == 3
    for item in result["scored_items"]:
        assert item["applied_exposure_weight"] == "1"
        assert item["contributing"] is True
    # The fresh weight is captured into every evidence event (capture-into-event).
    events = _evidence_events(store)
    assert len(events) == 3
    assert all(event.payload["applied_exposure_weight"] == "1" for event in events)


def test_retake_downweights_reseen_items_to_zero(store, registry, clock, random_source) -> None:
    first_pid, _ = _run_take(store, registry, clock, random_source)
    clock.advance(seconds=60)

    second_pid, result = _run_take(store, registry, clock, random_source)
    assert second_pid != first_pid
    # The memorized form yields no fresh evidence: re-seen items are zeroed.
    assert result["evidence_count"] == 0
    for item in result["scored_items"]:
        assert item["applied_exposure_weight"] == "0"
        assert item["contributing"] is False

    # Still exactly the three evidence events from the first take, none new.
    assert len(_evidence_events(store)) == 3
    # The captured weight rides the SCORED fact too, so replay reproduces it.
    scored = next(
        event
        for event in store.read()
        if event.type == "placement.scored" and event.payload["placement_id"] == second_pid
    )
    assert all(row["applied_exposure_weight"] == "0" for row in scored.payload["scored_items"])
