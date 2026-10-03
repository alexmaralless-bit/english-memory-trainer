"""Attempt facts: the event contract, the span/credit index and the pending set
(evidence contract 0.4, 4.6; roadmap 2.2).

The per-step writers that used to live here (``record_attempt``,
``record_block_attempt`` -- the ``attempt record[-block]`` commands) went away
with the step-delivery protocol [PD-2026-09-23]. Attempts are now written by
the lesson report (``lessons.report`` over the pure builders in
``evidence.report``), which emits the SAME event contract, so everything that
remains here serves both the new producer and the historic log:

- the event and aggregate names (``attempt.recorded``,
  ``attempt.state_changed``, ``evidence.added``, the ``attempt`` aggregate) and
  the drill-block constants;
- **semantic identity**: :func:`_credited_item_spans` indexes every (span,
  target, dimension) that already earned credit -- single attempts by their
  ``span_hash``/``primary_target``, drill blocks per CREDITED item -- so the
  same span never mints evidence twice, whichever protocol recorded it;
- :func:`_automaticity_updates`: the ``AUTOMATICITY_UPDATED`` facts caused by a
  batch of ``EVIDENCE_ADDED``, appended in the SAME UnitOfWork (scoring 3d);
- the pending set (:func:`pending_attempts`) and its abandon/stale closure
  (:func:`close_pending_attempts`) -- an attempt still ``recorded`` in a
  historic session closes ``closed_unassessed``, never a learner zero.

This module reads only published events and its own aggregates (evidence
depends on kernel + curriculum, never on lessons): the event log is the module
boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

# Consumed event contracts (published by lessons). String literals on purpose:
# events are the cross-module interface; importing lessons here would invert
# the dependency rule (evidence depends on kernel + curriculum only).
SESSION_STARTED_EVENT = "session.started"
SESSION_CLOSED_EVENTS = ("session.finished", "session.abandoned")

EVENT_ATTEMPT_RECORDED = "attempt.recorded"
EVENT_ATTEMPT_STATE_CHANGED = "attempt.state_changed"
EVENT_EVIDENCE_ADDED = "evidence.added"

ATTEMPT_AGGREGATE = "attempt"

# A drill block is one step, one snapshot and one attempt (evidence 4.6).
DRILL_BLOCK_FORM = "drill_block"
# The block passes as ONE objective evidence at or above this accuracy; below
# it the single boolean is False. A block is not a graduated rubric score:
# collapsing it here keeps it on the unchanged objective Mastery path.
BLOCK_CORRECT_THRESHOLD_PPM = 750_000

RECORDED = "recorded"
ASSESSED = "assessed"
# Terminal, non-contributing: the session was abandoned before assessment.
# Never an input to scoring -- the learner is not punished for a lost chat.
CLOSED_UNASSESSED = "closed_unassessed"


class EvidencePrecondition(KernelError):
    """The attempt is not admissible as stated -- fix the reference, not retry."""

    code = "EVIDENCE_PRECONDITION"


def _session_manifest(store: EventStore, session_id: str) -> dict[str, Any]:
    """Fold the session's lifecycle events: manifest if the session is active."""
    manifest: dict[str, Any] | None = None
    closed = False
    for event in store.read():
        if event.correlation_id != session_id:
            continue
        if event.type == SESSION_STARTED_EVENT:
            manifest = dict(event.payload.get("manifest") or {})
        elif event.type in SESSION_CLOSED_EVENTS:
            closed = True
    if manifest is None:
        raise EvidencePrecondition(f"session {session_id} does not exist")
    if closed:
        raise EvidencePrecondition(
            f"session {session_id} is closed; attempts attach only to an active session"
        )
    return manifest


def _item_pair(item_target_ref: Any, primary_target: dict[str, Any] | None) -> tuple[str, str | None] | None:
    """The (target, dimension) a block item's span is credited to (evidence 4.6).

    The item's own ``target_ref`` from the SNAPSHOT when it has one (a contrast
    item drills a different target than the block's primary), else the block's
    primary target. ``None`` when neither exists: with no target there is no
    pair, so the one-span-per-pair rule has nothing to bind and the item is
    credited.
    """
    primary = primary_target or {}
    ref = item_target_ref or primary.get("target_ref")
    if not ref:
        return None
    dimension = primary.get("dimension")
    return str(ref), None if dimension is None else str(dimension)


def _credited_item_spans(store: EventStore) -> set[tuple[str, str, str | None]]:
    """Every (span, target, dimension) a span already earned credit for.

    Both attempt shapes are indexed, because semantic identity is a property of
    the SPAN, not of the document it arrived in (0.4 4.1 + 4.6): a single
    attempt contributes its own ``span_hash``/``primary_target``, and a drill
    block contributes one entry per CREDITED item. An item recorded
    ``credited: false`` never earned anything, so it does not block a later
    honest answer.
    """
    seen: set[tuple[str, str, str | None]] = set()
    for event in store.read():
        if event.type != EVENT_ATTEMPT_RECORDED:
            continue
        payload = event.payload
        primary = payload.get("primary_target") or {}
        items = payload.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict) or item.get("credited") is False:
                    continue
                span = item.get("span_hash")
                pair = _item_pair(item.get("target_ref"), primary)
                if span is None or pair is None:
                    continue
                seen.add((str(span), *pair))
            continue
        span = payload.get("span_hash")
        if span is None or not primary.get("target_ref"):
            continue
        dimension = primary.get("dimension")
        seen.add((str(span), str(primary["target_ref"]), None if dimension is None else str(dimension)))
    return seen


def _automaticity_updates(
    store: EventStore,
    clock: Clock,
    registry: PolicyRegistry | None,
    batch: Sequence[DomainEvent],
) -> list[DomainEvent]:
    """The ``AUTOMATICITY_UPDATED`` facts caused by the evidence in ``batch``.

    Built here and appended by the caller INSIDE its UnitOfWork, exactly the
    shape ``evidence.reviews`` uses for state-transition facts: the axis and
    the scoring update that consumed the evidence must never be able to commit
    apart (scoring 3d). Empty when the session pinned no ``automaticity``
    version, or when neither the state nor any number of the axis moved --
    nothing observed means nothing to say.
    """
    sources = [event for event in batch if event.type == EVENT_EVIDENCE_ADDED]
    if not sources:
        return []
    # Local import: evidence may call scoring's narrow producers (see the layer
    # allowlist), and a module-scope import would widen the start-time graph.
    from english_trainer.scoring.automaticity import build_automaticity_update

    resolver = registry if registry is not None else PolicyRegistry(store._conn, clock)
    built: list[DomainEvent] = []
    for source in sources:
        # At most one EVIDENCE_ADDED per attempt today; the loop keeps the
        # helper total rather than assuming that shape forever.
        update = build_automaticity_update(store, resolver, source)
        if update is not None:
            built.append(update)
    return built


def session_attempts(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """Recorded attempts of a session, in event order (the finish increment
    checks their statuses; scoring folds them in 2.3)."""
    out: list[dict[str, Any]] = []
    for event in store.read():
        if event.type == EVENT_ATTEMPT_RECORDED and event.correlation_id == session_id:
            out.append(dict(event.payload))
    return out


def pending_attempts(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """Attempts of the session whose disposition is still open (lessons 0.5).

    The pending set is read from the attempt *aggregates* (the operational
    truth for lifecycle status), located via the session's ``ATTEMPT_RECORDED``
    events. ``recorded`` attempts are pending; ``assessed`` and
    ``closed_unassessed`` are settled. Review assignments join this set once
    the scheduler exists.
    """
    from english_trainer.kernel.aggregates import read_aggregate

    pending: list[dict[str, Any]] = []
    for recorded in session_attempts(store, session_id):
        attempt_id = str(recorded["attempt_id"])
        found = read_aggregate(store._conn, ATTEMPT_AGGREGATE, attempt_id)
        state = found[0] if found is not None else recorded
        if state.get("status") not in (ASSESSED, CLOSED_UNASSESSED):
            pending.append(dict(state))
    return pending


def close_pending_attempts(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    reason: str,
    actor: str = "engine",
) -> list[str]:
    """Close every pending attempt of the session without scoring contribution.

    Runs INSIDE the caller's UnitOfWork (lessons owns the abandon trigger,
    evidence executes the closure -- 0.4 4.3): aggregate updates and the
    ``ATTEMPT_STATE_CHANGED`` events commit atomically with the session
    terminalization or not at all. Returns the closed attempt ids.
    """
    closed: list[str] = []
    for state in pending_attempts(store, session_id):
        attempt_id = str(state["attempt_id"])
        found = uow.get_aggregate(ATTEMPT_AGGREGATE, attempt_id)
        if found is None:
            continue
        current, revision = found
        previous = str(current.get("status"))
        uow.save_aggregate(
            ATTEMPT_AGGREGATE,
            attempt_id,
            {
                **current,
                "status": CLOSED_UNASSESSED,
                "non_contributing": True,
                "close_reason": reason,
                "closed_at": clock.now().isoformat(),
            },
            expected_revision=revision,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_ATTEMPT_STATE_CHANGED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=current.get("provider"),
                    correlation_id=session_id,
                    payload={
                        "attempt_id": attempt_id,
                        "session_id": session_id,
                        "from_status": previous,
                        "to_status": CLOSED_UNASSESSED,
                        "reason": reason,
                        "non_contributing": True,
                    },
                )
            ]
        )
        closed.append(attempt_id)
    return closed
