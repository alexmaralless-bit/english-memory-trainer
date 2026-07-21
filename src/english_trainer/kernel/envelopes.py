"""Command and DomainEvent envelopes (foundation contract 3.3).

Every mutation enters as a ``Command`` and every fact is recorded as a
``DomainEvent``, both wrapped in an envelope that carries the fields determinism
and audit need. The kernel defines only the envelope; the concrete event *types*
belong to the owning modules (foundation 4), so ``type`` is a free string here.

Validation enforces two invariants the rest of the kernel relies on: instants
are timezone-aware UTC, and ``payload_hash`` actually matches the payload -- a
mismatch means the payload was mutated after hashing, which would break
idempotency and replay.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from english_trainer.kernel.encoding import payload_hash


class Envelope(BaseModel):
    """Fields shared by every command and event (foundation 3.3).

    Frozen and closed: envelopes are immutable facts, and an unexpected field is
    a mistake, not something to silently accept.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: str
    occurred_at: datetime
    actor: str
    provider: str | None = None
    correlation_id: str
    causation_id: str | None = None
    idempotency_key: str | None = None
    pinned_versions: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        # Must be timezone-aware -- a naive instant has no defined moment. An
        # aware instant at any offset names a real moment, so we accept it and
        # normalize to UTC: storing the offset would let two envelopes for the
        # same instant differ in bytes (e.g. 12:00+02:00 vs 10:00Z) and break the
        # single-representation rule replay depends on (foundation 5).
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _check_payload_hash(self) -> Envelope:
        expected = payload_hash(self.payload)
        if self.payload_hash != expected:
            raise ValueError(
                f"payload_hash mismatch: envelope carries {self.payload_hash!r}, "
                f"canonical payload hashes to {expected!r}"
            )
        return self


class Command(Envelope):
    """An intent to mutate state. Carries an ``idempotency_key`` when mutating."""


class DomainEvent(Envelope):
    """A recorded fact. ``sequence`` is the canonical total order (foundation 3.3).

    ``sequence`` is assigned by the event store on append, so it is ``None``
    until then; replay applies events strictly in ``sequence`` order.
    """

    sequence: int | None = None


def make_command(
    *,
    id: str,
    type: str,
    occurred_at: datetime,
    actor: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
    provider: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    pinned_versions: dict[str, str] | None = None,
) -> Command:
    """Build a ``Command`` with the ``payload_hash`` computed for you."""
    payload = payload or {}
    return Command(
        id=id,
        type=type,
        occurred_at=occurred_at,
        actor=actor,
        provider=provider,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        pinned_versions=pinned_versions or {},
        payload=payload,
        payload_hash=payload_hash(payload),
    )


def make_event(
    *,
    id: str,
    type: str,
    occurred_at: datetime,
    actor: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
    provider: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    pinned_versions: dict[str, str] | None = None,
) -> DomainEvent:
    """Build a ``DomainEvent`` (no ``sequence`` yet) with its ``payload_hash``."""
    payload = payload or {}
    return DomainEvent(
        id=id,
        type=type,
        occurred_at=occurred_at,
        actor=actor,
        provider=provider,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        pinned_versions=pinned_versions or {},
        payload=payload,
        payload_hash=payload_hash(payload),
    )
