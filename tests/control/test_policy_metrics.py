"""The seven v1 PolicyMetric folds and balanced-only alert hysteresis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.metrics import _terminal_session_shares, metrics
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def make_store(tmp_path: Path) -> EventStore:
    conn = connect(tmp_path / "metrics.db")
    migrate(conn)
    return EventStore(conn)


def event(
    clock: FixedClock,
    random_source: SeededRandomSource,
    event_type: str,
    payload: dict[str, Any],
    correlation_id: str,
):
    return make_event(
        id=new_ulid(clock, random_source),
        type=event_type,
        occurred_at=clock.now(),
        actor="engine",
        correlation_id=correlation_id,
        payload=payload,
    )


def by_id(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in result["metrics"]}


def test_empty_history_is_honest_no_data(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    result = by_id(metrics(store, policy(), NOW))
    assert result["calibration_error"]["value"] == "no-data"
    assert result["presented_review_share"]["value"] == "no-data"
    assert result["backlog_age_p90"]["value"] == "no-data"
    assert result["max_deferrals"]["value"] == 0
    assert result["lapse_rate_after_mastered"]["value"] == "no-data"
    assert result["transfer_gap"]["value"] == "no-data"
    store._conn.close()


def test_calibration_uses_last_presentation_and_excludes_insufficient(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = FixedClock(NOW)
    random_source = SeededRandomSource(2)
    batch = []
    for index in range(50):
        review_id = f"r{index}"
        common = {
            "review_assignment_id": review_id,
            "targets": [{"target_ref": f"t{index}", "dimension": "recognition"}],
            "context_id": "ctx",
        }
        batch.extend(
            [
                event(
                    clock,
                    random_source,
                    "session.step_presented",
                    {**common, "predicted_retrievability": "0.2"},
                    f"s{index}",
                ),
                event(
                    clock,
                    random_source,
                    "session.step_presented",
                    {**common, "predicted_retrievability": "0.8"},
                    f"s{index}",
                ),
                event(
                    clock,
                    random_source,
                    "review.outcome",
                    {"review_id": review_id, "outcome": "CONFIRMED"},
                    f"s{index}",
                ),
            ]
        )
    batch.append(
        event(
            clock,
            random_source,
            "review.outcome",
            {"review_id": "ignored", "outcome": "INSUFFICIENT_EVIDENCE"},
            "ignored",
        )
    )
    with UnitOfWork(store, clock) as uow:
        uow.append(batch)
    calibration = by_id(metrics(store, policy(), NOW))["calibration_error"]
    assert calibration["sample_count"] == 50
    assert calibration["value"] == 200_000
    store._conn.close()


def add_terminal_plan(
    store: EventStore,
    clock: FixedClock,
    random_source: SeededRandomSource,
    session_id: str,
    *,
    mode: str,
    review: int,
    growth: int,
) -> None:
    total = review + growth
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            "session_plan",
            f"p-{session_id}",
            {
                "session_id": session_id,
                "mode": mode,
                "ledger": {
                    "presented_seconds": total,
                    "presented": {"review": review, "growth": growth, "integration": 0, "choice": 0},
                },
            },
            expected_revision=0,
        )
        uow.append([event(clock, random_source, "session.finished", {}, session_id)])


def add_report_session(
    store: EventStore,
    clock: FixedClock,
    random_source: SeededRandomSource,
    session_id: str,
    *,
    mode: str,
    units: list[dict[str, Any]],
) -> None:
    """A terminal report-protocol session (control 4.10 [PD-2026-09-23]): a
    ``lesson.reported`` event plus its own ``session.step_presented`` facts
    (``source: lesson_report``), never a filled ledger -- exactly what
    ``lessons.report.commit_report`` writes. Each ``units`` entry is either a
    single item (``target_ref``, ``dimension``, optional ``review_id``) or a
    drill block (adds ``item_ids``, a list of member ids; ``review_id`` then
    addresses the whole block)."""
    events = []
    for index, unit in enumerate(units):
        payload: dict[str, Any] = {
            "session_id": session_id,
            "source": "lesson_report",
            "targets": [{"target_ref": unit["target_ref"], "dimension": unit["dimension"], "role": "target"}],
        }
        if unit.get("review_id") is not None:
            payload["review_assignment_id"] = unit["review_id"]
        item_ids = unit.get("item_ids")
        if item_ids is not None:
            payload["block_id"] = unit.get("block_id", f"block-{index}")
            payload["item_ids"] = item_ids
        else:
            payload["item_id"] = unit.get("item_id", f"item-{index}")
        events.append(event(clock, random_source, "session.step_presented", payload, session_id))
    events.append(event(clock, random_source, "lesson.reported", {"session_id": session_id}, session_id))
    events.append(event(clock, random_source, "session.finished", {}, session_id))
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            "session_plan",
            f"p-{session_id}",
            {"session_id": session_id, "mode": mode, "ledger": {}},
            expected_revision=0,
        )
        uow.append(events)


def test_report_protocol_sessions_compute_shares_from_reported_items(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = FixedClock(NOW)
    random_source = SeededRandomSource(5)
    be = ("grammar.be.identity", "controlled_production")
    poss = ("grammar.pronouns.possessives", "controlled_production")

    # Lesson 1 (seed): the only reported unit is a first-ever presentation of
    # `be` -- no evidence.added/step_presented for it exists yet, so it is
    # growth. No review is addressed.
    add_report_session(
        store,
        clock,
        random_source,
        "seed",
        mode="balanced",
        units=[{"target_ref": be[0], "dimension": be[1]}],
    )

    # Lesson 2 (main): one review item on `be` (already presented by "seed",
    # so NOT growth, but IS review) plus a 3-member drill block on `poss`
    # (never presented before -- growth -- and addresses no review). Total
    # reported units = 1 + 3 = 4 (a block counts once PER MEMBER, not once
    # for the whole block).
    add_report_session(
        store,
        clock,
        random_source,
        "main",
        mode="balanced",
        units=[
            {"target_ref": be[0], "dimension": be[1], "review_id": "rv-1", "item_id": "rv-item"},
            {
                "target_ref": poss[0],
                "dimension": poss[1],
                "item_ids": ["b1", "b2", "b3"],
                "block_id": "blk-1",
            },
        ],
    )

    # An empty report (no session.step_presented facts) contributes no sample.
    add_report_session(store, clock, random_source, "empty", mode="balanced", units=[])

    # A historic (pre-report) ledger session in the SAME store: it carries no
    # lesson.reported event, so it must still be read from its filled ledger,
    # entirely unaffected by the new report-derived branch.
    add_terminal_plan(store, clock, random_source, "ledger-1", mode="balanced", review=300, growth=700)

    samples = {str(sample["session_id"]): sample for sample in _terminal_session_shares(store)}

    assert set(samples) == {"seed", "main", "ledger-1"}  # "empty" contributes no sample

    assert samples["seed"]["review_bp"] == 0
    assert samples["seed"]["growth_bp"] == 10000  # its one unit is a first exposure

    assert samples["main"]["review_bp"] == 2500  # 1 review unit / 4 total
    assert samples["main"]["growth_bp"] == 7500  # 3 growth block-members / 4 total

    assert samples["ledger-1"]["review_bp"] == 3000  # unchanged ledger formula: 300/1000
    assert samples["ledger-1"]["growth_bp"] == 7000  # 700/1000
    store._conn.close()


def test_presented_metrics_and_alerts_use_fact_with_hysteresis(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = FixedClock(NOW)
    random_source = SeededRandomSource(3)
    for index in range(3):
        add_terminal_plan(
            store,
            clock,
            random_source,
            f"high-{index}",
            mode="balanced",
            review=900,
            growth=100,
        )
    first = metrics(store, policy(), NOW)
    values = by_id(first)
    assert values["presented_review_share"]["value"] == 9000
    assert values["presented_growth_rate"]["value"] == 1000
    assert {alert["id"]: alert["active"] for alert in first["alerts"]} == {
        "review_share_high": True,
        "growth_rate_low": True,
    }

    # Three balanced recovery sessions cross both exit thresholds. A
    # maintenance session with zero growth is deliberately ignored by alerts.
    add_terminal_plan(
        store,
        clock,
        random_source,
        "maintenance",
        mode="maintenance",
        review=600,
        growth=0,
    )
    for index in range(3):
        add_terminal_plan(
            store,
            clock,
            random_source,
            f"recovered-{index}",
            mode="balanced",
            review=200,
            growth=400,
        )
    second = metrics(store, policy(), NOW)
    recovered_alerts = {alert["id"]: alert["active"] for alert in second["alerts"]}
    assert recovered_alerts == {"review_share_high": False, "growth_rate_low": False}
    store._conn.close()


def test_backlog_nearest_rank_lapse_rate_and_transfer_gap(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    clock = FixedClock(NOW)
    random_source = SeededRandomSource(4)
    batch = []
    for index in range(10):
        target = f"mastered-{index}"
        batch.append(
            event(
                clock,
                random_source,
                "scoring.state_transition",
                {"target_ref": target, "to_state": "MASTERED"},
                target,
            )
        )
        if index < 5:
            batch.append(
                event(
                    clock,
                    random_source,
                    "review.outcome",
                    {"target_ref": target, "outcome": "REGRESSION", "review_id": f"l{index}"},
                    target,
                )
            )
            batch.append(
                event(
                    clock,
                    random_source,
                    "scoring.state_transition",
                    {
                        "target_ref": target,
                        "from_state": "MASTERED",
                        "to_state": "ACTIVE",
                        "trigger": "REGRESSION",
                    },
                    target,
                )
            )
    for index in range(50):
        target = f"transfer-{index}"
        for suffix, outcome in (
            ("new", "CONFIRMED" if index < 25 else "REGRESSION"),
            ("familiar", "CONFIRMED"),
        ):
            review_id = f"{target}-{suffix}"
            batch.append(
                event(
                    clock,
                    random_source,
                    "session.step_presented",
                    {
                        "review_assignment_id": review_id,
                        "targets": [{"target_ref": target, "dimension": "transfer"}],
                        "context_id": "same-context",
                    },
                    target,
                )
            )
            batch.append(
                event(
                    clock,
                    random_source,
                    "review.outcome",
                    {"review_id": review_id, "outcome": outcome, "target_ref": target},
                    target,
                )
            )
    with UnitOfWork(store, clock) as uow:
        uow.append(batch)
    backlog = [
        {
            "target_ref": f"b{days}",
            "dimension": "recognition",
            "first_due_at": (NOW - timedelta(days=days)).isoformat(),
        }
        for days in range(1, 11)
    ]
    result = by_id(metrics(store, policy(), NOW, backlog=backlog))
    assert result["backlog_age_p90"]["value"] == 9 * 86_400
    assert result["lapse_rate_after_mastered"]["value"] == 500_000
    assert result["transfer_gap"]["value"] == 500_000
    store._conn.close()
