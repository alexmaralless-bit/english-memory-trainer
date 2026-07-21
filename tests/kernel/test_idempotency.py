"""Idempotency boundary: same key+payload is cached, same key+different payload
is a stable conflict (foundation 3.4)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import IdempotencyConflict
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import CachedResult, UnitOfWork


def _apply(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, key: str, payload: dict):
    """Simulate a command handler that checks idempotency, then appends + caches."""
    h = payload_hash(payload)
    with UnitOfWork(store, clock) as uow:
        cached = uow.check_idempotency(key, h)
        if cached is not None:
            return cached
        ev = make_event(
            id=new_ulid(clock, rnd),
            type="demo.applied",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id="corr-1",
            idempotency_key=key,
            payload=payload,
        )
        stored = uow.append([ev])
        result = {"sequence": stored[0].sequence}
        uow.record_result(key, h, result)
        return result


def test_same_key_same_payload_returns_cached(store, clock, random_source) -> None:
    first = _apply(store, clock, random_source, "k1", {"x": 1})
    assert first == {"sequence": 1}
    assert store.count() == 1

    second = _apply(store, clock, random_source, "k1", {"x": 1})
    assert isinstance(second, CachedResult)
    assert second.value == {"sequence": 1}
    assert store.count() == 1  # no second event


def test_same_key_different_payload_conflicts(store, clock, random_source) -> None:
    _apply(store, clock, random_source, "k1", {"x": 1})
    with pytest.raises(IdempotencyConflict) as exc:
        _apply(store, clock, random_source, "k1", {"x": 2})
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert store.count() == 1  # the conflicting attempt wrote nothing


def test_distinct_keys_both_apply(store, clock, random_source) -> None:
    _apply(store, clock, random_source, "k1", {"x": 1})
    _apply(store, clock, random_source, "k2", {"x": 1})
    assert store.count() == 2
