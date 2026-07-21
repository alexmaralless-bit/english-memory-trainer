"""SQLite event store (foundation 2.1, 3.7, 3.9).

The authoritative event log is an append-only table in SQLite, committed in the
same transaction as the outbox and idempotency rows so the whole write is ACID
on one resource (foundation 2.1). This module is the thin ``sqlite3`` layer the
contract asks for -- WAL, foreign keys on, a forward-only migrator, no ORM.

Determinism lives in the schema: ``events.sequence`` is a monotonic integer that
gives the canonical total order, and updates and deletes are refused by triggers
so the log can only grow. The JSONL derived export and outbox *delivery* are a
later increment; this store establishes the atomic write and the sequence.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from english_trainer.kernel.encoding import canonical_and_hash, canonical_json
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import AppendOnlyViolation, KernelError

SCHEMA_VERSION = 2

# Forward-only migrations: (version, ordered statements). Applied once each,
# individually, inside one transaction -- SQLite DDL is transactional, but
# ``executescript`` auto-commits, so statements are kept separate. Never edit a
# shipped migration; add a new one (append-only, like the event log itself).
_MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            # Authoritative event log. ``sequence`` is the canonical total order.
            """
            CREATE TABLE events (
                sequence        INTEGER PRIMARY KEY AUTOINCREMENT,
                id              TEXT NOT NULL UNIQUE,
                type            TEXT NOT NULL,
                occurred_at     TEXT NOT NULL,
                actor           TEXT NOT NULL,
                provider        TEXT,
                correlation_id  TEXT NOT NULL,
                causation_id    TEXT,
                idempotency_key TEXT,
                pinned_versions TEXT NOT NULL,
                payload         TEXT NOT NULL,
                payload_hash    TEXT NOT NULL
            )
            """,
            # Append-only: refuse any update or delete on the log (foundation 3.3).
            "CREATE TRIGGER events_no_update BEFORE UPDATE ON events "
            "BEGIN SELECT RAISE(ABORT, 'events is append-only'); END",
            "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
            "BEGIN SELECT RAISE(ABORT, 'events is append-only'); END",
            # Outbox: written in the same transaction as its events; delivery is
            # a later increment (foundation 3.7). Ordering key is the sequence.
            """
            CREATE TABLE outbox (
                message_id  TEXT PRIMARY KEY,
                sequence    INTEGER NOT NULL REFERENCES events(sequence),
                topic       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                delivered   INTEGER NOT NULL DEFAULT 0
            )
            """,
            # Idempotency: key -> the payload it first ran with and its cached
            # result (foundation 3.4). Retention/eviction is a later increment.
            """
            CREATE TABLE idempotency (
                idempotency_key TEXT PRIMARY KEY,
                payload_hash    TEXT NOT NULL,
                result          TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        2,
        (
            # Per-consumer delivery checkpoint (foundation 3.7/3.8). Each consumer
            # (outbox subscriber, projection, JSONL export) records how far it has
            # applied the global event ``sequence``. A single ``delivered`` flag on
            # the outbox row cannot express independent progress of many consumers;
            # this high-water mark can, and it doubles as the dedup gate (a message
            # at or below ``applied_sequence`` was already handled).
            """
            CREATE TABLE consumer_offsets (
                consumer_name    TEXT PRIMARY KEY,
                applied_sequence INTEGER NOT NULL DEFAULT 0,
                updated_at       TEXT NOT NULL
            )
            """,
        ),
    ),
)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys on, and row access by name."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any unapplied forward-only migrations. Idempotent."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')));"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, statements in _MIGRATIONS:
        if version in applied:
            continue
        conn.execute("BEGIN;")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?);", (version,))
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


class EventStore:
    """Append-only reads and writes over the ``events`` table.

    There is **no public append**. Writing goes through
    :class:`~english_trainer.kernel.uow.UnitOfWork`, which claims the store with an
    opaque capability and calls the internal ``_append`` with it. Presenting that
    exact capability is the only way to write, so no code -- not even code running
    inside a legitimate UoW -- can smuggle an event past the UoW's outbox and
    idempotency bookkeeping (foundation 2.1/3.7).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # The capability the active UnitOfWork holds, or ``None``. Identity of
        # this object -- not merely its presence -- authorizes a write.
        self._txn_owner: object | None = None

    def _claim(self, token: object) -> None:
        """Make ``token`` the active write capability. Refuses to nest."""
        if self._txn_owner is not None:
            raise KernelError("event store already has an active transaction owner")
        self._txn_owner = token

    def _release(self, token: object) -> None:
        """Drop the claim if ``token`` holds it (idempotent, safe in ``finally``)."""
        if self._txn_owner is token:
            self._txn_owner = None

    def _append(self, events: Sequence[DomainEvent], token: object) -> list[DomainEvent]:
        """Append events in order, assigning a monotonic ``sequence`` to each.

        Internal: only the owning UnitOfWork may call this, and only by presenting
        the exact capability it claimed the store with, from inside its open
        transaction. Both are required -- a matching token but no transaction, or a
        transaction but no/other token, is refused. Being inside *some* transaction
        or holding *some* owner is not enough (foundation 2.1).

        Each payload is serialized to its canonical bytes and hashed **once**;
        those exact bytes are what gets stored, that exact hash is what is checked
        against the envelope's ``payload_hash``, and the returned event's payload
        is rebuilt from those bytes (never from the caller's possibly-mutated
        object). The whole batch is prepared before any row is inserted, so a
        payload mutated after construction is rejected (stale hash) and a bad event
        cannot leave an earlier one half-inserted (foundation 3.3).
        """
        if token is None or token is not self._txn_owner:
            raise KernelError("EventStore append requires the active UnitOfWork's write capability")
        if not self._conn.in_transaction:
            raise KernelError("EventStore append requires the UnitOfWork's open transaction")

        prepared: list[tuple[DomainEvent, str, str]] = []
        for event in events:
            canonical, digest = canonical_and_hash(event.payload)
            if event.payload_hash != digest:
                raise KernelError(
                    f"event {event.id} payload_hash {event.payload_hash!r} does not match "
                    f"its payload (hashes to {digest!r}); payload was mutated after construction"
                )
            pinned_text = canonical_json(event.pinned_versions).decode("ascii")
            prepared.append((event, canonical.decode("ascii"), pinned_text))

        stored: list[DomainEvent] = []
        for event, payload_text, pinned_text in prepared:
            cursor = self._conn.execute(
                "INSERT INTO events "
                "(id, type, occurred_at, actor, provider, correlation_id, causation_id, "
                " idempotency_key, pinned_versions, payload, payload_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?);",
                (
                    event.id,
                    event.type,
                    event.occurred_at.isoformat(),
                    event.actor,
                    event.provider,
                    event.correlation_id,
                    event.causation_id,
                    event.idempotency_key,
                    pinned_text,
                    payload_text,
                    event.payload_hash,
                ),
            )
            snapshot_payload = json.loads(payload_text)  # the exact stored bytes, not the input object
            stored.append(
                event.model_copy(update={"sequence": int(cursor.lastrowid or 0), "payload": snapshot_payload})
            )
        return stored

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> DomainEvent:
        return DomainEvent(
            sequence=row["sequence"],
            id=row["id"],
            type=row["type"],
            occurred_at=row["occurred_at"],
            actor=row["actor"],
            provider=row["provider"],
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            idempotency_key=row["idempotency_key"],
            pinned_versions=json.loads(row["pinned_versions"]),
            payload=json.loads(row["payload"]),
            payload_hash=row["payload_hash"],
        )

    _SELECT_COLUMNS = (
        "SELECT sequence, id, type, occurred_at, actor, provider, correlation_id, "
        "causation_id, idempotency_key, pinned_versions, payload, payload_hash FROM events"
    )

    def read(self) -> Iterator[DomainEvent]:
        """Yield every event strictly in ``sequence`` order (foundation 5)."""
        rows = self._conn.execute(f"{self._SELECT_COLUMNS} ORDER BY sequence ASC;")
        for row in rows:
            yield self._row_to_event(row)

    def read_since(self, after_sequence: int) -> Iterator[DomainEvent]:
        """Yield events with ``sequence`` greater than ``after_sequence``, in order.

        The delivery tail for a consumer sitting at ``after_sequence`` (its
        high-water mark). ``after_sequence == 0`` yields the whole log.
        """
        rows = self._conn.execute(
            f"{self._SELECT_COLUMNS} WHERE sequence > ? ORDER BY sequence ASC;",
            (after_sequence,),
        )
        for row in rows:
            yield self._row_to_event(row)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM events;").fetchone()
        return int(row["n"])

    def assert_append_only(self) -> None:
        """Prove update and delete on the event log are actually refused
        (foundation 3.3).

        A name check is not enough -- a database could carry same-named triggers
        that do nothing -- so this is a **runtime** proof. When the log already has
        rows, a whole-table UPDATE and DELETE must abort (the trigger fires before
        any change, so nothing is modified). When it is empty, row triggers cannot
        fire, so a throwaway row is inserted inside a SAVEPOINT, proven un-editable
        and un-deletable, then rolled back; the empty table guarantees the probe id
        cannot collide with a real event.
        """
        if self.count() == 0:
            self._conn.execute("SAVEPOINT append_only_probe;")
            try:
                self._conn.execute(
                    "INSERT INTO events "
                    "(id, type, occurred_at, actor, correlation_id, pinned_versions, payload, payload_hash) "
                    "VALUES ('__probe__','__probe__','1970-01-01T00:00:00+00:00','__probe__',"
                    "'__probe__','{}','{}','probe');"
                )
                self._assert_update_delete_abort()
            finally:
                self._conn.execute("ROLLBACK TO append_only_probe;")
                self._conn.execute("RELEASE append_only_probe;")
        else:
            self._assert_update_delete_abort()

    def _assert_update_delete_abort(self) -> None:
        for statement in ("UPDATE events SET type = type;", "DELETE FROM events;"):
            aborted = False
            try:
                self._conn.execute(statement)
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                if "append-only" not in str(exc):
                    raise
                aborted = True
            if not aborted:
                raise AppendOnlyViolation(f"append-only not enforced for: {statement}")
