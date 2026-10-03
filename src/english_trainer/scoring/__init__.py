"""Scoring: the only writer of the evaluative state (contract 0.4, part 2).

Two axes deliberately separated: Mastery (quality, 0-100 per dimension) and
Stability/Retrievability (memory). Scores are a pure Decimal fold over the
event log under a pinned versioned policy -- no floats, no wall-clock inputs,
so ``trainer scoring replay`` can prove the fold reproduces byte-identically.
The module reads only published events (evidence, scheduler) and its policy:
the event log is the module boundary.
"""

from english_trainer.scoring.automaticity import (
    AUTOMATIC,
    AUTOMATICITY_KIND,
    DELIBERATE,
    EVENT_AUTOMATICITY_UPDATED,
    NOT_MEASURED,
    PROCEDURALIZED,
    AutomaticityPolicyInvalid,
    AutomaticityState,
    automaticity_snapshot,
    backfill_automaticity_updates,
    build_automaticity_update,
    fold_automaticity,
    require_valid_automaticity,
    validate_automaticity_policy,
)
from english_trainer.scoring.engine import (
    ACTIVE,
    AT_RISK,
    EVIDENCE_ADDED_EVENT,
    LEARNING,
    MASTERED,
    NEW,
    OUTCOMES,
    TargetState,
    fold_scores,
    retrievability,
    snapshot,
    transition,
)
from english_trainer.scoring.policy import (
    SCORING_KIND,
    ScoringPolicyInvalid,
    require_valid,
    scoring_context,
    validate_scoring_policy,
)
from english_trainer.scoring.replay import replay_automaticity, replay_scores

__all__ = [
    "ACTIVE",
    "AT_RISK",
    "AUTOMATIC",
    "AUTOMATICITY_KIND",
    "DELIBERATE",
    "EVENT_AUTOMATICITY_UPDATED",
    "EVIDENCE_ADDED_EVENT",
    "LEARNING",
    "MASTERED",
    "NEW",
    "NOT_MEASURED",
    "OUTCOMES",
    "PROCEDURALIZED",
    "SCORING_KIND",
    "AutomaticityPolicyInvalid",
    "AutomaticityState",
    "ScoringPolicyInvalid",
    "TargetState",
    "automaticity_snapshot",
    "backfill_automaticity_updates",
    "build_automaticity_update",
    "fold_automaticity",
    "fold_scores",
    "replay_automaticity",
    "replay_scores",
    "require_valid",
    "require_valid_automaticity",
    "retrievability",
    "scoring_context",
    "snapshot",
    "transition",
    "validate_automaticity_policy",
    "validate_scoring_policy",
]
