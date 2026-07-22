"""Urgency classification of review candidates (control 4.5; roadmap 2.3).

Risk is checked FIRST [R-4]: a critical target must never be silenced by a
saturation or maintenance shortcut. The v1 predicates use exactly the inputs
that exist today and name their absent ones honestly:

- ``risk`` = knowledge state AT_RISK, OR retrievability below the critical
  floor. The recurring-error clause joins when ``ERROR_OBSERVED`` events
  exist (observed record, later in 2.3).
- ``stake`` = CORE/HIGH priority band (lexical targets), OR strong-prerequisite
  leverage from the pinned program. The relevance clause (active goals,
  personal dictionary) joins with the learner module.
- ``saturated`` is always false until saturation state has inputs (control
  4.6 needs presented/exposure history per dimension).

The function is pure over plain dicts -- control never imports the scheduler;
lessons glues the backlog to the classifier at composition time.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from english_trainer.control.policy import step_cost

CRITICAL = "critical"
IMPORTANT = "important"
NORMAL = "normal"
MAINTENANCE = "maintenance"
DEFERRABLE = "deferrable"  # unreachable until saturation has inputs

CLASS_ORDER = (CRITICAL, IMPORTANT, NORMAL, MAINTENANCE)

# The review step type exercising each dimension (control 4.3a matrix).
STEP_TYPE_BY_DIMENSION = {
    "recognition": "recognition_check",
    "controlled_production": "controlled_production",
    "spontaneous_production": "spontaneous_production",
    "transfer": "transfer_task",
}

_PPM = Decimal(1_000_000)


def _leverage_counts(program: dict[str, Any]) -> dict[str, int]:
    """How many topics name each target as a STRONG prerequisite."""
    counts: dict[str, int] = {}
    for topic in program.get("topics", []):
        strong = (topic.get("advisory_prerequisites") or {}).get("strong") or []
        for ref in strong:
            counts[str(ref)] = counts.get(str(ref), 0) + 1
    return counts


def classify_review_candidates(
    backlog: list[dict[str, Any]],
    program: dict[str, Any],
    control_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn scheduler backlog entries into classified review candidates.

    First match wins, risk first (control 4.5): risk∧stake → critical,
    risk → important, retrievability ≥ maintenance floor → maintenance,
    else normal.
    """
    classification = control_policy["classification"]
    critical_floor = int(classification["critical_floor_retrievability_ppm"])
    maintenance_floor = int(classification["maintenance_floor_retrievability_ppm"])
    min_dependents = int(classification["prereq_leverage_min_dependents"])

    leverage = _leverage_counts(program)
    bands = {
        str(unit.get("id")): str(unit.get("curriculum_priority_band", ""))
        for unit in program.get("lexicon", [])
    }
    topics = {str(topic.get("id")): topic for topic in program.get("topics", [])}

    out: list[dict[str, Any]] = []
    for entry in backlog:
        target = str(entry["target_ref"])
        dimension = str(entry["dimension"])
        step_type = STEP_TYPE_BY_DIMENSION.get(dimension, "recognition_check")
        retrievability_ppm = int(Decimal(str(entry.get("retrievability") or "0")) * _PPM)

        risk = entry.get("knowledge_state") == "AT_RISK" or retrievability_ppm < critical_floor
        stake = bands.get(target) in ("CORE", "HIGH") or leverage.get(target, 0) >= min_dependents
        if risk and stake:
            urgency = CRITICAL
        elif risk:
            urgency = IMPORTANT
        elif retrievability_ppm >= maintenance_floor:
            urgency = MAINTENANCE
        else:
            urgency = NORMAL

        topic = topics.get(target)
        criteria_ref = f"criteria:{target}" if topic and topic.get("mastery_criteria") else None
        out.append(
            {
                "candidate_id": f"review:{target}:{dimension}",
                "kind": "review",
                "bucket": "review",
                "step_type": step_type,
                "expected_seconds": step_cost(control_policy, step_type),
                "target_ref": target,
                "dimension": dimension,
                "urgency_class": urgency,
                "stake_rank": 1 if stake else 2,  # 0 = relevance, joins with learner
                "retrievability_ppm": retrievability_ppm,
                "deferral_count": 0,  # joins with the starvation reserve (2.8)
                "criteria_ref": criteria_ref,
                "context_id": f"review|{step_type}",
                "lexicon_first": False,
                "lexicon_refs": [str(r) for r in (topic.get("lexicon") or [])] if topic else [target],
                "schedule_epoch": int(entry.get("schedule_epoch") or 0),
            }
        )
    return out
