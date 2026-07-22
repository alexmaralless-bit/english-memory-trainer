"""Resume window and the deterministic, replayable PLACEMENT_EXPIRED event
(assessments 2 [PD-2026-07-20])."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from english_trainer.assessments.placement import (
    PlacementPrecondition,
    answer_placement,
    get_placement,
    resume_placement,
    start_placement,
    submit_placement,
    sweep_expired_placements,
)

GRAMMAR_ALL = {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}
WINDOW_SECONDS = 48 * 3600


def _expired_events(store) -> list:
    return [event for event in store.read() if event.type == "placement.expired"]


def test_resume_within_window_returns_next_section(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)

    clock.advance(seconds=3600)  # one hour later -- well inside the window
    resumed = resume_placement(store, registry, clock, random_source, pid)
    assert resumed["status"] == "IN_PROGRESS"
    assert resumed["next_section"] == "vocabulary"
    assert any(event.type == "placement.resumed" for event in store.read())


def test_resume_after_window_expires_deterministically(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    state, _ = get_placement(store, pid)
    last_activity = str(state["last_activity_at"])

    clock.advance(seconds=WINDOW_SECONDS + 60)  # past the resume window
    with pytest.raises(PlacementPrecondition):
        resume_placement(store, registry, clock, random_source, pid)

    events = _expired_events(store)
    assert len(events) == 1
    expired = events[0]
    boundary = datetime.fromisoformat(last_activity) + timedelta(seconds=WINDOW_SECONDS)
    # boundary_at is derived from last_activity_at, NOT the sweep's wall clock
    # (which is 48h+60s later): this is the replayable-determinism guarantee.
    assert expired.payload["boundary_at"] == boundary.isoformat()
    assert expired.occurred_at == boundary
    assert expired.payload["last_activity_at"] == last_activity
    assert expired.payload["pinned_assessments_policy"] == "assessments@1"

    terminal, _ = get_placement(store, pid)
    assert terminal["status"] == "EXPIRED"


def test_expiry_is_append_only_not_re_emitted(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    clock.advance(seconds=WINDOW_SECONDS + 60)

    with pytest.raises(PlacementPrecondition):
        resume_placement(store, registry, clock, random_source, pid)
    # A second resume finds it already EXPIRED and mints no second fact.
    with pytest.raises(PlacementPrecondition):
        resume_placement(store, registry, clock, random_source, pid)
    assert len(_expired_events(store)) == 1


def test_sweep_expires_the_active_placement_once(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    clock.advance(seconds=WINDOW_SECONDS + 1)

    assert sweep_expired_placements(store, registry, clock, random_source) == [pid]
    # Re-running the sweep mints nothing (idempotent, append-only).
    assert sweep_expired_placements(store, registry, clock, random_source) == []
    assert len(_expired_events(store)) == 1


def test_sweep_leaves_a_fresh_placement_untouched(store, registry, clock, random_source) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    clock.advance(seconds=3600)  # inside the window
    assert sweep_expired_placements(store, registry, clock, random_source) == []
    assert _expired_events(store) == []
    # And a scored placement is no longer active, so the sweep ignores it.
    submit_placement(store, registry, clock, random_source, pid)
    assert sweep_expired_placements(store, registry, clock, random_source) == []
