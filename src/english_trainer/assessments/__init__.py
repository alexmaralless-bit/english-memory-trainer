"""assessments: placement diagnostics -- forms, lifecycle, exposure (2.6).

The module owns the *procedure* of placement: fixed authored versioned forms,
their lifecycle (checkpoint / resume / one terminal submit), exposure history
with down-weighting, and the ``origin=placement`` hand-off to scoring (which
owns the ACTIVE ceiling). It reads only published events and its own
aggregates; the event log is its boundary with scoring/scheduler/learner.
"""

from english_trainer.assessments.forms import (
    DEFAULT_FORM_VERSION,
    UnknownForm,
    item_exposure_id,
    select_form,
)
from english_trainer.assessments.placement import (
    EVENT_ABANDONED,
    EVENT_CHECKPOINT,
    EVENT_DECLINED,
    EVENT_EXPIRED,
    EVENT_RESUMED,
    EVENT_SCORED,
    EVENT_STARTED,
    EVENT_SUBMITTED,
    PLACEMENT_AGGREGATE,
    PlacementPrecondition,
    abandon_placement,
    active_placement_id,
    answer_placement,
    decline_placement,
    ensure_policy,
    get_placement,
    resume_placement,
    start_placement,
    submit_placement,
    sweep_expired_placements,
)
from english_trainer.assessments.policy import (
    ASSESSMENTS_KIND,
    ASSESSMENTS_VERSION,
    CEFR_LEVELS,
    CORE_SKILLS,
    AssessmentsPolicyInvalid,
    default_policy,
    require_valid,
    resume_window,
    validate_assessments_policy,
)
from english_trainer.assessments.self_assessment import (
    SELF_ASSESSMENT_SCHEMA_VERSION,
    SelfAssessmentInvalid,
    normalize_self_assessment,
)

__all__ = [
    "ASSESSMENTS_KIND",
    "ASSESSMENTS_VERSION",
    "CEFR_LEVELS",
    "CORE_SKILLS",
    "DEFAULT_FORM_VERSION",
    "EVENT_ABANDONED",
    "EVENT_CHECKPOINT",
    "EVENT_DECLINED",
    "EVENT_EXPIRED",
    "EVENT_RESUMED",
    "EVENT_SCORED",
    "EVENT_STARTED",
    "EVENT_SUBMITTED",
    "PLACEMENT_AGGREGATE",
    "SELF_ASSESSMENT_SCHEMA_VERSION",
    "AssessmentsPolicyInvalid",
    "PlacementPrecondition",
    "SelfAssessmentInvalid",
    "UnknownForm",
    "abandon_placement",
    "active_placement_id",
    "answer_placement",
    "decline_placement",
    "default_policy",
    "ensure_policy",
    "get_placement",
    "item_exposure_id",
    "normalize_self_assessment",
    "require_valid",
    "resume_placement",
    "resume_window",
    "select_form",
    "start_placement",
    "submit_placement",
    "sweep_expired_placements",
    "validate_assessments_policy",
]
