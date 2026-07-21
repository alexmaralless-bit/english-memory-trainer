"""Projection framework: incremental apply and isolate-and-swap rebuild
(foundation 3.8; OPEN-21).

A projection is a set of SQLite read-model tables owned by one named consumer.
Incrementally it advances like any outbox consumer -- exactly-once per event,
checkpointed in ``consumer_offsets`` (increment 2). What this module adds is
the **rebuild protocol** the contract demands (review E-2):

- the projection is rebuilt into *isolated* tables (``<name>__rebuild``) by
  replaying the event table up to a captured high-water mark;
- the swap is **atomic**: dropping the live tables, renaming the rebuilt ones
  and setting the applied offset to the high-water mark happen in ONE
  transaction -- SQLite DDL is transactional, so a crash mid-swap leaves the
  old state fully intact;
- late deliveries cannot mix old and new: events past the high-water mark are
  simply redelivered after the swap (the offset was reset to the mark inside
  the same transaction), and each reaches the rebuilt tables exactly once.

Determinism (foundation 5): a projection's ``apply_event`` must be a pure
function of the event -- given the same event table, rebuild always produces
the same read model. The kernel supplies the mechanism; which projections exist
belongs to the owning modules (scoring read-models, the Obsidian exporter).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.outbox import OffsetStore, deliver
from english_trainer.kernel.store import EventStore

# Maps a logical table name to its physical name: identity for the live state,
# suffixed during a rebuild. Projections must route ALL their SQL through it.
TableResolver = Callable[[str], str]

_REBUILD_SUFFIX = "__rebuild"


@runtime_checkable
class SqlProjection(Protocol):
    """A read-model over SQLite tables (foundation 3.8).

    ``name`` keys the applied offset; ``tables`` lists every table the
    projection owns (nothing else may write them). ``create_schema`` must be
    idempotent (``CREATE TABLE IF NOT EXISTS``); ``apply_event`` must be
    deterministic and must address tables only through the resolver.
    """

    name: str
    tables: tuple[str, ...]

    def create_schema(self, conn: sqlite3.Connection, table: TableResolver) -> None: ...

    def apply_event(self, conn: sqlite3.Connection, event: DomainEvent, table: TableResolver) -> None: ...


def _live(name: str) -> str:
    return name


def _rebuild_name(name: str) -> str:
    return f"{name}{_REBUILD_SUFFIX}"


def project(store: EventStore, projection: SqlProjection, clock: Clock) -> int:
    """Apply newly outboxed events to the live read model. Returns the count.

    Delegates to the outbox delivery protocol (increment 2): per-event
    transactions, offset re-checked under the write lock, exactly-once.
    """
    projection.create_schema(store._conn, _live)

    class _Adapter:
        name = projection.name

        def apply(self, event: DomainEvent) -> None:
            projection.apply_event(store._conn, event, _live)

    return deliver(store, _Adapter(), clock)


def rebuild_projection(store: EventStore, projection: SqlProjection, clock: Clock) -> int:
    """Rebuild the read model from the event table; return the high-water mark.

    Isolate-and-swap: the new state is built in suffixed tables while the live
    ones keep serving (and may even keep advancing); the swap replaces tables
    AND resets the applied offset in one atomic transaction. Events appended
    past the captured mark are redelivered to the new state afterwards --
    exactly once, because the offset moved back with the swap.
    """
    conn = store._conn
    if conn.in_transaction:
        raise KernelError("rebuild_projection must not run inside an open transaction")

    # Clean any leftovers of a crashed earlier rebuild, then build in isolation.
    for name in projection.tables:
        conn.execute(f'DROP TABLE IF EXISTS "{_rebuild_name(name)}";')
    projection.create_schema(conn, _rebuild_name)

    row = conn.execute("SELECT COALESCE(MAX(sequence), 0) AS high FROM events;").fetchone()
    high_water = int(row["high"])

    try:
        conn.execute("BEGIN;")
        for event in store.read():
            assert event.sequence is not None
            if event.sequence <= high_water:
                projection.apply_event(conn, event, _rebuild_name)
        conn.execute("COMMIT;")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        for name in projection.tables:
            conn.execute(f'DROP TABLE IF EXISTS "{_rebuild_name(name)}";')
        raise

    # The swap: tables and offset move together or not at all (foundation 3.8:
    # the applied offset is committed atomically with the consumer state).
    try:
        conn.execute("BEGIN;")
        for name in projection.tables:
            conn.execute(f'DROP TABLE IF EXISTS "{name}";')
            conn.execute(f'ALTER TABLE "{_rebuild_name(name)}" RENAME TO "{name}";')
        OffsetStore(conn).set(projection.name, high_water, clock.now().isoformat())
        conn.execute("COMMIT;")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    return high_water
