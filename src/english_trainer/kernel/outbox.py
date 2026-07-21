"""Transactional outbox delivery (foundation 3.7, 3.8).

Increment 1 wrote events and their outbox rows in one transaction. This module
is the other half: delivering those events to consumers -- the JSONL export, and
later the SQLite read-models and the Obsidian vault -- **after** the commit, in
canonical ``sequence`` order, at-least-once.

Delivery is checkpointed per consumer. Each consumer records how far it has
applied the global event ``sequence`` in ``consumer_offsets``; that high-water
mark is both its resume point and its dedup gate. A message at or below the mark
was already handled, so redelivery after a crash is a no-op. The consumer's
effect and the offset advance commit in **one** transaction, so a consumer whose
effect is a SQLite write is exactly-once; a consumer whose effect is external (a
file) is at-least-once and must reconcile its tail on resume (see
:class:`~english_trainer.kernel.export.JsonlExporter`).
"""

from __future__ import annotations

from sqlite3 import Connection
from typing import Protocol, runtime_checkable

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.store import EventStore


@runtime_checkable
class Consumer(Protocol):
    """Something that applies events in order. ``name`` keys its offset row."""

    name: str

    def apply(self, event: DomainEvent) -> None: ...


@runtime_checkable
class Reconcilable(Protocol):
    """A consumer with external (non-SQLite) state that must be trimmed to the
    committed offset before resuming -- crash recovery for at-least-once effects."""

    def reconcile(self, applied_sequence: int) -> None: ...


class OffsetStore:
    """Read and advance per-consumer high-water marks in ``consumer_offsets``."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get(self, consumer_name: str) -> int:
        row = self._conn.execute(
            "SELECT applied_sequence FROM consumer_offsets WHERE consumer_name = ?;",
            (consumer_name,),
        ).fetchone()
        return 0 if row is None else int(row["applied_sequence"])

    def advance(self, consumer_name: str, sequence: int, now: str) -> None:
        """Move the mark forward to ``sequence``. Never moves backward, so a
        redelivered (lower) sequence cannot rewind a consumer's progress."""
        self._conn.execute(
            "INSERT INTO consumer_offsets (consumer_name, applied_sequence, updated_at) "
            "VALUES (?,?,?) "
            "ON CONFLICT(consumer_name) DO UPDATE SET "
            "applied_sequence = excluded.applied_sequence, updated_at = excluded.updated_at "
            "WHERE excluded.applied_sequence > consumer_offsets.applied_sequence;",
            (consumer_name, sequence, now),
        )

    def set(self, consumer_name: str, sequence: int, now: str) -> None:
        """Force the mark to ``sequence`` unconditionally (used by a full rebuild)."""
        self._conn.execute(
            "INSERT INTO consumer_offsets (consumer_name, applied_sequence, updated_at) "
            "VALUES (?,?,?) "
            "ON CONFLICT(consumer_name) DO UPDATE SET "
            "applied_sequence = excluded.applied_sequence, updated_at = excluded.updated_at;",
            (consumer_name, sequence, now),
        )


def deliver(store: EventStore, consumer: Consumer, clock: Clock) -> int:
    """Deliver every not-yet-applied event to ``consumer`` in ``sequence`` order.

    Returns the number of events delivered this call. Idempotent: a second call
    with no new events delivers nothing. Each event's ``apply`` and the offset
    advance commit together, so an interrupted delivery either fully happened or
    is retried from the last committed mark -- never half-applied in SQLite.
    """
    conn = store._conn
    offsets = OffsetStore(conn)
    applied = offsets.get(consumer.name)
    if isinstance(consumer, Reconcilable):
        consumer.reconcile(applied)

    pending = list(store.read_since(applied))  # materialize before writing
    delivered = 0
    for event in pending:
        assert event.sequence is not None
        conn.execute("BEGIN;")
        try:
            consumer.apply(event)
            offsets.advance(consumer.name, event.sequence, clock.now().isoformat())
            conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        delivered += 1
    return delivered
