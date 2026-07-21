"""SQLite event store (foundation 2.1, 3.7, 3.9).

The authoritative event log is an append-only table in SQLite, committed in the
same transaction as the outbox and idempotency rows so the whole write is ACID
on one resource (foundation 2.1). This module is the thin ``sqlite3`` layer the
contract asks for -- WAL, foreign keys on, a forward-only migrator, no ORM.

Determinism lives in the schema: ``events.sequence`` is a monotonic integer that
gives the canonical total order, and updates and deletes are refused by triggers
so the log can only grow. Every event is written together with its outbox row --
that pairing is enforced here, in ``_append``, so no caller can separate them.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from english_trainer.kernel.encoding import canonical_and_hash, canonical_json
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import AppendOnlyViolation, KernelError

SCHEMA_VERSION = 4

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
    (
        3,
        (
            # Versioned policy registry (foundation 3.6, OPEN-9). Each version is an
            # immutable content snapshot addressable by (kind, version_id). Content
            # is never rewritten and rows are never deleted -- a version referenced
            # by a pin must stay resolvable forever (retention != immutability).
            # Only ``status`` may change (registered -> deprecated -> retired).
            """
            CREATE TABLE policies (
                kind         TEXT NOT NULL,
                version_id   TEXT NOT NULL,
                content      TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'registered',
                created_at   TEXT NOT NULL,
                PRIMARY KEY (kind, version_id)
            )
            """,
            # Immutability: content and its hash are frozen once written; only
            # status transitions are allowed to update a row.
            "CREATE TRIGGER policies_content_immutable BEFORE UPDATE OF content, content_hash ON policies "
            "BEGIN SELECT RAISE(ABORT, 'policy content is immutable'); END",
            # Retention: a registered version is never deleted (a pin may reference
            # it). Deprecation is a status change, not a removal.
            "CREATE TRIGGER policies_no_delete BEFORE DELETE ON policies "
            "BEGIN SELECT RAISE(ABORT, 'policies are retained, never deleted'); END",
            # Active pointer per kind for the active-resolve path (production
            # eligibility at delivery). Pins never read this; they resolve by id.
            """
            CREATE TABLE policy_active (
                kind         TEXT PRIMARY KEY,
                version_id   TEXT NOT NULL,
                activated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        4,
        (
            # Policy integrity at the storage layer (review 1.2-4). The API checks
            # are polite errors; these triggers are the guarantee -- a direct SQL
            # UPDATE must not be able to break a pinned resolve or the lifecycle.
            #
            # Identity is immutable: renaming (kind, version_id) would orphan pins.
            "CREATE TRIGGER policies_identity_immutable "
            "BEFORE UPDATE OF kind, version_id, created_at ON policies "
            "BEGIN SELECT RAISE(ABORT, 'policy identity is immutable'); END",
            # Status domain is closed, on insert and update alike.
            "CREATE TRIGGER policies_status_valid_insert BEFORE INSERT ON policies "
            "WHEN NEW.status NOT IN ('registered','deprecated','retired') "
            "BEGIN SELECT RAISE(ABORT, 'invalid policy status'); END",
            "CREATE TRIGGER policies_status_valid_update BEFORE UPDATE OF status ON policies "
            "WHEN NEW.status NOT IN ('registered','deprecated','retired') "
            "BEGIN SELECT RAISE(ABORT, 'invalid policy status'); END",
            # Transitions are one-way: retired is terminal, deprecated cannot
            # return to registered.
            "CREATE TRIGGER policies_retired_terminal BEFORE UPDATE OF status ON policies "
            "WHEN OLD.status = 'retired' AND NEW.status <> 'retired' "
            "BEGIN SELECT RAISE(ABORT, 'retired policy status is terminal'); END",
            "CREATE TRIGGER policies_status_one_way BEFORE UPDATE OF status ON policies "
            "WHEN OLD.status = 'deprecated' AND NEW.status = 'registered' "
            "BEGIN SELECT RAISE(ABORT, 'policy status transitions are one-way'); END",
            # Recreate policy_active with a foreign key so the pointer cannot name
            # a version that does not exist (SQLite cannot add an FK in place).
            # This must happen BEFORE any trigger that references policy_active:
            # ALTER TABLE RENAME rewrites such references to the renamed table.
            "ALTER TABLE policy_active RENAME TO policy_active_v3",
            """
            CREATE TABLE policy_active (
                kind         TEXT PRIMARY KEY,
                version_id   TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                FOREIGN KEY (kind, version_id) REFERENCES policies (kind, version_id)
            )
            """,
            "INSERT INTO policy_active SELECT kind, version_id, activated_at FROM policy_active_v3",
            "DROP TABLE policy_active_v3",
            # The active version can never be retired: each statement is atomic in
            # SQLite, so this closes the activate-vs-retire race at the database.
            "CREATE TRIGGER policies_retire_not_active BEFORE UPDATE OF status ON policies "
            "WHEN NEW.status = 'retired' AND EXISTS "
            "(SELECT 1 FROM policy_active a WHERE a.kind = NEW.kind AND a.version_id = NEW.version_id) "
            "BEGIN SELECT RAISE(ABORT, 'cannot retire the active policy'); END",
            # ...and the pointer can never land on a retired version, whichever
            # side moves last.
            "CREATE TRIGGER policy_active_not_retired_insert BEFORE INSERT ON policy_active "
            "WHEN (SELECT status FROM policies p WHERE p.kind = NEW.kind AND p.version_id = NEW.version_id) "
            "= 'retired' BEGIN SELECT RAISE(ABORT, 'cannot activate retired policy'); END",
            "CREATE TRIGGER policy_active_not_retired_update BEFORE UPDATE ON policy_active "
            "WHEN (SELECT status FROM policies p WHERE p.kind = NEW.kind AND p.version_id = NEW.version_id) "
            "= 'retired' BEGIN SELECT RAISE(ABORT, 'cannot activate retired policy'); END",
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

    The core integrity invariant is **structural**: ``_append`` inserts every
    event together with its outbox row, in the same statements of the same
    transaction. There is no code path -- UnitOfWork, forged claim, stolen
    credential, hand-rolled BEGIN -- that can write an event without its outbox
    row, because the store itself refuses to separate them (foundation 2.1/3.7).

    On top of that, writes are capability-gated: ``_claim`` mints an opaque token
    and hands it to the owning UnitOfWork; the store retains only a one-way
    digest, so nothing readable from the store's state is an appendable
    credential. The gate protects the UoW's transactional protocol (idempotency
    bookkeeping, commit discipline); the event+outbox atomicity above does not
    depend on it.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # sha256 of the active UnitOfWork's token, or None. A digest, not the
        # token: reading this attribute yields nothing _append would accept.
        self._txn_owner_digest: str | None = None

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _claim(self) -> str:
        """Mint and return the write capability for one UnitOfWork transaction.

        Refuses to nest and refuses a connection that is already mid-transaction
        (a hand-rolled BEGIN cannot then acquire a capability at all). The token
        is transient and never persisted, so its randomness cannot influence any
        replayed state (foundation 3.2 concerns reproducible *state*, and none is
        derived from this value).
        """
        if self._txn_owner_digest is not None:
            raise KernelError("event store already has an active transaction owner")
        if self._conn.in_transaction:
            raise KernelError("cannot claim the event store inside an already-open transaction")
        token = secrets.token_hex(16)
        self._txn_owner_digest = self._digest(token)
        return token

    def _release(self, token: str | None) -> None:
        """Drop the claim if ``token`` holds it (idempotent, safe in ``finally``)."""
        if token is None or self._txn_owner_digest is None:
            return
        if self._digest(token) == self._txn_owner_digest:
            self._txn_owner_digest = None

    def _append(self, events: Sequence[DomainEvent], token: str | None, now: str) -> list[DomainEvent]:
        """Append events in order -- each with its outbox row -- assigning a
        monotonic ``sequence``.

        Internal: requires the active UnitOfWork's token (verified against the
        stored digest) AND an open transaction; either alone is refused. ``now``
        stamps the outbox rows (injected clock, never the system clock).

        Each payload is serialized to its canonical bytes and hashed **once**;
        those exact bytes are stored, that exact hash is checked against the
        envelope's ``payload_hash``, and the returned event's ``payload`` and
        ``pinned_versions`` are rebuilt from the stored snapshots (never from the
        caller's possibly-mutated objects). The whole batch is validated before
        any row is inserted (foundation 3.3).
        """
        if token is None or self._txn_owner_digest is None or self._digest(token) != self._txn_owner_digest:
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
            sequence = int(cursor.lastrowid or 0)
            # The outbox row rides in the same transaction, inseparably: no append
            # path can produce an event without one (foundation 2.1/3.7).
            self._conn.execute(
                "INSERT INTO outbox (message_id, sequence, topic, created_at) VALUES (?,?,?,?);",
                (f"{event.id}:{event.type}", sequence, event.type, now),
            )
            stored.append(
                event.model_copy(
                    update={
                        "sequence": sequence,
                        # Rebuilt from the stored snapshots, not the caller's objects.
                        "payload": json.loads(payload_text),
                        "pinned_versions": json.loads(pinned_text),
                    }
                )
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

        The replay tail. ``after_sequence == 0`` yields the whole log. Delivery
        must use :meth:`read_outboxed_since` instead -- the transactional-outbox
        boundary is the outbox, not the event table (foundation 3.7).
        """
        rows = self._conn.execute(
            f"{self._SELECT_COLUMNS} WHERE sequence > ? ORDER BY sequence ASC;",
            (after_sequence,),
        )
        for row in rows:
            yield self._row_to_event(row)

    def read_outboxed_since(self, after_sequence: int) -> Iterator[DomainEvent]:
        """Yield events past ``after_sequence`` that have an outbox row, in order.

        The delivery tail (foundation 3.7): consumers receive exactly what was
        enqueued through the transactional outbox, never a bare event row.
        """
        rows = self._conn.execute(
            "SELECT e.sequence, e.id, e.type, e.occurred_at, e.actor, e.provider, "
            "e.correlation_id, e.causation_id, e.idempotency_key, e.pinned_versions, "
            "e.payload, e.payload_hash FROM events e "
            "JOIN outbox o ON o.sequence = e.sequence "
            "WHERE e.sequence > ? ORDER BY e.sequence ASC;",
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
        that do nothing -- so this is a **runtime** proof, and the whole probe runs
        inside a SAVEPOINT that is always rolled back. That rollback is what makes
        the probe safe even against a *broken* database: if a no-op trigger let the
        UPDATE or DELETE through, the damage is confined to the savepoint and
        undone before the violation is reported. On an empty log (where row
        triggers cannot fire) a throwaway row is inserted first; the empty table
        guarantees its id cannot collide with a real event.
        """
        self._conn.execute("SAVEPOINT append_only_probe;")
        try:
            if self.count() == 0:
                self._conn.execute(
                    "INSERT INTO events "
                    "(id, type, occurred_at, actor, correlation_id, pinned_versions, payload, payload_hash) "
                    "VALUES ('__probe__','__probe__','1970-01-01T00:00:00+00:00','__probe__',"
                    "'__probe__','{}','{}','probe');"
                )
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
        finally:
            self._conn.execute("ROLLBACK TO append_only_probe;")
            self._conn.execute("RELEASE append_only_probe;")
