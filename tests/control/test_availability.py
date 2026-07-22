"""Availability profile, observed rhythm and re-entry boost (control 4.7a)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.availability import (
    EVENT_AVAILABILITY_UPDATED,
    availability_get,
    availability_set,
    is_long_break,
    observed_availability,
    resolve_total_seconds,
    validate_declared,
)
from english_trainer.control.compose import compose_plan
from english_trainer.control.errors import AvailabilityInvalid
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def store_at(tmp_path: Path) -> EventStore:
    conn = connect(tmp_path / "availability.db")
    migrate(conn)
    return EventStore(conn)


def emit_session(
    store: EventStore,
    random_source: SeededRandomSource,
    session_id: str,
    started_at: datetime,
    *,
    total_seconds: int,
    terminal_at: datetime | None,
) -> None:
    events = [
        (started_at, "session.started", {"manifest": {"started_at": started_at.isoformat()}}),
        (
            started_at,
            "session.composed",
            {"budget": {"total_seconds": total_seconds}, "session_id": session_id},
        ),
    ]
    if terminal_at is not None:
        events.append((terminal_at, "session.finished", {"session_id": session_id}))
    for instant, event_type, payload in events:
        clock = FixedClock(instant)
        with UnitOfWork(store, clock) as uow:
            uow.append(
                [
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=event_type,
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id=session_id,
                        payload=payload,
                    )
                ]
            )


def test_declared_schema_is_integer_only_and_normalizes_instants() -> None:
    normalized = validate_declared(
        {
            "sessions_per_week_milli": 2500,
            "typical_minutes": 35,
            "next_available_at": "2026-07-22T14:00:00+02:00",
        }
    )
    assert normalized["next_available_at"] == "2026-07-22T12:00:00+00:00"
    assert validate_declared({"sessions_per_week_milli": 0}) == {"sessions_per_week_milli": 0}
    with pytest.raises(AvailabilityInvalid, match="non-negative integer"):
        validate_declared({"sessions_per_week_milli": 2.5})
    with pytest.raises(AvailabilityInvalid, match="timezone-aware"):
        validate_declared({"blackout_until": "2026-07-22T12:00:00"})


def test_observed_uses_calendar_window_terminal_budgets_and_lower_medians(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    random_source = SeededRandomSource(5)
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    starts = [now - timedelta(days=10), now - timedelta(days=9), now - timedelta(days=7)]
    for index, (started, seconds) in enumerate(zip(starts, (1200, 1800, 2400), strict=True)):
        # Wildly different lifecycle durations prove STARTED->FINISHED duration
        # is not the source of typical_minutes.
        emit_session(
            store,
            random_source,
            f"s{index}",
            started,
            total_seconds=seconds,
            terminal_at=started + timedelta(hours=index + 1),
        )
    emit_session(
        store,
        random_source,
        "still-open",
        now - timedelta(days=1),
        total_seconds=6000,
        terminal_at=None,
    )

    observed, trace = observed_availability(store, policy(), now, timezone_name="+02:00")
    assert observed == {
        "sessions_per_week_milli": 500,
        "typical_minutes": 30,
        "median_interval_seconds": 172_800,
    }
    assert trace["timezone"] == "+02:00"
    # Current Monday 00:00 at the learner's +02 offset minus five weeks.
    assert trace["window_start"] == "2026-06-14T22:00:00+00:00"
    assert trace["terminal_sessions"] == 3
    store._conn.close()


def test_sparse_history_is_no_data_not_zero(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    random_source = SeededRandomSource(7)
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    for index in range(2):
        started = now - timedelta(days=index + 1)
        emit_session(store, random_source, f"s{index}", started, total_seconds=1800, terminal_at=started)
    observed, _ = observed_availability(store, policy(), now)
    assert observed["sessions_per_week_milli"] == "no-data"
    assert observed["typical_minutes"] == "no-data"
    assert observed["median_interval_seconds"] is None
    store._conn.close()


def test_budget_precedence_is_fixed() -> None:
    p = policy()
    observed = {"typical_minutes": 25, "sessions_per_week_milli": 1000, "median_interval_seconds": 1}
    assert resolve_total_seconds(
        p, duration_minutes=40, declared={"typical_minutes": 35}, observed=observed
    ) == (2400, "cli")
    assert resolve_total_seconds(
        p, duration_minutes=None, declared={"typical_minutes": 35}, observed=observed
    ) == (2100, "declared")
    assert resolve_total_seconds(p, duration_minutes=None, declared={}, observed=observed) == (
        1500,
        "observed",
    )
    assert resolve_total_seconds(
        p,
        duration_minutes=None,
        declared={},
        observed={"typical_minutes": "no-data"},
    ) == (1800, "policy_default")


def test_long_break_requires_blackout_or_a_future_gap_beyond_observed_median() -> None:
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    observed = {"median_interval_seconds": 86_400}
    assert is_long_break({"blackout_until": "2026-07-22T13:00:00+00:00"}, observed, now)
    assert is_long_break({"next_available_at": "2026-07-24T12:00:01+00:00"}, observed, now)
    assert not is_long_break({"next_available_at": "2026-07-23T12:00:00+00:00"}, observed, now)
    assert not is_long_break(
        {"next_available_at": "2026-07-30T12:00:00+00:00"},
        {"median_interval_seconds": None},
        now,
    )


def test_set_is_atomic_idempotent_and_publishes_only_a_change(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    clock = FixedClock(datetime(2026, 7, 22, 12, tzinfo=UTC))
    random_source = SeededRandomSource(11)
    declared = {"sessions_per_week_milli": 2000, "typical_minutes": 30}
    first = availability_set(store, clock, random_source, declared, idempotency_key="k1")
    assert first["updated"] is True and first["revision"] == 1
    replay = availability_set(store, clock, random_source, declared, idempotency_key="k1")
    assert replay["cached"] is True and replay["event_id"] == first["event_id"]
    unchanged = availability_set(store, clock, random_source, declared, idempotency_key="k2")
    assert unchanged["updated"] is False and unchanged["revision"] == 1
    updates = [event for event in store.read() if event.type == EVENT_AVAILABILITY_UPDATED]
    assert len(updates) == 1
    shown = availability_get(store, policy(), clock)
    assert shown["declared"] == declared
    assert shown["divergence_ppm"] == "no-data"
    assert shown["proposal"] is None
    store._conn.close()


def review_candidate(candidate_id: str, urgency: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "kind": "review",
        "bucket": "review",
        "step_type": "recognition_check",
        "expected_seconds": 30,
        "target_ref": candidate_id,
        "dimension": "recognition",
        "urgency_class": urgency,
        "stake_rank": 2,
        "retrievability_ppm": 100_000,
        "deferral_count": 0,
        "criteria_ref": None,
        "context_id": f"review|{candidate_id}",
        "lexicon_first": False,
        "lexicon_refs": [],
        "schedule_epoch": 0,
    }


def probe_candidate() -> dict[str, Any]:
    return {
        "candidate_id": "probe:t",
        "kind": "probe",
        "bucket": "choice",
        "step_type": "spontaneous_production",
        "expected_seconds": 360,
        "target_ref": "t",
        "dimension": "recognition",
        "context_id": "probe|t",
        "avoid_context": None,
        "probe_id": "p1",
        "signal_id": "sig1",
        "requested_difficulty": "spontaneous_production",
        "lexicon_first": False,
        "lexicon_refs": [],
        "topic_hint": None,
        "sort_rank": 0,
    }


def compose_with_availability(*, long_break: bool) -> dict[str, Any]:
    counter = iter(range(100))
    return compose_plan(
        program={"topics": [], "lexicon": []},
        policy=policy(),
        generation_version="generation@1",
        mode="balanced",
        total_seconds=1800,
        review_candidates=[review_candidate("critical", "critical")],
        probe=probe_candidate(),
        availability_long_break=long_break,
        new_id=lambda: f"id-{next(counter)}",
    )


def test_long_break_boosts_critical_before_probe_without_overshoot() -> None:
    ordinary = compose_with_availability(long_break=False)
    boosted = compose_with_availability(long_break=True)
    ordinary_kinds = [step["kind"] for step in ordinary["steps"]]
    boosted_kinds = [step["kind"] for step in boosted["steps"]]
    assert ordinary_kinds.index("probe") < ordinary_kinds.index("review")
    assert boosted_kinds.index("review") < boosted_kinds.index("probe")
    assert boosted["budget"]["planned"]["review"] <= boosted["allocations"]["review_cap"]


def test_availability_parameter_has_a_byte_identical_empty_default() -> None:
    counter_a = iter(range(100))
    counter_b = iter(range(100))
    kwargs: dict[str, Any] = {
        "program": {"topics": [], "lexicon": []},
        "policy": policy(),
        "generation_version": "generation@1",
        "mode": "balanced",
        "total_seconds": 1800,
        "review_candidates": [review_candidate("critical", "critical")],
    }
    omitted = compose_plan(**copy.deepcopy(kwargs), new_id=lambda: f"id-{next(counter_a)}")
    explicit = compose_plan(
        **copy.deepcopy(kwargs), availability_long_break=False, new_id=lambda: f"id-{next(counter_b)}"
    )
    assert canonical_json(omitted) == canonical_json(explicit)
