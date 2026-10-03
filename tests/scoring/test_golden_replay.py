"""Golden replay: the scoring fold over a FIXED, committed event log never
moves (lesson-brief/report concept [PD-2026-09-23]; W1-B).

``tests/fixtures/golden/old_protocol_events.jsonl`` is the exported event log
of a full session driven through the OLD per-step protocol (``session next``,
``exercise rendered``, ``attempt record``/``finalize``, ``review close``,
``attempt record-block``, ...) -- the very commands the lesson-brief/report
concept deletes in a later wave. This test proves the point the concept
depends on: the scoring fold is a pure function of the event log, never of
whatever protocol produced it, so deleting those commands cannot silently
change a single already-recorded learner's numbers.

Deliberately does NOT run the generator (``tests/fixtures/golden/
make_old_protocol_log.py``) or import anything from the old protocol modules:
it loads the committed JSONL directly into a fresh store and replays it, so it
keeps working after those modules are gone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.replay import replay_scores

REPO = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden"


def _policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _load_fixture_events(path: Path) -> list[DomainEvent]:
    """Parse the exported JSONL back into ``DomainEvent`` objects, in file
    (= canonical ``sequence``) order. The ``sequence`` field is dropped: the
    fresh store assigns its own on append, and the file's relative order is
    what actually matters for the fold."""
    events: list[DomainEvent] = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        record.pop("sequence", None)
        events.append(DomainEvent(**record))
    return events


def _replay_fixture(tmp_path: Path) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = connect(tmp_path / "golden.db")
    migrate(conn)
    store = EventStore(conn)
    clock = _fixed_clock()
    registry = PolicyRegistry(conn, clock)

    # Only what `replay_scores`/`replay_automaticity` themselves resolve
    # (registry.resolve_active): no curriculum/control/generation/scheduler is
    # needed to REPLAY a log, only to have produced one.
    registry.register("scoring", "scoring@1", _policy("scoring-v1.yaml"))
    registry.activate("scoring", "scoring@1")
    registry.register("automaticity", "automaticity@1", _policy("automaticity-v1.yaml"))
    registry.activate("automaticity", "automaticity@1")

    events = _load_fixture_events(FIXTURE_DIR / "old_protocol_events.jsonl")
    with UnitOfWork(store, clock) as uow:
        uow.append(events)

    assert store.count() == len(events)
    return replay_scores(store, registry)


def _fixed_clock() -> FixedClock:
    from datetime import UTC, datetime

    return FixedClock(datetime(2026, 9, 23, 9, 0, tzinfo=UTC))


def _expected() -> dict[str, Any]:
    loaded = json.loads((FIXTURE_DIR / "expected.json").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_golden_log_replays_to_the_recorded_scoring_hash(tmp_path: Path) -> None:
    expected = _expected()
    result = _replay_fixture(tmp_path)
    assert result["events"] == expected["event_count"]
    assert result["policy_version"] == expected["scoring_policy_version"]
    assert result["targets"] == expected["scoring_targets"]
    assert result["consistent"] is expected["scoring_consistent"]
    assert result["snapshot_hash"] == expected["scoring_snapshot_hash"]


def test_golden_log_replays_to_the_recorded_automaticity_hash(tmp_path: Path) -> None:
    expected = _expected()
    result = _replay_fixture(tmp_path)
    automaticity = result["automaticity"]
    assert automaticity["policy_version"] == expected["automaticity_policy_version"]
    assert automaticity["target_count"] == expected["automaticity_targets"]
    assert automaticity["consistent"] is expected["automaticity_consistent"]
    assert automaticity["snapshot_hash"] == expected["automaticity_snapshot_hash"]
    # The AUTOMATICITY_UPDATED facts the fixture carries agree with the
    # rebuilt fold exactly -- no producer/consumer drift snuck into the fixture.
    assert automaticity["mismatches"] == []


def test_replaying_the_fixture_twice_is_byte_identical(tmp_path: Path) -> None:
    first = _replay_fixture(tmp_path / "a")
    second = _replay_fixture(tmp_path / "b")
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert first["automaticity"]["snapshot_hash"] == second["automaticity"]["snapshot_hash"]
