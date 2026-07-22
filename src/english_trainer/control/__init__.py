"""Control: the composition brain of a session (control contract 0.12).

This module owns the *policy logic* -- executable ``control@1`` values, the
canonical composition pipeline, candidate discovery, ledger arithmetic and the
safety predicate -- as pure, deterministic functions. The *transactions* that
apply them (``session start`` composing a plan, ``session next`` claiming a
step under CAS) live in :mod:`english_trainer.lessons`: the canon assigns the
CLI commands to lessons and their behavior to control, and this split mirrors
that assignment without an import cycle.
"""

from english_trainer.control.classify import CLASS_ORDER, classify_review_candidates
from english_trainer.control.compose import compose_plan, step_targets
from english_trainer.control.errors import (
    BudgetTooSmall,
    ControlPolicyInvalid,
    NoCandidates,
    PlanVersionConflict,
    ProbePrecondition,
    SignalInvalid,
)
from english_trainer.control.policy import (
    CONTROL_KIND,
    PRODUCTION_STEP_TYPES,
    mode_shares,
    require_valid,
    step_cost,
    validate_control_policy,
)
from english_trainer.control.signals import (
    active_signals,
    apply_signals,
    build_probe_candidate,
    build_signal,
    current_session_seq,
    derive_probe,
    is_excluded,
    record_signal,
)

__all__ = [
    "CLASS_ORDER",
    "CONTROL_KIND",
    "PRODUCTION_STEP_TYPES",
    "BudgetTooSmall",
    "ControlPolicyInvalid",
    "NoCandidates",
    "PlanVersionConflict",
    "ProbePrecondition",
    "SignalInvalid",
    "active_signals",
    "apply_signals",
    "build_probe_candidate",
    "build_signal",
    "classify_review_candidates",
    "compose_plan",
    "current_session_seq",
    "derive_probe",
    "is_excluded",
    "mode_shares",
    "record_signal",
    "require_valid",
    "step_cost",
    "step_targets",
    "validate_control_policy",
]
