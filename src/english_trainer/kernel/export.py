"""JSONL derived export of the event log (foundation 2.1).

The authoritative log lives in the SQLite ``events`` table. The JSONL file is a
**derived, rebuildable** view of it -- for audit, git diffs, human reading, and
replay cross-checks. It is never a source of truth: it can be regenerated
byte-for-byte from the event table at any time, and the same events always
produce the same file.

The exporter is an outbox consumer (foundation 3.7): ``deliver`` appends one
canonical JSON line per event and advances the export offset. Because a file
append and a SQLite commit cannot share one transaction, delivery is
at-least-once -- a crash between the append and the offset commit can leave a
trailing line past the committed offset. ``reconcile`` trims exactly those lines
on the next run, so the acknowledged prefix (up to the committed offset) is
always exact (foundation 2.1: lag is not an integrity error, divergence is).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.encoding import canonical_json, payload_hash
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.outbox import OffsetStore, deliver
from english_trainer.kernel.store import EventStore

EXPORT_CONSUMER = "jsonl-export"


def event_to_record(event: DomainEvent) -> dict[str, object]:
    """The line-record for an event: envelope fields with ``occurred_at`` as an
    ISO string so the whole thing is canonical-JSON serializable."""
    return {
        "sequence": event.sequence,
        "id": event.id,
        "type": event.type,
        "occurred_at": event.occurred_at.isoformat(),
        "actor": event.actor,
        "provider": event.provider,
        "correlation_id": event.correlation_id,
        "causation_id": event.causation_id,
        "idempotency_key": event.idempotency_key,
        "pinned_versions": event.pinned_versions,
        "payload": event.payload,
        "payload_hash": event.payload_hash,
    }


def _line(event: DomainEvent) -> str:
    # canonical_json guarantees sorted keys and escaped non-ASCII, so a line is
    # one deterministic representation of the event regardless of field order.
    return canonical_json(event_to_record(event)).decode("ascii")


class JsonlExporter:
    """Append-only JSONL export consumer over a single file (foundation 2.1)."""

    name = EXPORT_CONSUMER

    def __init__(self, path: Path) -> None:
        self._path = path

    def apply(self, event: DomainEvent) -> None:
        with self._path.open("a", encoding="ascii") as handle:
            handle.write(_line(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def reconcile(self, applied_sequence: int) -> None:
        """Drop any lines past the committed offset (crash-recovery for the
        at-least-once file effect). Lines are in ``sequence`` order, so the tail
        beyond ``applied_sequence`` is exactly the un-acknowledged remainder.

        Rewrites the file only when there is a tail to trim; the common path (a
        fully-acknowledged file) leaves it untouched, avoiding a needless
        truncate-and-write on every delivery."""
        if not self._path.exists():
            return
        lines = [raw for raw in self._path.read_text(encoding="ascii").splitlines() if raw.strip()]
        kept: list[str] = []
        for raw in lines:
            if int(json.loads(raw)["sequence"]) <= applied_sequence:
                kept.append(raw)
            else:
                break
        if len(kept) == len(lines):
            return  # nothing beyond the offset; leave the file as is
        self._path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="ascii")

    def rebuild(self, events: Iterable[DomainEvent]) -> None:
        """Regenerate the whole file from ``events``. Byte-identical for equal
        input -- the idempotent full export the contract requires."""
        lines = [_line(event) for event in events]
        self._path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="ascii")

    def records(self) -> list[dict[str, Any]]:
        """Parse the current file into its line-records, in file order."""
        if not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        for raw in self._path.read_text(encoding="ascii").splitlines():
            if raw.strip():
                out.append(json.loads(raw))
        return out


def export_pending(store: EventStore, exporter: JsonlExporter, clock: Clock) -> int:
    """Deliver newly-appended events to the JSONL file. Returns lines written."""
    return deliver(store, exporter, clock)


def rebuild_export(store: EventStore, exporter: JsonlExporter, clock: Clock) -> None:
    """Regenerate the file from the event table and reset the export offset to
    the last event -- the recovery path for a corrupt or missing export."""
    events = list(store.read())
    exporter.rebuild(events)
    last = events[-1].sequence if events else 0
    assert last is not None
    conn = store._conn
    conn.execute("BEGIN;")
    try:
        OffsetStore(conn).set(exporter.name, last, clock.now().isoformat())
        conn.execute("COMMIT;")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise


def verify_line_hashes(records: Iterable[dict[str, Any]]) -> list[int]:
    """Return the sequences whose ``payload_hash`` does not match their payload
    -- invalid content, independent of the event table (foundation 2.1)."""
    bad: list[int] = []
    for record in records:
        payload = record.get("payload", {})
        if record.get("payload_hash") != payload_hash(payload):
            bad.append(int(record["sequence"]))
    return bad
