"""Live lessons wiring for the pure control folds delivered in 2.8a-d."""

from __future__ import annotations

from datetime import timedelta

from english_trainer.control.availability import availability_set
from english_trainer.control.deferral import reduce_deferrals
from english_trainer.control.signals import EVENT_SIGNAL_CONSUMED, active_signals, record_signal
from english_trainer.evidence.attempts import record_attempt
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import next_step, replan_session
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import (
    abandon_session,
    finish_session,
    get_plan,
    live_composition_inputs,
    start_session,
)

EXERCISE = {
    "prompt": "Choose the form of be: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}


def _seed_due_review(store, registry, clock, rnd) -> None:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    session_id = str(manifest["session_id"])
    claimed = next_step(store, registry, clock, rnd, session_id, expected_plan_version=1)
    step_id = str(claimed["step"]["step_id"])
    rendered = record_rendered_exercise(
        store,
        registry,
        clock,
        rnd,
        session_id,
        step_id=step_id,
        exercise=dict(EXERCISE),
    )
    record_attempt(
        store,
        clock,
        rnd,
        session_id,
        step_id=step_id,
        exercise_instance_id=str(rendered["exercise_instance_id"]),
        raw_answer="am",
    )
    finish_session(store, clock, rnd, session_id)


def test_too_easy_replan_materializes_probe_and_consumes_signal_atomically(
    store, registry, clock, random_source
) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    first = next_step(store, registry, clock, random_source, session_id, expected_plan_version=1)
    target = str(first["step"]["target_ref"])
    policy = registry.resolve_pinned("control", "control@1")
    signal = record_signal(
        store,
        clock,
        random_source,
        kind="too_easy",
        payload={"target_ref": target},
        policy=policy,
        idempotency_key="too-easy-live",
    )

    replan_session(store, registry, clock, random_source, session_id, expected_plan_version=2)
    _, plan, _ = get_plan(store, session_id)
    probes = [step for step in plan["steps"] if step.get("kind") == "probe"]
    assert len(probes) == 1 and probes[0]["probe_id"] == signal["probe_id"]
    consumed = [event for event in store.read() if event.type == EVENT_SIGNAL_CONSUMED]
    assert len(consumed) == 1 and consumed[0].payload["signal_id"] == signal["signal_id"]
    assert active_signals(store, current_seq=1, now=clock.now()) == []


def test_live_signal_changes_review_classification(store, full_registry, clock, random_source) -> None:
    _seed_due_review(store, full_registry, clock, random_source)
    later = FixedClock(clock.now() + timedelta(days=1, seconds=1))
    policy = full_registry.resolve_pinned("control", "control@1")
    signal = record_signal(
        store,
        later,
        random_source,
        kind="need_more_practice",
        payload={"target_ref": "grammar.be.identity"},
        policy=policy,
        idempotency_key="practice-live",
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
        abandon_session(store, due_at, random_source, session_id)

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
