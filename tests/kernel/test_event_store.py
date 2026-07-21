"""Event store: monotonic sequence, append-only, atomic UoW commit/rollback
(foundation 2.1, 3.3, 3.7)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import payload_hash
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


def test_append_without_the_write_capability_is_refused(store: EventStore, clock, random_source) -> None:
    # There is no public append. The internal one refuses a missing or wrong
    # token, so nothing outside the owning UoW can write (foundation 2.1).
    now = clock.now().isoformat()
    assert not hasattr(store, "append")
    with pytest.raises(KernelError):
        store._append([_event(clock, random_source)], None, now)
    with pytest.raises(KernelError):
        store._append([_event(clock, random_source)], "not-the-token", now)
    assert store.count() == 0


def test_manual_begin_cannot_claim_or_append(store: EventStore, clock, random_source) -> None:
    # A hand-rolled BEGIN cannot acquire a capability at all (claim refuses a
    # connection already mid-transaction), and a guessed token is refused.
    store._conn.execute("BEGIN;")
    try:
        with pytest.raises(KernelError):
            store._claim()
        with pytest.raises(KernelError):
            store._append([_event(clock, random_source)], "guessed", clock.now().isoformat())
    finally:
        store._conn.execute("ROLLBACK;")
    assert store.count() == 0
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 0


def test_claimed_token_without_transaction_cannot_append(store: EventStore, clock, random_source) -> None:
    # Even a legitimately minted token is useless outside an open transaction.
    token = store._claim()
    try:
        with pytest.raises(KernelError):
            store._append([_event(clock, random_source)], token, clock.now().isoformat())
    finally:
        store._release(token)
    assert store.count() == 0


def test_store_state_never_leaks_an_appendable_credential(store: EventStore, clock, random_source) -> None:
    # The store retains only a one-way digest of the token. Inside a live UoW,
    # stealing everything readable from the store still cannot authorize a write.
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
        stolen = store._txn_owner_digest
        assert stolen is not None
        with pytest.raises(KernelError):
            store._append([_event(clock, random_source)], stolen, clock.now().isoformat())
    assert store.count() == 1  # only the event that went through uow.append
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 1


def test_no_append_path_can_separate_event_from_outbox(store: EventStore, clock, random_source) -> None:
    # The structural invariant: even code that re-implements the UoW protocol by
    # hand (claim -> BEGIN -> _append -> COMMIT) gets the outbox row written in
    # the same transaction -- events without outbox rows cannot exist.
    token = store._claim()
    try:
        store._conn.execute("BEGIN;")
        store._append([_event(clock, random_source)], token, clock.now().isoformat())
        store._conn.execute("COMMIT;")
    finally:
        if store._conn.in_transaction:
            store._conn.execute("ROLLBACK;")
        store._release(token)
    assert store.count() == 1
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 1


def test_stored_payload_is_the_hashed_canonical_snapshot(store: EventStore, clock, random_source) -> None:
    # The bytes persisted for a payload hash to the stored payload_hash: the store
    # hashes and writes one and the same serialization, leaving no window for a
    # concurrent mutation to be hashed as one thing and written as another.
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    row = store._conn.execute("SELECT payload, payload_hash FROM events;").fetchone()
    assert hashlib.sha256(row["payload"].encode("ascii")).hexdigest() == row["payload_hash"]


def test_returned_event_is_rebuilt_from_the_stored_snapshot(store: EventStore, clock, random_source) -> None:
    # The event append() hands back carries the payload AND pinned_versions that
    # were actually stored (rebuilt from the canonical bytes), so it stays
    # self-consistent rather than echoing the caller's mutable objects.
    source = make_event(
        id=new_ulid(clock, random_source),
        type="demo.pinned",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="corr-1",
        pinned_versions={"scoring": "v1"},
        payload={"n": 1},
    )
    with UnitOfWork(store, clock) as uow:
        (returned,) = uow.append([source])
        # Mutate the caller's dicts after the insert: the returned event must not
        # reflect either mutation.
        source.payload["n"] = 999
        source.pinned_versions["scoring"] = "mutated-after-insert"
    assert payload_hash(returned.payload) == returned.payload_hash
    assert returned.payload == {"n": 1}
    assert returned.pinned_versions == {"scoring": "v1"}
    (loaded,) = list(store.read())
    assert returned.payload == loaded.payload
    assert returned.pinned_versions == loaded.pinned_versions


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


def test_probe_on_broken_log_does_not_destroy_real_rows(tmp_path: Path) -> None:
    # A no-op delete trigger means the probe's DELETE actually runs -- but it runs
    # inside the probe's savepoint, so the violation is reported AND the real
    # rows survive. A checker must never damage what it checks.
    conn = connect(tmp_path / "noop2.db")
    migrate(conn)
    store = EventStore(conn)
    try:
        clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
        rnd = SeededRandomSource(7)
        with UnitOfWork(store, clock) as uow:
            uow.append([_event(clock, rnd)])
        conn.execute("DROP TRIGGER events_no_update;")
        conn.execute("DROP TRIGGER events_no_delete;")
        conn.execute("CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT 1; END;")
        conn.execute("CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT 1; END;")
        with pytest.raises(AppendOnlyViolation):
            store.assert_append_only()
        assert store.count() == 1  # the probe's damage was rolled back
        assert not conn.in_transaction
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
