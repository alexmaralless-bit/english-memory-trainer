"""LearnerPreferences invariants (learner 4a [PD-2026-09-22]).

The load-bearing claims: the form a session takes is versioned event-sourced
state, separate from anything measured -- defaults, merge-over-current
semantics, idempotent retries, and (above all) zero effect on scoring, ever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import IdempotencyConflict
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.learner.errors import PreferencesInvalid
from english_trainer.learner.preferences import (
    DEFAULT_PREFERENCES,
    EVENT_PREFERENCES_UPDATED,
    preferences_get,
    preferences_set,
)

REPO = Path(__file__).resolve().parents[2]

_DEFAULT_SNAPSHOT: dict[str, Any] = {
    **DEFAULT_PREFERENCES,
    "preferred_drill_forms": [],
    "preferences_version": 0,
    "updated_at": None,
}


def _preferences_events(store: EventStore) -> list[Any]:
    return [event for event in store.read() if event.type == EVENT_PREFERENCES_UPDATED]


def _scoring_policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "scoring-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _emit(
    store: EventStore, clock: FixedClock, rnd: SeededRandomSource, event_type: str, payload: dict[str, Any]
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=str(payload.get("session_id") or "corr"),
                    payload=payload,
                )
            ]
        )


def _evidence(
    store: EventStore, clock: FixedClock, rnd: SeededRandomSource, *, target: str = "t.one"
) -> None:
    _emit(
        store,
        clock,
        rnd,
        "evidence.added",
        {
            "evidence_id": new_ulid(clock, rnd),
            "session_id": "s1",
            "primary_target": {"target_ref": target, "dimension": "recognition"},
            "origin": "session",
            "assessment_basis": "objective_check",
            "correct": True,
            "hints": 0,
        },
    )


# -- defaults -----------------------------------------------------------------


def test_defaults_before_any_edit(store: EventStore) -> None:
    assert preferences_get(store) == _DEFAULT_SNAPSHOT


# -- set: validation ------------------------------------------------------


def test_unknown_field_is_rejected(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"nickname": "Alex"})
    assert _preferences_events(store) == []  # the refusal left no trace


@pytest.mark.parametrize("value", [2, 13, 6.0, "6", True])
def test_round_size_out_of_range_or_wrong_type_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, value: object
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"round_size": value})
    assert _preferences_events(store) == []


@pytest.mark.parametrize("value", [59, 901, 240.0, "240"])
def test_timed_limit_seconds_out_of_range_or_wrong_type_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, value: object
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"timed_limit_seconds": value})
    assert _preferences_events(store) == []


def test_unknown_explanation_language_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"explanation_language": "fr"})


def test_unknown_feedback_mode_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"feedback_mode": "silent"})


def test_unknown_drill_form_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(
            store, clock, random_source, changes={"preferred_drill_forms": ["ru_to_en_sentence", "made_up"]}
        )


def test_preferred_drill_forms_must_be_a_list(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    with pytest.raises(PreferencesInvalid):
        preferences_set(store, clock, random_source, changes={"preferred_drill_forms": "ru_to_en_sentence"})


def test_preferred_drill_forms_deduplicates_preserving_order(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    result = preferences_set(
        store,
        clock,
        random_source,
        changes={"preferred_drill_forms": ["minimal_pair", "frame_recall", "minimal_pair"]},
    )
    assert result["preferred_drill_forms"] == ["minimal_pair", "frame_recall"]


# -- set: merge semantics and versioning --------------------------------------


def test_set_merges_over_current_and_leaves_other_fields_untouched(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    first = preferences_set(store, clock, random_source, changes={"round_size": 8})
    assert first["round_size"] == 8
    assert first["explanation_language"] == "ru"  # untouched default
    assert first["preferences_version"] == 1

    second = preferences_set(store, clock, random_source, changes={"explanation_language": "en"})
    assert second["round_size"] == 8  # carried over from the first edit
    assert second["explanation_language"] == "en"
    assert second["preferences_version"] == 2

    current = preferences_get(store)
    assert current == {k: second[k] for k in current}
    assert len(_preferences_events(store)) == 2


def test_set_publishes_exactly_one_full_snapshot_event(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    preferences_set(store, clock, random_source, changes={"round_size": 9, "feedback_mode": "always_explain"})
    events = _preferences_events(store)
    assert len(events) == 1
    payload = events[0].payload
    # A FULL snapshot, not a delta: every documented field is present.
    assert payload.keys() >= {
        "round_size",
        "explanation_language",
        "preferred_drill_forms",
        "timed_limit_seconds",
        "feedback_mode",
        "preferences_version",
        "updated_at",
    }
    assert payload["round_size"] == 9
    assert payload["feedback_mode"] == "always_explain"


# -- set: idempotency -----------------------------------------------------


def test_repeat_with_same_key_and_payload_is_cached_and_writes_nothing(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    first = preferences_set(store, clock, random_source, changes={"round_size": 8}, idempotency_key="pref-1")
    assert first["cached"] is False
    before = len(_preferences_events(store))

    repeat = preferences_set(store, clock, random_source, changes={"round_size": 8}, idempotency_key="pref-1")
    assert repeat["cached"] is True
    assert repeat["preferences_version"] == first["preferences_version"]
    assert len(_preferences_events(store)) == before  # no second event


def test_same_key_different_payload_is_a_stable_conflict(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    preferences_set(store, clock, random_source, changes={"round_size": 8}, idempotency_key="pref-2")
    before = len(_preferences_events(store))
    with pytest.raises(IdempotencyConflict):
        preferences_set(store, clock, random_source, changes={"round_size": 4}, idempotency_key="pref-2")
    assert len(_preferences_events(store)) == before  # the conflict left no trace


# -- scoring is never affected ------------------------------------------------


def test_preferences_never_change_scoring(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    from english_trainer.scoring.engine import fold_scores, snapshot

    policy = _scoring_policy()
    _evidence(store, clock, random_source)
    before = snapshot(fold_scores(store, policy))
    assert before  # sanity: the seeded evidence really produced scoring state

    preferences_set(
        store,
        clock,
        random_source,
        changes={
            "round_size": 12,
            "explanation_language": "en",
            "timed_limit_seconds": 900,
            "feedback_mode": "always_explain",
            "preferred_drill_forms": ["minimal_pair"],
        },
    )

    after = snapshot(fold_scores(store, policy))
    assert after == before  # byte-for-byte: a preferences edit is invisible to scoring
