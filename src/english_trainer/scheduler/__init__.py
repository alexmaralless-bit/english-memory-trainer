"""Scheduler: when to repeat (contract 0.4, part 3).

Never a gatekeeper -- the overdue backlog shapes recommendations and the
session manifest, never topic availability. Schedules are a pure fold over
published events; ``review_status`` is computed from the schedule and the
clock, while the AT_RISK crossing is an append-only replayable fact with a
deterministic boundary instant.
"""

from english_trainer.scheduler.engine import (
    DUE,
    EVENT_OVERDUE_AT_RISK,
    NOT_DUE,
    OVERDUE,
    ScheduleState,
    at_risk_boundary,
    due_backlog,
    fold_schedules,
    review_status,
    sweep_overdue,
)
from english_trainer.scheduler.policy import (
    SCHEDULER_KIND,
    SchedulerPolicyInvalid,
    effective_intervals_days,
    require_valid,
    validate_scheduler_policy,
)

__all__ = [
    "DUE",
    "EVENT_OVERDUE_AT_RISK",
    "NOT_DUE",
    "OVERDUE",
    "SCHEDULER_KIND",
    "ScheduleState",
    "SchedulerPolicyInvalid",
    "at_risk_boundary",
    "due_backlog",
    "effective_intervals_days",
    "fold_schedules",
    "require_valid",
    "review_status",
    "sweep_overdue",
    "validate_scheduler_policy",
]
