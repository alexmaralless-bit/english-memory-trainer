"""Persisted, catalogue-resolvable DecisionTrace facts (control 4.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.classify import classify_review_candidates
from english_trainer.control.compose import compose_plan
from english_trainer.control.trace import DecisionTraceUnavailable, explain, save_decision_traces
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_classification_names_the_first_matching_rule_and_computed_inputs() -> None:
    program = {
        "topics": [],
        "lexicon": [{"id": "lex.x", "curriculum_priority_band": "CORE"}],
    }
    (candidate,) = classify_review_candidates(
        [
            {
                "target_ref": "lex.x",
                "dimension": "recognition",
                "retrievability": "0.4",
                "knowledge_state": "ACTIVE",
                "schedule_epoch": 1,
            }
        ],
        program,
        policy(),
    )
    trace = candidate["classification_trace"]
    assert trace["matched_rule"] == "control.4.5.rule.1"
    assert trace["risk"] is True and trace["stake"] is True
    assert trace["retrievability_ppm"] == 400_000
    assert trace["risk_factors"]["below_retrievability_floor"] is True


def test_every_materialized_step_carries_a_total_trace() -> None:
    counter = iter(range(100))
    plan = compose_plan(
        program={
            "topics": [
                {
                    "id": "grammar.x",
                    "dimensions": ["recognition"],
                    "contexts": ["work"],
                    "lexicon": [],
                }
            ],
            "lexicon": [],
        },
        policy=policy(),
        generation_version="generation@1",
        mode="balanced",
        total_seconds=1800,
        pinned_versions={"curriculum": "curriculum@demo", "control": "control@1"},
        active_safety_version="curriculum@active",
        new_id=lambda: f"id-{next(counter)}",
    )
    assert plan["steps"]
    for step in plan["steps"]:
        trace = step["decision_trace"]
        assert trace["decision_id"] == step["decision_id"]
        assert trace["rule_refs"]
        assert set(trace) == {
            "schema_version",
            "decision_id",
            "rule_refs",
            "computed_inputs",
            "parameters",
            "facts",
        }
        assert all("parameter_id" in item for item in trace["parameters"].values())
        assert trace["facts"]["pinned_versions"]["control_policy"] == "control@1"
        assert trace["facts"]["active_safety_version"] == "curriculum@active"


def test_explain_returns_the_persisted_trace_without_recomputation(tmp_path: Path) -> None:
    conn = connect(tmp_path / "trace.db")
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(datetime(2026, 7, 22, 12, tzinfo=UTC))
    trace = {"schema_version": 1, "decision_id": "d1", "rule_refs": ["control.4.5.rule.5"]}
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            "session_plan",
            "p1",
            {"steps": [{"step_id": "s1", "decision_trace": trace}]},
            expected_revision=0,
        )
        save_decision_traces(uow, {"steps": [{"step_id": "s1", "decision_trace": trace}]})
    # Even if the mutable plan revision later drops the step, explain reads the
    # immutable per-step trace aggregate.
    with UnitOfWork(store, clock) as uow:
        found = uow.get_aggregate("session_plan", "p1")
        assert found is not None
        uow.save_aggregate("session_plan", "p1", {"steps": []}, expected_revision=found[1])
    assert explain(store, "s1") == trace
    with pytest.raises(DecisionTraceUnavailable, match="does not exist"):
        explain(store, "missing")
    conn.close()
