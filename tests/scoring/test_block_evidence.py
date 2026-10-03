"""A reported drill block scores exactly once, and replays byte-identically.

The interesting failure this guards against is inflation: if a block of four
prompts reached scoring as four evidences, one drill sitting would move Mastery
four times. A block in the lesson report [PD-2026-09-23] travels as ONE
attempt and ONE ``evidence.added`` (``form: drill_block``) whose boolean is the
block accuracy against the threshold; the per-item verdicts ride alongside and
are inert for the Mastery fold, so the block is worth exactly one evidence
whatever its size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.report import commit_report
from english_trainer.scoring.engine import fold_scores, snapshot
from english_trainer.scoring.replay import replay_scores
from tests.lessons.report_support import BE, CP, EPOCH, item, report, report_registry, start

ANSWERS = ("I am a pilot.", "She is a doctor.", "They are late.", "We are ready.")


def _open(tmp_path: Path, name: str) -> tuple[EventStore, PolicyRegistry, FixedClock, SeededRandomSource]:
    conn = connect(tmp_path / f"{name}.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    return EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(20260923)


def _report_block(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    rnd: SeededRandomSource,
    verdicts: list[str],
) -> None:
    started = start(store, registry, clock, rnd, lesson_profile="drill")
    session_id = str(started["session_id"])
    items = [
        item(f"d{index}", ANSWERS[index], kind="drill_item", verdict=verdict, block_id="b1")
        for index, verdict in enumerate(verdicts)
    ]
    body = report(
        session_id,
        started["brief"],
        items,
        blocks=[{"block_id": "b1", "target_ref": BE, "mode": "blocked"}],
    )
    clock.advance(seconds=20 * 60)
    commit_report(
        store, registry, clock, rnd, session_id, body, provider="claude-code", idempotency_key=session_id
    )


def _scoring(registry: PolicyRegistry) -> dict[str, Any]:
    return registry.resolve_pinned("scoring", registry.active_version("scoring"))


def test_a_block_scores_once_not_once_per_item(tmp_path: Path) -> None:
    store, registry, clock, rnd = _open(tmp_path, "once")
    _report_block(store, registry, clock, rnd, ["correct"] * 4)
    evidence = [e for e in store.read() if e.type == "evidence.added"]
    blocks = [e for e in evidence if e.payload.get("form") == "drill_block"]
    assert len(blocks) == 1 and len(blocks[0].payload["items"]) == 4
    scores = fold_scores(store, _scoring(registry))
    assert scores[BE].evidence_count == 1  # four prompts, ONE evidence
    assert scores[BE].mastery[CP] > 0
    # Stability is seeded once too, by that single admissible evidence.
    assert scores[BE].stability_days is not None


def test_a_failed_block_adds_no_mastery_and_never_punishes(tmp_path: Path) -> None:
    store, registry, clock, rnd = _open(tmp_path, "failed")
    _report_block(store, registry, clock, rnd, ["incorrect"] * 4)
    scores = fold_scores(store, _scoring(registry))
    # Monotonicity (canon 2.1): a wrong block adds nothing, it does not subtract.
    assert scores[BE].mastery == {}
    assert scores[BE].evidence_count == 1


def test_a_block_is_worth_one_evidence_whatever_its_size(tmp_path: Path) -> None:
    big_store, big_registry, big_clock, big_rnd = _open(tmp_path, "big")
    _report_block(big_store, big_registry, big_clock, big_rnd, ["correct"] * 4)
    small_store, small_registry, small_clock, small_rnd = _open(tmp_path, "small")
    _report_block(small_store, small_registry, small_clock, small_rnd, ["correct"])
    big = fold_scores(big_store, _scoring(big_registry))[BE].mastery[CP]
    small = fold_scores(small_store, _scoring(small_registry))[BE].mastery[CP]
    assert big == small


def test_replay_is_byte_stable_with_a_block_in_the_log(tmp_path: Path) -> None:
    store, registry, clock, rnd = _open(tmp_path, "replay")
    _report_block(store, registry, clock, rnd, ["correct", "correct", "partial", "incorrect"])
    first = replay_scores(store, registry)
    second = replay_scores(store, registry)
    assert first["consistent"] is True
    assert first["snapshot_hash"] == second["snapshot_hash"]
    # The per-item verdicts are inert for the fold: the hash equals the one
    # the fold itself produces (foundation 5).
    assert first["snapshot_hash"] == payload_hash(snapshot(fold_scores(store, _scoring(registry))))
