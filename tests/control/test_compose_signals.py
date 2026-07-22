"""Signals and the probe inside the composition pipeline (control 4.4 steps
3a/6a, 4.7): deterministic, excluding, probe first-fit and atomic consume."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.compose import compose_plan, step_targets
from english_trainer.control.signals import (
    EVENT_SESSION_STARTED,
    EVENT_SIGNAL_CONSUMED,
    EVENT_STEP_PRESENTED,
    active_signals,
    build_probe_candidate,
    record_signal,
)
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def topic(tid: str) -> dict[str, Any]:
    return {"id": tid, "dimensions": ["recognition", "controlled_production"], "contexts": ["team-intro"]}


PROGRAM: dict[str, Any] = {"topics": [topic("grammar.a"), topic("grammar.b")], "lexicon": []}


def compose(**overrides: Any) -> dict[str, Any]:
    counter = iter(range(10_000))
    defaults: dict[str, Any] = {
        "program": PROGRAM,
        "policy": policy(),
        "generation_version": "generation@1",
        "mode": "balanced",
        "total_seconds": 1800,
        "new_id": lambda: f"id-{next(counter):04d}",
    }
    defaults.update(overrides)
    return compose_plan(**defaults)


def a_probe(difficulty: str = "spontaneous_production") -> dict[str, Any]:
    return build_probe_candidate(
        policy(),
        probe_id="P1",
        signal_id="SIG1",
        target_ref="grammar.a",
        dimension="recognition",
        requested_difficulty=difficulty,
        avoid_context="team-intro|new_material_intro",
    )


def test_composition_with_active_signals_is_byte_deterministic() -> None:
    signals = [{"kind": "snooze", "target_ref": "grammar.b"}]
    kw = {"signals": signals, "probe": a_probe(), "presented_targets": frozenset()}
    first, second = compose(**kw), compose(**kw)
    assert canonical_json(first) == canonical_json(second)
    # The snoozed growth target is excluded; the probe was admitted and consumed.
    assert all(s.get("target_ref") != "grammar.b" for s in first["steps"])
    assert first["consumed"] == ["SIG1"]


def test_probe_is_admitted_first_fit_and_reports_consumed() -> None:
    plan = compose(probe=a_probe(), presented_targets=frozenset({"grammar.a", "grammar.b"}))
    probes = [s for s in plan["steps"] if s["kind"] == "probe"]
    assert len(probes) == 1 and plan["consumed"] == ["SIG1"]
    step = probes[0]
    assert step["probe_id"] == "P1" and step["requested_difficulty"] == "spontaneous_production"
    assert step["bucket"] == "choice" and step["avoid_context"] == "team-intro|new_material_intro"
    # step_targets exposes (target, dimension) so STEP_PRESENTED derives origin.
    assert step_targets(step) == [{"target_ref": "grammar.a", "dimension": "recognition"}]
    assert "PROBE_BUDGET_UNAVAILABLE" not in plan["waivers"]


def test_probe_that_does_not_fit_is_budget_unavailable_and_not_consumed() -> None:
    # 400s of remaining budget: the choice floor takes free conversation (300s),
    # leaving no room for a 480s transfer_task probe.
    plan = compose(
        probe=a_probe("transfer_task"),
        presented_targets=frozenset({"grammar.a", "grammar.b"}),
        presented_by_bucket={"review": 0, "growth": 1400, "integration": 0, "choice": 0},
    )
    assert "PROBE_BUDGET_UNAVAILABLE" in plan["waivers"]
    assert plan["consumed"] == [] and all(s["kind"] != "probe" for s in plan["steps"])


# -- atomic consume vs survival, end to end over the event log (4.7) ----------


def make_store() -> EventStore:
    conn = connect(":memory:")
    migrate(conn)
    return EventStore(conn)


def emit(
    evt_store: EventStore, clock: FixedClock, rnd: SeededRandomSource, type_: str, payload: dict[str, Any]
) -> None:
    with UnitOfWork(evt_store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=type_,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="S1",
                    payload=payload,
                )
            ]
        )


def test_probe_consumed_atomically_else_the_signal_survives() -> None:
    evt_store, clock, rnd = make_store(), FixedClock(NOW), SeededRandomSource(3)
    emit(evt_store, clock, rnd, EVENT_SESSION_STARTED, {"n": 1})
    emit(
        evt_store,
        clock,
        rnd,
        EVENT_STEP_PRESENTED,
        {
            "step_id": "step-1",
            "plan_version": 1,
            "kind": "growth",
            "step_type": "controlled_production",
            "targets": [{"target_ref": "grammar.a", "dimension": "recognition"}],
            "context_id": "team-intro|controlled_production",
        },
    )
    recorded = record_signal(
        evt_store,
        clock,
        rnd,
        kind="too_easy",
        payload={"target_ref": "grammar.a"},
        policy=policy(),
        idempotency_key="k1",
    )
    signal_id = recorded["signal_id"]
    # Before any consumption the too_easy signal is in force.
    assert {s["signal_id"] for s in active_signals(evt_store, 1, NOW)} == {signal_id}

    probe = build_probe_candidate(
        policy(), probe_id=recorded["probe_id"], signal_id=signal_id, **recorded["probe"]
    )
    plan = compose(probe=probe, presented_targets=frozenset({"grammar.a", "grammar.b"}))
    assert plan["consumed"] == [signal_id]

    # The signal survives until a SIGNAL_CONSUMED is actually written.
    assert {s["signal_id"] for s in active_signals(evt_store, 1, NOW)} == {signal_id}
    # Emit it (as the plan-saving UoW would, atomically) -> the one-shot is gone.
    emit(evt_store, clock, rnd, EVENT_SIGNAL_CONSUMED, {"signal_id": signal_id})
    assert active_signals(evt_store, 1, NOW) == []
