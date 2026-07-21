"""Kernel: the platform foundation (foundation contract 0.2).

Determinism, audit and integrity primitives that every business module builds
on -- injected time and randomness, typed ids, canonical encoding, command and
event envelopes, an append-only SQLite event store, and an atomic Unit of Work.
The kernel holds no business logic: concrete event types and rules belong to the
owning modules (owner matrix in wiki/OPEN.md).

Increments 1-3 are in place: the deterministic event-store core; transactional
outbox delivery, the JSONL derived export, and the integrity check; and the
versioned policy registry with pinning and retention. Deferred to later
increments: the generic correction envelope and reducer, multi-aggregate CAS,
isolate-and-swap projection rebuild for SQLite read-models, and the typer CLI.
"""

from __future__ import annotations

from english_trainer.kernel.check import CheckReport, database_check
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
    NoActivePolicy,
    PinnedPolicyUnavailable,
    StaleRevision,
)
from english_trainer.kernel.export import (
    JsonlExporter,
    export_pending,
    rebuild_export,
)
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.outbox import Consumer, OffsetStore, deliver
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.replay import fold, iter_events, replay
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import CachedResult, UnitOfWork

__all__ = [
    "KNOWN_KINDS",
    "AppendOnlyViolation",
    "CachedResult",
    "CheckReport",
    "Clock",
    "Command",
    "Consumer",
    "DomainEvent",
    "EventStore",
    "FixedClock",
    "IdempotencyConflict",
    "JsonlExporter",
    "KernelError",
    "NoActivePolicy",
    "OffsetStore",
    "PinnedPolicyUnavailable",
    "PolicyRegistry",
    "RandomSource",
    "SeededRandomSource",
    "StaleRevision",
    "SystemClock",
    "SystemRandom",
    "UnitOfWork",
    "canonical_json",
    "connect",
    "database_check",
    "deliver",
    "export_pending",
    "fold",
    "iter_events",
    "make_command",
    "make_event",
    "migrate",
    "new_ulid",
    "payload_hash",
    "rebuild_export",
    "replay",
]
