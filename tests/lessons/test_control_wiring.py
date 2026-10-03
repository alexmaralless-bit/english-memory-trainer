"""Live lessons wiring for the pure control folds delivered in 2.8a-d.

Evidence is seeded through a lesson report [PD-2026-09-23] (evidence@2 +
lessons@2 activated on top of the control@1/scheduler@1/scoring@1 set these
expectations are tuned to); a learner signal is a historic
``LEARNER_SIGNAL_RECORDED`` fact -- the ``signal`` writer was removed, the
fold that honours it was not."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from english_trainer.control.availability import availability_set
from english_trainer.control.deferral import reduce_deferrals
from english_trainer.control.signals import EVENT_SIGNAL_RECORDED
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.sessions import (
    abandon_session,
    get_plan,
    live_composition_inputs,
    start_session,
)
from tests.lessons.report_support import enable_reports, item, reported_session


def _seed_due_review(store, registry, clock, rnd) -> None:
    """Day 0: one correct recognition answer on grammar.be.identity, reported."""
    enable_reports(registry)
    reported_session(
        store,
        registry,
        clock,
        rnd,
        [item("i1", "am", target_ref="grammar.be.identity", dimension="recognition", kind="recognition")],
    )


def _record_signal(store, clock, rnd, signal_id: str, signal: dict[str, Any], session_seq: int) -> None:
    """A historic learner signal, in the exact shape the removed writer stored."""
    record = {
        "kind": None,
        "target_ref": None,
        "domain": None,
        "avoid_context": None,
        "expires_at": None,
        "expires_after_session_seq": None,
        "profile": None,
        "theme": None,
        **signal,
    }
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=EVENT_SIGNAL_RECORDED,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=signal_id,
                    payload={
                        "signal_id": signal_id,
                        "recorded_at": clock.now().isoformat(),
                        "current_session_seq": session_seq,
                        "signal": record,
                    },
                )
            ]
        )


def test_live_signal_changes_review_classification(store, full_registry, clock, random_source) -> None:
    _seed_due_review(store, full_registry, clock, random_source)
    later = FixedClock(clock.now() + timedelta(days=1, seconds=1))
    policy = full_registry.resolve_pinned("control", "control@1")
    signal = {"signal_id": "practice-live"}
    _record_signal(
        store,
        later,
        random_source,
        "practice-live",
        {
            "kind": "need_more_practice",
            "target_ref": "grammar.be.identity",
            "expires_after_session_seq": 1 + int(policy["signals"]["default_effect_sessions"]),
        },
        session_seq=1,
    )
    manifest = start_session(store, full_registry, later, random_source, provider="codex")
    _, plan, _ = get_plan(store, str(manifest["session_id"]))
    (review,) = [step for step in plan["steps"] if step.get("kind") == "review"]
    assert review["urgency_class"] == "important"  # base normal, signal shifts one rung up
    assert signal["signal_id"] in review["decision_trace"]["computed_inputs"]["applied_signal_ids"]


def test_live_saturation_makes_due_review_deferrable(store, full_registry, clock, random_source) -> None:
    _seed_due_review(store, full_registry, clock, random_source)
    # The real first delivery is one exposure. Add two closed historical
    # sessions with a delivered target so the event fold reaches max=3.
    for index in range(2):
        session_id = f"saturation-{index}"
        with UnitOfWork(store, clock) as uow:
            uow.append(
                [
                    make_event(
                        id=new_ulid(clock, random_source),
                        type="session.started",
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id=session_id,
                        payload={
                            "manifest": {"session_id": session_id, "started_at": clock.now().isoformat()}
                        },
                    ),
                    make_event(
                        id=new_ulid(clock, random_source),
                        type="session.step_presented",
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id=session_id,
                        payload={
                            "step_id": f"sat-step-{index}",
                            "kind": "review",
                            "step_type": "recognition_check",
                            "targets": [{"target_ref": "grammar.be.identity", "dimension": "recognition"}],
                            "context_id": f"sat-context-{index}",
                        },
                    ),
                    make_event(
                        id=new_ulid(clock, random_source),
                        type="session.finished",
                        occurred_at=clock.now(),
                        actor="engine",
                        correlation_id=session_id,
                        payload={"session_id": session_id},
                    ),
                ]
            )
    due_at = FixedClock(clock.now() + timedelta(days=1, seconds=1))
    pinned = {
        kind: full_registry.active_version(kind)
        for kind in ("curriculum", "control", "generation", "scheduler", "scoring")
    }
    live = live_composition_inputs(
        store,
        full_registry,
        pinned,
        full_registry.resolve_pinned("curriculum", pinned["curriculum"]),
        full_registry.resolve_pinned("control", pinned["control"]),
        due_at,
        starting_new_session=True,
    )
    (candidate,) = live["review_candidates"]
    assert candidate["urgency_class"] == "deferrable"
    assert candidate["classification_trace"]["saturation"]["saturated"] is True
    manifest = start_session(store, full_registry, due_at, random_source, provider="codex")
    _, plan, _ = get_plan(store, str(manifest["session_id"]))
    assert not [step for step in plan["steps"] if step.get("kind") == "review"]
    assert plan["eligible_review"] == [{"target_ref": "grammar.be.identity", "dimension": "recognition"}]


def test_terminal_sessions_feed_deferrals_and_live_starvation_reserve(
    store, full_registry, clock, random_source
) -> None:
    _seed_due_review(store, full_registry, clock, random_source)
    due_at = FixedClock(clock.now() + timedelta(days=1))
    for _ in range(3):
        manifest = start_session(
            store,
            full_registry,
            due_at,
            random_source,
            provider="codex",
            duration_minutes=10,
        )
        session_id = str(manifest["session_id"])
        _, plan, _ = get_plan(store, session_id)
        assert not [step for step in plan["steps"] if step.get("kind") == "review"]
        abandon_session(
            store,
            due_at,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
        )

    policy = full_registry.resolve_pinned("control", "control@1")
    standing = reduce_deferrals(store.read(), policy)[("grammar.be.identity", "recognition")]
    assert standing.deferral_count == 3 and standing.qualified_at_session_seq is not None

    manifest = start_session(
        store,
        full_registry,
        due_at,
        random_source,
        provider="codex",
        duration_minutes=11,
    )
    _, plan, _ = get_plan(store, str(manifest["session_id"]))
    assert plan["starvation_admitted"] == ["review:grammar.be.identity:recognition"]
    assert len([step for step in plan["steps"] if step.get("kind") == "review"]) == 1


def test_declared_availability_drives_start_budget(store, registry, clock, random_source) -> None:
    availability_set(
        store,
        clock,
        random_source,
        {"sessions_per_week_milli": 3000, "typical_minutes": 12},
        idempotency_key="availability-live",
    )
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    _, plan, _ = get_plan(store, str(manifest["session_id"]))
    assert plan["total_seconds"] == 720
    assert plan["availability"]["budget_source"] == "declared"


# -- LearnerPreferences (learner 4a, Д8) -------------------------------------
#
# lessons must not import learner (tests/architecture allowlist), so these
# prove the wiring at the event-log boundary: a raw LEARNER_PREFERENCES_UPDATED
# event -- exactly what learner.preferences.preferences_set publishes -- folds
# into `live_composition_inputs()["learner_preferences"]`, the same dict
# `start_session`/`replan_session` pass through to `compose_plan` (control 4.2;
# tests/control/test_automaticity.py proves round_size then sizes every drill
# block).


def _pinned(registry, *kinds: str) -> dict[str, str]:
    return {kind: registry.active_version(kind) for kind in kinds}


def test_live_composition_inputs_defaults_learner_preferences_when_unset(
    store, registry, clock, random_source
) -> None:
    pinned = _pinned(registry, "curriculum", "control", "generation")
    live = live_composition_inputs(
        store,
        registry,
        pinned,
        registry.resolve_pinned("curriculum", pinned["curriculum"]),
        registry.resolve_pinned("control", pinned["control"]),
        clock,
        starting_new_session=True,
    )
    # Mirrors learner.preferences.DEFAULT_PREFERENCES exactly (learner 4a).
    assert live["learner_preferences"] == {"round_size": 6, "timed_limit_seconds": 240}


def test_live_composition_inputs_folds_the_latest_learner_preferences_event(
    store, registry, clock, random_source
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="learner.preferences_updated",
                    occurred_at=clock.now(),
                    actor="learner",
                    correlation_id="learner-preferences",
                    payload={
                        "round_size": 8,
                        "explanation_language": "en",
                        "preferred_drill_forms": [],
                        "timed_limit_seconds": 300,
                        "feedback_mode": "always_explain",
                        "preferences_version": 1,
                        "updated_at": clock.now().isoformat(),
                    },
                )
            ]
        )
    pinned = _pinned(registry, "curriculum", "control", "generation")
    live = live_composition_inputs(
        store,
        registry,
        pinned,
        registry.resolve_pinned("curriculum", pinned["curriculum"]),
        registry.resolve_pinned("control", pinned["control"]),
        clock,
        starting_new_session=True,
    )
    # Only the two fields control reads travel through; extra snapshot fields
    # (explanation_language, feedback_mode, ...) are the tutor's concern, not
    # control's (learner 4a).
    assert live["learner_preferences"] == {"round_size": 8, "timed_limit_seconds": 300}

    # A second full-snapshot event supersedes the first -- the newest always
    # wins, never a merge of the two (learner 4a versioned full-snapshot
    # contract).
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="learner.preferences_updated",
                    occurred_at=clock.now(),
                    actor="learner",
                    correlation_id="learner-preferences",
                    payload={
                        "round_size": 4,
                        "explanation_language": "en",
                        "preferred_drill_forms": [],
                        "timed_limit_seconds": 300,
                        "feedback_mode": "always_explain",
                        "preferences_version": 2,
                        "updated_at": clock.now().isoformat(),
                    },
                )
            ]
        )
    live_again = live_composition_inputs(
        store,
        registry,
        pinned,
        registry.resolve_pinned("curriculum", pinned["curriculum"]),
        registry.resolve_pinned("control", pinned["control"]),
        clock,
        starting_new_session=True,
    )
    assert live_again["learner_preferences"] == {"round_size": 4, "timed_limit_seconds": 300}
