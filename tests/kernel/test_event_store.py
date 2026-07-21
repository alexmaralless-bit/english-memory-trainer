"""Event store: monotonic sequence, append-only, atomic UoW commit/rollback
(foundation 2.1, 3.3, 3.7)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import AppendOnlyViolation, KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
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


def test_manual_begin_cannot_impersonate_a_uow(store: EventStore, clock, random_source) -> None:
    # A hand-rolled BEGIN sets in_transaction, but not the UoW capability, so it
    # cannot smuggle an event past append() without an outbox row.
    store._conn.execute("BEGIN;")
    try:
        with pytest.raises(KernelError):
            store.append([_event(clock, random_source)])
    finally:
        store._conn.execute("ROLLBACK;")
    assert store.count() == 0
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 0


def test_stored_payload_is_the_hashed_canonical_snapshot(store: EventStore, clock, random_source) -> None:
    # The bytes persisted for a payload hash to the stored payload_hash: the store
    # hashes and writes one and the same serialization, leaving no window for a
    # concurrent mutation to be hashed as one thing and written as another.
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    row = store._conn.execute("SELECT payload, payload_hash FROM events;").fetchone()
    assert hashlib.sha256(row["payload"].encode("ascii")).hexdigest() == row["payload_hash"]


def test_mutated_payload_is_refused_at_the_store_boundary(store: EventStore, clock, random_source) -> None:
    ev = _event(clock, random_source)
    ev.payload["kind"] = "tampered"  # the envelope is frozen; its payload dict is not
    with pytest.raises(KernelError), UnitOfWork(store, clock) as uow:
        uow.append([ev])
    assert store.count() == 0  # the mismatched event never entered the log


def test_assert_append_only_passes_on_an_empty_log(store: EventStore) -> None:
    # The runtime probe (savepoint + throwaway row) proves the guards abort even
    # when the log is empty, then rolls the probe back.
    assert store.count() == 0
    store.assert_append_only()
    assert store.count() == 0  # the probe row did not survive


def test_assert_append_only_rejects_noop_triggers(tmp_path: Path) -> None:
    # Same trigger names, but no-op bodies: the old name-only check passed this;
    # the runtime probe must catch that update/delete are not actually refused.
    conn = connect(tmp_path / "noop.db")
    migrate(conn)
    store = EventStore(conn)
    try:
        conn.execute("DROP TRIGGER events_no_update;")
        conn.execute("DROP TRIGGER events_no_delete;")
        conn.execute("CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT 1; END;")
        conn.execute("CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT 1; END;")
        with pytest.raises(AppendOnlyViolation):
            store.assert_append_only()
    finally:
        conn.close()


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
