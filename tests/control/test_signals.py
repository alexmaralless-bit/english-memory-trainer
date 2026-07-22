"""Learner control signals: the discriminated union, the two expiry types,
record idempotency, probe requests and supersede (control 4.7)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.errors import ProbePrecondition, SignalInvalid
from english_trainer.control.signals import (
    EVENT_PROBE_REQUESTED,
    EVENT_SESSION_STARTED,
    EVENT_SIGNAL_CONSUMED,
    EVENT_SIGNAL_RECORDED,
    EVENT_STEP_PRESENTED,
    active_signals,
    build_signal,
    record_signal,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def store() -> EventStore:
    conn = connect(":memory:")
    migrate(conn)
    return EventStore(conn)


def emit(evt_store: EventStore, clock: FixedClock, rnd: SeededRandomSource, **kw: Any) -> None:
    with UnitOfWork(evt_store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=kw["type"],
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=kw["correlation_id"],
                    payload=kw["payload"],
                )
            ]
        )


def types(evt_store: EventStore) -> list[str]:
    return [event.type for event in evt_store.read()]


# -- the discriminated union and both expiry types (control 4.7) -------------


def test_too_easy_requires_a_target_and_is_one_shot() -> None:
    with pytest.raises(SignalInvalid):
        build_signal("too_easy", {}, current_seq=4, policy=policy())
    record = build_signal("too_easy", {"target_ref": "grammar.x"}, current_seq=4, policy=policy())
    # One-shot: neither expiry field is set (it is consumed by its probe).
    assert record["expires_after_session_seq"] is None and record["expires_at"] is None


def test_too_repetitive_expires_after_the_exposure_window() -> None:
    record = build_signal("too_repetitive", {}, current_seq=4, policy=policy())
    # exposure_window_sessions = 5, target optional.
    assert record["expires_after_session_seq"] == 9 and record["target_ref"] is None


def test_need_more_practice_expires_after_default_effect_sessions() -> None:
    with pytest.raises(SignalInvalid):
        build_signal("need_more_practice", {}, current_seq=4, policy=policy())
    record = build_signal("need_more_practice", {"target_ref": "grammar.x"}, current_seq=4, policy=policy())
    assert record["expires_after_session_seq"] == 7  # default_effect_sessions = 3


def test_not_relevant_now_demands_exactly_one_scope_and_an_expiry() -> None:
    with pytest.raises(SignalInvalid):  # neither scope
        build_signal("not_relevant_now", {"expires_at": NOW.isoformat()}, current_seq=1, policy=policy())
    with pytest.raises(SignalInvalid):  # both scopes
        build_signal(
            "not_relevant_now",
            {"target_ref": "t", "domain": "d", "expires_at": NOW.isoformat()},
            current_seq=1,
            policy=policy(),
        )
    with pytest.raises(SignalInvalid):  # missing expiry
        build_signal("not_relevant_now", {"domain": "work"}, current_seq=1, policy=policy())
    record = build_signal(
        "not_relevant_now", {"domain": "work", "expires_at": NOW.isoformat()}, current_seq=1, policy=policy()
    )
    assert record["domain"] == "work" and record["expires_at"] == NOW.isoformat()


def test_snooze_and_prefer_different_context_payloads() -> None:
    with pytest.raises(SignalInvalid):
        build_signal("snooze", {"target_ref": "t"}, current_seq=1, policy=policy())  # missing until
    snooze = build_signal(
        "snooze", {"target_ref": "t", "until": NOW.isoformat()}, current_seq=1, policy=policy()
    )
    assert snooze["expires_at"] == NOW.isoformat()

    with pytest.raises(SignalInvalid):
        build_signal("prefer_different_context", {"target_ref": "t"}, current_seq=1, policy=policy())
    pdc = build_signal(
        "prefer_different_context",
        {"target_ref": "t", "avoid_context": "email|transfer_task"},
        current_seq=2,
        policy=policy(),
    )
    assert pdc["avoid_context"] == "email|transfer_task" and pdc["expires_after_session_seq"] == 5


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(SignalInvalid):
        build_signal("make_it_easier", {"target_ref": "t"}, current_seq=1, policy=policy())


# -- record_signal: events, idempotency, active-session reply (control 3b) ----


def presented(evt_store: EventStore, clock: FixedClock, rnd: SeededRandomSource, session: str) -> None:
    """A started session plus one delivered growth step for grammar.x."""
    emit(evt_store, clock, rnd, type=EVENT_SESSION_STARTED, correlation_id=session, payload={"n": 1})
    emit(
        evt_store,
        clock,
        rnd,
        type=EVENT_STEP_PRESENTED,
        correlation_id=session,
        payload={
            "step_id": "step-1",
            "plan_version": 2,
            "kind": "growth",
            "step_type": "new_material_intro",
            "targets": [{"target_ref": "grammar.x", "dimension": "recognition"}],
            "context_id": "team-intro|new_material_intro",
        },
    )


def test_too_easy_records_signal_and_requests_a_derived_probe() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    presented(evt_store, clock, rnd, "S1")

    result = record_signal(
        evt_store,
        clock,
        rnd,
        kind="too_easy",
        payload={"target_ref": "grammar.x"},
        policy=policy(),
        idempotency_key="k1",
    )
    # Active session -> the reply steers to replan and carries the live version.
    assert result["next_action"] == "session.replan"
    assert result["session_id"] == "S1" and result["current_plan_version"] == 2
    # The probe difficulty steps up from new_material_intro; avoid_context is the
    # source step's context; dimension came from the presented step (4.7).
    assert result["probe"] == {
        "target_ref": "grammar.x",
        "dimension": "recognition",
        "requested_difficulty": "spontaneous_production",
        "avoid_context": "team-intro|new_material_intro",
    }
    kinds = types(evt_store)
    assert kinds.count(EVENT_SIGNAL_RECORDED) == 1 and kinds.count(EVENT_PROBE_REQUESTED) == 1


def test_too_easy_without_a_presented_step_is_refused() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    emit(evt_store, clock, rnd, type=EVENT_SESSION_STARTED, correlation_id="S1", payload={"n": 1})
    with pytest.raises(ProbePrecondition) as excinfo:
        record_signal(
            evt_store,
            clock,
            rnd,
            kind="too_easy",
            payload={"target_ref": "never.seen"},
            policy=policy(),
            idempotency_key="k1",
        )
    assert excinfo.value.reason == "no_presented_step"
    # A refused command writes nothing (the UoW rolled back).
    assert EVENT_SIGNAL_RECORDED not in types(evt_store)


def test_record_signal_is_idempotent_by_key() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    presented(evt_store, clock, rnd, "S1")
    first = record_signal(
        evt_store,
        clock,
        rnd,
        kind="too_easy",
        payload={"target_ref": "grammar.x"},
        policy=policy(),
        idempotency_key="k1",
    )
    second = record_signal(
        evt_store,
        clock,
        rnd,
        kind="too_easy",
        payload={"target_ref": "grammar.x"},
        policy=policy(),
        idempotency_key="k1",
    )
    assert first["cached"] is False and second["cached"] is True
    assert second["signal_id"] == first["signal_id"] and second["probe_id"] == first["probe_id"]
    # Exactly one signal and one probe were ever written.
    kinds = types(evt_store)
    assert kinds.count(EVENT_SIGNAL_RECORDED) == 1 and kinds.count(EVENT_PROBE_REQUESTED) == 1


def test_session_seq_counts_starts_and_zero_before_any_session() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    # No session yet -> current_session_seq = 0, so the effect expires at 0 + 5.
    result = record_signal(
        evt_store,
        clock,
        rnd,
        kind="too_repetitive",
        payload={"target_ref": "grammar.x"},
        policy=policy(),
        idempotency_key="k1",
    )
    assert "next_action" not in result  # no active session
    signal = next(e for e in evt_store.read() if e.type == EVENT_SIGNAL_RECORDED)
    assert signal.payload["current_session_seq"] == 0
    assert signal.payload["signal"]["expires_after_session_seq"] == 5


# -- active_signals: expiry, supersede (control 4.7) -------------------------


def record_bare(
    evt_store: EventStore, clock: FixedClock, rnd: SeededRandomSource, signal: dict[str, Any], signal_id: str
) -> None:
    emit(
        evt_store,
        clock,
        rnd,
        type=EVENT_SIGNAL_RECORDED,
        correlation_id="S1",
        payload={
            "signal_id": signal_id,
            "recorded_at": NOW.isoformat(),
            "current_session_seq": 4,
            "signal": signal,
        },
    )


def test_active_signals_drops_expired_and_supersedes_same_scope() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    # An expired-by-seq signal (window ended at seq 3, we are at 4).
    record_bare(
        evt_store,
        clock,
        rnd,
        build_signal("need_more_practice", {"target_ref": "grammar.x"}, current_seq=0, policy=policy()),
        "sig-expired",
    )  # expires_after_session_seq = 3
    # Two snoozes on the same target: the later supersedes the earlier.
    future = datetime(2027, 1, 1, tzinfo=UTC).isoformat()
    record_bare(
        evt_store,
        clock,
        rnd,
        build_signal("snooze", {"target_ref": "grammar.y", "until": future}, current_seq=4, policy=policy()),
        "snooze-old",
    )
    record_bare(
        evt_store,
        clock,
        rnd,
        build_signal("snooze", {"target_ref": "grammar.y", "until": future}, current_seq=4, policy=policy()),
        "snooze-new",
    )
    active = active_signals(evt_store, current_seq=4, now=NOW)
    ids = {s["signal_id"] for s in active}
    assert "sig-expired" not in ids  # expired by session seq
    assert "snooze-old" not in ids and "snooze-new" in ids  # later wins


def test_active_signals_drops_consumed() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    record_bare(
        evt_store,
        clock,
        rnd,
        build_signal("too_easy", {"target_ref": "grammar.x"}, current_seq=4, policy=policy()),
        "sig-consume",
    )
    assert {s["signal_id"] for s in active_signals(evt_store, 4, NOW)} == {"sig-consume"}
    emit(
        evt_store,
        clock,
        rnd,
        type=EVENT_SIGNAL_CONSUMED,
        correlation_id="S1",
        payload={"signal_id": "sig-consume"},
    )
    assert active_signals(evt_store, 4, NOW) == []  # a consumed one-shot is gone
