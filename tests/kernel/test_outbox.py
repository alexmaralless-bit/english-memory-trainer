"""Outbox delivery: in-order, checkpointed per consumer, idempotent on
redelivery, and resumable after a failure (foundation 3.7)."""

from __future__ import annotations

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.outbox import OffsetStore, deliver
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


def _append(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, n: int, start: int = 0) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=f"e{start + i}",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="c",
                    payload={"i": start + i},
                )
                for i in range(n)
            ]
        )


class ListConsumer:
    """Records the sequence of every event it applies (order + idempotency probe)."""

    def __init__(self, name: str = "proj") -> None:
        self.name = name
        self.seen: list[int] = []

    def apply(self, event: DomainEvent) -> None:
        assert event.sequence is not None
        self.seen.append(event.sequence)


class FailAtConsumer(ListConsumer):
    def __init__(self, fail_sequence: int, name: str = "proj") -> None:
        super().__init__(name)
        self._fail = fail_sequence

    def apply(self, event: DomainEvent) -> None:
        if event.sequence == self._fail:
            raise RuntimeError("boom")
        super().apply(event)


def test_delivers_in_sequence_order(store, clock, random_source) -> None:
    _append(store, clock, random_source, 4)
    consumer = ListConsumer()
    assert deliver(store, consumer, clock) == 4
    assert consumer.seen == [1, 2, 3, 4]


def test_redelivery_is_idempotent(store, clock, random_source) -> None:
    _append(store, clock, random_source, 3)
    consumer = ListConsumer()
    assert deliver(store, consumer, clock) == 3
    # The offset gates the second call: nothing new, apply is not called again.
    assert deliver(store, consumer, clock) == 0
    assert consumer.seen == [1, 2, 3]


def test_incremental_delivery_only_touches_new_events(store, clock, random_source) -> None:
    _append(store, clock, random_source, 2)
    consumer = ListConsumer()
    deliver(store, consumer, clock)
    _append(store, clock, random_source, 2, start=2)
    assert deliver(store, consumer, clock) == 2
    assert consumer.seen == [1, 2, 3, 4]


def test_consumers_track_offsets_independently(store, clock, random_source) -> None:
    _append(store, clock, random_source, 3)
    ahead, behind = ListConsumer("ahead"), ListConsumer("behind")
    deliver(store, ahead, clock)  # 'ahead' catches up to 3
    _append(store, clock, random_source, 1, start=3)  # sequence 4
    assert deliver(store, behind, clock) == 4  # 'behind' sees all four
    assert deliver(store, ahead, clock) == 1  # 'ahead' only the new one
    assert ahead.seen == [1, 2, 3, 4]
    assert behind.seen == [1, 2, 3, 4]


def test_failed_delivery_is_resumable_not_lost(store, clock, random_source) -> None:
    _append(store, clock, random_source, 4)
    failing = FailAtConsumer(3)
    with pytest.raises(RuntimeError):
        deliver(store, failing, clock)
    # 1 and 2 committed with their offset; 3 rolled back. The mark sits at 2.
    assert failing.seen == [1, 2]
    assert OffsetStore(store._conn).get("proj") == 2
    resumed = ListConsumer("proj")  # same offset row
    assert deliver(store, resumed, clock) == 2
    assert resumed.seen == [3, 4]


def test_offset_never_rewinds(store, clock) -> None:
    offsets = OffsetStore(store._conn)
    now = clock.now().isoformat()
    offsets.advance("x", 5, now)
    offsets.advance("x", 3, now)  # lower sequence must be ignored
    assert offsets.get("x") == 5


def test_delivery_reads_from_the_outbox_not_the_event_table(store, clock, random_source) -> None:
    # The transactional-outbox boundary is the outbox: an event whose outbox row
    # is gone is not delivered (foundation 3.7).
    _append(store, clock, random_source, 2)
    store._conn.execute("DELETE FROM outbox WHERE sequence = 2;")
    consumer = ListConsumer()
    assert deliver(store, consumer, clock) == 1
    assert consumer.seen == [1]


def test_offset_recheck_inside_the_transaction_prevents_double_apply(store, clock, random_source) -> None:
    # Simulate a competing deliverer finishing first: the consumer bumps the
    # offset to the end while applying event 1. The remaining materialized tail
    # must be skipped -- the offset is re-read inside each event's transaction,
    # not trusted from the stale snapshot taken before delivery began.
    _append(store, clock, random_source, 4)

    class RacingConsumer(ListConsumer):
        def apply(self, event) -> None:
            super().apply(event)
            OffsetStore(store._conn).set(self.name, 4, "t")  # a rival caught up

    racing = RacingConsumer()
    assert deliver(store, racing, clock) == 1
    assert racing.seen == [1]  # 2..4 skipped: already applied per the fresh offset


def test_base_exception_during_delivery_rolls_back(store, clock, random_source) -> None:
    # KeyboardInterrupt mid-delivery must not leave an open transaction, and the
    # committed prefix must survive so delivery is resumable.
    _append(store, clock, random_source, 3)

    class Boom(ListConsumer):
        def apply(self, event) -> None:
            if event.sequence == 2:
                raise KeyboardInterrupt("signal mid-delivery")
            super().apply(event)

    boom = Boom()
    with pytest.raises(KeyboardInterrupt):
        deliver(store, boom, clock)
    assert not store._conn.in_transaction
    assert OffsetStore(store._conn).get("proj") == 1  # event 1 committed, 2 rolled back
    resumed = ListConsumer("proj")
    assert deliver(store, resumed, clock) == 2
    assert resumed.seen == [2, 3]
