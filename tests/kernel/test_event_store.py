"""Event store: monotonic sequence, append-only, atomic UoW commit/rollback
(foundation 2.1, 3.3, 3.7)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


def _event(clock: FixedClock, rnd: SeededRandomSource, kind: str = "demo.happened"):
    return make_event(
        id=new_ulid(clock, rnd),
        type=kind,
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="corr-1",
        payload={"kind": kind},
    )


def test_sequence_is_monotonic(store: EventStore, clock, random_source) -> None:
    with UnitOfWork(store, clock) as uow:
        stored = uow.append([_event(clock, random_source) for _ in range(5)])
    seqs = [e.sequence for e in stored]
    assert seqs == [1, 2, 3, 4, 5]
    # And the stored order matches read order.
    assert [e.sequence for e in store.read()] == seqs


def test_append_writes_matching_outbox_row(store: EventStore, clock, random_source) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    row = store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()
    assert row["n"] == 1


def test_append_only_enforced(store: EventStore, clock, random_source) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    store.assert_append_only()  # raises if update/delete are not refused
    assert store.count() == 1  # the probe changed nothing


def test_rollback_leaves_no_trace(store: EventStore, clock, random_source) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    assert store.count() == 1

    try:
        with UnitOfWork(store, clock) as uow:
            uow.append([_event(clock, random_source)])
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    # Neither the event nor its outbox row survived the rollback.
    assert store.count() == 1
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 1


def test_append_outside_a_transaction_is_refused(store: EventStore, clock, random_source) -> None:
    # A direct append with no open UoW would write an event without its outbox
    # row and operational state -- the boundary refuses it (foundation 2.1).
    with pytest.raises(KernelError):
        store.append([_event(clock, random_source)])
    assert store.count() == 0


def test_mutated_payload_is_refused_at_the_store_boundary(store: EventStore, clock, random_source) -> None:
    ev = _event(clock, random_source)
    ev.payload["kind"] = "tampered"  # the envelope is frozen; its payload dict is not
    with pytest.raises(KernelError), UnitOfWork(store, clock) as uow:
        uow.append([ev])
    assert store.count() == 0  # the mismatched event never entered the log


def test_assert_append_only_passes_on_an_empty_log(store: EventStore) -> None:
    # Row-level BEFORE triggers cannot fire without a row; the schema-level check
    # must still confirm the guards exist, so an empty log is not a false pass.
    assert store.count() == 0
    store.assert_append_only()


def test_event_read_roundtrips_payload(store: EventStore, clock, random_source) -> None:
    ev = make_event(
        id=new_ulid(clock, random_source),
        type="demo.rich",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="corr-1",
        pinned_versions={"scoring": "3", "curriculum": "7"},
        payload={"nested": {"a": [1, 2, 3]}, "s": "вот"},
    )
    with UnitOfWork(store, clock) as uow:
        uow.append([ev])
    (loaded,) = list(store.read())
    assert loaded.payload == ev.payload
    assert loaded.pinned_versions == ev.pinned_versions
    assert loaded.payload_hash == ev.payload_hash  # re-validates on load
