"""Deterministic PolicyMetric folds and balanced-session alerts (control 4.10)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from english_trainer.control.deferral import reduce_deferrals
from english_trainer.kernel.aggregates import list_aggregates
from english_trainer.kernel.store import EventStore

_NO_DATA = "no-data"
_SUCCESS = frozenset({"CONFIRMED", "PROGRESS", "RECOVERED"})
_FAILURE = "REGRESSION"
_TERMINAL = frozenset({"session.finished", "session.abandoned"})


def _metric(
    metric_id: str,
    value: int | str,
    *,
    unit: str,
    window: str,
    sample_count: int,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "value": value,
        "unit": unit,
        "window": window,
        "sample_count": sample_count,
    }


def _prediction_error_metrics(store: EventStore) -> tuple[dict[str, Any], list[tuple[bool, bool]]]:
    latest_prediction: dict[str, Decimal] = {}
    contexts_seen: dict[str, set[str]] = {}
    novelty_by_assignment: dict[str, bool] = {}
    errors: list[int] = []
    transfer_samples: list[tuple[bool, bool]] = []
    for event in store.read():
        payload = event.payload
        if event.type == "session.step_presented":
            review_id = payload.get("review_assignment_id")
            prediction = payload.get("predicted_retrievability")
            if review_id is not None and prediction is not None:
                with suppress(InvalidOperation):
                    latest_prediction[str(review_id)] = Decimal(str(prediction))
            targets = payload.get("targets") or []
            if review_id is not None and targets:
                target = str(targets[0].get("target_ref") or "")
                context = str(payload.get("context_id") or "")
                seen = contexts_seen.setdefault(target, set())
                novelty_by_assignment[str(review_id)] = context not in seen
                seen.add(context)
        elif event.type == "review.outcome":
            outcome = str(payload.get("outcome") or "")
            if outcome not in _SUCCESS and outcome != _FAILURE:
                continue
            review_id = str(payload.get("review_id") or "")
            prediction = latest_prediction.get(review_id)
            success = outcome in _SUCCESS
            if prediction is not None:
                fact = Decimal(1) if success else Decimal(0)
                errors.append(int(abs(prediction - fact) * Decimal(1_000_000)))
            novelty = novelty_by_assignment.get(review_id)
            if novelty is not None:
                transfer_samples.append((novelty, success))

    windowed = errors[-200:]
    calibration = _metric(
        "calibration_error",
        sum(windowed) // len(windowed) if len(windowed) >= 50 else _NO_DATA,
        unit="ppm",
        window="last_200_review_outcomes",
        sample_count=len(windowed),
    )
    return calibration, transfer_samples


def _terminal_session_shares(store: EventStore) -> list[dict[str, int | str]]:
    plans = {
        str(state.get("session_id")): state for _, state, _ in list_aggregates(store._conn, "session_plan")
    }
    terminal_ids: list[str] = []
    seen: set[str] = set()
    for event in store.read():
        if event.type in _TERMINAL:
            session_id = str(event.correlation_id)
            if session_id not in seen:
                seen.add(session_id)
                terminal_ids.append(session_id)
    samples: list[dict[str, int | str]] = []
    for session_id in terminal_ids:
        plan = plans.get(session_id)
        if plan is None:
            continue
        ledger = plan.get("ledger") or {}
        presented = ledger.get("presented") or {}
        total = int(ledger.get("presented_seconds") or 0)
        if total <= 0:
            continue
        samples.append(
            {
                "session_id": session_id,
                "mode": str(plan.get("mode") or ""),
                "review_bp": int(presented.get("review") or 0) * 10000 // total,
                "growth_bp": int(presented.get("growth") or 0) * 10000 // total,
            }
        )
    return samples


def _share_metric(samples: list[dict[str, int | str]], metric_id: str, field: str) -> dict[str, Any]:
    windowed = samples[-10:]
    return _metric(
        metric_id,
        sum(int(sample[field]) for sample in windowed) // len(windowed) if len(windowed) >= 3 else _NO_DATA,
        unit="basis_points",
        window="last_10_terminal_sessions",
        sample_count=len(windowed),
    )


def _backlog_metrics(
    backlog: list[dict[str, Any]], now: datetime, store: EventStore, policy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    ages: list[tuple[int, str, str]] = []
    for item in backlog:
        raw_due = item.get("first_due_at") or item.get("next_review_at")
        if not isinstance(raw_due, str):
            continue
        try:
            due = datetime.fromisoformat(raw_due.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            continue
        age = max(0, int((now.astimezone(UTC) - due).total_seconds()))
        ages.append((age, str(item.get("target_ref") or ""), str(item.get("dimension") or "")))
    ages.sort()
    if ages:
        rank = (9 * len(ages) + 9) // 10  # nearest-rank ceil(0.9*n)
        p90: int | str = ages[rank - 1][0]
    else:
        p90 = _NO_DATA
    deferrals = reduce_deferrals(store.read(), policy)
    backlog_keys = {(str(item.get("target_ref") or ""), str(item.get("dimension") or "")) for item in backlog}
    maximum = max(
        (state.deferral_count for key, state in deferrals.items() if key in backlog_keys),
        default=0,
    )
    return (
        _metric(
            "backlog_age_p90",
            p90,
            unit="seconds",
            window="current_backlog",
            sample_count=len(ages),
        ),
        _metric(
            "max_deferrals",
            maximum,
            unit="count",
            window="current_backlog",
            sample_count=len(backlog),
        ),
    )


def _lapse_metric(store: EventStore, now: datetime) -> dict[str, Any]:
    boundary = now.astimezone(UTC) - timedelta(days=90)
    mastered: dict[str, datetime] = {}
    lapsed: set[str] = set()
    for event in store.read():
        if event.occurred_at < boundary or event.occurred_at > now:
            continue
        payload = event.payload
        if event.type == "scoring.state_transition" and payload.get("to_state") == "MASTERED":
            mastered[str(payload.get("target_ref") or "")] = event.occurred_at
        elif event.type == "review.outcome" and payload.get("outcome") == "REGRESSION":
            target = str(payload.get("target_ref") or "")
            mastered_at = mastered.get(target)
            if mastered_at is not None and event.occurred_at >= mastered_at:
                lapsed.add(target)
    sample_count = len(mastered)
    return _metric(
        "lapse_rate_after_mastered",
        len(lapsed) * 1_000_000 // sample_count if sample_count >= 10 else _NO_DATA,
        unit="ppm",
        window="90_days",
        sample_count=sample_count,
    )


def _transfer_gap_metric(samples: list[tuple[bool, bool]]) -> dict[str, Any]:
    novel = [success for is_novel, success in samples if is_novel][-50:]
    familiar = [success for is_novel, success in samples if not is_novel][-50:]
    if len(novel) >= 50 and len(familiar) >= 50:
        novel_rate = sum(novel) * 1_000_000 // len(novel)
        familiar_rate = sum(familiar) * 1_000_000 // len(familiar)
        value: int | str = familiar_rate - novel_rate
    else:
        value = _NO_DATA
    return _metric(
        "transfer_gap",
        value,
        unit="ppm",
        window="last_50_each_familiar_and_new_context",
        sample_count=min(len(novel), len(familiar)),
    )


def _alert_state(
    values: list[int],
    *,
    enters: Callable[[int], bool],
    exits: Callable[[int], bool],
    consecutive: int,
) -> tuple[bool, int]:
    active = False
    run = 0
    for value in values:
        predicate = exits if active else enters
        if predicate(value):
            run += 1
            if run >= consecutive:
                active = not active
                run = 0
        else:
            run = 0
    return active, run


def _alerts(samples: list[dict[str, int | str]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    balanced = [sample for sample in samples if sample["mode"] == "balanced"]
    alert_policy = policy["alerts"]
    review_consecutive = int(alert_policy["review_share_consecutive"])
    review_enter = int(alert_policy["review_share_enter_bp"])
    review_exit = int(alert_policy["review_share_exit_bp"])
    review_active, review_run = _alert_state(
        [int(sample["review_bp"]) for sample in balanced],
        enters=lambda value: value >= review_enter,
        exits=lambda value: value <= review_exit,
        consecutive=review_consecutive,
    )
    growth_consecutive = int(alert_policy["growth_rate_consecutive"])
    growth_enter = int(alert_policy["growth_rate_enter_bp"])
    growth_exit = int(alert_policy["growth_rate_exit_bp"])
    growth_active, growth_run = _alert_state(
        [int(sample["growth_bp"]) for sample in balanced],
        enters=lambda value: value <= growth_enter,
        exits=lambda value: value >= growth_exit,
        consecutive=growth_consecutive,
    )
    reaction = {
        "mode_choices": ["maintenance", "balanced"],
        "suggestions": ["increase_session_duration", "drop_optional_goals"],
        "automatic_slowdown": False,
    }
    return [
        {
            "id": "review_share_high",
            "active": review_active,
            "pending_consecutive": review_run,
            "sessions_considered": len(balanced),
            "reaction": reaction,
        },
        {
            "id": "growth_rate_low",
            "active": growth_active,
            "pending_consecutive": growth_run,
            "sessions_considered": len(balanced),
            "reaction": reaction,
        },
    ]


def metrics(
    store: EventStore,
    policy: dict[str, Any],
    now: datetime,
    *,
    backlog: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return all seven v1 metrics plus report-only hysteresis alerts."""
    calibration, transfer_samples = _prediction_error_metrics(store)
    session_samples = _terminal_session_shares(store)
    backlog_age, max_deferrals = _backlog_metrics(backlog or [], now, store, policy)
    values = [
        calibration,
        _share_metric(session_samples, "presented_review_share", "review_bp"),
        _share_metric(session_samples, "presented_growth_rate", "growth_bp"),
        backlog_age,
        max_deferrals,
        _lapse_metric(store, now),
        _transfer_gap_metric(transfer_samples),
    ]
    return {
        "as_of": now.astimezone(UTC).isoformat(),
        "metrics": values,
        "alerts": _alerts(session_samples, policy),
    }
