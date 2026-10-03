"""The review scheduler: when to repeat (scheduler 2-5; roadmap 2.3).

Schedules are a pure fold over the event log, like scores: the first
admissible evidence for a (target, dimension) opens its ``ReviewSchedule``
(epoch 1, first interval), and every ``REVIEW_OUTCOME`` adapts it --
CONFIRMED/RECOVERED step forward, REGRESSION steps back, PROGRESS holds,
INSUFFICIENT_EVIDENCE holds the interval index and books a short retry (for
ANY reason, including ``abandoned`` -- the learner is not punished for a lost
chat). ``REVIEW_ASSIGNMENT_CANCELLED`` is an explicit terminal no-op: the
system withdrew the goal itself, so neither the schedule nor a retry moves.
Intervals are elapsed time (24h), never calendar days.

``scheduler@2`` (scheduler.md 3a, PD-2026-09-22 PD-D) prepends a short
relearning ladder (``relearning_ladder_days``, e.g. ``[1, 2, 4]``) to the base
table: ``effective_intervals_days`` in ``scheduler/policy.py`` builds the
ladder-then-base table once per policy version. A failed ladder rung
(REGRESSION, or anything below CONFIRMED) repeats the same rung instead of
stepping back or advancing; past the ladder, REGRESSION step-back/reset is
unchanged. ``scheduler@1`` carries no ladder key, so its effective table is
the base table -- byte-identical to before ``scheduler@2`` existed. Each event
resolves its OWN table from its own pinned scheduler version when a
``PolicyRegistry`` is supplied (``fold_schedules(..., registry=...)``): a log
spanning a scheduler@1 -> scheduler@2 activation replays every event under the
table it was actually assigned under, never today's active one -- activation
is not retroactive (foundation 3.6). Callers that omit ``registry`` keep
exactly one policy for the whole fold, as before.

``permanent_interleave`` (scheduler.md 3a, PD-2026-09-22 PD-F) marks a
``ReviewSchedule`` whose target is an article-tier frame -- a lexical item
whose ``frame_of`` names a ``grammar.articles.*`` topic (lexical-system 1c).
The scheduler layer stays PURE and knows nothing about curriculum shape or
``frame_of``: classification is injected as ``permanent_interleave_targets``
(a plain ``frozenset[str]`` of target refs), computed by the caller from
whatever curriculum snapshot it has resolved (tests/architecture -- scheduler
may depend on kernel/scoring only, never curriculum). ``None`` (the default
every existing caller uses today) means an empty set: every schedule's flag
is ``False``, byte-identical to before this field existed. A flagged target,
once its ``interval_index`` reaches the last rung of the effective table, is
re-pinned to ``permanent_interleave_interval_days`` (scheduler@2 policy;
validated equal to the base table's last rung) on every further
CONFIRMED/RECOVERED instead of merely holding there -- it never leaves the due
queue and this fold never reads knowledge state, so the rule applies even at
MASTERED. Everything else -- REGRESSION, PROGRESS, INSUFFICIENT_EVIDENCE,
CANCELLED -- is unchanged; ``scheduler@1`` carries no
``permanent_interleave_interval_days`` key, so the branch is unreachable under
it regardless of the flag. Deriving ``permanent_interleave_targets`` from a
pinned curriculum snapshot PER EVENT (so a log spanning two curriculum
versions honours each event's own classification, the same way the
``registry`` kwarg already does for scheduler-policy pins) is a follow-up for
whoever owns the call sites -- out of scope here.

``review_status`` (not_due / due / overdue) is COMPUTED from the schedule and
the clock -- an operational axis, never knowledge state, and never persisted
as truth. ``OVERDUE_AT_RISK_TRIGGERED``, by contrast, IS a fact: crossing the
at-risk boundary changes knowledge state, so the sweep emits it append-only
with a deterministic ``boundary_at`` (derived from ``next_review_at``, never
the sweep's wall clock) and an idempotency key of (target, dimension,
schedule_epoch) -- re-running the sweep can never mint a second fact, while a
legitimately new schedule epoch can.

The due backlog orders by LOSS RISK, not by idle time (canonical tuple,
scheduler 5): retrievability ascending leads; overdue days only separate near
ties. ``is_prereq_of_next`` and ``weakest_dimension_gap`` are honest zeros
until the learner model and per-dimension gap data exist; the tuple keeps
their slots so the order is stable when they arrive.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scheduler.policy import SCHEDULER_KIND, effective_intervals_days
from english_trainer.scheduler.policy import require_valid as require_valid_scheduler
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.policy import scoring_context
from english_trainer.scoring.transitions import build_state_transition

# Consumed event contracts; literals on purpose -- events are the boundary.
EVIDENCE_ADDED_EVENT = "evidence.added"
REVIEW_OUTCOME_EVENT = "review.outcome"
CANCELLED_EVENT = "review.assignment_cancelled"

EVENT_OVERDUE_AT_RISK = "review.overdue_at_risk"

NOT_DUE = "not_due"
DUE = "due"
OVERDUE = "overdue"

_DAY_SECONDS = Decimal(86400)

PERMANENT_INTERLEAVE_INTERVAL_KEY = "permanent_interleave_interval_days"


@dataclass
class ScheduleState:
    """One (target, dimension) review schedule -- the fold's unit."""

    schedule_epoch: int
    interval_index: int
    interval_days: int
    next_review_at: datetime
    last_outcome: str | None
    last_activity_at: datetime
    permanent_interleave: bool = False


def _resolve_event_policy(
    pinned_versions: dict[str, Any] | None,
    default_policy: dict[str, Any],
    registry: PolicyRegistry | None,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The scheduler policy THIS event was pinned to, when resolvable.

    Without a ``registry`` (the default every existing caller uses), every
    event folds under the caller's single ``default_policy`` -- today's
    behaviour, unchanged. With one, an event that pinned a scheduler version
    resolves that exact version (pinned resolve, never current-active,
    foundation 3.6); a version resolved once is cached for the rest of the
    fold. An event without a scheduler pin (or one predating this field) falls
    back to ``default_policy`` too.
    """
    if registry is None:
        return default_policy
    version_id = (pinned_versions or {}).get(SCHEDULER_KIND)
    if not version_id:
        return default_policy
    cached = cache.get(version_id)
    if cached is None:
        cached = require_valid_scheduler(registry.resolve_pinned(SCHEDULER_KIND, version_id))
        cache[version_id] = cached
    return cached


def fold_schedules(
    store: EventStore,
    policy: dict[str, Any],
    *,
    registry: PolicyRegistry | None = None,
    permanent_interleave_targets: frozenset[str] | None = None,
) -> dict[tuple[str, str], ScheduleState]:
    """Fold the event log into review schedules (deterministic).

    ``policy`` is the table used for every event unless ``registry`` is
    supplied, in which case each event resolves its OWN pinned scheduler
    version (scheduler@1 vs scheduler@2 span a log the same way scoring
    policy versions would) -- see ``_resolve_event_policy``.

    ``permanent_interleave_targets`` is a plain set of target refs a caller
    has already classified as article-tier frames (scheduler.md 3a); the
    scheduler itself never inspects curriculum content (tests/architecture --
    this layer may depend on kernel/scoring only, never curriculum). ``None``
    means every schedule's ``permanent_interleave`` is ``False``, unchanged
    from before this field existed. Applied uniformly for the whole fold, the
    same way ``policy`` is without ``registry``; resolving it PER EVENT from
    each event's own pinned curriculum snapshot is left to a future caller.
    """
    policy_cache: dict[str, dict[str, Any]] = {}
    permanent_targets = permanent_interleave_targets or frozenset()
    schedules: dict[tuple[str, str], ScheduleState] = {}

    for event in store.read():
        if event.type == EVIDENCE_ADDED_EVENT:
            primary = event.payload.get("primary_target") or {}
            ref = primary.get("target_ref")
            if not ref:
                continue
            key = (str(ref), str(primary.get("dimension") or "recognition"))
            if key in schedules:
                continue  # intervals adapt only through review outcomes
            event_policy = _resolve_event_policy(event.pinned_versions, policy, registry, policy_cache)
            intervals = effective_intervals_days(event_policy)
            schedules[key] = ScheduleState(
                schedule_epoch=1,
                interval_index=0,
                interval_days=intervals[0],
                next_review_at=event.occurred_at + timedelta(days=intervals[0]),
                last_outcome=None,
                last_activity_at=event.occurred_at,
                permanent_interleave=str(ref) in permanent_targets,
            )
        elif event.type == REVIEW_OUTCOME_EVENT:
            payload = event.payload
            ref = payload.get("target_ref")
            if not ref:
                continue
            key = (str(ref), str(payload.get("dimension") or "recognition"))
            event_policy = _resolve_event_policy(event.pinned_versions, policy, registry, policy_cache)
            intervals = effective_intervals_days(event_policy)
            retry_days = int(event_policy["retry_days"])
            ladder_len = len(event_policy.get("relearning_ladder_days") or ())
            interleave_days = event_policy.get(PERMANENT_INTERLEAVE_INTERVAL_KEY)
            state = schedules.get(key)
            if state is None:
                # An outcome for a never-scheduled pair: open a schedule so the
                # fact is not lost (hidden/conversation review, canon 5).
                state = schedules[key] = ScheduleState(
                    1,
                    0,
                    intervals[0],
                    event.occurred_at,
                    None,
                    event.occurred_at,
                    permanent_interleave=str(ref) in permanent_targets,
                )
            outcome = str(payload.get("outcome") or "")
            index = state.interval_index
            if outcome in ("CONFIRMED", "RECOVERED"):
                if state.permanent_interleave and interleave_days is not None and index >= len(intervals) - 1:
                    # Past the end of the effective table: re-pinned to the
                    # permanent-interleave interval on EVERY further
                    # CONFIRMED/RECOVERED, forever -- it never leaves the due
                    # queue and this fold never reads knowledge state, so the
                    # rule applies even at MASTERED (scheduler.md 3a).
                    # ``scheduler@1`` carries no
                    # ``permanent_interleave_interval_days`` key, so
                    # ``interleave_days`` is ``None`` and this branch is
                    # unreachable under it -- byte-identical to before this
                    # field existed.
                    index = len(intervals) - 1
                    days = int(interleave_days)
                else:
                    index = min(index + 1, len(intervals) - 1)
                    days = intervals[index]
            elif outcome == "REGRESSION":
                if index < ladder_len:
                    # A failed ladder rung repeats itself -- it neither steps
                    # back nor advances (scheduler.md 3a).
                    days = intervals[index]
                else:
                    index = max(index - 1, 0)
                    days = intervals[index]
            elif outcome == "PROGRESS":
                days = intervals[index]  # hold
            elif outcome == "INSUFFICIENT_EVIDENCE":
                days = retry_days  # hold the index, book a short retry (any reason)
            else:
                continue  # unknown outcome: audited by scoring, no scheduler branch
            state.interval_index = index
            state.interval_days = days
            state.next_review_at = event.occurred_at + timedelta(days=days)
            state.last_outcome = outcome
            state.last_activity_at = event.occurred_at
            state.schedule_epoch += 1
        elif event.type == CANCELLED_EVENT:
            continue  # explicit terminal no-op: no reschedule, no retry [RR2-4]

    return schedules


def review_status(state: ScheduleState, now: datetime, policy: dict[str, Any]) -> str:
    """``not_due / due / overdue`` -- computed, never persisted as truth."""
    if now < state.next_review_at:
        return NOT_DUE
    lateness_days = Decimal((now - state.next_review_at).total_seconds()) / _DAY_SECONDS
    threshold = Decimal(str(policy["overdue_factor"])) * Decimal(state.interval_days)
    return OVERDUE if lateness_days > threshold else DUE


def at_risk_boundary(state: ScheduleState, policy: dict[str, Any]) -> datetime:
    """The deterministic AT_RISK crossing instant -- from the schedule, never
    from the sweep's wall clock."""
    factor = Decimal(str(policy["at_risk_overdue_factor"]))
    seconds = int(factor * Decimal(state.interval_days) * _DAY_SECONDS)
    return state.next_review_at + timedelta(seconds=seconds)


def due_backlog(
    store: EventStore,
    scheduler_policy: dict[str, Any],
    scoring_policy: dict[str, Any],
    program: dict[str, Any],
    now: datetime,
    *,
    registry: PolicyRegistry | None = None,
    permanent_interleave_targets: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Due/overdue candidates in the canonical priority order (scheduler 5).

    Loss risk leads: retrievability ascending, then curriculum priority, then
    the reserved slots, then overdue days as a near-tie separator, then the
    stable (target_id, dimension_id) tie-breaker. ``registry`` is optional and
    forwarded to ``fold_schedules`` for per-event pinned-policy resolution
    (existing callers omit it and keep today's single-policy fold).
    ``permanent_interleave_targets`` is likewise forwarded, unchanged, to
    derive ``permanent_interleave`` (scheduler.md 3a) -- the scheduler itself
    never reads curriculum content, so the caller (which HAS ``program``
    already) computes this set; without it every candidate's
    ``permanent_interleave`` is ``False``. Each candidate carries its
    schedule's flag so a consumer (e.g. a future per-session cap, OPEN-38) can
    single these targets out; ordering itself is unchanged by the flag.
    """
    context = scoring_context(scoring_policy)
    schedules = fold_schedules(
        store, scheduler_policy, registry=registry, permanent_interleave_targets=permanent_interleave_targets
    )
    scores = fold_scores(store, scoring_policy)
    priority_rank = {str(t.get("id")): rank for rank, t in enumerate(program.get("topics", []))}

    out: list[dict[str, Any]] = []
    for (target_ref, dimension), state in schedules.items():
        status = review_status(state, now, scheduler_policy)
        if status == NOT_DUE:
            continue
        stability = None
        target_scores = scores.get(target_ref)
        if target_scores is not None and target_scores.stability_days is not None:
            stability = target_scores.stability_days
        if stability is None or stability <= 0:
            retriev = Decimal(0)
        else:
            elapsed = context.divide(
                context.create_decimal(int((now - state.last_activity_at).total_seconds())), _DAY_SECONDS
            )
            with decimal.localcontext(context):
                retriev = (-context.divide(elapsed, stability)).exp()
        overdue_days = int(Decimal((now - state.next_review_at).total_seconds()) / _DAY_SECONDS)
        out.append(
            {
                "target_ref": target_ref,
                "dimension": dimension,
                "status": status,
                "retrievability": str(retriev),
                "overdue_days": overdue_days,
                "schedule_epoch": state.schedule_epoch,
                "interval_days": state.interval_days,
                "next_review_at": state.next_review_at.isoformat(),
                "first_due_at": state.next_review_at.isoformat(),
                "curriculum_priority_rank": priority_rank.get(target_ref, 10_000_000),
                "knowledge_state": target_scores.knowledge_state if target_scores else "NEW",
                "permanent_interleave": state.permanent_interleave,
            }
        )
    out.sort(
        key=lambda c: (
            Decimal(c["retrievability"]),  # risk of loss leads (asc)
            c["curriculum_priority_rank"],
            0,  # is_prereq_of_next desc -- honest zero until the learner model
            0,  # weakest_dimension_gap desc -- honest zero until per-dimension gaps
            -c["overdue_days"],  # desc: separates near ties only
            c["target_ref"],
            c["dimension"],
        )
    )
    return out


def _already_triggered(store: EventStore) -> set[tuple[str, str, int]]:
    seen: set[tuple[str, str, int]] = set()
    for event in store.read():
        if event.type == EVENT_OVERDUE_AT_RISK:
            payload = event.payload
            seen.add(
                (
                    str(payload.get("target_ref")),
                    str(payload.get("dimension")),
                    int(payload.get("schedule_epoch") or 0),
                )
            )
    return seen


def sweep_overdue(
    store: EventStore,
    scheduler_version: str,
    scheduler_policy: dict[str, Any],
    clock: Clock,
    random_source: RandomSource,
    *,
    actor: str = "engine",
    permanent_interleave_targets: frozenset[str] | None = None,
    registry: PolicyRegistry | None = None,
) -> list[str]:
    """Emit ``OVERDUE_AT_RISK_TRIGGERED`` for every new boundary crossing.

    Append-only and idempotent by (target, dimension, schedule_epoch): a
    re-run mints nothing, a legitimately new epoch mints a new fact. Returns
    the target refs that crossed. One UnitOfWork for the whole batch.

    Folds with the caller's single ``scheduler_policy`` unless ``registry`` is
    supplied, in which case ``fold_schedules`` resolves each event's OWN
    pinned scheduler version instead (foundation 3.6 -- activation is never
    retroactive), mirroring ``fold_schedules``/``due_backlog``'s ``registry``
    kwarg. ``None`` (every caller before this) keeps today's single-policy
    fold. Independently of this, a fresh ``PolicyRegistry`` is still built
    here to resolve the ACTIVE scoring pin for the emitted facts and to drive
    ``build_state_transition`` -- an unrelated use of the same class, not the
    per-event scheduler resolution ``registry`` controls.
    ``permanent_interleave_targets`` is forwarded to
    ``fold_schedules`` unchanged (scheduler.md 3a); ``None`` -- every existing
    caller today -- keeps every schedule's ``permanent_interleave`` ``False``,
    which for the boundary computed here is harmless-but-inert only because
    the shipped policy validates ``permanent_interleave_interval_days`` equal
    to the base table's last rung (scheduler/policy.py); a caller that ever
    diverges the two must pass this set for the boundary to stay correct.
    """
    schedules = fold_schedules(
        store,
        scheduler_policy,
        registry=registry,
        permanent_interleave_targets=permanent_interleave_targets,
    )
    triggered = _already_triggered(store)
    now = clock.now()
    crossings: list[tuple[tuple[str, str], ScheduleState, datetime]] = []
    for key in sorted(schedules):
        state = schedules[key]
        boundary = at_risk_boundary(state, scheduler_policy)
        if now >= boundary and (key[0], key[1], state.schedule_epoch) not in triggered:
            crossings.append((key, state, boundary))
    if not crossings:
        return []
    active_registry = PolicyRegistry(store._conn, clock)
    try:
        scoring_version = active_registry.active_version("scoring")
    except NoActivePolicy:
        scoring_version = None
    source_events = []
    transition_events = []
    state_overrides: dict[str, tuple[str, str | None]] = {}
    for key, state, boundary in crossings:
        pins = {"scheduler": scheduler_version}
        if scoring_version is not None:
            pins["scoring"] = scoring_version
        source = make_event(
            id=new_ulid(clock, random_source),
            type=EVENT_OVERDUE_AT_RISK,
            occurred_at=boundary,
            actor=actor,
            correlation_id=new_ulid(clock, random_source),
            payload={
                "target_ref": key[0],
                "dimension": key[1],
                "schedule_epoch": state.schedule_epoch,
                "boundary_at": boundary.isoformat(),
                "next_review_at": state.next_review_at.isoformat(),
            },
            pinned_versions=pins,
        )
        source_events.append(source)
        transition_event = build_state_transition(
            store,
            active_registry,
            source,
            before_override=state_overrides.get(key[0]),
        )
        if transition_event is not None:
            transition_events.append(transition_event)
            state_overrides[key[0]] = (
                str(transition_event.payload["to_state"]),
                str(transition_event.payload["from_state"]),
            )
    with UnitOfWork(store, clock) as uow:
        uow.append([*source_events, *transition_events])
    return [key[0] for key, _, _ in crossings]
