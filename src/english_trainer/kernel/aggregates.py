"""Reading revisioned operational aggregates (foundation 3.5).

Mutable operational state -- sessions, review assignments, queues -- lives in
the ``aggregates`` table as revisioned documents. Reads are plain and can
happen anywhere; **writes go only through the UnitOfWork** (``save_aggregate``),
which enforces compare-and-set: the caller states the revision it read, and a
write against any other revision is refused with a stable ``StaleRevision``.
Several aggregates saved in one UnitOfWork commit all-or-nothing -- one stale
expectation rolls back every write of the transaction, along with its events
and outbox rows. Partial success is impossible by construction.

The kernel owns this mechanism only; which aggregate types exist and what their
state means belongs to the business modules (0.5 owns the aggregate-boundary
rules). State is canonically encoded, so the float ban and NFC discipline of
event payloads apply to operational state too.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def read_aggregate(
    conn: sqlite3.Connection, aggregate_type: str, aggregate_id: str
) -> tuple[dict[str, Any], int] | None:
    """Return ``(state, revision)`` or ``None`` -- never a half-loaded object."""
    row = conn.execute(
        "SELECT state, revision FROM aggregates WHERE aggregate_type = ? AND aggregate_id = ?;",
        (aggregate_type, aggregate_id),
    ).fetchone()
    if row is None:
        return None
    state: dict[str, Any] = json.loads(row["state"])
    return state, int(row["revision"])
