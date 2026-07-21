"""Unit of Work: atomic event + outbox + idempotency (foundation 3.7).

A UoW is one SQLite transaction. Inside it, appended events, enqueued outbox
messages and the recorded idempotency result all commit together or roll back
together -- there is no partial success. That atomicity is what lets the
authoritative event log, the operational state and the outbox live on one
resource without a two-phase commit (foundation 2.1).

Idempotency is checked at the boundary: a command whose key was already applied
with the same payload returns the cached result and writes nothing; the same key
with a different payload is a stable ``IdempotencyConflict``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import TracebackType

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import IdempotencyConflict
from english_trainer.kernel.store import EventStore


class CachedResult:
    """Marker returned when an idempotency key was already applied."""

    __slots__ = ("value",)

    def __init__(self, value: dict[str, object]) -> None:
        self.value = value


class UnitOfWork:
    """One atomic transaction over the event store, outbox and idempotency.

    Use as a context manager: the body appends events and enqueues messages;
    leaving the block without an exception commits, an exception rolls back.
    """

    def __init__(self, store: EventStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._conn = store._conn  # single connection; the store owns it
        self._pending_outbox: list[tuple[str, int, str]] = []
        self._open = False

    # -- idempotency boundary ------------------------------------------------

    def check_idempotency(self, key: str, payload_hash: str) -> CachedResult | None:
        """Return the cached result for ``key`` if it was already applied.

        ``None`` means the caller should proceed. A key seen with a *different*
        payload raises ``IdempotencyConflict``.
        """
        row = self._conn.execute(
            "SELECT payload_hash, result FROM idempotency WHERE idempotency_key = ?;",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            raise IdempotencyConflict(f"idempotency key {key!r} reused with a different payload")
        return CachedResult(json.loads(row["result"]))

    # -- transaction ---------------------------------------------------------

    def __enter__(self) -> UnitOfWork:
        self._conn.execute("BEGIN;")
        self._open = True
        return self

    def append(self, events: Sequence[DomainEvent]) -> list[DomainEvent]:
        """Append events; their outbox messages are enqueued in the same UoW."""
        stored = self._store.append(events)
        for event in stored:
            assert event.sequence is not None
            message_id = f"{event.id}:{event.type}"
            self._pending_outbox.append((message_id, event.sequence, event.type))
        return stored

    def record_result(self, key: str, payload_hash: str, result: dict[str, object]) -> None:
        """Store the cached result for an idempotency key inside this UoW."""
        self._conn.execute(
            "INSERT INTO idempotency (idempotency_key, payload_hash, result, created_at) VALUES (?,?,?,?);",
            (key, payload_hash, json.dumps(result, sort_keys=True), self._clock.now().isoformat()),
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._open:
            return
        self._open = False
        if exc_type is not None:
            self._conn.execute("ROLLBACK;")
            return
        now = self._clock.now().isoformat()
        for message_id, sequence, topic in self._pending_outbox:
            self._conn.execute(
                "INSERT INTO outbox (message_id, sequence, topic, created_at) VALUES (?,?,?,?);",
                (message_id, sequence, topic, now),
            )
        self._conn.execute("COMMIT;")
