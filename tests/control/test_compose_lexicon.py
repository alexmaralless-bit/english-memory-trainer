"""Personal-lexicon relevance in composition (control 4.4-4.5; learner 4).

The default path is byte-identical to before; a learner-requested curriculum
LexicalItem enters the lexicon-first micro lane even when it is attached to a
topic (an explicit vocabulary request). Relevance never touches scoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.compose import compose_plan, growth_candidates
from english_trainer.kernel.encoding import canonical_json

REPO = Path(__file__).resolve().parents[2]


def _policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# A single lexical item, ATTACHED to the topic -- so the default micro lane
# excludes it and it is not otherwise a growth candidate.
PROGRAM: dict[str, Any] = {
    "topics": [
        {
            "id": "grammar.t1",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["work"],
            "lexicon": ["word.feasible"],
        }
    ],
    "lexicon": [
        {
            "id": "word.feasible",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
        }
    ],
}


def _compose(**overrides: Any) -> dict[str, Any]:
    counter = iter(range(10_000))
    defaults: dict[str, Any] = {
        "program": PROGRAM,
        "policy": _policy(),
        "generation_version": "generation@1",
        "mode": "balanced",
        "total_seconds": 1800,
        "new_id": lambda: f"id-{next(counter):04d}",
    }
    defaults.update(overrides)
    return compose_plan(**defaults)


def _targets(plan: dict[str, Any]) -> set[str]:
    return {str(s["target_ref"]) for s in plan["steps"] if s.get("target_ref")}


def test_empty_relevance_is_byte_identical() -> None:
    # The default and an explicit empty frozenset produce the same bytes.
    assert canonical_json(_compose()) == canonical_json(_compose(relevant_targets=frozenset()))


def test_topic_linked_item_absent_by_default() -> None:
    assert "word.feasible" not in _targets(_compose())


def test_learner_requested_item_enters_growth() -> None:
    plan = _compose(relevant_targets=frozenset({"word.feasible"}))
    assert "word.feasible" in _targets(plan)
    step = next(s for s in plan["steps"] if s.get("target_ref") == "word.feasible")
    assert step["kind"] == "growth" and step["lexicon_first"] is True


def test_relevance_sets_learner_relevance_on_growth_candidate() -> None:
    relevant = frozenset({"word.feasible", "grammar.t1"})
    cands = {c["candidate_id"]: c for c in growth_candidates(PROGRAM, frozenset(), _policy(), relevant)}
    assert cands["growth:topic:grammar.t1"]["learner_relevance"] == 1
    assert cands["growth:lexicon:word.feasible"]["learner_relevance"] == 1
    # An irrelevant candidate stays 0; unlinked-fallback logic is unchanged.
    plain = {c["candidate_id"]: c for c in growth_candidates(PROGRAM, frozenset(), _policy())}
    assert plain["growth:topic:grammar.t1"]["learner_relevance"] == 0
