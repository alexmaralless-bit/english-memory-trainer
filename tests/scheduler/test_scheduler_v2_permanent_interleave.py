"""``scheduler@2``: the permanent-interleave tier for article-tier frames
(wiki/modules/scheduler.md 3a, decision PD-2026-09-22 PD-F).

The scheduler layer stays PURE (tests/architecture forbids importing
``curriculum``): classification of a target as an article-tier frame --
``frame_of`` under ``grammar.articles.*`` (lexical-system 1c) -- is NOT
computed here. It is injected as ``permanent_interleave_targets``, a plain
``frozenset[str]`` of target refs a caller has already classified; deriving
that set from a pinned curriculum snapshot belongs to a future work item at
the call sites (reported, not implemented, here).

Covers: the shipped policy's ``permanent_interleave_interval_days`` validates
against the base table's last rung; flag derivation from the injected set
(membership only -- the scheduler never parses ``frame_of``); re-scheduling
at the permanent interval on every CONFIRMED/RECOVERED past the end of the
effective table, indefinitely, never leaving the due queue; targets outside
the set are unaffected; ``scheduler@1`` stays byte-identical even when a
target is in the set; double-fold determinism; and replay with mixed
scheduler-policy pins alongside a fixed injected set.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scheduler.engine import due_backlog, fold_schedules
from english_trainer.scheduler.policy import validate_scheduler_policy

EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]

# Only used for due_backlog's curriculum_priority_rank lookup; classification
# of "chunk.article-frame" as permanent-interleave is NOT read from this --
# it comes purely from the injected ``permanent_interleave_targets`` set.
PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [{"id": "grammar.articles.identity", "dimensions": ["recognition"], "lexicon": []}],
    "lexicon": [],
}


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


def _evidence(store, clock, rnd, target="chunk.article-frame", dimension="recognition", pinned=None) -> None:
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
    store, clock, rnd, target="chunk.article-frame", outcome="CONFIRMED", dimension="recognition", pinned=None
) -> None:
    _emit(
        store,
        clock,
        rnd,
        "review.outcome",
        {"target_ref": target, "dimension": dimension, "outcome": outcome, "origin": "session"},
        pinned_versions=pinned,
    )


def _confirm(store, clock, rnd, target, count, pinned=None) -> None:
    for _ in range(count):
        _outcome(store, clock, rnd, target=target, outcome="CONFIRMED", pinned=pinned)


# -- policy shape --------------------------------------------------------------


def test_shipped_v2_policy_carries_a_valid_permanent_interleave_interval(scheduler_v2_policy) -> None:
    assert validate_scheduler_policy(scheduler_v2_policy) == []
    assert (
        scheduler_v2_policy["permanent_interleave_interval_days"] == scheduler_v2_policy["intervals_days"][-1]
    )


def test_absent_permanent_interleave_key_is_valid_scheduler_at_1(scheduler_policy) -> None:
    assert "permanent_interleave_interval_days" not in scheduler_policy
    assert validate_scheduler_policy(scheduler_policy) == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"permanent_interleave_interval_days": 179},  # off by one from the last rung
        {"permanent_interleave_interval_days": 0},  # not positive
        {"permanent_interleave_interval_days": -180},  # not positive
        {"permanent_interleave_interval_days": 180.0},  # float, banned on the decision path
        {"permanent_interleave_interval_days": "180"},  # not an int
    ],
)
def test_malformed_permanent_interleave_interval_is_rejected(scheduler_v2_policy, mutation) -> None:
    payload = {**scheduler_v2_policy, **mutation}
    assert validate_scheduler_policy(payload) != []


# -- flag derivation: membership in the injected set, nothing else -----------


def test_target_in_the_injected_set_is_flagged(store, clock, random_source, scheduler_v2_policy) -> None:
    _evidence(store, clock, random_source, target="chunk.article-frame")
    schedules = fold_schedules(
        store, scheduler_v2_policy, permanent_interleave_targets=frozenset({"chunk.article-frame"})
    )
    assert schedules[("chunk.article-frame", "recognition")].permanent_interleave is True


def test_target_outside_the_injected_set_is_not_flagged(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    _evidence(store, clock, random_source, target="chunk.other-frame")
    schedules = fold_schedules(
        store, scheduler_v2_policy, permanent_interleave_targets=frozenset({"chunk.article-frame"})
    )
    assert schedules[("chunk.other-frame", "recognition")].permanent_interleave is False


def test_default_none_flags_nothing(store, clock, random_source, scheduler_v2_policy) -> None:
    """The default every existing caller uses today: no injected set -> every
    schedule's flag is False, byte-identical to before this field existed."""
    _evidence(store, clock, random_source, target="chunk.article-frame")
    schedules = fold_schedules(store, scheduler_v2_policy)  # permanent_interleave_targets omitted
    assert schedules[("chunk.article-frame", "recognition")].permanent_interleave is False


def test_empty_set_flags_nothing(store, clock, random_source, scheduler_v2_policy) -> None:
    _evidence(store, clock, random_source, target="chunk.article-frame")
    schedules = fold_schedules(store, scheduler_v2_policy, permanent_interleave_targets=frozenset())
    assert schedules[("chunk.article-frame", "recognition")].permanent_interleave is False


def test_flag_survives_the_never_scheduled_outcome_fallback_path(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    """A REVIEW_OUTCOME for a pair with no prior evidence.added opens its own
    schedule (hidden/conversation review, canon 5); the flag must still
    resolve there, not only on the EVIDENCE_ADDED_EVENT path."""
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    schedules = fold_schedules(
        store, scheduler_v2_policy, permanent_interleave_targets=frozenset({"chunk.article-frame"})
    )
    assert schedules[("chunk.article-frame", "recognition")].permanent_interleave is True


# -- re-scheduling at the permanent interval past the end of the table --------


def test_article_frame_reschedules_at_the_permanent_interval_forever(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    targets = frozenset({"chunk.article-frame"})
    intervals_len = 9  # [1, 2, 4, 7, 14, 30, 60, 120, 180]
    _evidence(store, clock, random_source, target="chunk.article-frame")
    _confirm(store, clock, random_source, "chunk.article-frame", intervals_len - 1)
    state = fold_schedules(store, scheduler_v2_policy, permanent_interleave_targets=targets)[
        ("chunk.article-frame", "recognition")
    ]
    assert (state.interval_index, state.interval_days) == (8, 180)
    epoch_at_end = state.schedule_epoch

    # Three MORE confirmations past the end of the table: stays pinned to the
    # last rung, never advances past it, and each is a genuinely NEW
    # assignment (schedule_epoch keeps incrementing) -- it never drops out.
    for _ in range(3):
        _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
        state = fold_schedules(store, scheduler_v2_policy, permanent_interleave_targets=targets)[
            ("chunk.article-frame", "recognition")
        ]
        assert (state.interval_index, state.interval_days) == (8, 180)
    assert state.schedule_epoch == epoch_at_end + 3
    assert state.permanent_interleave is True


def test_permanent_interleave_reads_its_own_named_policy_value_not_the_table_tail(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    """White-box: point ``permanent_interleave_interval_days`` at a value that
    deliberately differs from ``intervals_days[-1]`` (the shipped policy keeps
    them equal by validation, so this uses an unvalidated custom policy
    passed directly to the fold). A flagged target must be re-pinned to THIS
    number, not merely clamped at the table's last rung -- proving the branch
    reads the named constant rather than reusing the table tail."""
    custom_policy = {**scheduler_v2_policy, "permanent_interleave_interval_days": 999}
    intervals_len = 9

    _evidence(store, clock, random_source, target="chunk.article-frame")
    _confirm(store, clock, random_source, "chunk.article-frame", intervals_len - 1)
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    flagged = fold_schedules(
        store, custom_policy, permanent_interleave_targets=frozenset({"chunk.article-frame"})
    )[("chunk.article-frame", "recognition")]
    assert flagged.interval_days == 999

    _evidence(store, clock, random_source, target="chunk.other-frame")
    _confirm(store, clock, random_source, "chunk.other-frame", intervals_len - 1)
    _outcome(store, clock, random_source, target="chunk.other-frame", outcome="CONFIRMED")
    unflagged = fold_schedules(
        store, custom_policy, permanent_interleave_targets=frozenset({"chunk.article-frame"})
    )[("chunk.other-frame", "recognition")]
    assert unflagged.interval_days == 180  # not in the set: still the ordinary table tail


def test_permanent_interleave_stays_due_after_it_would_have_gone_quiet(
    store, clock, random_source, scheduler_v2_policy, scoring_policy
) -> None:
    """After reaching the permanent interval, the target is simply not due
    until 180 days pass (like anything else) -- but once that time passes it
    reappears in ``due_backlog``, never excluded by anything past-table."""
    targets = frozenset({"chunk.article-frame"})
    intervals_len = 9
    _evidence(store, clock, random_source, target="chunk.article-frame")
    _confirm(store, clock, random_source, "chunk.article-frame", intervals_len - 1)
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")

    just_before = clock.now() + timedelta(days=180) - timedelta(seconds=1)
    backlog = due_backlog(
        store, scheduler_v2_policy, scoring_policy, PROGRAM, just_before, permanent_interleave_targets=targets
    )
    assert not any(c["target_ref"] == "chunk.article-frame" for c in backlog)

    just_after = clock.now() + timedelta(days=181)
    backlog = due_backlog(
        store, scheduler_v2_policy, scoring_policy, PROGRAM, just_after, permanent_interleave_targets=targets
    )
    candidate = next(c for c in backlog if c["target_ref"] == "chunk.article-frame")
    assert candidate["permanent_interleave"] is True


def test_due_backlog_without_the_injected_set_never_flags_candidates(
    store, clock, random_source, scheduler_v2_policy, scoring_policy
) -> None:
    _evidence(store, clock, random_source, target="chunk.article-frame")
    just_after = clock.now() + timedelta(days=2)
    backlog = due_backlog(store, scheduler_v2_policy, scoring_policy, PROGRAM, just_after)  # set omitted
    candidate = next(c for c in backlog if c["target_ref"] == "chunk.article-frame")
    assert candidate["permanent_interleave"] is False


# -- v1 stays byte-identical, even when the target is in the injected set -----


def test_v1_unaffected_even_when_the_target_is_in_the_injected_set(
    store, clock, random_source, scheduler_policy
) -> None:
    """``scheduler@1`` carries no ``permanent_interleave_interval_days`` key:
    the special branch is unreachable regardless of the injected set --
    ordinary v1 clamp-at-last-rung behaviour, unchanged."""
    assert "permanent_interleave_interval_days" not in scheduler_policy
    targets = frozenset({"chunk.article-frame"})
    _evidence(store, clock, random_source, target="chunk.article-frame")
    for _ in range(7):  # base table has 8 rungs under v1 (no ladder): 1..180 is 7 steps from index 0
        _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    state = fold_schedules(store, scheduler_policy, permanent_interleave_targets=targets)[
        ("chunk.article-frame", "recognition")
    ]
    assert (state.interval_index, state.interval_days) == (7, 180)
    # The flag itself still resolves true (membership is independent of
    # scheduler version) -- only the SPECIAL branch is gated by the policy.
    assert state.permanent_interleave is True

    epoch_at_end = state.schedule_epoch
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    state = fold_schedules(store, scheduler_policy, permanent_interleave_targets=targets)[
        ("chunk.article-frame", "recognition")
    ]
    # Same clamp as scheduler@1 always had: index/days unchanged, but the
    # event still counts as a new assignment (schedule_epoch increments).
    assert (state.interval_index, state.interval_days) == (7, 180)
    assert state.schedule_epoch == epoch_at_end + 1


def test_v1_fold_without_the_new_input_is_byte_identical_to_before_the_field_existed(
    store, clock, random_source, scheduler_policy
) -> None:
    _evidence(store, clock, random_source, target="chunk.article-frame")
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")
    state = fold_schedules(store, scheduler_policy)[("chunk.article-frame", "recognition")]
    assert (state.interval_index, state.interval_days) == (2, 7)
    assert state.permanent_interleave is False


# -- double-fold determinism and replay with mixed scheduler pins ------------


def test_double_fold_is_deterministic_with_permanent_interleave(
    store, clock, random_source, scheduler_v2_policy
) -> None:
    targets = frozenset({"chunk.article-frame"})
    _evidence(store, clock, random_source, target="chunk.article-frame")
    _confirm(store, clock, random_source, "chunk.article-frame", 8)
    _outcome(store, clock, random_source, target="chunk.article-frame", outcome="CONFIRMED")

    def _fold() -> tuple[int, int, datetime, bool]:
        state = fold_schedules(store, scheduler_v2_policy, permanent_interleave_targets=targets)[
            ("chunk.article-frame", "recognition")
        ]
        return (state.interval_index, state.interval_days, state.next_review_at, state.permanent_interleave)

    first = _fold()
    second = _fold()
    assert first == second


def test_replay_with_mixed_scheduler_pins_and_a_fixed_injected_set(
    store, clock, random_source, scheduler_policy, scheduler_v2_policy
) -> None:
    """Three targets, each entirely under ONE scheduler pin, folded with a
    single fixed ``permanent_interleave_targets`` set (applied uniformly for
    the whole fold, the same way ``policy`` itself is without ``registry``):
    replay is deterministic, each event honours its OWN scheduler pin
    (foundation 3.6 -- activation is never retroactive), and the special
    branch only fires where BOTH the pin (scheduler@2) and the injected set
    agree."""
    reg = PolicyRegistry(store._conn, clock)
    reg.register("scheduler", "scheduler@1", scheduler_policy)
    reg.register("scheduler", "scheduler@2", scheduler_v2_policy)
    targets = frozenset({"t.v1-flagged", "t.v2-flagged"})

    v1_pin = {"scheduler": "scheduler@1"}
    v2_pin = {"scheduler": "scheduler@2"}

    # In the set, but pinned scheduler@1 -- no interleave key, so the flag
    # resolves true yet the special branch never fires (ordinary v1 clamp).
    _evidence(store, clock, random_source, target="t.v1-flagged", pinned=v1_pin)
    for _ in range(7):  # v1 base table: 7 steps from index 0 to the last rung (180)
        _outcome(store, clock, random_source, target="t.v1-flagged", outcome="CONFIRMED", pinned=v1_pin)

    # In the set AND pinned scheduler@2 -- the special branch fires.
    _evidence(store, clock, random_source, target="t.v2-flagged", pinned=v2_pin)
    _confirm(store, clock, random_source, "t.v2-flagged", 8, pinned=v2_pin)
    _outcome(store, clock, random_source, target="t.v2-flagged", outcome="CONFIRMED", pinned=v2_pin)

    # Pinned scheduler@2 but NOT in the set -- ordinary clamp.
    _evidence(store, clock, random_source, target="t.v2-plain", pinned=v2_pin)
    _confirm(store, clock, random_source, "t.v2-plain", 8, pinned=v2_pin)
    _outcome(store, clock, random_source, target="t.v2-plain", outcome="CONFIRMED", pinned=v2_pin)

    def _fold() -> dict[str, tuple[int, int, bool]]:
        schedules = fold_schedules(
            store, scheduler_policy, registry=reg, permanent_interleave_targets=targets
        )
        return {
            key[0]: (state.interval_index, state.interval_days, state.permanent_interleave)
            for key, state in schedules.items()
        }

    first = _fold()
    second = _fold()
    assert first == second  # deterministic replay

    assert first["t.v1-flagged"] == (7, 180, True)  # flagged, but v1 has no interleave key
    assert first["t.v2-flagged"] == (8, 180, True)  # flagged AND v2 -- special branch active
    assert first["t.v2-plain"] == (8, 180, False)  # v2, but not in the set
