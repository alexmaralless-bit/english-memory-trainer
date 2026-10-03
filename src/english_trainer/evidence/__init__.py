"""Evidence: the only door through which knowledge reaches scoring (0.4).

The module turns the tutor's lesson report into event-sourced facts (the pure
builders in :mod:`english_trainer.evidence.report`), keeps semantic identity
(one credited span per target and dimension) and settles review assignments.
**The engine classifies** -- scores, review outcomes and error spans are
derived from the pinned policies, never taken from the client. It reads only
published events and its own aggregates: the event log is the module boundary.
"""

from english_trainer.evidence.attempts import (
    ASSESSED,
    ATTEMPT_AGGREGATE,
    CLOSED_UNASSESSED,
    EVENT_ATTEMPT_RECORDED,
    EVENT_ATTEMPT_STATE_CHANGED,
    RECORDED,
    EvidencePrecondition,
    close_pending_attempts,
    pending_attempts,
    session_attempts,
)
from english_trainer.evidence.observed import EVENT_ERROR_OBSERVED

__all__ = [
    "ASSESSED",
    "ATTEMPT_AGGREGATE",
    "CLOSED_UNASSESSED",
    "EVENT_ATTEMPT_RECORDED",
    "EVENT_ATTEMPT_STATE_CHANGED",
    "EVENT_ERROR_OBSERVED",
    "RECORDED",
    "EvidencePrecondition",
    "close_pending_attempts",
    "pending_attempts",
    "session_attempts",
]
