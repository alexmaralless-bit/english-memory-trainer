"""Unit of Work: atomic event + outbox + idempotency (foundation 3.7).

A UoW is one SQLite transaction. Inside it, appended events (each written
together with its outbox row by the store itself), and the recorded idempotency
result all commit together or roll back together -- there is no partial success.
That atomicity is what lets the authoritative event log, the operational state
and the outbox live on one resource without a two-phase commit (foundation 2.1).

The UoW is single-use: one ``with`` block per transaction. It refuses writes
outside an open block, rolls back on any error -- including ``BaseException`` and
errors swallowed by the caller (the UoW poisons itself on any failed write) --
and never leaks its claim on the store, even when the recovery rollback itself
fails. Idempotency is checked at the boundary: a command whose key was already
applied with the same payload returns the cached result and writes nothing; the
same key with a different payload is a stable ``IdempotencyConflict``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import TracebackType

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import IdempotencyConflict, KernelError
from english_trainer.kernel.store import EventStore


class CachedResult:
    """Marker returned when an idempotency key was already applied."""

    __slots__ = ("value",)

    def __init__(self, value: dict[str, object]) -> None:
        self.value = value


class UnitOfWork:
    """One atomic, single-use transaction over event store, outbox, idempotency.

    Use as a context manager exactly once: the body appends events and records
    results; leaving the block without an exception commits, an exception (or a
    failure during commit, or any swallowed write error) rolls everything back.
    """

    def __init__(self, store: EventStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._conn = store._conn  # single connection; the store owns it
        self._open = False
        self._used = False
        # The write capability minted by the store on enter. Held privately;
        # nothing readable from the store's own state can stand in for it.
        self._token: str | None = None
        # Poisoned once any write raises: the transaction can then only roll back,
        # even if the caller swallowed the exception inside the block. Otherwise a
        # caught mid-batch failure could commit a partial write (foundation 3.7).
        self._poisoned = False

    # -- idempotency boundary ------------------------------------------------

    def check_idempotency(self, key: str, payload_hash: str) -> CachedResult | None:
        """Return the cached result for ``key`` if it was already applied.

        ``None`` means the caller should proceed. A key seen with a *different*
        payload raises ``IdempotencyConflict``.
        """
        self._require_open()
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

    def _require_open(self) -> None:
        if not self._open:
            raise KernelError("UnitOfWork is not open: use it as a single `with` block")

    def __enter__(self) -> UnitOfWork:
        if self._used:
            raise KernelError("UnitOfWork is single-use; create a new one per transaction")
        # Claim first: the store refuses to mint a capability while another UoW
        # holds it or while the connection is already mid-transaction.
        token = self._store._claim()
        was_in_transaction = self._conn.in_transaction
        try:
            self._conn.execute("BEGIN;")
        except BaseException:
            # BEGIN may have opened the transaction before the failure surfaced
            # (an async signal right after SQLite returned). Roll that back if we
            # opened it -- and release the claim even if the rollback itself
            # fails, so the store is never left owner-locked.
            try:
                if self._conn.in_transaction and not was_in_transaction:
                    self._conn.execute("ROLLBACK;")
            finally:
                self._store._release(token)
            raise
        self._token = token
        self._used = True
        self._open = True
        return self

    def append(self, events: Sequence[DomainEvent]) -> list[DomainEvent]:
        """Append events; the store writes each one's outbox row inseparably."""
        self._require_open()
        try:
            stored = self._store._append(events, self._token, self._clock.now().isoformat())
        except BaseException:
            self._poisoned = True
            raise
        return stored

    def record_result(self, key: str, payload_hash: str, result: dict[str, object]) -> None:
        """Store the cached result for an idempotency key inside this UoW."""
        self._require_open()
        try:
            self._conn.execute(
                "INSERT INTO idempotency (idempotency_key, payload_hash, result, created_at) "
                "VALUES (?,?,?,?);",
                (key, payload_hash, json.dumps(result, sort_keys=True), self._clock.now().isoformat()),
            )
        except BaseException:
            self._poisoned = True
            raise

    def _rollback(self) -> None:
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK;")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._open:
            return
        self._open = False
        try:
            # Roll back on any in-block exception OR any earlier swallowed write
            # error (poisoned) -- all-or-nothing must not depend on whether the
            # caller re-raised.
            if exc_type is not None or self._poisoned:
                self._rollback()
                return
            # Commit path: any failure here -- including BaseException such as
            # KeyboardInterrupt -- must roll the whole transaction back, never
            # leave it open (foundation 3.7).
            try:
                self._conn.execute("COMMIT;")
            except BaseException:
                self._rollback()
                raise
        finally:
            self._store._release(self._token)
            self._token = None
