"""Injected time and randomness (foundation contract 3.2).

Domain code never touches the system clock or ``random`` directly -- only these
injected sources. That is what makes replay deterministic: a test pins a
``FixedClock`` and a ``SeededRandomSource`` and gets byte-identical output, and
a future architectural check (foundation 8) forbids the direct calls.

All instants are timezone-aware UTC. A local calendar date is derived from the
learner's timezone elsewhere (learning-model 7-8), never stored as the truth.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from random import Random
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Source of the current instant. Always returns UTC-aware datetimes."""

    def now(self) -> datetime: ...


@runtime_checkable
class RandomSource(Protocol):
    """Source of randomness for ID generation and seeded assessment forms."""

    def token_bytes(self, n: int) -> bytes: ...

    def randbelow(self, upper: int) -> int: ...


class SystemClock:
    """Wall-clock UTC. The only place the real clock is read in production."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock frozen at ``instant`` (tests). ``advance`` steps it forward."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware instant")
        self._instant = instant.astimezone(UTC)

    def now(self) -> datetime:
        return self._instant

    def advance(self, *, seconds: float) -> None:
        from datetime import timedelta

        self._instant = self._instant + timedelta(seconds=seconds)


class SystemRandom:
    """Cryptographic randomness. The production default; not reproducible."""

    def token_bytes(self, n: int) -> bytes:
        return secrets.token_bytes(n)

    def randbelow(self, upper: int) -> int:
        return secrets.randbelow(upper)


class SeededRandomSource:
    """Deterministic randomness from a fixed seed (tests, seeded placement).

    Backed by ``random.Random`` so the same seed reproduces the same stream
    regardless of the process hash seed (foundation 5).
    """

    def __init__(self, seed: int | str | bytes) -> None:
        self._rng = Random(seed)

    def token_bytes(self, n: int) -> bytes:
        return self._rng.randbytes(n)

    def randbelow(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper must be positive")
        return self._rng.randrange(upper)
