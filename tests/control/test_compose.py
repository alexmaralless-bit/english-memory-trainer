"""The composition pipeline: deterministic, floor-respecting, honestly waived
(control 4.3-4.4)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.compose import compose_plan, step_targets
from english_trainer.control.errors import BudgetTooSmall, NoCandidates
from english_trainer.kernel.encoding import canonical_json

REPO = Path(__file__).resolve().parents[2]


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def topic(topic_id: str, *, lexicon: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": topic_id,
        "dimensions": ["recognition", "controlled_production"],
        "contexts": ["team-introduction"],
        "lexicon": lexicon or [],
    }


PROGRAM: dict[str, Any] = {
    "topics": [
        topic("grammar.be.identity", lexicon=["role.engineer"]),
        topic("grammar.pronouns.possessives"),
        topic("grammar.basic-word-order"),
    ],
    "lexicon": [
        # Linked to a topic => NOT a micro-lane candidate.
        {"id": "role.engineer", "curriculum_priority_band": "CORE", "usage_policy": "safe_to_use"},
        # Unlinked, safe, CORE => the one micro-lane candidate (PD-5 D).
        {"id": "reaction.no-way", "curriculum_priority_band": "CORE", "usage_policy": "safe_to_use"},
        # Unlinked but not safe to produce => excluded by safety (step 2).
        {"id": "slang.old", "curriculum_priority_band": "CORE", "usage_policy": "recognition_only"},
    ],
}


def compose(program: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    counter = iter(range(10_000))
    defaults: dict[str, Any] = {
        "program": program or PROGRAM,
        "policy": policy(),
        "generation_version": "generation@1",
        "mode": "balanced",
        "total_seconds": 1800,
        "new_id": lambda: f"id-{next(counter):04d}",
    }
    defaults.update(overrides)
    return compose_plan(**defaults)


def test_balanced_composition_is_floor_first_and_ordered() -> None:
    plan = compose()
    kinds = [(s["kind"], s["step_type"], s.get("target_ref")) for s in plan["steps"]]
    # Floors first (growth x2 crosses the 450s floor, choice conversation
    # crosses its 180s floor whole), then top-up in canonical order; the
    # micro-lane unit ranks after every topic.
    assert kinds == [
        ("growth", "new_material_intro", "grammar.be.identity"),
        ("growth", "new_material_intro", "grammar.pronouns.possessives"),
        ("choice", "free_conversation", None),
        ("growth", "new_material_intro", "grammar.basic-word-order"),
        ("growth", "new_material_intro", "reaction.no-way"),
    ]
    assert plan["budget"]["planned"] == {"review": 0, "growth": 1200, "integration": 0, "choice": 300}
    assert plan["ledger"] == {
        "presented": {"review": 0, "growth": 0, "integration": 0, "choice": 0},
        "presented_seconds": 0,
        "remaining_seconds": 1800,
    }
    # Empty buckets are waived loudly, never silently (4.4 step 5).
    assert "NO_INTEGRATION_CANDIDATE" in plan["waivers"]
    assert "NO_REVIEW_CANDIDATE" in plan["waivers"]
    # The micro-lane step is marked and carries exactly its unit.
    micro = plan["steps"][4]
    assert micro["lexicon_first"] is True
    assert micro["generation_directive"]["lexicon_refs"] == ["reaction.no-way"]
    # Every step has exactly one exercise source: a directive, never a bank id yet.
    assert all(s["bank_item_id"] is None and s["generation_directive"] for s in plan["steps"])


def test_two_executions_produce_byte_identical_plans() -> None:
    assert canonical_json(compose()) == canonical_json(compose())


def test_budget_below_the_policy_minimum_is_refused() -> None:
    with pytest.raises(BudgetTooSmall):
        compose(total_seconds=9 * 60)


def test_consecutive_mode_quota_filters_at_admission() -> None:
    program = {"topics": [topic(f"t.{n:02d}") for n in range(6)], "lexicon": []}
    plan = compose(program)
    step_types = [s["step_type"] for s in plan["steps"]]
    # Never three same-typed steps in a row (max_consecutive_same_mode = 2)...
    for i in range(len(step_types) - 2):
        assert len(set(step_types[i : i + 3])) > 1
    # ...and the quota stops the homogeneous tail: 4 intros + 1 conversation,
    # not 5 intros, even though budget remained.
    assert step_types.count("new_material_intro") == 4


def test_empty_remainder_is_an_error_not_an_empty_plan() -> None:
    with pytest.raises(NoCandidates):
        compose(
            presented_by_bucket={"review": 0, "growth": 1380, "integration": 0, "choice": 300},
        )  # 120s left: nothing fits, and a zero-step revision must not exist [R-2]


def test_replan_keeps_step_ids_and_gets_only_the_remainder() -> None:
    first = compose()
    presented = {**first["steps"][0], "presented_at": "2026-07-21T12:00:00+00:00"}
    survivors = {s["candidate_id"]: s["step_id"] for s in first["steps"][1:]}
    second = compose(
        presented_targets=frozenset({"grammar.be.identity"}),
        presented_by_bucket={"review": 0, "growth": 300, "integration": 0, "choice": 0},
        presented_steps=[presented],
        keep_step_ids=survivors,
    )
    assert second["ledger"]["remaining_seconds"] == 1500
    assert second["steps"][0] == presented  # passed through verbatim
    by_candidate = {s["candidate_id"]: s for s in second["steps"][1:]}
    # The presented target dropped out of growth; survivors keep their ids (4.2).
    assert "growth:topic:grammar.be.identity" not in by_candidate
    for candidate_id, step in by_candidate.items():
        if candidate_id in survivors:
            assert step["step_id"] == survivors[candidate_id]


def test_step_targets_shape() -> None:
    plan = compose()
    growth, conversation = plan["steps"][0], plan["steps"][2]
    assert step_targets(growth) == [{"target_ref": "grammar.be.identity", "dimension": "recognition"}]
    assert step_targets(conversation) == []  # target-less choice only


def test_micro_lane_respects_currency() -> None:
    program = copy.deepcopy(PROGRAM)
    for unit in program["lexicon"]:
        if unit["id"] == "reaction.no-way":
            unit["currency"] = "dated"
    plan = compose(program)
    assert all(s.get("target_ref") != "reaction.no-way" for s in plan["steps"])
