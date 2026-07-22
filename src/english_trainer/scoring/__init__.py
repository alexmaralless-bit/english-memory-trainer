"""Scoring: the only writer of the evaluative state (contract 0.4, part 2).

Two axes deliberately separated: Mastery (quality, 0-100 per dimension) and
Stability/Retrievability (memory). Scores are a pure Decimal fold over the
event log under a pinned versioned policy -- no floats, no wall-clock inputs,
so ``trainer scoring replay`` can prove the fold reproduces byte-identically.
The module reads only published events (evidence, scheduler) and its policy:
the event log is the module boundary.
"""

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
from english_trainer.scoring.replay import replay_scores

__all__ = [
    "ACTIVE",
    "AT_RISK",
    "EVIDENCE_ADDED_EVENT",
    "LEARNING",
    "MASTERED",
    "NEW",
    "OUTCOMES",
    "SCORING_KIND",
    "ScoringPolicyInvalid",
    "TargetState",
    "fold_scores",
    "replay_scores",
    "require_valid",
    "retrievability",
    "scoring_context",
    "snapshot",
    "transition",
    "validate_scoring_policy",
]
