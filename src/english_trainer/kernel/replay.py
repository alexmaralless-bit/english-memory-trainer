"""Deterministic replay (foundation contract 5, 3.8 in part).

Replay folds the event log into state by applying events strictly in
``sequence`` order. Two properties the contract demands hold here: the result is
independent of the physical row/query order (only ``sequence`` matters), and it
is reproducible across processes. This ``fold`` is the base the future
``scoring replay`` and read-model projections build on.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.store import EventStore


def iter_events(store: EventStore) -> Iterable[DomainEvent]:
    """Every event in canonical ``sequence`` order."""
    return store.read()


def fold[State](
    events: Iterable[DomainEvent],
    reducer: Callable[[State, DomainEvent], State],
    initial: State,
) -> State:
    """Apply ``reducer`` over events in the given order, starting from ``initial``.

    Callers pass events already ordered by ``sequence`` (via ``iter_events`` or
    the store). ``fold`` itself does not reorder: order is the store's contract.
    """
    state = initial
    for event in events:
        state = reducer(state, event)
    return state


def replay[State](
    store: EventStore,
    reducer: Callable[[State, DomainEvent], State],
    initial: State,
) -> State:
    """Rebuild state from the whole log in ``sequence`` order."""
    return fold(iter_events(store), reducer, initial)
