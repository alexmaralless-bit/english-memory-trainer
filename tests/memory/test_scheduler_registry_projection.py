"""``memory/engine.py`` forwards ``registry=`` into ``fold_schedules``
(scheduler 3a; foundation 3.6): a log spanning a scheduler@1 -> scheduler@2
activation must render each event under its OWN pinned scheduler version,
never whatever is active today, and an article-tier frame's
``permanent_interleave`` flag (scheduler 3a, PD-F) -- derived from the
event's own pinned curriculum snapshot -- must surface on the rendered pages
and the vocabulary-review dashboard, not just live silently on the fold.

This uses its own registry/program (not the shared ``conftest`` fixtures):
it needs BOTH scheduler policy versions registered and an article-tier topic,
neither of which the shared tiny program carries.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.memory.engine import render_pages

EPOCH = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": "grammar.v1-pin",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "A target whose evidence is pinned to scheduler@1.",
            "dimensions": ["recognition"],
            "contexts": [],
            "lexicon": [],
        },
        {
            "id": "grammar.v2-pin",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "A target whose evidence is pinned to scheduler@2.",
            "dimensions": ["recognition"],
            "contexts": [],
            "lexicon": [],
        },
        {
            "id": "grammar.articles.demo",
            "cefr": "A1",
            "track": "grammar-engine",
            "can_do": "Use a/an/the for first mention.",
            "dimensions": ["recognition"],
            "contexts": [],
            "lexicon": [],
        },
    ],
    "lexicon": [
        {
            "id": "chunk.articles-demo.a-role",
            "title": "I'm a ___",
            "type": "chunk",
            "meaning_ru": "я … (роль)",
            "frame_of": "grammar.articles.demo",
            "carries": ["article:indefinite-first-mention"],
            "tier": 2,
        },
    ],
}


def _load_policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(EPOCH)


@pytest.fixture
def random_source() -> SeededRandomSource:
    return SeededRandomSource(20260922)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[EventStore]:
    conn = connect(tmp_path / "memory.db")
    migrate(conn)
    try:
        yield EventStore(conn)
    finally:
        conn.close()


@pytest.fixture
def dual_registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("curriculum", "v-test", PROGRAM)
    reg.activate("curriculum", "v-test")
    reg.register("scoring", "scoring@1", _load_policy("scoring-v1.yaml"))
    reg.activate("scoring", "scoring@1")
    reg.register("scheduler", "scheduler@1", _load_policy("scheduler-v1.yaml"))
    reg.register("scheduler", "scheduler@2", _load_policy("scheduler-v2.yaml"))
    reg.activate("scheduler", "scheduler@2")  # v2 is current; v1 stays pinned-resolvable
    return reg


def _emit(
    store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    event_type: str,
    payload: dict[str, Any],
    pinned: dict[str, str],
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=new_ulid(clock, rnd),
                    payload=payload,
                    pinned_versions=pinned,
                )
            ]
        )


def _evidence(
    store: EventStore, clock: FixedClock, rnd: SeededRandomSource, target: str, pinned: dict
) -> None:
    _emit(
        store,
        clock,
        rnd,
        "evidence.added",
        {
            "evidence_id": new_ulid(clock, rnd),
            "session_id": "s1",
            "primary_target": {"target_ref": target, "dimension": "recognition"},
            "origin": "session",
            "assessment_basis": "objective_check",
            "correct": True,
            "hints": 0,
        },
        pinned,
    )


def _outcome(
    store: EventStore, clock: FixedClock, rnd: SeededRandomSource, target: str, outcome: str, pinned: dict
) -> None:
    _emit(
        store,
        clock,
        rnd,
        "review.outcome",
        {"target_ref": target, "dimension": "recognition", "outcome": outcome, "origin": "session"},
        pinned,
    )


def test_mixed_pin_log_projects_each_events_own_scheduler_interval(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, dual_registry: PolicyRegistry
) -> None:
    v1_pin = {"scheduler": "scheduler@1"}
    v2_pin = {"scheduler": "scheduler@2"}
    _evidence(store, clock, random_source, "grammar.v1-pin", v1_pin)
    _outcome(store, clock, random_source, "grammar.v1-pin", "CONFIRMED", v1_pin)
    _evidence(store, clock, random_source, "grammar.v2-pin", v2_pin)
    _outcome(store, clock, random_source, "grammar.v2-pin", "CONFIRMED", v2_pin)

    pages = render_pages(store, dual_registry)
    v1_page = pages["topics/grammar.v1-pin.md"]
    v2_page = pages["topics/grammar.v2-pin.md"]
    # scheduler@1 has no ladder: CONFIRMED steps from intervals[0]=1 to
    # intervals[1]=3 days.
    assert "interval 3d" in v1_page
    # scheduler@2's ladder [1, 2, 4] runs first: CONFIRMED steps from rung 1
    # (1 day) to rung 2 (2 days) -- NOT 3d, which is what BOTH targets would
    # show if the registry were not threaded through and every event folded
    # under the caller's single active policy (scheduler@2) regardless of pin.
    assert "interval 2d" in v2_page

    # Deterministic replay: folding the same log twice reproduces the same
    # bytes for both targets, across the version boundary.
    assert render_pages(store, dual_registry) == pages


def test_permanent_interleave_frame_is_marked_on_its_page_and_dashboard(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, dual_registry: PolicyRegistry
) -> None:
    target = "chunk.articles-demo.a-role"
    pin = {"scheduler": "scheduler@2", "curriculum": "v-test"}
    _evidence(store, clock, random_source, target, pin)
    # Walk it past the ladder [1,2,4] and the whole base table [7,14,30,60,
    # 120,180] (9 rungs total) so it reaches -- and stays pinned at -- the
    # permanent-interleave tier.
    for _ in range(9):
        _outcome(store, clock, random_source, target, "CONFIRMED", pin)

    pages = render_pages(store, dual_registry)
    frame_page = pages["knowledge/chunks/chunk.articles-demo.a-role.md"]
    assert "постоянный ярус" in frame_page

    dashboard = pages["current/vocabulary-review.md"]
    assert "Постоянный ярус (не покидает очередь): 1" in dashboard
    assert "[[chunk.articles-demo.a-role]]" in dashboard
    assert "постоянный ярус" in dashboard


def test_non_article_target_is_never_marked_permanent_interleave(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, dual_registry: PolicyRegistry
) -> None:
    pin = {"scheduler": "scheduler@2", "curriculum": "v-test"}
    _evidence(store, clock, random_source, "grammar.v2-pin", pin)
    for _ in range(9):
        _outcome(store, clock, random_source, "grammar.v2-pin", "CONFIRMED", pin)

    dashboard = render_pages(store, dual_registry)["current/vocabulary-review.md"]
    assert "Постоянный ярус (не покидает очередь): 0" in dashboard
