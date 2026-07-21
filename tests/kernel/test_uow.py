"""UnitOfWork lifecycle guards: a UoW is single-use, writes only inside its
open block, and never carries pending outbox state between transactions
(foundation 3.7)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


def _event(clock: FixedClock, rnd: SeededRandomSource):
    return make_event(
        id=new_ulid(clock, rnd),
        type="demo.happened",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="corr-1",
        payload={"a": 1},
    )


def test_uow_is_single_use(store: EventStore, clock, random_source) -> None:
    uow = UnitOfWork(store, clock)
    with uow:
        uow.append([_event(clock, random_source)])
    # Re-entering the same instance is refused -- one `with` block per transaction.
    with pytest.raises(KernelError), uow:
        pass
    assert store.count() == 1


def test_writes_outside_the_block_are_refused(store: EventStore, clock, random_source) -> None:
    uow = UnitOfWork(store, clock)  # never entered
    with pytest.raises(KernelError):
        uow.append([_event(clock, random_source)])
    with pytest.raises(KernelError):
        uow.check_idempotency("k", "h")
    with pytest.raises(KernelError):
        uow.record_result("k", "h", {"x": 1})
    assert store.count() == 0


def test_consecutive_uows_do_not_leak_outbox_state(store: EventStore, clock, random_source) -> None:
    with UnitOfWork(store, clock) as uow1:
        uow1.append([_event(clock, random_source)])
    with UnitOfWork(store, clock) as uow2:
        uow2.append([_event(clock, random_source)])
    assert store.count() == 2
    # Exactly two outbox rows: the second UoW did not re-enqueue the first's event.
    row = store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()
    assert row["n"] == 2
