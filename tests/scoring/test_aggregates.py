"""Aggregates: working level with honest no-data, weakest-skill rule,
Learning Score, and the XP fold (canon scoring 4-7)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.aggregates import (
    learning_score,
    measured_working_level,
    working_levels,
    xp_ledger,
)
from english_trainer.scoring.engine import TargetState
from tests.scoring.conftest import EPOCH


def _state(knowledge_state: str = "ACTIVE", mastery: dict[str, str] | None = None) -> TargetState:
    state = TargetState()
    state.knowledge_state = knowledge_state
    state.mastery = {k: Decimal(v) for k, v in (mastery or {"recognition": "60"}).items()}
    return state


def _program(n_grammar: int, n_reading: int = 0) -> dict[str, Any]:
    topics = [{"id": f"grammar.t{i}", "cefr": "A1", "track": "grammar-engine"} for i in range(n_grammar)] + [
        {"id": f"reading.t{i}", "cefr": "A1", "track": "reading"} for i in range(n_reading)
    ]
    return {"topics": topics, "lexicon": []}


def test_level_needs_coverage_and_stays_unknown_below_it(policy) -> None:
    program = _program(4)  # min_topics is 5: four ACTIVE topics are not enough
    scores = {f"grammar.t{i}": _state() for i in range(4)}
    levels = working_levels(scores, program, policy)
    assert levels["grammar"]["level"] is None  # coverage floor not met
    assert levels["grammar"]["confidence"] == "low"  # 4 topics: low, below the medium floor
    assert measured_working_level(levels) is None  # unknown skill => unknown overall


def test_level_appears_with_coverage_and_weakest_skill_rules(policy) -> None:
    program = _program(6, n_reading=6)
    scores = {f"grammar.t{i}": _state() for i in range(6)}
    scores |= {f"reading.t{i}": _state() for i in range(6)}
    levels = working_levels(scores, program, policy)
    assert levels["grammar"]["level"] == "A1" and levels["grammar"]["confidence"] == "medium"
    assert levels["reading"]["level"] == "A1"
    # writing/vocabulary have zero measured topics: the overall level stays
    # unknown -- conservative, an unmeasured area never lifts or fills in.
    assert levels["writing"]["level"] is None
    assert measured_working_level(levels) is None


def test_learning_score_is_no_data_without_a_measured_level(policy) -> None:
    program = _program(6)
    scores = {f"grammar.t{i}": _state(mastery={"recognition": "40", "transfer": "80"}) for i in range(6)}
    assert learning_score(scores, program, policy, None) is None  # no-data, not 0
    value = learning_score(scores, program, policy, "A1")
    assert value is not None and Decimal(value) == Decimal("60")  # mean of dimension means


def _emit(store: EventStore, clock, rnd, event_type: str, payload: dict[str, Any]) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="s1",
                    payload=payload,
                )
            ]
        )


def test_xp_awards_once_and_caps_per_day(store, clock, random_source, policy) -> None:
    # Three assessed attempts (10 XP each), one recorded-only (no award), one
    # duplicate source id (award-once), one closed review (20 XP).
    for n in range(3):
        _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": f"a{n}", "status": "assessed"})
    _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": "a9", "status": "recorded"})
    _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": "a0", "status": "assessed"})
    _emit(store, clock, random_source, "review.outcome", {"review_id": "r1", "outcome": "CONFIRMED"})
    ledger = xp_ledger(store, policy)
    assert ledger["total"] == 3 * 10 + 20
    assert ledger["practice_days"] == 1 and ledger["streak"] == 1
    assert {a["source_id"] for a in ledger["awards"]} == {"a0", "a1", "a2", "r1"}

    # The daily cap bounds a single day deterministically; the excess is
    # simply not awarded (no deferral, no debt).
    for n in range(30):
        _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": f"b{n}", "status": "assessed"})
    capped = xp_ledger(store, policy)
    assert capped["by_day"][clock.now().date().isoformat()] == 200  # daily_cap

    # A second consecutive day extends the streak.
    next_day = FixedClock(EPOCH + timedelta(days=1))
    _emit(store, next_day, random_source, "attempt.recorded", {"attempt_id": "c1", "status": "assessed"})
    two_days = xp_ledger(store, policy)
    assert two_days["practice_days"] == 2 and two_days["streak"] == 2


def test_xp_awards_rubric_finalized_attempts_once(store, clock, random_source, policy) -> None:
    # A rubric attempt is recorded (recorded) then finalized via
    # attempt.state_changed(to_status=assessed) -- it must earn XP exactly once,
    # and the objective/rubric paths stay mutually exclusive (no double count).
    _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": "r1", "status": "recorded"})
    _emit(
        store,
        clock,
        random_source,
        "attempt.state_changed",
        {"attempt_id": "r1", "from_status": "recorded", "to_status": "assessed", "reason": "scored"},
    )
    # An abandoned attempt (state_changed -> closed_unassessed) awards nothing.
    _emit(store, clock, random_source, "attempt.recorded", {"attempt_id": "r2", "status": "recorded"})
    _emit(
        store,
        clock,
        random_source,
        "attempt.state_changed",
        {"attempt_id": "r2", "from_status": "recorded", "to_status": "closed_unassessed"},
    )
    ledger = xp_ledger(store, policy)
    assert ledger["total"] == 10  # exactly one attempt_finalized award (10 XP)
    assert {a["source_id"] for a in ledger["awards"]} == {"r1"}
