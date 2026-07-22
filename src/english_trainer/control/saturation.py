"""Saturation state and recurring-error detection (control 4.6, 4.5; roadmap 2.8b).

The engine measures *its own* over-drilling. ``SaturationState`` is keyed
``(target_ref, dimension)`` [RR2-13] -- keying by target alone would let frequent
recognition checks drown out weak production of the same target -- and is built
by a deterministic fold over events that already exist:

- ``STEP_PRESENTED`` -- one exposure per ``(target_ref, dimension)`` in
  ``targets[]``, with its ``context_id``; a ``transfer_task`` delivery records
  the transfer-check instant (control 4.6: exposure and saturation are counted
  from delivery to the tutor, not from a screen the engine never sees);
- ``EVIDENCE_ADDED`` / ``REVIEW_OUTCOME`` -- an independent success advances the
  streak, a failure or a scaffolded (hinted) success breaks it, and
  ``INSUFFICIENT_EVIDENCE`` is neutral (excluded, matching the calibration rule
  in control 4.10 -- a five-value outcome is never silently coerced to zero).

The reducer is clock-free: the exposure window is measured in *sessions* (a
running ``session.started`` count, the same session clock signals.py uses), so
two folds over the same log produce byte-identical state. Wall time enters only
in :func:`is_saturated`, where the transfer-staleness branch compares ``now``
against ``last_transfer_check_at`` in whole seconds (``timedelta`` floor
division -- no IEEE float on the decision path).

``ERROR_OBSERVED`` is emitted by evidence's observed-record path and consumed
by :func:`recurring_error_keys`.

The live wiring that feeds this state from lessons into ``classify``/``compose``
at composition time is DEFERRED (lessons domain, a later pass): these are pure
functions, ready to be called, exactly as 2.8a deferred its signal wiring.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from english_trainer.kernel.envelopes import DomainEvent

# Consumed event contracts. String literals on purpose: events are the
# cross-module interface, and importing lessons/evidence here would invert the
# dependency rule (control depends on kernel only). These mirror the names the
# owning modules publish (evidence attempts.py / reviews.py, lessons sessions).
EVENT_SESSION_STARTED = "session.started"
EVENT_STEP_PRESENTED = "session.step_presented"
EVENT_EVIDENCE_ADDED = "evidence.added"
EVENT_REVIEW_OUTCOME = "review.outcome"
# Published by evidence.observed. The literal preserves the event boundary:
# control may not import the evidence package.
EVENT_ERROR_OBSERVED = "evidence.error_observed"

Key = tuple[str, str]

_TRANSFER_STEP_TYPE = "transfer_task"

# Review-outcome markings (control 4.10): a five-value outcome, not a bool.
_SUCCESS_OUTCOMES = frozenset({"CONFIRMED", "PROGRESS", "RECOVERED"})
_FAILURE_OUTCOMES = frozenset({"REGRESSION"})
# INSUFFICIENT_EVIDENCE (and any unknown) -> neutral: it never touches the streak.


@dataclass(frozen=True)
class SaturationState:
    """Per-``(target_ref, dimension)`` over-exposure signals (control 4.6, §2).

    - ``exposures_in_window`` -- deliveries in the last ``exposure_window_sessions``
      sessions (the name is literal: it is windowed);
    - ``consecutive_independent_successes`` -- the current run of independent
      successes, reset by any failure or scaffolded success;
    - ``distinct_contexts`` -- distinct ``context_id`` values the pair has ever
      been delivered in (breadth of practice, all-time);
    - ``last_transfer_check_at`` -- the most recent ``transfer_task`` delivery
      instant (canonical UTC ISO string), or ``None`` if transfer was never
      checked.
    """

    exposures_in_window: int = 0
    consecutive_independent_successes: int = 0
    distinct_contexts: int = 0
    last_transfer_check_at: str | None = None


def _seq(event: DomainEvent) -> int:
    """Canonical order key: the store's ``sequence`` (``None`` sorts first)."""
    return event.sequence if event.sequence is not None else 0


def target_pairs(payload: dict[str, Any]) -> list[Key]:
    """The ``(target_ref, dimension)`` pairs of a ``STEP_PRESENTED`` (control 4.6).

    A pair needs both fields; a target-less choice contributes none, and a
    dimension-less pair is skipped (saturation is per-dimension by contract).
    """
    out: list[Key] = []
    for target in payload.get("targets") or []:
        ref, dim = target.get("target_ref"), target.get("dimension")
        if ref is not None and dim is not None:
            out.append((str(ref), str(dim)))
    return out


def _evidence_pairs(payload: dict[str, Any]) -> list[Key]:
    """The pairs an evidence/outcome/error event pertains to, deduped in order.

    Handles all three published shapes: ``REVIEW_OUTCOME``/``ERROR_OBSERVED``
    carry a top-level ``(target_ref, dimension)``; ``EVIDENCE_ADDED`` carries
    ``credit_allocations[]`` (used only) plus a ``primary_target``; either may
    carry a ``targets[]`` list.
    """
    pairs: list[Key] = []
    ref, dim = payload.get("target_ref"), payload.get("dimension")
    if ref is not None and dim is not None:
        pairs.append((str(ref), str(dim)))
    for alloc in payload.get("credit_allocations") or []:
        a_ref, a_dim = alloc.get("target_ref"), alloc.get("dimension")
        if a_ref is not None and a_dim is not None and alloc.get("used", True):
            pairs.append((str(a_ref), str(a_dim)))
    primary = payload.get("primary_target")
    if isinstance(primary, dict):
        p_ref, p_dim = primary.get("target_ref"), primary.get("dimension")
        if p_ref is not None and p_dim is not None:
            pairs.append((str(p_ref), str(p_dim)))
    for target in payload.get("targets") or []:
        t_ref, t_dim = target.get("target_ref"), target.get("dimension")
        if t_ref is not None and t_dim is not None:
            pairs.append((str(t_ref), str(t_dim)))
    return list(dict.fromkeys(pairs))


def _success(payload: dict[str, Any]) -> bool | None:
    """``True`` success, ``False`` failure, ``None`` neutral (control 4.6/4.10).

    A five-value ``outcome`` is mapped by the calibration rule; a bare objective
    ``correct`` bool is the ``EVIDENCE_ADDED`` fallback; anything indeterminate
    (``INSUFFICIENT_EVIDENCE``, unknown, absent) is neutral and skips the streak.
    """
    outcome = payload.get("outcome")
    if outcome is not None:
        value = str(outcome)
        if value in _SUCCESS_OUTCOMES:
            return True
        if value in _FAILURE_OUTCOMES:
            return False
        return None
    if "correct" in payload:
        return bool(payload["correct"])
    return None


def _is_independent(payload: dict[str, Any]) -> bool:
    """Whether a success was reached without scaffolding (control 4.6).

    An explicit ``independent`` flag wins; otherwise a hinted attempt counts as
    scaffolded (not independent) and an unhinted one as independent. This is the
    honest v1 proxy until evidence carries the flag directly.
    """
    if "independent" in payload:
        return bool(payload["independent"])
    return not payload.get("hints")


def reduce_saturation(events: Iterable[DomainEvent], policy: dict[str, Any]) -> dict[Key, SaturationState]:
    """Fold the event log into per-``(target, dimension)`` ``SaturationState``.

    Deterministic: events are applied in canonical ``sequence`` order and deduped
    by ``event_id``. Clock-free -- the exposure window is counted in sessions.
    """
    window = int(policy["saturation"]["exposure_window_sessions"])

    seen: set[str] = set()
    session_seq = 0
    exposures: dict[Key, list[int]] = {}
    contexts: dict[Key, set[str]] = {}
    streak: dict[Key, int] = {}
    last_transfer: dict[Key, str | None] = {}
    keys: set[Key] = set()

    for event in sorted(events, key=_seq):
        if event.id in seen:
            continue
        seen.add(event.id)
        etype = event.type
        if etype == EVENT_SESSION_STARTED:
            session_seq += 1
            continue
        if etype == EVENT_STEP_PRESENTED:
            context_id = str(event.payload.get("context_id") or "")
            step_type = str(event.payload.get("step_type") or "")
            when = event.occurred_at.isoformat()
            for key in target_pairs(event.payload):
                keys.add(key)
                exposures.setdefault(key, []).append(session_seq)
                contexts.setdefault(key, set()).add(context_id)
                if step_type == _TRANSFER_STEP_TYPE:
                    last_transfer[key] = when
            continue
        if etype in (EVENT_EVIDENCE_ADDED, EVENT_REVIEW_OUTCOME):
            success = _success(event.payload)
            independent = _is_independent(event.payload)
            mode = str(event.payload.get("mode") or event.payload.get("step_type") or "")
            when = event.occurred_at.isoformat()
            for key in _evidence_pairs(event.payload):
                keys.add(key)
                if success is None:
                    pass  # neutral: INSUFFICIENT_EVIDENCE never breaks the run
                elif success and independent:
                    streak[key] = streak.get(key, 0) + 1
                else:
                    streak[key] = 0
                if mode == _TRANSFER_STEP_TYPE:
                    last_transfer[key] = when
            continue
        # ERROR_OBSERVED is handled by recurring_error_keys, not here.

    max_seq = session_seq
    out: dict[Key, SaturationState] = {}
    for key in keys:
        windowed = sum(1 for seq in exposures.get(key, []) if seq > max_seq - window)
        out[key] = SaturationState(
            exposures_in_window=windowed,
            consecutive_independent_successes=streak.get(key, 0),
            distinct_contexts=len(contexts.get(key, set())),
            last_transfer_check_at=last_transfer.get(key),
        )
    return out


def is_saturated(state: SaturationState, policy: dict[str, Any], now: datetime) -> bool:
    """The EXACT §4.6 ``saturated`` predicate, per-dimension.

    ``exposures_in_window >= max_exposures_in_window`` OR
    (``consecutive_independent_successes >= consecutive_success_threshold`` AND
    ``distinct_contexts < min_distinct_contexts`` AND
    ``last_transfer_check_at != null`` AND
    ``now - last_transfer_check_at <= transfer_check_staleness_days``).

    A null ``last_transfer_check_at`` makes the second conjunction false: sustained
    success in a familiar pattern is NOT saturation while transfer is unverified.
    """
    sat = policy["saturation"]
    if state.exposures_in_window >= int(sat["max_exposures_in_window"]):
        return True
    if (
        state.consecutive_independent_successes >= int(sat["consecutive_success_threshold"])
        and state.distinct_contexts < int(sat["min_distinct_contexts"])
        and state.last_transfer_check_at is not None
    ):
        last = datetime.fromisoformat(state.last_transfer_check_at)
        elapsed_seconds = (now - last) // timedelta(seconds=1)
        if elapsed_seconds <= int(sat["transfer_check_staleness_days"]) * 86400:
            return True
    return False


def recurring_error_keys(events: Iterable[DomainEvent], policy: dict[str, Any]) -> frozenset[Key]:
    """The ``(target, dimension)`` pairs with a recurring live error (control 4.5).

    A pair recurs when it accumulates ``>= recurring_error_min_occurrences``
    ``ERROR_OBSERVED`` events within the last ``recurring_error_window_sessions``
    sessions. Returns the empty set when no such events exist.
    """
    classification = policy["classification"]
    window = int(classification["recurring_error_window_sessions"])
    min_occurrences = int(classification["recurring_error_min_occurrences"])

    seen: set[str] = set()
    session_seq = 0
    errors: dict[Key, list[int]] = {}
    for event in sorted(events, key=_seq):
        if event.id in seen:
            continue
        seen.add(event.id)
        if event.type == EVENT_SESSION_STARTED:
            session_seq += 1
            continue
        if event.type == EVENT_ERROR_OBSERVED:
            for key in _evidence_pairs(event.payload):
                errors.setdefault(key, []).append(session_seq)

    max_seq = session_seq
    return frozenset(
        key
        for key, seqs in errors.items()
        if sum(1 for seq in seqs if seq > max_seq - window) >= min_occurrences
    )
