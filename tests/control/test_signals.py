"""Learner control signals: the READ side -- the two expiry types, supersede
and one-shot consumption (control 4.7).

The write path (``trainer signal`` / ``record_signal``) was removed with the
per-step protocol [PD-2026-09-23]; signals already in the log stay in force
until they expire, so the fold over historic ``LEARNER_SIGNAL_RECORDED`` facts
is what remains live. The records below have the exact shape the removed
writer persisted."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from english_trainer.control.signals import (
    EVENT_SESSION_STARTED,
    EVENT_SIGNAL_CONSUMED,
    EVENT_SIGNAL_RECORDED,
    active_signals,
    current_session_seq,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


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


def _signal(kind: str, **fields: Any) -> dict[str, Any]:
    """A canonical signal record (the union's full field set, unset = None)."""
    record: dict[str, Any] = {
        "kind": kind,
        "target_ref": None,
        "domain": None,
        "avoid_context": None,
        "expires_at": None,
        "expires_after_session_seq": None,
        "profile": None,
        "theme": None,
    }
    record.update(fields)
    return record


def test_session_seq_counts_starts_and_is_zero_before_any_session() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    assert current_session_seq(evt_store) == 0
    emit(evt_store, clock, rnd, type=EVENT_SESSION_STARTED, correlation_id="S1", payload={"n": 1})
    emit(evt_store, clock, rnd, type=EVENT_SESSION_STARTED, correlation_id="S2", payload={"n": 2})
    assert current_session_seq(evt_store) == 2


def test_an_expires_at_signal_lapses_at_its_instant() -> None:
    evt_store, clock, rnd = store(), FixedClock(NOW), SeededRandomSource(7)
    record_bare(
        evt_store,
        clock,
        rnd,
        _signal("not_relevant_now", domain="work", expires_at=NOW.isoformat()),
        "domain-snooze",
    )
    later = datetime(2026, 7, 22, 12, 0, 1, tzinfo=UTC)
    before = datetime(2026, 7, 22, 11, 59, 59, tzinfo=UTC)
    assert {s["signal_id"] for s in active_signals(evt_store, 4, before)} == {"domain-snooze"}
    assert active_signals(evt_store, 4, later) == []


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
        _signal("need_more_practice", target_ref="grammar.x", expires_after_session_seq=3),
        "sig-expired",
    )  # expires_after_session_seq = 3
    # Two snoozes on the same target: the later supersedes the earlier.
    future = datetime(2027, 1, 1, tzinfo=UTC).isoformat()
    record_bare(
        evt_store,
        clock,
        rnd,
        _signal("snooze", target_ref="grammar.y", expires_at=future),
        "snooze-old",
    )
    record_bare(
        evt_store,
        clock,
        rnd,
        _signal("snooze", target_ref="grammar.y", expires_at=future),
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
        _signal("too_easy", target_ref="grammar.x"),
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
