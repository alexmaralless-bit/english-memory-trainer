"""End-to-end learner-lexicon scenario (roadmap living-layer; learner 0.11).

The centerpiece invariant, proven here on a FixedClock + SeededRandomSource:
**a translation request survives a chat swap but never by itself becomes
evidence of knowledge.** The tutor uses a word, the learner asks what it means,
the agent records an ``encounter``; scoring is byte-identical before and after;
the next provider sees the word in its briefing; only a separate graded answer
moves the LexicalItem's scoring state. An unknown-to-curriculum word stays an
unlinked personal note and is never a scoring target.

The whole scenario is run on two independent databases and their canonical
final state is compared byte-for-byte -- determinism is a checkable guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from english_trainer.adapters.ingress import capture_user_turn
from english_trainer.curriculum.service import activate_version, register_version
from english_trainer.evidence.attempts import record_attempt
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.learner.lexicon import (
    EVENT_LEXICON_ENTRY_ADDED,
    lexicon_add,
    lexicon_encounter,
    lexicon_entries,
    relevant_lexicon_targets,
)
from english_trainer.lessons.delivery import next_step, peek_step, replan_session
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.resume import resume_session
from english_trainer.lessons.sessions import get_plan, start_session
from english_trainer.scoring.engine import fold_scores, snapshot

REPO = Path(__file__).resolve().parents[2]
EPOCH = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
SEED = 20260722
WORD = "word.feasible"

# ``word.feasible`` is a real curriculum LexicalItem, ATTACHED to the topic's
# lexicon -- so the lexicon-first micro lane excludes it by default and no plan
# step targets it until the learner asks about it. It is the only lexical item,
# so there is no unlinked fallback either: the word appears in a plan ONLY as a
# consequence of the encounter.
PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": "grammar.be.identity",
            "cefr": "A1",
            "track": "grammar-engine",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [WORD],
        },
    ],
    "lexicon": [
        {
            "id": WORD,
            "type": "word",
            "title": "feasible",
            "cefr": "A2",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
            "meaning_ru": "осуществимый; выполнимый",
        },
    ],
}


def _policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _activate(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, rng: SeededRandomSource
) -> None:
    register_version(registry, PROGRAM, "learner-lexicon@1")
    activate_version(store, registry, clock, rng, "learner-lexicon@1", expected_active=None)
    registry.register("generation", "generation@1", {"policy_id": "generation@1"})
    registry.activate("generation", "generation@1")
    for filename, kind, version in (
        ("control-v1.yaml", "control", "control@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
    ):
        registry.register(kind, version, _policy(filename))
        registry.activate(kind, version)


def _plan_target_refs(store: EventStore, session_id: str) -> set[str]:
    _, plan_state, _ = get_plan(store, session_id)
    return {str(step["target_ref"]) for step in plan_state["steps"] if step.get("target_ref")}


def _present_until(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    rng: SeededRandomSource,
    session_id: str,
    target_ref: str,
) -> dict[str, Any]:
    """Claim steps in order until the one that targets ``target_ref`` is presented."""
    for _ in range(20):
        peek = peek_step(store, session_id)
        assert peek["step"] is not None, "plan exhausted before reaching the target word"
        result = next_step(
            store,
            registry,
            clock,
            rng,
            session_id,
            expected_session_revision=peek["session_revision"],
            expected_plan_version=peek["plan_version"],
        )
        if str(result["step"].get("target_ref")) == target_ref:
            return result
    raise AssertionError("target word never presented")


def _run_scenario(db_path: Path) -> dict[str, Any]:
    """Run the whole scenario and return its canonical final observable state."""
    conn = connect(db_path)
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(EPOCH)
    rng = SeededRandomSource(SEED)
    registry = PolicyRegistry(conn, clock)
    scoring_policy = _policy("scoring-v1.yaml")

    _activate(store, registry, clock, rng)

    # (2) start a session BEFORE any encounter -- the word is not in the plan.
    manifest = start_session(store, registry, clock, rng, provider="codex", mode="balanced")
    session_id = str(manifest["session_id"])
    rev = int(manifest["session_revision"])
    assert WORD not in _plan_target_refs(store, session_id)

    # (3) capture the learner's untrusted turn "What does feasible mean?".
    turn = capture_user_turn(
        store,
        clock,
        rng,
        session_id,
        provider="codex",
        provider_message_id="m1",
        content="What does feasible mean?",
        expected_session_revision=rev,
    )
    rev = int(turn["session_revision"])

    # (6, first half) scoring BEFORE the encounter.
    scores_before = snapshot(fold_scores(store, scoring_policy))
    assert scores_before == {}

    # (4) the agent records the encounter with an explicit curriculum link.
    entry = lexicon_encounter(
        store,
        clock,
        rng,
        session_id,
        surface="feasible",
        note_ru="осуществимый; выполнимый",
        linked_item_id=WORD,
        program=PROGRAM,
        provider="codex",
        expected_session_revision=rev,
    )
    rev = int(entry["session_revision"])
    # (5) the entry is an ``encountered`` note linked to the curriculum item.
    assert entry["source"] == "encountered"
    assert entry["linked_item_id"] == WORD
    assert relevant_lexicon_targets(store) == frozenset({WORD})

    # (6, second half) scoring AFTER the encounter is byte-identical: enrollment
    # is not evidence.
    assert snapshot(fold_scores(store, scoring_policy)) == scores_before

    # (7) a de-duplicated re-encounter creates no second event.
    lexicon_count = sum(1 for e in store.read() if e.type == EVENT_LEXICON_ENTRY_ADDED)
    repeat = lexicon_encounter(
        store,
        clock,
        rng,
        session_id,
        surface="feasible",
        linked_item_id=WORD,
        program=PROGRAM,
        provider="codex",
        expected_session_revision=rev,
    )
    assert repeat["cached"] is True
    assert sum(1 for e in store.read() if e.type == EVENT_LEXICON_ENTRY_ADDED) == lexicon_count

    # (8) a DIFFERENT provider resumes the session.
    resumed = resume_session(store, registry, clock, rng, session_id, provider="claude-code")
    rev = int(resumed["session_revision"])
    # (9) the word is in the tutor briefing, in its own personal-lexicon block,
    # never declared learned.
    encounters = resumed["briefing"]["personal_lexicon"]["recent_encounters"]
    assert any(e["surface"] == "feasible" and e["linked_item_id"] == WORD for e in encounters)

    # (10) replan surfaces the word as an explicit growth target now.
    peek = peek_step(store, session_id)
    replan_session(
        store,
        registry,
        clock,
        rng,
        session_id,
        expected_session_revision=rev,
        expected_plan_version=peek["plan_version"],
    )
    assert WORD in _plan_target_refs(store, session_id)

    presented = _present_until(store, registry, clock, rng, session_id, WORD)
    word_step_id = str(presented["step"]["step_id"])
    rev = int(presented["session_revision"])

    # (11) a graded answer against that step.
    rendered = record_rendered_exercise(
        store,
        registry,
        clock,
        rng,
        session_id,
        expected_session_revision=rev,
        step_id=word_step_id,
        exercise={
            "prompt": "Which word means 'осуществимый'?",
            "answer_key": ["feasible"],
            "provenance": {"origin": "authored"},
            "lexicon_refs": [WORD],
        },
    )
    rev = int(rendered["session_revision"])
    attempt = record_attempt(
        store,
        clock,
        rng,
        session_id,
        expected_session_revision=rev,
        step_id=word_step_id,
        raw_answer="feasible",
        exercise_instance_id=str(rendered["exercise_instance_id"]),
        registry=registry,
    )
    assert attempt["status"] == "assessed"

    # (12) ONLY NOW does the LexicalItem's scoring state change.
    scores_after = snapshot(fold_scores(store, scoring_policy))
    assert WORD in scores_after
    assert scores_after[WORD] != scores_before.get(WORD)
    assert scores_after[WORD]["evidence_count"] >= 1

    # (13) an unknown-to-curriculum word stays an unlinked personal note and is
    # never a scoring target.
    unknown = lexicon_add(store, clock, rng, surface="blorptastic", note_ru="выдуманное")
    assert unknown["linked_item_id"] is None
    assert "blorptastic" not in relevant_lexicon_targets(store)
    assert "blorptastic" not in snapshot(fold_scores(store, scoring_policy))

    observable = {
        "lexicon": lexicon_entries(store),
        "scores": snapshot(fold_scores(store, scoring_policy)),
        "relevant_targets": sorted(relevant_lexicon_targets(store)),
        "recent_encounters": resumed["briefing"]["personal_lexicon"]["recent_encounters"],
    }
    conn.close()
    return observable


def test_learner_lexicon_scenario(tmp_path: Path) -> None:
    result = _run_scenario(tmp_path / "run-a.db")
    # Every load-bearing fact of the scenario asserted inside _run_scenario;
    # here we confirm the final shape and the encounter's separation from scoring.
    assert result["relevant_targets"] == [WORD]
    assert result["scores"][WORD]["evidence_count"] >= 1
    surfaces = {e["surface"] for e in result["lexicon"]}
    assert surfaces == {"feasible", "blorptastic"}


def test_scenario_is_byte_identical_across_databases(tmp_path: Path) -> None:
    first = _run_scenario(tmp_path / "run-1.db")
    second = _run_scenario(tmp_path / "run-2.db")
    assert canonical_json(first) == canonical_json(second)
