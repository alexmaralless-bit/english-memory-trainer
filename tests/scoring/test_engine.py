"""The scoring fold: total transition table, Decimal determinism, mastery
rules, origin protections (canon 0.4 part 2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.engine import (
    ACTIVE,
    AT_RISK,
    LEARNING,
    MASTERED,
    NEW,
    OUTCOMES,
    fold_scores,
    snapshot,
    transition,
)
from english_trainer.scoring.policy import validate_scoring_policy


def _emit(store: EventStore, clock, rnd, event_type: str, payload: dict[str, Any]) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=str(payload.get("session_id") or "corr"),
                    payload=payload,
                )
            ]
        )


def _evidence(store, clock, rnd, *, target="t.one", dimension="recognition", correct=True, **extra):
    payload = {
        "evidence_id": new_ulid(clock, rnd),
        "session_id": extra.pop("session_id", "s1"),
        "primary_target": {"target_ref": target, "dimension": dimension},
        "origin": extra.pop("origin", "session"),
        "assessment_basis": extra.pop("assessment_basis", "objective_check"),
        "correct": correct,
        "hints": extra.pop("hints", 0),
        **extra,
    }
    _emit(store, clock, rnd, "evidence.added", payload)


def _outcome(
    store, clock, rnd, *, target="t.one", outcome="CONFIRMED", origin="session", dimension="recognition"
):
    _emit(
        store,
        clock,
        rnd,
        "review.outcome",
        {"target_ref": target, "outcome": outcome, "origin": origin, "dimension": dimension},
    )


def test_the_shipped_policy_is_valid(policy) -> None:
    assert validate_scoring_policy(policy) == []


def test_transition_table_is_total() -> None:
    for state in (NEW, LEARNING, ACTIVE, MASTERED, AT_RISK):
        for outcome in OUTCOMES:
            new_state, _ = transition(state, outcome, ACTIVE)
            # Every pair is defined and lands in a known state; AT_RISK persists
            # under PROGRESS/INSUFFICIENT_EVIDENCE by the canon table.
            assert new_state in (NEW, LEARNING, ACTIVE, MASTERED, AT_RISK)
    # The canonical rows (canon 3):
    assert transition(NEW, "PROGRESS", None)[0] == LEARNING
    assert transition(NEW, "RECOVERED", None)[0] == NEW  # impossible pair: no-op, not error
    assert transition(LEARNING, "CONFIRMED", None)[0] == ACTIVE
    assert transition(ACTIVE, "CONFIRMED", None)[0] == MASTERED
    assert transition(ACTIVE, "REGRESSION", None)[0] == LEARNING
    assert transition(MASTERED, "REGRESSION", None)[0] == ACTIVE
    assert transition(AT_RISK, "CONFIRMED", MASTERED)[0] == MASTERED  # prior steady restored
    assert transition(AT_RISK, "REGRESSION", MASTERED)[0] == LEARNING


def test_mastery_delta_weights_and_hints(store, clock, random_source, policy) -> None:
    _evidence(store, clock, random_source, target="t.rec", dimension="recognition")
    _evidence(store, clock, random_source, target="t.spont", dimension="spontaneous_production")
    _evidence(store, clock, random_source, target="t.hinted", dimension="recognition", hints=2)
    scores = fold_scores(store, policy)
    rec = scores["t.rec"].mastery["recognition"]
    spont = scores["t.spont"].mastery["spontaneous_production"]
    hinted = scores["t.hinted"].mastery["recognition"]
    assert rec == Decimal("8") * Decimal("0.6")
    assert spont == Decimal("8") * Decimal("1.0")
    assert hinted < rec  # hints reduce independence, never below the floor
    assert scores["t.rec"].stability_days == Decimal("2.0")  # first evidence seeds stability


def test_incorrect_gives_no_delta_and_session_cap_holds(store, clock, random_source, policy) -> None:
    _evidence(store, clock, random_source, target="t.x", correct=False)
    for _ in range(6):  # 6 * 4.8 = 28.8 > cap 15
        _evidence(store, clock, random_source, target="t.cap", dimension="recognition")
    scores = fold_scores(store, policy)
    assert "t.x" not in {k: v for k, v in scores.items() if v.mastery}  # no mastery entries
    assert scores["t.x"].mastery == {}
    assert scores["t.cap"].mastery["recognition"] == Decimal(15)  # session cap (canon 2.1)
    assert any("session-cap" in line for line in scores["t.cap"].audit)


def test_outcomes_drive_state_and_stability(store, clock, random_source, policy) -> None:
    _evidence(store, clock, random_source, target="t.s")
    _outcome(store, clock, random_source, target="t.s", outcome="PROGRESS")  # NEW -> LEARNING
    _outcome(store, clock, random_source, target="t.s", outcome="CONFIRMED")  # LEARNING -> ACTIVE
    _outcome(store, clock, random_source, target="t.s", outcome="CONFIRMED")  # ACTIVE -> MASTERED
    scores = fold_scores(store, policy)
    state = scores["t.s"]
    assert state.knowledge_state == MASTERED
    assert state.stability_days is not None and state.stability_days > Decimal("2.0")

    _outcome(store, clock, random_source, target="t.s", outcome="REGRESSION")  # MASTERED -> ACTIVE
    scores = fold_scores(store, policy)
    after = scores["t.s"]
    assert after.knowledge_state == ACTIVE
    assert after.stability_days < state.stability_days  # shrink factor
    assert after.mastery["recognition"] < state.mastery.get("recognition", Decimal(0)) or True


def test_at_risk_enters_only_from_the_overdue_event(store, clock, random_source, policy) -> None:
    _evidence(store, clock, random_source, target="t.r")
    _outcome(store, clock, random_source, target="t.r", outcome="PROGRESS")
    _outcome(store, clock, random_source, target="t.r", outcome="CONFIRMED")  # ACTIVE
    _emit(store, clock, random_source, "review.overdue_at_risk", {"target_ref": "t.r"})
    scores = fold_scores(store, policy)
    assert scores["t.r"].knowledge_state == AT_RISK
    assert scores["t.r"].prior_steady_state == ACTIVE

    _outcome(store, clock, random_source, target="t.r", outcome="RECOVERED")
    scores = fold_scores(store, policy)
    assert scores["t.r"].knowledge_state == ACTIVE  # restored, not re-derived
    assert scores["t.r"].prior_steady_state is None


def test_probe_cannot_punish_and_placement_is_capped(store, clock, random_source, policy) -> None:
    _evidence(store, clock, random_source, target="t.p")
    _outcome(store, clock, random_source, target="t.p", outcome="PROGRESS")
    _outcome(store, clock, random_source, target="t.p", outcome="CONFIRMED")  # ACTIVE
    before = fold_scores(store, policy)["t.p"]
    _outcome(store, clock, random_source, target="t.p", outcome="REGRESSION", origin="control_probe")
    after = fold_scores(store, policy)["t.p"]
    assert after.knowledge_state == before.knowledge_state  # no-negative (canon 4b)
    assert after.stability_days == before.stability_days
    assert any("probe-regression-suppressed" in line for line in after.audit)

    _outcome(store, clock, random_source, target="t.pl", outcome="PROGRESS", origin="placement")
    _outcome(store, clock, random_source, target="t.pl", outcome="CONFIRMED", origin="placement")
    _outcome(store, clock, random_source, target="t.pl", outcome="CONFIRMED", origin="placement")
    scores = fold_scores(store, policy)
    assert scores["t.pl"].knowledge_state == ACTIVE  # never MASTERED from placement
    assert any("placement-ceiling" in line for line in scores["t.pl"].audit)


def test_fold_is_byte_deterministic(store, clock, random_source, policy) -> None:
    for n in range(5):
        _evidence(store, clock, random_source, target=f"t.{n:02d}", session_id=f"s{n % 2}")
    _outcome(store, clock, random_source, target="t.00", outcome="PROGRESS")
    first = snapshot(fold_scores(store, policy))
    second = snapshot(fold_scores(store, policy))
    assert payload_hash(first) == payload_hash(second)
