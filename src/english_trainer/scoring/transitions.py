"""Canonical, causally linked knowledge-state transition facts."""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import derived_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.engine import (
    ACTIVE,
    AT_RISK,
    MASTERED,
    OVERDUE_AT_RISK_EVENT,
    REVIEW_OUTCOME_EVENT,
    fold_scores,
    transition,
)

EVENT_STATE_TRANSITION = "scoring.state_transition"


def _already_exists(store: EventStore, source_event_id: str) -> DomainEvent | None:
    for event in store.read():
        if event.type == EVENT_STATE_TRANSITION and event.causation_id == source_event_id:
            return event
    return None


def _next_state(
    policy: dict[str, Any], source: DomainEvent, from_state: str, prior: str | None
) -> tuple[str, str | None, str] | None:
    if source.type == REVIEW_OUTCOME_EVENT:
        outcome = str(source.payload.get("outcome") or "")
        to_state, next_prior = transition(from_state, outcome, prior)
        if str(source.payload.get("origin") or "session") == "placement":
            ceiling = str((policy.get("origin_rules") or {}).get("placement_state_ceiling", ACTIVE))
            order = ["NEW", "LEARNING", ACTIVE, MASTERED]
            if to_state in order and order.index(to_state) > order.index(ceiling):
                to_state = ceiling
        return to_state, next_prior, outcome
    if source.type == OVERDUE_AT_RISK_EVENT:
        if from_state in (ACTIVE, MASTERED):
            return AT_RISK, from_state, "OVERDUE_AT_RISK_TRIGGERED"
        return from_state, prior, "OVERDUE_AT_RISK_TRIGGERED"
    return None


def build_state_transition(
    store: EventStore,
    registry: PolicyRegistry,
    source: DomainEvent,
    *,
    before_override: tuple[str, str | None] | None = None,
) -> DomainEvent | None:
    """Build the one transition fact caused by ``source``.

    Recognised scoring inputs also get a same-state fact.  That makes coverage
    total and auditable without having to infer whether an absent transition
    means "no state change" or "producer failed before appending it".
    """
    existing = _already_exists(store, source.id)
    if existing is not None:
        return existing
    scoring_version = source.pinned_versions.get("scoring")
    if scoring_version is None:
        return None
    policy = registry.resolve_pinned("scoring", scoring_version)
    target_ref = str(source.payload.get("target_ref") or "")
    if not target_ref:
        return None
    folded = fold_scores(store, policy).get(target_ref)
    before = before_override or (
        folded.knowledge_state if folded is not None else "NEW",
        folded.prior_steady_state if folded is not None else None,
    )
    from_state, prior = before
    next_state = _next_state(policy, source, from_state, prior)
    if next_state is None:
        return None
    to_state, _, trigger = next_state
    return make_event(
        id=derived_ulid(source.id, EVENT_STATE_TRANSITION),
        type=EVENT_STATE_TRANSITION,
        occurred_at=source.occurred_at,
        actor="engine",
        provider=source.provider,
        correlation_id=source.correlation_id,
        causation_id=source.id,
        payload={
            "target_ref": target_ref,
            "dimension": source.payload.get("dimension"),
            "from_state": from_state,
            "to_state": to_state,
            "trigger": trigger,
            "source_event_id": source.id,
            "scoring_policy_version": scoring_version,
        },
        pinned_versions={"scoring": scoring_version},
    )


def backfill_state_transitions(
    store: EventStore, registry: PolicyRegistry, uow: UnitOfWork
) -> dict[str, int]:
    """Append missing transition facts in source-sequence order, idempotently."""
    created: list[DomainEvent] = []
    states: dict[str, tuple[str, str | None]] = {}
    scanned = 0
    for source in store.read():
        if source.type not in (REVIEW_OUTCOME_EVENT, OVERDUE_AT_RISK_EVENT):
            continue
        scanned += 1
        target_ref = str(source.payload.get("target_ref") or "")
        scoring_version = source.pinned_versions.get("scoring")
        if scoring_version is None:
            continue
        policy = registry.resolve_pinned("scoring", scoring_version)
        before = states.get(target_ref, ("NEW", None))
        next_state = _next_state(policy, source, *before)
        if next_state is None:
            continue
        to_state, next_prior, _ = next_state
        transition_event = build_state_transition(
            store,
            registry,
            source,
            before_override=before,
        )
        states[target_ref] = (to_state, next_prior)
        if transition_event is not None and _already_exists(store, source.id) is None:
            created.append(transition_event)
    if created:
        uow.append(created)
    return {"scanned": scanned, "created": len(created)}


def transition_coverage(store: EventStore) -> dict[str, int | bool]:
    sources = [
        event
        for event in store.read()
        if event.type in (REVIEW_OUTCOME_EVENT, OVERDUE_AT_RISK_EVENT) and "scoring" in event.pinned_versions
    ]
    covered = {
        str(event.causation_id)
        for event in store.read()
        if event.type == EVENT_STATE_TRANSITION and event.causation_id is not None
    }
    missing = sum(1 for source in sources if source.id not in covered)
    return {"sources": len(sources), "missing": missing, "complete": missing == 0}
