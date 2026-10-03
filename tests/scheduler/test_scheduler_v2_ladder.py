"""``scheduler@2``: the short relearning ladder before the base interval table
(wiki/modules/scheduler.md 3a, decision PD-2026-09-22 PD-D).

Covers: the shipped policy validates and its effective table matches the
worked example in the work item; ladder progression/failure semantics;
``scheduler@1`` stays byte-identical (no ladder key -> base table only);
per-event pinned-policy resolution so a log spanning a scheduler@1 ->
scheduler@2 activation replays deterministically, honouring each event's OWN
pinned version rather than whatever the caller currently has active
(foundation 3.6 -- activation is never retroactive); and ``sweep_overdue``'s
own ``registry`` kwarg (work item D13.2), which threads the same per-event
resolution into the AT_RISK sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import PinnedPolicyUnavailable
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scheduler.engine import (
    EVENT_OVERDUE_AT_RISK,
    at_risk_boundary,
    fold_schedules,
    sweep_overdue,
)
from english_trainer.scheduler.policy import effective_intervals_days, validate_scheduler_policy

# Must match tests/scheduler/conftest.py's ``clock`` fixture (FixedClock(EPOCH)).
EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def scheduler_v2_policy() -> dict[str, Any]:
    return _load("scheduler-v2.yaml")


def _emit(
    store: EventStore,
    clock,
    rnd,
    event_type: str,
    payload: dict[str, Any],
    pinned_versions: dict[str, str] | None = None,
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="corr",
                    payload=payload,
                    pinned_versions=pinned_versions,
                )
            ]
        )


def _evidence(store, clock, rnd, target="t.a", dimension="recognition", pinned=None) -> None:
    _emit(
        store,
        clock,
        rnd,
        "evidence.added",
        {
            "evidence_id": new_ulid(clock, rnd),
            "session_id": "s1",
            "primary_target": {"target_ref": target, "dimension": dimension},
            "origin": "session",
            "assessment_basis": "objective_check",
            "correct": True,
            "hints": 0,
        },
        pinned_versions=pinned,
    )


def _outcome(
    store, clock, rnd, target="t.a", outcome="CONFIRMED", dimension="recognition", pinned=None
) -> None:
    _emit(
        store,
        clock,
        rnd,
        "review.outcome",
        {"target_ref": target, "dimension": dimension, "outcome": outcome, "origin": "session"},
        pinned_versions=pinned,
    )


# -- policy shape ------------------------------------------------------------


def test_the_shipped_v2_policy_is_valid(scheduler_v2_policy) -> None:
    assert validate_scheduler_policy(scheduler_v2_policy) == []


def test_v1_effective_table_is_the_base_table_unchanged(scheduler_policy) -> None:
    assert effective_intervals_days(scheduler_policy) == scheduler_policy["intervals_days"]


def test_v2_effective_table_matches_the_worked_example(scheduler_v2_policy) -> None:
    assert effective_intervals_days(scheduler_v2_policy) == [1, 2, 4, 7, 14, 30, 60, 120, 180]


@pytest.mark.parametrize(
    "mutation",
    [
        {"relearning_ladder_days": [1, 2, 4.0]},  # float rung
        {"relearning_ladder_days": [4, 2, 1]},  # not increasing
        {"relearning_ladder_days": [1, 1, 4]},  # not strictly increasing
        {"relearning_ladder_days": []},  # empty
        {"relearning_ladder_days": [200, 400]},  # last rung dangles past every base rung
    ],
)
def test_malformed_ladder_is_rejected(scheduler_v2_policy, mutation) -> None:
    payload = {**scheduler_v2_policy, **mutation}
    assert validate_scheduler_policy(payload) != []


def test_absent_ladder_key_is_valid_scheduler_at_1(scheduler_policy) -> None:
    assert "relearning_ladder_days" not in scheduler_policy
    assert validate_scheduler_policy(scheduler_policy) == []


# -- ladder mechanics (single policy, no registry -- direct fold) ------------


def test_ladder_progression_then_base_table_from_its_first_continuing_rung(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    _evidence(store, clock, random_source)
    state = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert state.interval_days == 1 and state.interval_index == 0

    _outcome(store, clock, random_source, outcome="CONFIRMED")  # ladder 1 -> 2
    state = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert state.interval_days == 2 and state.interval_index == 1

    _outcome(store, clock, random_source, outcome="CONFIRMED")  # ladder 2 -> 4
    state = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert state.interval_days == 4 and state.interval_index == 2

    _outcome(store, clock, random_source, outcome="CONFIRMED")  # ladder complete -> base table's 7
    state = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert state.interval_days == 7 and state.interval_index == 3

    _outcome(store, clock, random_source, outcome="CONFIRMED")  # base table continues -> 14
    state = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert state.interval_days == 14 and state.interval_index == 4


def test_failed_ladder_rung_repeats_itself_not_steps_back(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    _evidence(store, clock, random_source)
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # ladder 1 -> 2 (index 1)
    before = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert (before.interval_index, before.interval_days) == (1, 2)

    _outcome(store, clock, random_source, outcome="REGRESSION")  # still on a ladder rung
    after = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    # Neither advances to rung 3 (index 2) nor falls back to rung 1 (index 0):
    # a failed ladder rung repeats itself (scheduler.md 3a).
    assert (after.interval_index, after.interval_days) == (1, 2)
    # schedule_epoch still increments -- it is a new assignment, same day-count.
    assert after.schedule_epoch == before.schedule_epoch + 1


def test_regression_past_the_ladder_steps_back_as_before(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    _evidence(store, clock, random_source)
    for _ in range(4):  # 1 -> 2 -> 4 -> 7 -> 14 (now well past the 3-rung ladder)
        _outcome(store, clock, random_source, outcome="CONFIRMED")
    before = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert (before.interval_index, before.interval_days) == (4, 14)

    _outcome(store, clock, random_source, outcome="REGRESSION")
    after = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    # Ordinary base-table step-back, unchanged from scheduler@1: index 4 -> 3 (7 days).
    assert (after.interval_index, after.interval_days) == (3, 7)


def test_insufficient_evidence_and_cancelled_unchanged_under_v2(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    _evidence(store, clock, random_source)
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # index 0 -> 1 (2 days)
    before = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]

    _outcome(store, clock, random_source, outcome="INSUFFICIENT_EVIDENCE")
    held = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert held.interval_index == before.interval_index  # index held
    assert held.interval_days == scheduler_v2_policy["retry_days"]  # short retry

    epoch_before_cancel = held.schedule_epoch
    _emit(store, clock, random_source, "review.assignment_cancelled", {"target_ref": "t.a"})
    after_cancel = fold_schedules(store, scheduler_v2_policy)[("t.a", "recognition")]
    assert after_cancel.schedule_epoch == epoch_before_cancel  # explicit terminal no-op


# -- v1 stays byte-identical (regression guard) -------------------------------


def test_v1_fold_is_unaffected_by_the_ladder_feature(store, clock, random_source, scheduler_policy) -> None:
    _evidence(store, clock, random_source)
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # 1 -> 3
    _outcome(store, clock, random_source, outcome="CONFIRMED")  # 3 -> 7
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]
    assert (state.interval_index, state.interval_days) == (2, 7)

    _outcome(store, clock, random_source, outcome="REGRESSION")  # ordinary step-back, no ladder hold
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]
    assert (state.interval_index, state.interval_days) == (1, 3)


# -- per-event pinned-policy resolution and mixed-version replay -------------


@pytest.fixture
def dual_registry(store: EventStore, clock, scheduler_policy, scheduler_v2_policy) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("scheduler", "scheduler@1", scheduler_policy)
    reg.register("scheduler", "scheduler@2", scheduler_v2_policy)
    reg.activate("scheduler", "scheduler@2")  # v2 is the active version; v1 stays pinned-resolvable
    return reg


def test_registry_none_keeps_one_policy_for_the_whole_fold(
    store, clock, random_source, scheduler_policy
) -> None:
    """Without ``registry`` every caller -- including today's -- is unaffected
    by per-event pins: even an event pinned to v2 folds under the caller's own
    (here v1) policy. This is the exact backward-compatibility guarantee."""
    _evidence(store, clock, random_source, pinned={"scheduler": "scheduler@2"})
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]  # registry omitted
    assert state.interval_days == 1  # v1's table[0], same as v2's table[0] here (both 1)

    _outcome(store, clock, random_source, outcome="CONFIRMED", pinned={"scheduler": "scheduler@2"})
    state = fold_schedules(store, scheduler_policy)[("t.a", "recognition")]
    assert state.interval_days == 3  # v1's table[1] -- NOT v2's ladder rung 2 days


def test_mixed_log_replay_is_deterministic_and_honours_each_events_own_pin(
    store, clock, random_source, dual_registry, scheduler_policy
) -> None:
    """A log with target A entirely under scheduler@1 pins and target B
    entirely under scheduler@2 pins: replaying it (``registry`` supplied)
    resolves each event's own pinned table, and folding it twice reproduces
    byte-identical ``next_review_at`` values both times."""
    v1_pin = {"scheduler": "scheduler@1"}
    v2_pin = {"scheduler": "scheduler@2"}

    _evidence(store, clock, random_source, target="t.v1", pinned=v1_pin)
    _outcome(store, clock, random_source, target="t.v1", outcome="CONFIRMED", pinned=v1_pin)
    _outcome(store, clock, random_source, target="t.v1", outcome="CONFIRMED", pinned=v1_pin)

    _evidence(store, clock, random_source, target="t.v2", pinned=v2_pin)
    _outcome(store, clock, random_source, target="t.v2", outcome="CONFIRMED", pinned=v2_pin)
    _outcome(store, clock, random_source, target="t.v2", outcome="CONFIRMED", pinned=v2_pin)

    def _fold() -> dict[str, Any]:
        schedules = fold_schedules(store, scheduler_policy, registry=dual_registry)
        return {
            key: (state.interval_index, state.interval_days, state.next_review_at)
            for key, state in schedules.items()
        }

    first = _fold()
    second = _fold()
    assert first == second  # replay is deterministic

    # t.v1: base table 1 -> 3 -> 7 (scheduler@1, no ladder).
    assert first[("t.v1", "recognition")] == (2, 7, EPOCH + timedelta(days=7))
    # t.v2: ladder 1 -> 2 -> 4 (scheduler@2), NOT the base table's 1 -> 3 -> 7.
    assert first[("t.v2", "recognition")] == (2, 4, EPOCH + timedelta(days=4))


def test_same_target_transition_from_v1_to_v2_pin_stays_deterministic(
    store, clock, random_source, dual_registry, scheduler_policy
) -> None:
    """A target whose earlier outcomes were pinned scheduler@1 and whose latest
    outcome is pinned scheduler@2 (a session started after the v2 activation):
    replaying the log twice must still reproduce the same result, whatever
    that result is -- determinism holds across a policy-version transition,
    not only within one version."""
    v1_pin = {"scheduler": "scheduler@1"}
    v2_pin = {"scheduler": "scheduler@2"}
    _evidence(store, clock, random_source, target="t.transition", pinned=v1_pin)
    _outcome(store, clock, random_source, target="t.transition", outcome="CONFIRMED", pinned=v1_pin)
    _outcome(store, clock, random_source, target="t.transition", outcome="CONFIRMED", pinned=v2_pin)

    def _state() -> tuple[int, int, datetime]:
        schedules = fold_schedules(store, scheduler_policy, registry=dual_registry)
        state = schedules[("t.transition", "recognition")]
        return (state.interval_index, state.interval_days, state.next_review_at)

    assert _state() == _state()  # deterministic replay, not merely a one-off value


def test_unresolvable_pinned_version_is_a_hard_error_not_a_silent_fallback(
    store, clock, random_source, scheduler_policy
) -> None:
    reg = PolicyRegistry(store._conn, clock)
    reg.register("scheduler", "scheduler@1", scheduler_policy)
    reg.activate("scheduler", "scheduler@1")  # scheduler@2 deliberately NOT registered
    _evidence(store, clock, random_source, pinned={"scheduler": "scheduler@2"})
    with pytest.raises(PinnedPolicyUnavailable):
        fold_schedules(store, scheduler_policy, registry=reg)


# -- sweep_overdue's own registry kwarg (D13.2) -------------------------------


def test_sweep_overdue_without_registry_keeps_one_policy_for_every_target(
    store, clock, random_source, scheduler_policy
) -> None:
    """Unchanged default behaviour: omitting ``registry`` folds every target
    under the caller's single ``scheduler_policy``, even one pinned to v2 --
    the exact backward-compatibility guarantee ``fold_schedules`` already has."""
    v2_pin = {"scheduler": "scheduler@2"}
    _evidence(store, clock, random_source, target="t.v2", pinned=v2_pin)
    _outcome(store, clock, random_source, target="t.v2", outcome="CONFIRMED", pinned=v2_pin)
    # Under v1's base table (not v2's ladder) t.v2's boundary is day 6, not day 4.
    mid = FixedClock(EPOCH + timedelta(days=5))
    assert sweep_overdue(store, "scheduler@1", scheduler_policy, mid, random_source) == []


def test_sweep_overdue_registry_sweeps_each_target_by_its_own_pinned_policy(
    store, clock, random_source, dual_registry, scheduler_policy
) -> None:
    """A mixed-pin log: target A entirely under scheduler@1, target B under
    scheduler@2. With ``registry`` supplied, each target's AT_RISK boundary is
    computed from ITS OWN pinned table -- B's (short ladder) boundary crosses
    well before A's (base table) does, and the sweep reports each crossing
    only once its own boundary is reached."""
    v1_pin = {"scheduler": "scheduler@1"}
    v2_pin = {"scheduler": "scheduler@2"}
    _evidence(store, clock, random_source, target="t.v1", pinned=v1_pin)
    # base table: 1 -> 3
    _outcome(store, clock, random_source, target="t.v1", outcome="CONFIRMED", pinned=v1_pin)
    _evidence(store, clock, random_source, target="t.v2", pinned=v2_pin)
    # ladder: 1 -> 2
    _outcome(store, clock, random_source, target="t.v2", outcome="CONFIRMED", pinned=v2_pin)

    schedules = fold_schedules(store, scheduler_policy, registry=dual_registry)
    v1_state = schedules[("t.v1", "recognition")]
    v2_state = schedules[("t.v2", "recognition")]
    assert v1_state.interval_days == 3  # scheduler@1's base table
    assert v2_state.interval_days == 2  # scheduler@2's ladder rung 2 -- NOT the base table's 3

    # at_risk_overdue_factor is 1.0 in both shipped policies, so the boundary
    # difference below comes entirely from each target's OWN resolved interval.
    v1_boundary = at_risk_boundary(v1_state, scheduler_policy)
    v2_boundary = at_risk_boundary(v2_state, scheduler_policy)
    assert v1_boundary == EPOCH + timedelta(days=6)
    assert v2_boundary == EPOCH + timedelta(days=4)

    # At day 5: only t.v2's faster (ladder) boundary has been crossed.
    mid = FixedClock(EPOCH + timedelta(days=5))
    crossed = sweep_overdue(
        store, "scheduler@2", scheduler_policy, mid, random_source, registry=dual_registry
    )
    assert crossed == ["t.v2"]
    (event,) = [e for e in store.read() if e.type == EVENT_OVERDUE_AT_RISK]
    assert event.payload["target_ref"] == "t.v2"
    assert event.payload["boundary_at"] == v2_boundary.isoformat()

    # t.v1 crosses only once the clock passes ITS OWN (later, base-table) boundary.
    later = FixedClock(EPOCH + timedelta(days=7))
    crossed_again = sweep_overdue(
        store, "scheduler@2", scheduler_policy, later, random_source, registry=dual_registry
    )
    assert crossed_again == ["t.v1"]
    triggered = [e for e in store.read() if e.type == EVENT_OVERDUE_AT_RISK]
    assert {e.payload["target_ref"] for e in triggered} == {"t.v1", "t.v2"}
