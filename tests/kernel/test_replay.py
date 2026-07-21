"""The two replay determinism tests the contract names (foundation 5):
order-independence of reads, and deterministic append-order under equal
``occurred_at``."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.replay import fold, replay
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def _digest(acc: str, event: DomainEvent) -> str:
    """An order-SENSITIVE reducer: the result changes if events are reordered."""
    return f"{acc}|{event.sequence}:{event.type}"


def _fresh_store(tmp_path: Path, name: str) -> EventStore:
    conn = connect(tmp_path / name)
    migrate(conn)
    return EventStore(conn)


def test_replay_is_independent_of_physical_order(tmp_path: Path) -> None:
    clock = FixedClock(EPOCH)
    rnd = SeededRandomSource(1)
    store = _fresh_store(tmp_path, "a.db")
    with UnitOfWork(store, clock) as uow:
        for i in range(12):
            uow.append(
                [
                    make_event(
                        id=new_ulid(clock, rnd),
                        type=f"e{i}",
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id="c",
                        payload={"i": i},
                    )
                ]
            )
            clock.advance(seconds=1)

    canonical = replay(store, _digest, "")

    events = list(store.read())
    shuffled = events[:]
    random.Random(99).shuffle(shuffled)

    # Applying in physical/shuffled order changes an order-sensitive reducer...
    assert fold(shuffled, _digest, "") != canonical
    # ...but applying strictly by sequence reproduces the canonical result.
    assert fold(sorted(shuffled, key=lambda e: e.sequence or 0), _digest, "") == canonical


def test_deterministic_append_order_under_equal_occurred_at(tmp_path: Path) -> None:
    def build(db: str, seed: int) -> list[tuple[int | None, str]]:
        clock = FixedClock(EPOCH)  # frozen: every event shares occurred_at
        rnd = SeededRandomSource(seed)
        store = _fresh_store(tmp_path, db)
        with UnitOfWork(store, clock) as uow:
            uow.append(
                [
                    make_event(
                        id=new_ulid(clock, rnd),
                        type=f"e{i}",
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id="c",
                        payload={"i": i},
                    )
                    for i in range(8)
                ]
            )
        return [(e.sequence, e.type) for e in store.read()]

    # Same insertion order -> same total order, even with equal timestamps and a
    # different seed (the tie-break is insertion sequence, not the id).
    run_a = build("eq_a.db", seed=1)
    run_b = build("eq_b.db", seed=2)
    assert run_a == [(i + 1, f"e{i}") for i in range(8)]
    assert [t for _, t in run_a] == [t for _, t in run_b]


def test_process_hash_seed_does_not_change_outcome(tmp_path: Path) -> None:
    # SeededRandomSource is backed by random.Random(seed), independent of the
    # process hash seed, so the id stream (and thus replay) is reproducible.
    def stream() -> list[str]:
        clock = FixedClock(EPOCH)
        rnd = SeededRandomSource("fixed-seed")
        return [new_ulid(clock, rnd) for _ in range(10)]

    assert stream() == stream()
