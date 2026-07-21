"""UnitOfWork lifecycle guards: a UoW is single-use, writes only inside its
open block, and never carries pending outbox state between transactions
(foundation 3.7)."""

from __future__ import annotations

import contextlib

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


class _BeginThenSignalConn:
    """Wraps a real connection; the first BEGIN really opens the transaction and
    then raises -- like an async signal (KeyboardInterrupt) arriving the instant
    SQLite returns. Everything else passes straight through."""

    def __init__(self, real) -> None:
        self._real = real
        self._begins = 0

    def execute(self, sql, *args):
        if sql.strip().upper().startswith("BEGIN"):
            self._begins += 1
            if self._begins == 1:
                self._real.execute(sql, *args)  # the transaction really opens...
                raise KeyboardInterrupt("signal right after BEGIN")  # ...then the signal hits
        return self._real.execute(sql, *args)

    @property
    def in_transaction(self):
        return self._real.in_transaction


class _SignalOnCommitConn:
    """Wraps a real connection; COMMIT raises a BaseException instead of running
    -- the transaction stays open and the UoW must close it. Everything else
    passes straight through."""

    def __init__(self, real) -> None:
        self._real = real

    def execute(self, sql, *args):
        if sql.strip().upper().startswith("COMMIT"):
            raise KeyboardInterrupt("signal during commit")
        return self._real.execute(sql, *args)

    @property
    def in_transaction(self):
        return self._real.in_transaction


class _RollbackFailsConn:
    """Wraps a real connection; ROLLBACK itself raises (a genuinely broken
    connection). Used to prove the claim is still released."""

    def __init__(self, real) -> None:
        self._real = real
        self._begins = 0

    def execute(self, sql, *args):
        upper = sql.strip().upper()
        if upper.startswith("BEGIN"):
            self._begins += 1
            if self._begins == 1:
                self._real.execute(sql, *args)
                raise KeyboardInterrupt("signal right after BEGIN")
        if upper.startswith("ROLLBACK"):
            raise RuntimeError("rollback failed")
        return self._real.execute(sql, *args)

    @property
    def in_transaction(self):
        return self._real.in_transaction


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


def test_caught_stale_hash_fails_fast_and_rolls_back(store: EventStore, clock, random_source) -> None:
    # A batch whose second event has a stale hash: the handler swallows the error
    # and exits the block normally. All-or-nothing must not depend on that -- the
    # UoW is poisoned by the failed write and rolls back regardless.
    good = _event(clock, random_source)
    bad = _event(clock, random_source)
    bad.payload["a"] = 999  # frozen model, mutable payload -> hash no longer matches
    with UnitOfWork(store, clock) as uow, contextlib.suppress(KernelError):
        uow.append([good, bad])  # the swallowed error must not let the block commit
    assert store.count() == 0
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 0


def test_caught_partial_insert_rolls_back(store: EventStore, clock, random_source) -> None:
    # A batch that fails *mid-insert* (second event reuses the first's id, so the
    # UNIQUE constraint aborts it after the first row is already in the
    # transaction). The handler swallows the error; the poisoned UoW must still
    # roll the partial write back.
    first = _event(clock, random_source)
    clash = make_event(
        id=first.id,  # same id -> UNIQUE(id) violation on the second insert
        type="demo.clash",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="corr-1",
        payload={"a": 2},
    )
    with UnitOfWork(store, clock) as uow, contextlib.suppress(Exception):
        uow.append([first, clash])  # first inserts, clash aborts on UNIQUE(id)
    assert store.count() == 0  # the first, already-inserted row was rolled back
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 0


def test_partial_begin_does_not_leak_an_open_transaction(store: EventStore, clock, random_source) -> None:
    # If BEGIN opens the transaction and then the enter is interrupted, the UoW
    # must roll that transaction back and release the store -- not leave it open
    # for the next BEGIN to trip over.
    real = store._conn
    store._conn = _BeginThenSignalConn(real)  # type: ignore[assignment]
    failed = UnitOfWork(store, clock)
    with pytest.raises(KeyboardInterrupt):
        failed.__enter__()
    assert not real.in_transaction  # the half-opened transaction was rolled back

    store._conn = real  # restore a direct connection for the follow-up
    # The store was released, so a fresh UoW claims and commits cleanly.
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    assert store.count() == 1


def test_base_exception_in_commit_path_rolls_back(store: EventStore, clock, random_source) -> None:
    # KeyboardInterrupt (a BaseException) raised while committing must still roll
    # back and leave no open transaction -- "any failure" means any.
    real = store._conn
    store._conn = _SignalOnCommitConn(real)  # type: ignore[assignment]
    try:
        with pytest.raises(KeyboardInterrupt), UnitOfWork(store, clock) as uow:
            uow.append([_event(clock, random_source)])
    finally:
        store._conn = real
    assert store.count() == 0
    assert not real.in_transaction  # transaction was rolled back, not left open
    # The store is released, so a fresh UoW can still claim and commit.
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    assert store.count() == 1


def test_failed_rollback_in_enter_still_releases_the_claim(store: EventStore, clock, random_source) -> None:
    # Worst case: BEGIN opens the transaction, the signal hits, and the recovery
    # ROLLBACK itself fails. The connection is genuinely broken -- but the claim
    # must still be released, so the store is not owner-locked forever.
    real = store._conn
    store._conn = _RollbackFailsConn(real)  # type: ignore[assignment]
    failed = UnitOfWork(store, clock)
    with pytest.raises(RuntimeError, match="rollback failed"):
        failed.__enter__()
    assert store._txn_owner_digest is None  # claim released despite the failed rollback

    # Clean the connection up out-of-band (the UoW could not) and prove a fresh
    # UoW can claim and work.
    store._conn = real
    if real.in_transaction:
        real.execute("ROLLBACK;")
    with UnitOfWork(store, clock) as uow:
        uow.append([_event(clock, random_source)])
    assert store.count() == 1
