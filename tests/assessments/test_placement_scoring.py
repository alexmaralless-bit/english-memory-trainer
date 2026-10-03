"""Scoring hand-off: origin=placement is capped at ACTIVE (never MASTERED) by
the scoring fold, and the whole placement replays byte-identically (assessments
3-4; scoring 4b)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from english_trainer.assessments.placement import (
    answer_placement,
    start_placement,
    submit_placement,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.scoring.engine import ACTIVE, fold_scores, snapshot
from tests.assessments.conftest import EPOCH, SEED
from tests.assessments.fixtures import stub_program

GRAMMAR_ALL = {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}


def test_placement_evidence_is_capped_at_active(
    store, registry, clock, random_source, scoring_policy
) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    # Three correct items on one target: three CONFIRMED outcomes would reach
    # MASTERED, but origin=placement caps the state at ACTIVE.
    answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
    submit_placement(store, registry, clock, random_source, pid)

    scores = fold_scores(store, scoring_policy)
    target = scores["grammar.be.identity"]
    assert target.knowledge_state == ACTIVE
    assert any("placement-ceiling" in line for line in target.audit)


def test_incorrect_placement_answers_do_not_punish(
    store, registry, clock, random_source, scoring_policy
) -> None:
    started = start_placement(store, registry, clock, random_source)
    pid = started["placement_id"]
    answer_placement(
        store,
        clock,
        random_source,
        pid,
        section="grammar",
        answers={"g-be-1": "wrong", "g-be-2": "wrong", "g-be-3": "wrong"},
    )
    result = submit_placement(store, registry, clock, random_source, pid)
    # No correct items -> no contributing evidence, no outcomes, nothing scored.
    assert result["evidence_count"] == 0
    assert result["outcome_count"] == 0
    assert fold_scores(store, scoring_policy) == {}


def _run_flow(db_path: Path, scoring_policy: dict[str, Any]) -> str:
    conn = connect(db_path)
    migrate(conn)
    try:
        store = EventStore(conn)
        clock = FixedClock(EPOCH)
        random_source = SeededRandomSource(SEED)
        registry = PolicyRegistry(conn, clock)
        registry.register("curriculum", "placement-stub@1", stub_program())
        registry.activate("curriculum", "placement-stub@1")
        started = start_placement(store, registry, clock, random_source)
        pid = started["placement_id"]
        answer_placement(store, clock, random_source, pid, section="grammar", answers=GRAMMAR_ALL)
        answer_placement(
            store, clock, random_source, pid, section="vocabulary", answers={"v-greeting-1": "hi"}
        )
        submit_placement(store, registry, clock, random_source, pid)
        return payload_hash(snapshot(fold_scores(store, scoring_policy)))
    finally:
        conn.close()


def test_placement_replay_is_byte_deterministic(tmp_path, scoring_policy) -> None:
    first = _run_flow(tmp_path / "run-a.db", scoring_policy)
    second = _run_flow(tmp_path / "run-b.db", scoring_policy)
    # Same FixedClock + seed over the same flow -> byte-identical scoring state.
    assert first == second
