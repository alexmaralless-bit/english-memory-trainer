"""The two replay determinism tests the contract names (foundation 5):
order-independence of reads, and deterministic append-order under equal
``occurred_at``."""

from __future__ import annotations

import os
import random
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.replay import fold, replay
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)

# Run in a child process: build a store, append events with equal occurred_at
# into it, then replay a reducer over (sequence, type, payload_hash). Everything
# a leaked hash seed could touch -- the seeded id stream, canonical_json key
# ordering inside payload_hash, and the replay order -- feeds stdout, so two
# child processes with different PYTHONHASHSEED must print byte-identical output.
_CROSS_PROCESS_PROGRAM = """
from datetime import UTC, datetime
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.replay import replay
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))  # frozen: equal occurred_at
rnd = SeededRandomSource("fixed-seed")
conn = connect(":memory:")
migrate(conn)
store = EventStore(conn)
with UnitOfWork(store, clock) as uow:
    uow.append([
        make_event(
            id=new_ulid(clock, rnd),
            type=f"e{i}",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id="c",
            payload={"i": i, "note": {"z": 1, "a": 2}},
        )
        for i in range(8)
    ])
ids = "".join(new_ulid(clock, rnd) for _ in range(5))
digest = replay(store, lambda acc, e: f"{acc}|{e.sequence}:{e.type}:{e.payload_hash}", "")
print(ids)
print(digest)
"""


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


def test_interleaved_commits_reproduce_commit_order(tmp_path: Path) -> None:
    # The real "concurrent append" case: writers serialize on the connection and
    # arrive as separate transactions. With equal occurred_at and different seeds,
    # the recorded total order is exactly commit order -- and reproducible. The
    # tie-break is the assigned `sequence`, not occurred_at or the id.
    def build(db: str, seed: int) -> list[tuple[int | None, str]]:
        clock = FixedClock(EPOCH)  # frozen: every commit shares occurred_at
        rnd = SeededRandomSource(seed)
        store = _fresh_store(tmp_path, db)
        for i in range(6):
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
                    ]
                )
        return [(event.sequence, event.type) for event in store.read()]

    run_a = build("il_a.db", seed=7)
    run_b = build("il_b.db", seed=13)
    assert run_a == [(i + 1, f"e{i}") for i in range(6)]
    assert run_a == run_b


def test_process_hash_seed_does_not_change_outcome() -> None:
    # PYTHONHASHSEED only takes effect at interpreter start, so a same-process
    # call cannot prove independence from it. Run the append+replay program in two
    # child interpreters with different hash seeds and require byte-identical
    # stdout: the id stream, the payload hashing, and the replay all feed it.
    src = Path(__file__).resolve().parents[2] / "src"

    def run(hash_seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(src)}
        proc = subprocess.run(
            [sys.executable, "-c", _CROSS_PROCESS_PROGRAM],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return proc.stdout

    seed_one, seed_two = run("1"), run("2")
    assert seed_one == seed_two
    assert seed_one.strip()  # not silently empty (a crashed child would print nothing)
