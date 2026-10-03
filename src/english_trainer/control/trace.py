"""DecisionTrace construction and lookup (control 4.8).

Trace fields are split into computed inputs, immutable facts and catalogue
parameter references.  That shape makes every leaf explainable without copying
policy metadata into each plan.
"""

from __future__ import annotations

from typing import Any

from english_trainer.control.policy import AUTOMATICITY_STEP_TYPES, DRILL_BLOCK
from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

TRACE_AGGREGATE = "decision_trace"


class DecisionTraceUnavailable(KernelError):
    """A step id is unknown or predates decision-trace persistence."""

    code = "DECISION_TRACE_UNAVAILABLE"


def _automaticity_trace(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Why an automaticity-loop step looks the way it does (control 4.6).

    Names the three facts that are otherwise invisible in the plan: whether the
    block was blocked or interleaved, which contrast targets were chosen (and
    whether the interleave had to fall back for want of them), and that the
    block is accounted as ONE exposure regardless of how many items it runs.
    """
    step_type = str(candidate.get("step_type") or "")
    if step_type not in AUTOMATICITY_STEP_TYPES:
        return None
    reasons: dict[str, Any] = {
        "step_type": step_type,
        "matched_rule": "control.4.6.automaticity-loop",
    }
    if step_type == DRILL_BLOCK:
        reasons["mode"] = candidate.get("drill_mode")
        reasons["rounds"] = candidate.get("rounds")
        reasons["round_size"] = candidate.get("round_size")
        reasons["contrast_targets"] = [
            {"target_ref": item.get("target_ref"), "dimension": item.get("dimension")}
            for item in candidate.get("contrast_targets") or []
        ]
        reasons["contrast_rule"] = (
            "authored_contrast_refs_then_same_track_and_cefr" if candidate.get("contrast_targets") else None
        )
        if candidate.get("contrast_waiver"):
            reasons["waiver"] = "NO_CONTRAST_CANDIDATE"
        # The rule the whole step type depends on: a block is one exposure for
        # saturation and one step for max_steps_per_topic, whatever its size.
        reasons["exposure_accounting"] = "block_counts_as_one_exposure"
    if step_type == "timed_writing":
        reasons["declared_limit_seconds"] = candidate.get("declared_limit_seconds")
    if step_type == "reconstruction":
        reasons["text_ref"] = candidate.get("text_ref")
    return reasons


def build_decision_trace(
    candidate: dict[str, Any],
    *,
    decision_id: str,
    policy: dict[str, Any],
    generation_version: str,
    pinned_versions: dict[str, str] | None,
    active_safety_version: str | None,
    bucket_before: dict[str, int],
    bucket_after: dict[str, int],
) -> dict[str, Any]:
    """Materialize one total, canonical trace for an admitted candidate."""
    classification = dict(candidate.get("classification_trace") or {})
    if not classification:
        classification = {
            "matched_rule": "control.4.4.candidate-source",
            "risk": None,
            "stake": None,
            "retrievability_ppm": None,
            "urgency_class": candidate.get("urgency_class"),
            "saturation": None,
        }
    automaticity = _automaticity_trace(candidate)
    pins = dict(sorted((pinned_versions or {}).items()))
    pins["control_policy"] = str(policy.get("policy_id") or "control@1")
    pins.setdefault("generation", generation_version)
    diversity = policy["diversity"]
    return {
        "schema_version": 1,
        "decision_id": decision_id,
        "rule_refs": [str(classification["matched_rule"])],
        "computed_inputs": {
            "risk": classification.get("risk"),
            "risk_factors": classification.get("risk_factors"),
            "stake": classification.get("stake"),
            "stake_factors": classification.get("stake_factors"),
            "retrievability_ppm": classification.get("retrievability_ppm"),
            "urgency_class": candidate.get("urgency_class"),
            "saturation": classification.get("saturation"),
            "applied_signal_ids": sorted(str(item) for item in candidate.get("applied_signal_ids", [])),
            "bucket_occupancy_before": dict(sorted(bucket_before.items())),
            "bucket_occupancy_after": dict(sorted(bucket_after.items())),
            # Present only for the automaticity loop, so every historical trace
            # keeps its exact canonical shape.
            **({"automaticity": automaticity} if automaticity else {}),
        },
        "parameters": {
            "max_consecutive_same_mode": {
                "parameter_id": "control.diversity.max_consecutive_same_mode",
                "value": int(diversity["max_consecutive_same_mode"]),
            },
            "max_steps_per_topic": {
                "parameter_id": "control.diversity.max_steps_per_topic",
                "value": int(diversity["max_steps_per_topic"]),
            },
        },
        "facts": {
            "pinned_versions": pins,
            "active_safety_version": active_safety_version,
        },
    }


def explain(store: EventStore, step_id: str) -> dict[str, Any]:
    """Return the persisted trace for ``step_id``; never recompute history."""
    persisted = read_aggregate(store._conn, TRACE_AGGREGATE, step_id)
    if persisted is not None:
        return dict(persisted[0])
    # Compatibility for plans created between trace materialization and the
    # immutable trace aggregate: a live plan may still carry the snapshot.
    for _, state, _ in list_aggregates(store._conn, "session_plan"):
        for step in state.get("steps") or []:
            if str(step.get("step_id")) != step_id:
                continue
            trace = step.get("decision_trace")
            if not isinstance(trace, dict):
                raise DecisionTraceUnavailable(f"step {step_id} has no persisted decision trace")
            return dict(trace)
    raise DecisionTraceUnavailable(f"step {step_id} does not exist")


def save_decision_traces(uow: UnitOfWork, plan_state: dict[str, Any]) -> None:
    """Persist every new step trace immutably in the plan-creation UoW."""
    for step in plan_state.get("steps") or []:
        step_id = str(step.get("step_id"))
        trace = step.get("decision_trace")
        if not step_id or not isinstance(trace, dict):
            continue
        if uow.get_aggregate(TRACE_AGGREGATE, step_id) is not None:
            continue
        uow.save_aggregate(TRACE_AGGREGATE, step_id, dict(trace), expected_revision=0)
