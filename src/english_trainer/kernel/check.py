"""Integrity check over the store and its JSONL export (foundation 2.1, 6).

This is the mechanism behind ``trainer database check`` (the typer CLI wrapper
lands with the CLI increment). It verifies three things and, crucially,
distinguishes a real integrity error from mere export lag:

- foreign keys and the expected schema are intact -- and a broken schema is
  *reported*, never raised out of the check;
- the JSONL export matches the event table **up to the acknowledged offset** --
  the full envelope, not just sequence and hash, so a tampered actor or
  correlation id is divergence too -- and each acknowledged line hashes to its
  own payload;
- events past the acknowledged offset are reported as ``pending`` export work,
  **not** an error -- the export trails the commit by design (foundation 2.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from english_trainer.kernel.export import JsonlExporter, event_to_record, verify_line_hashes
from english_trainer.kernel.outbox import OffsetStore
from english_trainer.kernel.store import EventStore

_REQUIRED_TABLES = frozenset(
    {
        "events",
        "outbox",
        "idempotency",
        "consumer_offsets",
        "policies",
        "policy_active",
        "schema_migrations",
    }
)


@dataclass(frozen=True)
class CheckReport:
    """Outcome of :func:`database_check`. ``ok`` is false only on real errors;
    export lag lives in ``pending`` and never sets ``ok`` false."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    pending: dict[str, int] = field(default_factory=dict)


def database_check(store: EventStore, exporter: JsonlExporter) -> CheckReport:
    conn = store._conn
    errors: list[str] = []

    fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_rows:
        errors.append(f"foreign key violations: {len(fk_rows)}")

    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
    missing = _REQUIRED_TABLES - tables
    if missing:
        # A check must report a broken schema, not crash on it: the queries below
        # assume these tables exist, so stop here with a definite verdict.
        errors.append(f"missing tables: {sorted(missing)}")
        return CheckReport(ok=False, errors=errors, pending={})

    applied = OffsetStore(conn).get(exporter.name)
    events = [event for event in store.read() if event.sequence is not None]
    acknowledged_events = [
        event for event in events if event.sequence is not None and event.sequence <= applied
    ]

    try:
        acknowledged_lines = [record for record in exporter.records() if int(record["sequence"]) <= applied]
    except (ValueError, KeyError, TypeError) as exc:
        # A torn or corrupt export file is invalid content -- an error verdict,
        # not an exception out of the check (foundation 2.1).
        errors.append(f"export file unreadable: {exc}")
        return CheckReport(ok=False, errors=errors, pending={})

    if len(acknowledged_lines) != len(acknowledged_events):
        errors.append(
            f"export has {len(acknowledged_lines)} acknowledged lines, "
            f"event table has {len(acknowledged_events)} up to offset {applied}"
        )
    else:
        for record, event in zip(acknowledged_lines, acknowledged_events, strict=True):
            # Full-envelope comparison: any acknowledged field diverging from the
            # event table -- actor, correlation id, pins -- is an error, not just
            # sequence/hash mismatches.
            if record != event_to_record(event):
                errors.append(f"export diverges from event table at sequence {event.sequence}")
                break

    bad_hashes = verify_line_hashes(acknowledged_lines)
    if bad_hashes:
        errors.append(f"export lines with invalid payload_hash: {bad_hashes}")

    pending = {"unexported_events": len(events) - len(acknowledged_events)}
    return CheckReport(ok=not errors, errors=errors, pending=pending)
