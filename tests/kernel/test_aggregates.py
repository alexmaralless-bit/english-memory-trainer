"""Multi-aggregate compare-and-set: revisions, stale refusal, and all-or-nothing
across several aggregates in one UnitOfWork (foundation 3.5)."""

from __future__ import annotations

import contextlib

import pytest

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError, StaleRevision
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


def test_create_and_read_roundtrip(store: EventStore, clock) -> None:
    with UnitOfWork(store, clock) as uow:
        revision = uow.save_aggregate("session", "s1", {"status": "STARTED"}, expected_revision=0)
    assert revision == 1
    assert read_aggregate(store._conn, "session", "s1") == ({"status": "STARTED"}, 1)


def test_cas_update_increments_revision(store: EventStore, clock) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"status": "STARTED"}, expected_revision=0)
    with UnitOfWork(store, clock) as uow:
        revision = uow.save_aggregate("session", "s1", {"status": "IN_PROGRESS"}, expected_revision=1)
    assert revision == 2
    assert read_aggregate(store._conn, "session", "s1") == ({"status": "IN_PROGRESS"}, 2)


def test_stale_revision_is_refused_and_stable(store: EventStore, clock) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"status": "STARTED"}, expected_revision=0)
    with pytest.raises(StaleRevision) as exc, UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"status": "HIJACKED"}, expected_revision=99)
    assert exc.value.code == "STALE_REVISION"
    assert read_aggregate(store._conn, "session", "s1") == ({"status": "STARTED"}, 1)


def test_create_over_existing_is_stale(store: EventStore, clock) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"status": "STARTED"}, expected_revision=0)
    with pytest.raises(StaleRevision), UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"status": "CLONE"}, expected_revision=0)
    assert read_aggregate(store._conn, "session", "s1") == ({"status": "STARTED"}, 1)


def test_multi_aggregate_write_is_all_or_nothing(store: EventStore, clock, random_source) -> None:
    # Seed two aggregates.
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"n": 1}, expected_revision=0)
        uow.save_aggregate("review", "r1", {"n": 1}, expected_revision=0)

    # One UoW updates both plus appends an event -- but the second CAS is stale.
    with pytest.raises(StaleRevision), UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
        uow.save_aggregate("session", "s1", {"n": 2}, expected_revision=1)  # fine
        uow.save_aggregate("review", "r1", {"n": 2}, expected_revision=42)  # stale

    # Nothing survived: not the fine CAS, not the event, not its outbox row.
    assert read_aggregate(store._conn, "session", "s1") == ({"n": 1}, 1)
    assert read_aggregate(store._conn, "review", "r1") == ({"n": 1}, 1)
    assert store.count() == 0
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 0


def test_swallowed_stale_revision_still_rolls_back(store: EventStore, clock) -> None:
    # The caller catches StaleRevision inside the block: the poisoned UoW must
    # roll back regardless -- partial success cannot depend on caller manners.
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"n": 1}, expected_revision=0)
    with UnitOfWork(store, clock) as uow, contextlib.suppress(StaleRevision):
        uow.save_aggregate("session", "s1", {"n": 2}, expected_revision=1)  # applies...
        uow.save_aggregate("session", "s1", {"n": 3}, expected_revision=1)  # ...stale, swallowed
    assert read_aggregate(store._conn, "session", "s1") == ({"n": 1}, 1)  # both rolled back


def test_state_obeys_canonical_discipline(store: EventStore, clock) -> None:
    # Operational state goes through canonical encoding too: floats are refused
    # and the failed write poisons the transaction.
    with pytest.raises(TypeError), UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"score": 0.5}, expected_revision=0)
    assert read_aggregate(store._conn, "session", "s1") is None


def test_save_outside_uow_is_refused(store: EventStore, clock) -> None:
    uow = UnitOfWork(store, clock)  # never entered
    with pytest.raises(KernelError):
        uow.save_aggregate("session", "s1", {"n": 1}, expected_revision=0)
    assert read_aggregate(store._conn, "session", "s1") is None


def test_get_aggregate_reads_inside_the_transaction(store: EventStore, clock) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate("session", "s1", {"n": 1}, expected_revision=0)
        assert uow.get_aggregate("session", "s1") == ({"n": 1}, 1)  # own write visible
        assert uow.get_aggregate("session", "ghost") is None
