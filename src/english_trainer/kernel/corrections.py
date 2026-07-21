"""Generic correction envelope and correction-aware replay (foundation 3.6).

The event log is append-only: a recorded fact is never rewritten or deleted.
When a fact turns out to be wrong, the fix is a **new** event -- a correction --
that references the original by id and declares how it relates to it:

- ``replacement``: the correction's effect stands **instead of** the original's.
  Replay suppresses the original (and any superseded earlier replacements) and
  applies the correction at its own position in ``sequence``. The log still
  shows both facts; only the *effect* is single-counted.
- ``compensation``: the original stays applied and the correction applies too,
  as a counter-entry (how a ledger fixes itself). Nothing is suppressed.

The kernel owns only this envelope and the resolution rule; what a correction
*means* for scores or sessions belongs to the owning modules (0.4/0.5,
OPEN-11). Safety-overlay corrections must carry **both** policy versions --
``original_pinned_versions`` (what the corrected decision was pinned to) and
``active_safety_version`` (the active safety policy that triggered the
override) -- so audit and replay can explain the override (foundation 3.6,
rereview C-1).

Resolution is deterministic and single-pass over the full log in ``sequence``
order: the same events always produce the same effective stream, so a reducer
folded over it never counts both the original and the corrected effect, no
matter how long the correction chain is.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.replay import fold

# Reserved payload key. A correction event carries its metadata here, next to
# the module's own business payload keys.
CORRECTION_KEY = "correction"

_SEMANTICS = ("replacement", "compensation")


@dataclass(frozen=True)
class Correction:
    """Parsed correction metadata of an event (the ``correction`` payload block)."""

    corrects_event_id: str
    semantics: str
    original_pinned_versions: dict[str, str] | None = None
    active_safety_version: str | None = None


def make_correction_event(
    *,
    id: str,
    type: str,
    occurred_at: datetime,
    actor: str,
    correlation_id: str,
    corrects_event_id: str,
    semantics: str,
    payload: dict[str, Any] | None = None,
    original_pinned_versions: dict[str, str] | None = None,
    active_safety_version: str | None = None,
    provider: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    pinned_versions: dict[str, str] | None = None,
) -> DomainEvent:
    """Build a correction event: a normal ``DomainEvent`` whose payload carries
    the correction block under :data:`CORRECTION_KEY`.

    ``payload`` is the module's corrective business payload; it may not use the
    reserved key itself. Safety-overlay corrections must pass **both**
    ``original_pinned_versions`` and ``active_safety_version`` -- one without
    the other is refused, because an override that cannot name both sides is
    unexplainable to audit (foundation 3.6).
    """
    if semantics not in _SEMANTICS:
        raise KernelError(f"unknown correction semantics {semantics!r}; expected one of {_SEMANTICS}")
    payload = dict(payload or {})
    if CORRECTION_KEY in payload:
        raise KernelError(f"payload key {CORRECTION_KEY!r} is reserved for the correction block")
    if (original_pinned_versions is None) != (active_safety_version is None):
        raise KernelError(
            "a safety correction must carry BOTH original_pinned_versions and "
            "active_safety_version, or neither"
        )
    block: dict[str, Any] = {"corrects_event_id": corrects_event_id, "semantics": semantics}
    if original_pinned_versions is not None:
        block["original_pinned_versions"] = dict(original_pinned_versions)
        block["active_safety_version"] = active_safety_version
    payload[CORRECTION_KEY] = block
    return make_event(
        id=id,
        type=type,
        occurred_at=occurred_at,
        actor=actor,
        correlation_id=correlation_id,
        payload=payload,
        provider=provider,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        pinned_versions=pinned_versions,
    )


def correction_of(event: DomainEvent) -> Correction | None:
    """Return the event's correction metadata, or ``None`` for a plain event.

    A present-but-malformed block is a hard error, not ``None``: silently
    treating a broken correction as a plain event would double-count the effect
    it was meant to replace.
    """
    block = event.payload.get(CORRECTION_KEY)
    if block is None:
        return None
    if not isinstance(block, dict):
        raise KernelError(f"event {event.id}: correction block must be an object")
    allowed = {"corrects_event_id", "semantics", "original_pinned_versions", "active_safety_version"}
    unknown = set(block) - allowed
    if unknown:
        raise KernelError(f"event {event.id}: unknown correction keys {sorted(unknown)}")
    target = block.get("corrects_event_id")
    semantics = block.get("semantics")
    if not isinstance(target, str) or not target:
        raise KernelError(f"event {event.id}: correction requires a corrects_event_id")
    if semantics not in _SEMANTICS:
        raise KernelError(f"event {event.id}: unknown correction semantics {semantics!r}")
    pins = block.get("original_pinned_versions")
    safety = block.get("active_safety_version")
    if (pins is None) != (safety is None):
        raise KernelError(
            f"event {event.id}: a safety correction must carry both original_pinned_versions "
            "and active_safety_version, or neither"
        )
    if pins is not None and not isinstance(pins, dict):
        raise KernelError(f"event {event.id}: original_pinned_versions must be an object")
    if safety is not None and not isinstance(safety, str):
        raise KernelError(f"event {event.id}: active_safety_version must be a string")
    return Correction(
        corrects_event_id=target,
        semantics=str(semantics),
        original_pinned_versions=dict(pins) if pins is not None else None,
        active_safety_version=safety,
    )


def resolve_corrections(events: Iterable[DomainEvent]) -> list[DomainEvent]:
    """Return the **effective** stream: events in ``sequence`` order with every
    replaced effect suppressed exactly once.

    Rules (deterministic; the same log always resolves the same way):

    - a ``replacement`` suppresses its target; the correction itself applies at
      its own ``sequence`` position;
    - several replacements of the same target supersede each other -- only the
      latest applies, earlier ones are suppressed with the target;
    - chains resolve transitively: if B replaces A and C replaces B, only C's
      effect survives;
    - ``compensation`` suppresses nothing;
    - a correction must target an **earlier, existing** event of the stream.
      A missing or forward target is corrupted data and a hard error -- this
      resolver is for full-log replay, where every target must be present.
    """
    ordered = sorted(events, key=lambda event: event.sequence or 0)
    by_id: dict[str, DomainEvent] = {}
    for event in ordered:
        if event.sequence is None:
            raise KernelError(f"event {event.id} has no sequence; resolve over a persisted stream")
        by_id[event.id] = event

    suppressed: set[str] = set()  # event ids whose effect is replaced
    replaced_by: dict[str, DomainEvent] = {}  # target id -> latest replacement so far
    for event in ordered:
        correction = correction_of(event)
        if correction is None or correction.semantics != "replacement":
            continue
        target = by_id.get(correction.corrects_event_id)
        if target is None:
            raise KernelError(f"correction {event.id} targets unknown event {correction.corrects_event_id!r}")
        assert target.sequence is not None and event.sequence is not None
        if target.sequence >= event.sequence:
            raise KernelError(
                f"correction {event.id} must target an earlier event, "
                f"not {correction.corrects_event_id!r} at sequence {target.sequence}"
            )
        suppressed.add(target.id)
        earlier = replaced_by.get(target.id)
        if earlier is not None:
            # A later replacement of the same target supersedes the earlier one:
            # exactly one corrected effect may survive.
            suppressed.add(earlier.id)
        replaced_by[target.id] = event

    return [event for event in ordered if event.id not in suppressed]


def fold_corrected[State](
    events: Iterable[DomainEvent],
    reducer: Callable[[State, DomainEvent], State],
    initial: State,
) -> State:
    """Fold ``reducer`` over the effective stream (foundation 3.6, 5).

    The guarantee the contract names: replay never counts both an original and
    its corrected effect, and the result is idempotent under correction chains
    -- correcting a correction changes *which* single effect applies, never how
    many times.
    """
    return fold(resolve_corrections(events), reducer, initial)
