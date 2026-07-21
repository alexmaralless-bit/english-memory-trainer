"""Injected time/randomness are deterministic, and ULID-like ids sort by time
(foundation 3.1, 3.2, 5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.ids import is_ulid, new_ulid


def test_fixed_clock_requires_tz() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 7, 21, 12, 0, 0))  # naive


def test_fixed_clock_advances() -> None:
    clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
    t0 = clock.now()
    clock.advance(seconds=90)
    assert (clock.now() - t0).total_seconds() == 90
    assert clock.now().tzinfo is not None


def test_seeded_random_is_reproducible() -> None:
    a = SeededRandomSource(42)
    b = SeededRandomSource(42)
    assert [a.token_bytes(8) for _ in range(5)] == [b.token_bytes(8) for _ in range(5)]
    assert [a.randbelow(1000) for _ in range(5)] == [b.randbelow(1000) for _ in range(5)]


def test_ulids_sort_by_time() -> None:
    clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
    rnd = SeededRandomSource(1)
    ids = []
    for _ in range(20):
        ids.append(new_ulid(clock, rnd))
        clock.advance(seconds=1)
    assert ids == sorted(ids)
    assert all(is_ulid(i) and len(i) == 26 for i in ids)


def test_ulids_unique_within_same_millisecond() -> None:
    clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
    rnd = SeededRandomSource(7)
    ids = {new_ulid(clock, rnd) for _ in range(1000)}  # clock frozen -> same ms
    assert len(ids) == 1000  # 80 random bits make collisions negligible


def test_same_seed_reproduces_the_same_id_stream() -> None:
    def stream(seed: int) -> list[str]:
        clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
        rnd = SeededRandomSource(seed)
        return [new_ulid(clock, rnd) for _ in range(10)]

    assert stream(123) == stream(123)
