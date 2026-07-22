from __future__ import annotations

from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.transitions import (
    EVENT_STATE_TRANSITION,
    backfill_state_transitions,
    transition_coverage,
)


def _registry(store, clock, policy) -> PolicyRegistry:
    registry = PolicyRegistry(store._conn, clock)
    registry.register("scoring", "scoring@1", policy)
    registry.activate("scoring", "scoring@1")
    return registry


def test_transition_backfill_is_causal_ordered_and_idempotent(store, clock, random_source, policy) -> None:
    registry = _registry(store, clock, policy)
    sources = []
    for _ in range(3):
        sources.append(
            make_event(
                id=new_ulid(clock, random_source),
                type="review.outcome",
                occurred_at=clock.now(),
                actor="engine",
                correlation_id="session-1",
                payload={
                    "target_ref": "grammar.be.identity",
                    "dimension": "recognition",
                    "outcome": "CONFIRMED",
                    "origin": "session",
                },
                pinned_versions={"scoring": "scoring@1"},
            )
        )
    with UnitOfWork(store, clock) as uow:
        uow.append(sources)
    with UnitOfWork(store, clock) as uow:
        assert backfill_state_transitions(store, registry, uow) == {"scanned": 3, "created": 3}
    transitions = [event for event in store.read() if event.type == EVENT_STATE_TRANSITION]
    assert [(event.payload["from_state"], event.payload["to_state"]) for event in transitions] == [
        ("NEW", "LEARNING"),
        ("LEARNING", "ACTIVE"),
        ("ACTIVE", "MASTERED"),
    ]
    assert [event.causation_id for event in transitions] == [event.id for event in sources]
    assert transition_coverage(store) == {"sources": 3, "missing": 0, "complete": True}

    with UnitOfWork(store, clock) as uow:
        assert backfill_state_transitions(store, registry, uow) == {"scanned": 3, "created": 0}
    assert len([event for event in store.read() if event.type == EVENT_STATE_TRANSITION]) == 3


def test_no_op_source_still_gets_a_total_audit_fact(store, clock, random_source, policy) -> None:
    registry = _registry(store, clock, policy)
    source = make_event(
        id=new_ulid(clock, random_source),
        type="review.outcome",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="session-1",
        payload={
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "outcome": "INSUFFICIENT_EVIDENCE",
            "origin": "session",
        },
        pinned_versions={"scoring": "scoring@1"},
    )
    with UnitOfWork(store, clock) as uow:
        uow.append([source])
    with UnitOfWork(store, clock) as uow:
        assert backfill_state_transitions(store, registry, uow) == {"scanned": 1, "created": 1}
    transition = next(event for event in store.read() if event.type == EVENT_STATE_TRANSITION)
    assert transition.causation_id == source.id
    assert transition.payload["from_state"] == transition.payload["to_state"] == "NEW"
    assert transition_coverage(store)["complete"] is True
