"""Availability profile and deterministic observed-rhythm fold (control 4.7a).

Availability changes workload, never knowledge.  Declared preferences live in
one revisioned aggregate; observed values are rebuilt from session lifecycle
facts on every read, so replay has no second clock or mutable statistics cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from english_trainer.control.errors import AvailabilityInvalid
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import CachedResult, UnitOfWork

AVAILABILITY_AGGREGATE = "availability_profile"
AVAILABILITY_ID = "default"
EVENT_AVAILABILITY_UPDATED = "control.availability_updated"

_STARTED = "session.started"
_TERMINAL = frozenset({"session.finished", "session.abandoned"})
_COMPOSED = "session.composed"
_NO_DATA = "no-data"


def _aware_instant(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise AvailabilityInvalid(f"{field} must be an aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AvailabilityInvalid(f"{field} must be an aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AvailabilityInvalid(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC).isoformat()


def validate_declared(declared: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized snapshot of the integer-only declared schema."""
    allowed = {
        "sessions_per_week_milli",
        "typical_minutes",
        "next_available_at",
        "blackout_until",
    }
    unknown = sorted(set(declared) - allowed)
    if unknown:
        raise AvailabilityInvalid(f"unknown declared availability field(s): {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for field in ("sessions_per_week_milli", "typical_minutes"):
        if field not in declared or declared[field] is None:
            continue
        value = declared[field]
        minimum = 0 if field == "sessions_per_week_milli" else 1
        if type(value) is not int or value < minimum:
            qualifier = "non-negative" if minimum == 0 else "positive"
            raise AvailabilityInvalid(f"{field} must be a {qualifier} integer")
        normalized[field] = value
    for field in ("next_available_at", "blackout_until"):
        if field in declared and declared[field] is not None:
            normalized[field] = _aware_instant(declared[field], field)
    return normalized


def _parse_event_instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _lower_median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _learner_timezone(name: str) -> tzinfo:
    """Resolve UTC/fixed offsets without an external tzdb, then IANA zones
    when the host provides its standard zoneinfo database."""
    if name in {"UTC", "Z", "+00:00"}:
        return UTC
    if len(name) == 6 and name[0] in {"+", "-"} and name[3] == ":":
        try:
            hours = int(name[1:3])
            minutes = int(name[4:6])
        except ValueError as exc:
            raise AvailabilityInvalid(f"unknown learner timezone {name!r}") from exc
        if hours > 23 or minutes > 59:
            raise AvailabilityInvalid(f"unknown learner timezone {name!r}")
        sign = 1 if name[0] == "+" else -1
        return timezone(sign * timedelta(hours=hours, minutes=minutes), name)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise AvailabilityInvalid(f"unknown learner timezone {name!r}") from exc


def observed_availability(
    store: EventStore,
    policy: dict[str, Any],
    now: datetime,
    *,
    timezone_name: str = "UTC",
) -> tuple[dict[str, int | str | None], dict[str, Any]]:
    """Fold observed rhythm over exactly the policy's calendar-week window."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise AvailabilityInvalid("now must be timezone-aware")
    learner_timezone = _learner_timezone(timezone_name)

    availability_policy = policy["availability"]
    weeks = int(availability_policy["divergence_window_weeks"])
    local_now = now.astimezone(learner_timezone)
    current_week_start = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_start = (current_week_start - timedelta(weeks=weeks - 1)).astimezone(UTC)
    window_end = now.astimezone(UTC)

    budgets: dict[str, int] = {}
    terminal_at: dict[str, datetime] = {}
    starts: list[datetime] = []
    for event in store.read():
        session_id = str(event.correlation_id)
        if event.type == _COMPOSED:
            budget = event.payload.get("budget")
            total = budget.get("total_seconds") if isinstance(budget, dict) else None
            if type(total) is int and total > 0:
                budgets[session_id] = total
        elif event.type in _TERMINAL:
            instant = event.occurred_at.astimezone(UTC)
            if window_start <= instant <= window_end:
                terminal_at[session_id] = instant
        elif event.type == _STARTED:
            manifest = event.payload.get("manifest")
            started_at = manifest.get("started_at") if isinstance(manifest, dict) else None
            started_instant = _parse_event_instant(started_at)
            if started_instant is not None and window_start <= started_instant <= window_end:
                starts.append(started_instant)

    terminal_minutes = [budgets[sid] // 60 for sid in sorted(terminal_at) if sid in budgets]
    minimum = int(availability_policy["min_observed_sessions"])
    if len(terminal_minutes) >= minimum:
        sessions_per_week: int | str = len(terminal_minutes) * 1000 // weeks
        typical_minutes: int | str = _lower_median(terminal_minutes)
    else:
        sessions_per_week = _NO_DATA
        typical_minutes = _NO_DATA

    starts.sort()
    intervals = [int((right - left).total_seconds()) for left, right in pairwise(starts)]
    median_interval = _lower_median(intervals) if len(starts) >= 3 else None
    observed: dict[str, int | str | None] = {
        "sessions_per_week_milli": sessions_per_week,
        "typical_minutes": typical_minutes,
        "median_interval_seconds": median_interval,
    }
    trace = {
        "now": window_end.isoformat(),
        "timezone": timezone_name,
        "window_start": window_start.isoformat(),
        "window_weeks": weeks,
        "terminal_sessions": len(terminal_minutes),
        "started_sessions": len(starts),
    }
    return observed, trace


def divergence_ppm(declared: dict[str, Any], observed: dict[str, int | str | None]) -> int | str:
    declared_frequency = declared.get("sessions_per_week_milli")
    observed_frequency = observed.get("sessions_per_week_milli")
    if type(declared_frequency) is not int or type(observed_frequency) is not int:
        return _NO_DATA
    return abs(declared_frequency - observed_frequency) * 1_000_000 // max(declared_frequency, 1000)


def is_long_break(declared: dict[str, Any], observed: dict[str, int | str | None], now: datetime) -> bool:
    """The exact v1 predicate; a future next date alone is insufficient."""
    instant = now.astimezone(UTC)
    blackout = _parse_event_instant(declared.get("blackout_until"))
    if blackout is not None and blackout > instant:
        return True
    next_available = _parse_event_instant(declared.get("next_available_at"))
    median = observed.get("median_interval_seconds")
    return (
        next_available is not None
        and next_available > instant
        and type(median) is int
        and int((next_available - instant).total_seconds()) > median
    )


def resolve_total_seconds(
    policy: dict[str, Any],
    *,
    duration_minutes: int | None,
    declared: dict[str, Any],
    observed: dict[str, int | str | None],
) -> tuple[int, str]:
    """Resolve the fixed CLI -> declared -> observed -> policy precedence."""
    if duration_minutes is not None:
        if type(duration_minutes) is not int or duration_minutes <= 0:
            raise AvailabilityInvalid("duration_minutes must be a positive integer")
        return duration_minutes * 60, "cli"
    declared_minutes = declared.get("typical_minutes")
    if type(declared_minutes) is int:
        return declared_minutes * 60, "declared"
    observed_minutes = observed.get("typical_minutes")
    if type(observed_minutes) is int:
        return observed_minutes * 60, "observed"
    return int(policy["budget"]["default_total_minutes"]) * 60, "policy_default"


def availability_get(
    store: EventStore,
    policy: dict[str, Any],
    clock: Clock,
    *,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """Return declared, observed, divergence, proposal and deterministic trace."""
    found = read_aggregate(store._conn, AVAILABILITY_AGGREGATE, AVAILABILITY_ID)
    declared = dict(found[0].get("declared") or {}) if found is not None else {}
    revision = found[1] if found is not None else 0
    observed, trace = observed_availability(store, policy, clock.now(), timezone_name=timezone_name)
    divergence = divergence_ppm(declared, observed)
    tolerance = int(policy["availability"]["divergence_tolerance_ppm"])
    proposal = None
    if type(divergence) is int and divergence > tolerance:
        proposal = {
            "kind": "review_declared_frequency",
            "declared_sessions_per_week_milli": declared["sessions_per_week_milli"],
            "observed_sessions_per_week_milli": observed["sessions_per_week_milli"],
            "divergence_ppm": divergence,
        }
    return {
        "revision": revision,
        "declared": declared,
        "observed": observed,
        "divergence_ppm": divergence,
        "proposal": proposal,
        "long_break": is_long_break(declared, observed, clock.now()),
        "trace": trace,
    }


def availability_set(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    declared: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    actor: str = "engine",
    control_policy_version: str = "control@1",
) -> dict[str, Any]:
    """Accept a declared-profile replacement and publish only a real change."""
    normalized = validate_declared(declared)
    request_hash = payload_hash({"command": "availability.set", "declared": normalized})
    with UnitOfWork(store, clock) as uow:
        if idempotency_key is not None:
            prior = uow.check_idempotency(idempotency_key, request_hash)
            if isinstance(prior, CachedResult):
                return {**prior.value, "cached": True}

        found = uow.get_aggregate(AVAILABILITY_AGGREGATE, AVAILABILITY_ID)
        previous = dict(found[0].get("declared") or {}) if found is not None else {}
        revision = found[1] if found is not None else 0
        changed = previous != normalized
        next_revision = revision
        event_id: str | None = None
        if changed:
            next_revision = uow.save_aggregate(
                AVAILABILITY_AGGREGATE,
                AVAILABILITY_ID,
                {"declared": normalized},
                expected_revision=revision,
            )
            event_id = new_ulid(clock, random_source)
            uow.append(
                [
                    make_event(
                        id=event_id,
                        type=EVENT_AVAILABILITY_UPDATED,
                        occurred_at=clock.now(),
                        actor=actor,
                        correlation_id=AVAILABILITY_ID,
                        payload={
                            "previous": previous,
                            "declared": normalized,
                            "revision": next_revision,
                        },
                        pinned_versions={"control": control_policy_version},
                    )
                ]
            )
        result: dict[str, object] = {
            "declared": normalized,
            "revision": next_revision,
            "updated": changed,
            "event_id": event_id,
        }
        if idempotency_key is not None:
            uow.record_result(idempotency_key, request_hash, result)
    return {**result, "cached": False}
