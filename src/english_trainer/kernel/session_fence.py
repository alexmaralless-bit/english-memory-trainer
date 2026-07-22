"""One implementation of the public optimistic session fence.

Business modules share this helper so checking and bumping the session token
always happens in the same UnitOfWork as the command's own effects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.errors import KernelError, SessionRevisionConflict
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

SESSION_AGGREGATE = "session"


def current_session_revision(store: EventStore, session_id: str) -> int:
    """Return the public optimistic token for the next session mutation."""
    found = read_aggregate(store._conn, SESSION_AGGREGATE, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    return found[1]


def load_session_for_update(
    store: EventStore, session_id: str, expected_session_revision: int
) -> tuple[dict[str, Any], int]:
    found = read_aggregate(store._conn, SESSION_AGGREGATE, session_id)
    if found is None:
        raise KernelError(f"session {session_id} does not exist")
    state, revision = found
    if revision != expected_session_revision:
        raise SessionRevisionConflict(
            session_id=session_id,
            expected=expected_session_revision,
            current=revision,
        )
    return state, revision


def bump_session(
    uow: UnitOfWork,
    session_id: str,
    state: dict[str, Any],
    revision: int,
    occurred_at: datetime,
    *,
    changes: dict[str, Any] | None = None,
) -> int:
    new_state = {
        **state,
        **(changes or {}),
        "last_activity_at": occurred_at.isoformat(),
    }
    uow.save_aggregate(
        SESSION_AGGREGATE,
        session_id,
        new_state,
        expected_revision=revision,
    )
    return revision + 1
