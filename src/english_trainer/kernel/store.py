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

import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import AppendOnlyViolation

SCHEMA_VERSION = 1

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

    Writes normally go through :class:`~english_trainer.kernel.uow.UnitOfWork`,
    which wraps append + outbox + idempotency in one transaction. ``append`` here
    assigns each event its ``sequence`` and returns the persisted events.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, events: Sequence[DomainEvent]) -> list[DomainEvent]:
        """Append events in order, assigning a monotonic ``sequence`` to each.

        Must run inside an open transaction (the UoW opens it). Returns the
        events with their assigned ``sequence`` set.
        """
        import json

        stored: list[DomainEvent] = []
        for event in events:
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
                    json.dumps(event.pinned_versions, sort_keys=True),
                    json.dumps(event.payload, sort_keys=True),
                    event.payload_hash,
                ),
            )
            stored.append(event.model_copy(update={"sequence": int(cursor.lastrowid or 0)}))
        return stored

    def read(self) -> Iterator[DomainEvent]:
        """Yield every event strictly in ``sequence`` order (foundation 5)."""
        import json

        rows = self._conn.execute(
            "SELECT sequence, id, type, occurred_at, actor, provider, correlation_id, "
            "causation_id, idempotency_key, pinned_versions, payload, payload_hash "
            "FROM events ORDER BY sequence ASC;"
        )
        for row in rows:
            yield DomainEvent(
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

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM events;").fetchone()
        return int(row["n"])

    def assert_append_only(self) -> None:
        """Prove the triggers reject update/delete (used by the invariant test)."""
        for statement in ("UPDATE events SET type = type;", "DELETE FROM events;"):
            try:
                self._conn.execute(statement)
            except sqlite3.IntegrityError as exc:
                if "append-only" in str(exc):
                    continue
                raise
            except sqlite3.OperationalError as exc:
                if "append-only" in str(exc):
                    continue
                raise
            raise AppendOnlyViolation(f"append-only not enforced for: {statement}")
