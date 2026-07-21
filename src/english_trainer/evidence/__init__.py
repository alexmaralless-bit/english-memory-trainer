"""Evidence: the only door through which knowledge reaches scoring (0.4).

The module accepts the agent's observations, checks admissibility and semantic
identity, and persists everything as event-sourced facts. The agent reports;
**the engine classifies** -- target, dimension, mode and origin are derived
from the delivered step, never taken from the client. It reads only published
events and its own aggregates: the event log is the module boundary.
"""

from english_trainer.evidence.attempts import (
    ASSESSED,
    ATTEMPT_AGGREGATE,
    CLOSED_UNASSESSED,
    EVENT_ATTEMPT_RECORDED,
    EVENT_ATTEMPT_STATE_CHANGED,
    RECORDED,
    REQUIRES_EXERCISE_INSTANCE,
    EvidencePrecondition,
    close_pending_attempts,
    list_notes,
    pending_attempts,
    record_attempt,
    session_attempts,
)

__all__ = [
    "ASSESSED",
    "ATTEMPT_AGGREGATE",
    "CLOSED_UNASSESSED",
    "EVENT_ATTEMPT_RECORDED",
    "EVENT_ATTEMPT_STATE_CHANGED",
    "RECORDED",
    "REQUIRES_EXERCISE_INSTANCE",
    "EvidencePrecondition",
    "close_pending_attempts",
    "list_notes",
    "pending_attempts",
    "record_attempt",
    "session_attempts",
]
