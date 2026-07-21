"""Kernel: the platform foundation (foundation contract 0.2).

Determinism, audit and integrity primitives that every business module builds
on -- injected time and randomness, typed ids, canonical encoding, command and
event envelopes, an append-only SQLite event store, and an atomic Unit of Work.
The kernel holds no business logic: concrete event types and rules belong to the
owning modules (owner matrix in wiki/OPEN.md).

This is increment 1 (deterministic event-store core). Deferred to later
increments: JSONL export and outbox delivery, the versioned policy registry,
multi-aggregate CAS, the projection/rebuild framework, and the CLI surface.
"""

from __future__ import annotations

from english_trainer.kernel.clock import (
    Clock,
    FixedClock,
    RandomSource,
    SeededRandomSource,
    SystemClock,
    SystemRandom,
)
from english_trainer.kernel.encoding import canonical_json, payload_hash
from english_trainer.kernel.envelopes import Command, DomainEvent, make_command, make_event
from english_trainer.kernel.errors import (
    AppendOnlyViolation,
    IdempotencyConflict,
    KernelError,
    StaleRevision,
)
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.replay import fold, iter_events, replay
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import CachedResult, UnitOfWork

__all__ = [
    "AppendOnlyViolation",
    "CachedResult",
    "Clock",
    "Command",
    "DomainEvent",
    "EventStore",
    "FixedClock",
    "IdempotencyConflict",
    "KernelError",
    "RandomSource",
    "SeededRandomSource",
    "StaleRevision",
    "SystemClock",
    "SystemRandom",
    "UnitOfWork",
    "canonical_json",
    "connect",
    "fold",
    "iter_events",
    "make_command",
    "make_event",
    "migrate",
    "new_ulid",
    "payload_hash",
    "replay",
]
