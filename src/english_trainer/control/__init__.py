"""Control: the composition brain of a session (control contract 0.12).

This module owns the *policy logic* -- executable ``control@1`` values, the
canonical composition pipeline, candidate discovery, ledger arithmetic and the
safety predicate -- as pure, deterministic functions. The *transactions* that
apply them (``session start`` composing a plan, ``session next`` claiming a
step under CAS) live in :mod:`english_trainer.lessons`: the canon assigns the
CLI commands to lessons and their behavior to control, and this split mirrors
that assignment without an import cycle.
"""

from english_trainer.control.availability import (
    availability_get,
    availability_set,
    divergence_ppm,
    is_long_break,
    observed_availability,
    resolve_total_seconds,
    validate_declared,
)
from english_trainer.control.classify import CLASS_ORDER, classify_review_candidates
from english_trainer.control.compose import (
    compose_plan,
    contrast_targets,
    drill_block_mode,
    step_targets,
)
from english_trainer.control.deferral import (
    DeferralState,
    qualified_candidates,
    reduce_deferrals,
)
from english_trainer.control.errors import (
    AvailabilityInvalid,
    BudgetTooSmall,
    ControlPolicyInvalid,
    NoCandidates,
)
from english_trainer.control.metrics import metrics
from english_trainer.control.policy import (
    CONTRAST_MAX,
    CONTRAST_MIN,
    CONTROL_KIND,
    PRODUCTION_STEP_TYPES,
    STEP_TYPE_RANK,
    STEP_TYPES_BY_KIND,
    mode_shares,
    require_valid,
    step_cost,
    validate_control_policy,
)
from english_trainer.control.saturation import (
    SaturationState,
    is_saturated,
    recurring_error_keys,
    reduce_saturation,
)
from english_trainer.control.signals import (
    active_signals,
    apply_signals,
    build_probe_candidate,
    current_session_seq,
    is_excluded,
)
from english_trainer.control.trace import (
    DecisionTraceUnavailable,
    build_decision_trace,
    explain,
    save_decision_traces,
)
from english_trainer.control.tunables import (
    CalibrationPrecondition,
    TunableCatalogueInvalid,
    confirm_calibration,
    list_calibrations,
    list_tunables,
    propose_calibration,
    require_valid_catalogue,
    validate_catalogue,
)

__all__ = [
    "CLASS_ORDER",
    "CONTRAST_MAX",
    "CONTRAST_MIN",
    "CONTROL_KIND",
    "PRODUCTION_STEP_TYPES",
    "STEP_TYPES_BY_KIND",
    "STEP_TYPE_RANK",
    "AvailabilityInvalid",
    "BudgetTooSmall",
    "CalibrationPrecondition",
    "ControlPolicyInvalid",
    "DecisionTraceUnavailable",
    "DeferralState",
    "NoCandidates",
    "SaturationState",
    "TunableCatalogueInvalid",
    "active_signals",
    "apply_signals",
    "availability_get",
    "availability_set",
    "build_decision_trace",
    "build_probe_candidate",
    "classify_review_candidates",
    "compose_plan",
    "confirm_calibration",
    "contrast_targets",
    "current_session_seq",
    "divergence_ppm",
    "drill_block_mode",
    "explain",
    "is_excluded",
    "is_long_break",
    "is_saturated",
    "list_calibrations",
    "list_tunables",
    "metrics",
    "mode_shares",
    "observed_availability",
    "propose_calibration",
    "qualified_candidates",
    "recurring_error_keys",
    "reduce_deferrals",
    "reduce_saturation",
    "require_valid",
    "require_valid_catalogue",
    "resolve_total_seconds",
    "save_decision_traces",
    "step_cost",
    "step_targets",
    "validate_catalogue",
    "validate_control_policy",
    "validate_declared",
]
