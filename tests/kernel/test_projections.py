"""Projection framework: exactly-once incremental apply, deterministic rebuild,
atomic isolate-and-swap, and no old/new mixing under late deliveries
(foundation 3.8)."""

from __future__ import annotations

import sqlite3

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.outbox import OffsetStore
from english_trainer.kernel.projections import TableResolver, project, rebuild_projection
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


class ByTypeCounts:
    """Demo read model: event count and last sequence per event type.

    ``last_sequence`` makes the model order-sensitive, so a wrong replay order
    or a double apply changes observable state.
    """

    name = "proj-by-type"
    tables = ("proj_counts",)

    def create_schema(self, conn: sqlite3.Connection, table: TableResolver) -> None:
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{table("proj_counts")}" '
            "(type TEXT PRIMARY KEY, n INTEGER NOT NULL, last_sequence INTEGER NOT NULL);"
        )

    def apply_event(self, conn: sqlite3.Connection, event: DomainEvent, table: TableResolver) -> None:
        conn.execute(
            f'INSERT INTO "{table("proj_counts")}" (type, n, last_sequence) VALUES (?, 1, ?) '
            "ON CONFLICT(type) DO UPDATE SET n = n + 1, last_sequence = excluded.last_sequence;",
            (event.type, event.sequence),
        )


def _append(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, kinds: list[str]) -> None:
    from english_trainer.kernel.ids import new_ulid

    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=kind,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="c",
                    payload={},
                )
                for kind in kinds
            ]
        )


def _state(store: EventStore) -> list[tuple[str, int, int]]:
    rows = store._conn.execute("SELECT type, n, last_sequence FROM proj_counts ORDER BY type;")
    return [(row["type"], row["n"], row["last_sequence"]) for row in rows]


def test_incremental_apply_is_exactly_once_and_resumable(store, clock, random_source) -> None:
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a", "b", "a"])
    assert project(store, projection, clock) == 3
    assert project(store, projection, clock) == 0  # nothing new, nothing reapplied
    assert _state(store) == [("a", 2, 3), ("b", 1, 2)]
    _append(store, clock, random_source, ["b"])
    assert project(store, projection, clock) == 1
    assert _state(store) == [("a", 2, 3), ("b", 2, 4)]


def test_rebuild_reproduces_the_incremental_state(store, clock, random_source) -> None:
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a", "b", "a", "c"])
    project(store, projection, clock)
    incremental = _state(store)

    high = rebuild_projection(store, projection, clock)
    assert _state(store) == incremental  # deterministic: same events, same model
    assert high == 4
    assert OffsetStore(store._conn).get(projection.name) == 4


def test_rebuild_repairs_a_corrupted_read_model(store, clock, random_source) -> None:
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a", "b"])
    project(store, projection, clock)
    # A projection table is derived state: corrupt it, then rebuild from events.
    store._conn.execute("UPDATE proj_counts SET n = 999;")
    rebuild_projection(store, projection, clock)
    assert _state(store) == [("a", 1, 1), ("b", 1, 2)]


def test_events_past_the_mark_are_redelivered_after_swap(store, clock, random_source) -> None:
    # The isolate-and-swap guarantee: the offset moves back to the high-water
    # mark with the swap, so later events reach the NEW tables exactly once.
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a"])
    project(store, projection, clock)

    high = rebuild_projection(store, projection, clock)
    assert high == 1
    _append(store, clock, random_source, ["b", "a"])  # arrive after the rebuild
    assert project(store, projection, clock) == 2
    assert _state(store) == [("a", 2, 3), ("b", 1, 2)]


def test_failed_rebuild_leaves_live_state_and_offset_untouched(store, clock, random_source) -> None:
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a", "b"])
    project(store, projection, clock)
    before_state = _state(store)
    before_offset = OffsetStore(store._conn).get(projection.name)

    class Exploding(ByTypeCounts):
        def apply_event(self, conn, event, table) -> None:  # type: ignore[override]
            if event.sequence == 2:
                raise RuntimeError("boom mid-rebuild")
            super().apply_event(conn, event, table)

    with pytest.raises(RuntimeError, match="boom"):
        rebuild_projection(store, Exploding(), clock)

    assert _state(store) == before_state  # live tables never touched
    assert OffsetStore(store._conn).get(projection.name) == before_offset
    leftovers = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%__rebuild';"
    ).fetchall()
    assert not leftovers  # isolation debris cleaned up
    assert not store._conn.in_transaction


def test_rebuild_inside_a_transaction_is_refused(store, clock, random_source) -> None:
    projection = ByTypeCounts()
    _append(store, clock, random_source, ["a"])
    project(store, projection, clock)
    store._conn.execute("BEGIN;")
    try:
        with pytest.raises(KernelError, match="transaction"):
            rebuild_projection(store, projection, clock)
    finally:
        store._conn.execute("ROLLBACK;")


def test_rebuild_of_empty_log_yields_empty_model(store, clock) -> None:
    projection = ByTypeCounts()
    high = rebuild_projection(store, projection, clock)
    assert high == 0
    assert _state(store) == []
    assert OffsetStore(store._conn).get(projection.name) == 0
