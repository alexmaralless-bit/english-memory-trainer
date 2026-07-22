"""The ``deferral_count`` lifecycle (control 4.5 [R-6]): once-per-session,
reset on presentation, and qualification episodes opening and closing.

The eligibility of review candidates is a composition-time fact not yet in the
log (DEFERRED wiring), so it is fed here as the ``eligibility`` argument -- the
same shape the lessons wiring will hand the reducer later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.deferral import (
    EVENT_SESSION_COMPOSED,
    EVENT_SESSION_FINISHED,
    DeferralState,
    reduce_deferrals,
)
from english_trainer.control.saturation import EVENT_SESSION_STARTED, EVENT_STEP_PRESENTED, Key
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
BASE = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
KEY: Key = ("grammar.x", "recognition")


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def store() -> EventStore:
    conn = connect(":memory:")
    migrate(conn)
    return EventStore(conn)


def emit(
    evt_store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    type_: str,
    payload: dict[str, Any],
    correlation: str,
) -> None:
    with UnitOfWork(evt_store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=type_,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=correlation,
                    payload=payload,
                )
            ]
        )


def run_session(
    evt_store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    sid: str,
    *,
    composed_reviews: list[Key] | None = None,
    revisions: int = 0,
    presented_key: Key | None = None,
) -> None:
    """One started->finished session. ``composed_reviews`` are admitted review
    steps in a SESSION_COMPOSED; ``revisions`` emits that many empty composed
    revisions (to prove once-per-session); ``presented_key`` delivers a step."""
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {}, sid)
    for _ in range(revisions):
        emit(evt_store, clock, rnd, EVENT_SESSION_COMPOSED, {"plan_version": 1, "steps": []}, sid)
    if composed_reviews is not None:
        steps = [{"kind": "review", "target_ref": t, "dimension": d} for (t, d) in composed_reviews]
        emit(evt_store, clock, rnd, EVENT_SESSION_COMPOSED, {"plan_version": 1, "steps": steps}, sid)
    if presented_key is not None:
        emit(
            evt_store,
            clock,
            rnd,
            EVENT_STEP_PRESENTED,
            {"targets": [{"target_ref": presented_key[0], "dimension": presented_key[1]}]},
            sid,
        )
    emit(evt_store, clock, rnd, EVENT_SESSION_FINISHED, {}, sid)


def eligible_for(sids: list[str], key: Key = KEY) -> dict[str, dict[str, set[Key]]]:
    return {sid: {"eligible": {key}, "excluded": set()} for sid in sids}


# -- systematic deferral accrues once per session and qualifies ---------------


def test_three_systematic_deferrals_open_a_qualification_episode() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(1)
    for i in range(1, 4):  # deferrals_to_qualify = 3
        run_session(evt_store, clock, rnd, f"S{i}")
    result = reduce_deferrals(evt_store.read(), policy(), eligibility=eligible_for(["S1", "S2", "S3"]))
    # Qualified at the session that reached the threshold (session_seq 3).
    assert result[KEY] == DeferralState(deferral_count=3, qualified_at_session_seq=3)


def test_the_counter_changes_at_most_once_per_session() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(2)
    # A single session with two composed revisions, neither admitting the target.
    run_session(evt_store, clock, rnd, "S1", revisions=2)
    result = reduce_deferrals(evt_store.read(), policy(), eligibility=eligible_for(["S1"]))
    assert result[KEY].deferral_count == 1  # once, not once-per-revision [R-6]


# -- reset on presentation ---------------------------------------------------


def test_a_presentation_resets_the_counter() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(3)
    run_session(evt_store, clock, rnd, "S1")
    run_session(evt_store, clock, rnd, "S2")  # count -> 2
    run_session(evt_store, clock, rnd, "S3", presented_key=KEY)  # delivered -> reset
    result = reduce_deferrals(
        evt_store.read(),
        policy(),
        eligibility=eligible_for(["S1", "S2"]),  # S3 not eligible
    )
    assert result.get(KEY, DeferralState()).deferral_count == 0
    assert KEY not in result  # a reset, zero-count pair is dropped from the output


# -- qualification episode opens, closes on admission, reopens ---------------


def test_admission_closes_the_episode_and_a_later_deferral_reopens_it() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(4)
    for i in range(1, 4):
        run_session(evt_store, clock, rnd, f"S{i}")  # qualified (3, 3)
    # S4: admitted to a revision but NOT presented -> episode closes, count held.
    run_session(evt_store, clock, rnd, "S4", composed_reviews=[KEY])
    closed = reduce_deferrals(evt_store.read(), policy(), eligibility=eligible_for(["S1", "S2", "S3", "S4"]))
    assert closed[KEY] == DeferralState(deferral_count=3, qualified_at_session_seq=None)

    # S5: eligible, not admitted again -> a fresh systematic deferral reopens the
    # episode at the new session_seq (5), so it does not capture the reserve forever.
    run_session(evt_store, clock, rnd, "S5")
    reopened = reduce_deferrals(
        evt_store.read(), policy(), eligibility=eligible_for(["S1", "S2", "S3", "S4", "S5"])
    )
    assert reopened[KEY] == DeferralState(deferral_count=4, qualified_at_session_seq=5)


# -- honest default and determinism ------------------------------------------


def test_without_eligibility_no_deferrals_accrue() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(5)
    for i in range(1, 4):
        run_session(evt_store, clock, rnd, f"S{i}")
    # No eligibility argument and no eligible_review on SESSION_COMPOSED -> empty:
    # the honest state until the composition-time wiring ships.
    assert reduce_deferrals(evt_store.read(), policy()) == {}


def test_reduce_deferrals_is_deterministic() -> None:
    evt_store, clock, rnd = store(), FixedClock(BASE), SeededRandomSource(6)
    for i in range(1, 4):
        run_session(evt_store, clock, rnd, f"S{i}")
    elig = eligible_for(["S1", "S2", "S3"])
    assert reduce_deferrals(list(evt_store.read()), policy(), eligibility=elig) == reduce_deferrals(
        list(evt_store.read()), policy(), eligibility=elig
    )
