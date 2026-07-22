"""Urgency classification of review candidates (control 4.5; roadmap 2.3, 2.8b).

Risk is checked FIRST [R-4]: a critical target must never be silenced by a
saturation or maintenance shortcut. The predicates use exactly the inputs that
exist today and name their absent ones honestly:

- ``risk`` = knowledge state AT_RISK, OR a recurring live error (control 4.6),
  OR retrievability below the critical floor. The recurring-error clause joins
  when ``recurring_errors`` is supplied -- an empty set (no ``ERROR_OBSERVED``
  events) leaves it false.
- ``stake`` = CORE/HIGH priority band (lexical targets), OR strong-prerequisite
  leverage from the pinned program. The relevance clause (active goals,
  personal dictionary) joins with the learner module.
- ``saturated`` (rule 3, AFTER risk) reads the per-dimension ``SaturationState``
  (control 4.6) via ``is_saturated``; it stays false while ``saturation``/``now``
  are absent, so the ``deferrable`` class is unreachable without inputs.
- ``deferral_count`` / ``qualified_at_session_seq`` come from the starvation
  fold (control 4.5); both default to ``0`` / ``None`` without ``deferrals``.

The function is pure over plain dicts -- control never imports the scheduler;
lessons glues the backlog, saturation, recurring-error and deferral state to the
classifier at composition time (that wiring is DEFERRED to the lessons domain).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from english_trainer.control.deferral import DeferralState
from english_trainer.control.policy import step_cost
from english_trainer.control.saturation import Key, SaturationState, is_saturated

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
    *,
    saturation: dict[Key, SaturationState] | None = None,
    recurring_errors: frozenset[Key] | None = None,
    deferrals: dict[Key, DeferralState] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Turn scheduler backlog entries into classified review candidates.

    First match wins, risk first (control 4.5): risk∧stake → critical,
    risk → important, saturated → deferrable, retrievability ≥ maintenance floor
    → maintenance, else normal.

    The keyword inputs are the DEFERRED composition-time state; each defaults to
    the honest empty case (no saturation, no recurring error, no deferrals), so
    an existing caller that passes none gets byte-identical output to before.
    ``now`` is required only to evaluate the saturation transfer-staleness branch.
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
        key: Key = (target, dimension)

        recurring = recurring_errors is not None and key in recurring_errors
        risk = entry.get("knowledge_state") == "AT_RISK" or recurring or retrievability_ppm < critical_floor
        stake = bands.get(target) in ("CORE", "HIGH") or leverage.get(target, 0) >= min_dependents

        saturated = False
        saturation_state: SaturationState | None = None
        if saturation is not None and now is not None:
            saturation_state = saturation.get(key)
            saturated = saturation_state is not None and is_saturated(saturation_state, control_policy, now)

        # The total ordered §4.5 table, first match wins, risk before saturation.
        if risk and stake:
            urgency = CRITICAL
            matched_rule = "control.4.5.rule.1"
        elif risk:
            urgency = IMPORTANT
            matched_rule = "control.4.5.rule.2"
        elif saturated:
            urgency = DEFERRABLE
            matched_rule = "control.4.5.rule.3"
        elif retrievability_ppm >= maintenance_floor:
            urgency = MAINTENANCE
            matched_rule = "control.4.5.rule.4"
        else:
            urgency = NORMAL
            matched_rule = "control.4.5.rule.5"

        deferral_count = 0
        qualified_at_session_seq: int | None = None
        if deferrals is not None:
            deferral_state = deferrals.get(key)
            if deferral_state is not None:
                deferral_count = deferral_state.deferral_count
                qualified_at_session_seq = deferral_state.qualified_at_session_seq

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
                "risk": risk,
                "stake": stake,
                "stake_rank": 1 if stake else 2,  # 0 = relevance, joins with learner
                "retrievability_ppm": retrievability_ppm,
                "deferral_count": deferral_count,  # from the starvation fold (4.5)
                "qualified_at_session_seq": qualified_at_session_seq,  # reserve order key
                "criteria_ref": criteria_ref,
                "context_id": f"review|{step_type}",
                "lexicon_first": False,
                "lexicon_refs": [str(r) for r in (topic.get("lexicon") or [])] if topic else [target],
                "schedule_epoch": int(entry.get("schedule_epoch") or 0),
                "classification_trace": {
                    "matched_rule": matched_rule,
                    "risk": risk,
                    "risk_factors": {
                        "at_risk_state": entry.get("knowledge_state") == "AT_RISK",
                        "recurring_error": recurring,
                        "below_retrievability_floor": retrievability_ppm < critical_floor,
                    },
                    "stake": stake,
                    "stake_factors": {
                        "priority_band": bands.get(target) in ("CORE", "HIGH"),
                        "prerequisite_leverage": leverage.get(target, 0) >= min_dependents,
                        "relevance": False,
                    },
                    "retrievability_ppm": retrievability_ppm,
                    "urgency_class": urgency,
                    "saturation": (
                        {
                            "exposures_in_window": saturation_state.exposures_in_window,
                            "consecutive_independent_successes": (
                                saturation_state.consecutive_independent_successes
                            ),
                            "distinct_contexts": saturation_state.distinct_contexts,
                            "last_transfer_check_at": saturation_state.last_transfer_check_at,
                            "saturated": saturated,
                        }
                        if saturation_state is not None
                        else None
                    ),
                },
            }
        )
    return out
