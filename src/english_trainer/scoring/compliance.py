"""Tutor Compliance Score over read-only audit obligation observations."""

from __future__ import annotations

from typing import Any

from english_trainer.audit import obligations
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

_TERMINAL_SESSIONS = {"session.finished", "session.abandoned", "session.stale_abandoned"}


def tutor_compliance(store: EventStore, registry: PolicyRegistry) -> dict[str, Any]:
    """Score the last N fully observed terminal sessions, or return no-data."""
    events = list(store.read())
    terminal_ids = [
        str(event.correlation_id)
        for event in events
        if event.type in _TERMINAL_SESSIONS and event.correlation_id
    ]
    complete = [
        report
        for session_id in terminal_ids
        if (report := obligations(store, registry, session_id))["status"] == "complete"
    ]
    if not complete:
        return {"status": "no-data", "score": None, "sessions": 0, "satisfied": 0, "applicable": 0}
    last_session_id = str(complete[-1]["session_id"])
    started = next(
        event
        for event in events
        if event.type == "session.started" and event.correlation_id == last_session_id
    )
    version = str(dict((started.payload.get("manifest") or {}).get("pinned_versions") or {})["obligations"])
    policy = registry.resolve_pinned("obligations", version)
    selected = complete[-int(policy.get("measurement_window_terminal_sessions", 10)) :]
    applicable = [item for report in selected for item in report["observations"] if item.get("applicable")]
    if not applicable:
        return {
            "status": "no-data",
            "score": None,
            "sessions": len(selected),
            "satisfied": 0,
            "applicable": 0,
        }
    satisfied = sum(1 for item in applicable if item.get("satisfied"))
    return {
        "status": "measured",
        "score": satisfied * 100 // len(applicable),
        "sessions": len(selected),
        "satisfied": satisfied,
        "applicable": len(applicable),
    }
