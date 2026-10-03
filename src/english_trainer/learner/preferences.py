"""``LearnerPreferences``: how the learner wants to practice (learner contract,
§4a [PD-2026-09-22]).

The learner already told a tutor "rounds of six words", "explain in Russian"
-- there was simply nowhere to keep it, so every new tutor started from zero.
Preferences answer HOW to practice, never WHAT is known: they live next to the
*declared* (`SelfReportedLevel`), never next to anything *measured*
(learner §1/§4a) -- and, unlike the personal lexicon, they never enter
`learner_relevance` either: they only shape the *form* of a round, not its
content.

Each edit publishes exactly ONE ``LEARNER_PREFERENCES_UPDATED`` event carrying
the FULL resulting snapshot and a monotonically increasing
``preferences_version`` -- never a partial delta. Reconstructing "current" from
a chain of patches would be a second way to compute the same state (learner
§4a MUST); the fold below only ever needs the single latest event, exactly
like ``learner.lexicon``'s deterministic fold over its own event type.

Preferences MUST NOT influence scoring (learner §4a MUST NOT): no field enters
a scoring formula, evidence admissibility, Mastery, working level, XP or the
automaticity axis. ``feedback_mode: always_explain`` only changes the
explanation protocol the tutor follows, never how an attempt is graded --
enforced here by construction: this module has no parameter for a score,
Mastery or knowledge state, and its one event type is never read by
``scoring.engine.fold_scores``.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import CachedResult, UnitOfWork
from english_trainer.learner.errors import PreferencesInvalid

# The one domain event this module publishes for LearnerPreferences (learner
# §4a). Full-snapshot, versioned -- never a partial delta.
EVENT_PREFERENCES_UPDATED = "learner.preferences_updated"

# A single, fixed logical identity: one learner, one LearnerPreferences record
# (CLAUDE.md -- local-first, single-learner personal tool; learner §4a has no
# per-skill or per-topic split, unlike SelfReportedLevel).
_CORRELATION_ID = "learner-preferences"

_ROUND_SIZE_RANGE = (3, 12)
_TIMED_LIMIT_RANGE = (60, 900)
_LANGUAGES = frozenset({"ru", "en"})
_FEEDBACK_MODES = frozenset({"stage_dependent", "always_explain"})
_DRILL_FORMS = frozenset(
    {"ru_to_en_sentence", "frame_recall", "cue_to_sentence", "transformation", "minimal_pair"}
)

# Defaults MUST match learner §4a exactly; a learner who never called `set`
# reads this snapshot at ``preferences_version`` 0.
DEFAULT_PREFERENCES: dict[str, Any] = {
    "round_size": 6,
    "explanation_language": "ru",
    "preferred_drill_forms": [],
    "timed_limit_seconds": 240,
    "feedback_mode": "stage_dependent",
}

_FIELDS = tuple(DEFAULT_PREFERENCES)


def _validate_changes(changes: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial patch before it ever touches state (cli 4.5): an
    unknown field, or a value outside its documented range/domain, is
    ``PreferencesInvalid`` (-> INVALID_INPUT) and leaves no trace."""
    unknown = sorted(set(changes) - set(_FIELDS))
    if unknown:
        raise PreferencesInvalid(f"unknown preference field(s): {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    if "round_size" in changes:
        value = changes["round_size"]
        low, high = _ROUND_SIZE_RANGE
        if type(value) is not int or not (low <= value <= high):
            raise PreferencesInvalid(f"round_size must be an integer in [{low}, {high}], not {value!r}")
        normalized["round_size"] = value
    if "timed_limit_seconds" in changes:
        value = changes["timed_limit_seconds"]
        low, high = _TIMED_LIMIT_RANGE
        if type(value) is not int or not (low <= value <= high):
            raise PreferencesInvalid(
                f"timed_limit_seconds must be an integer in [{low}, {high}], not {value!r}"
            )
        normalized["timed_limit_seconds"] = value
    if "explanation_language" in changes:
        value = changes["explanation_language"]
        if value not in _LANGUAGES:
            raise PreferencesInvalid(
                f"explanation_language must be one of {sorted(_LANGUAGES)}, not {value!r}"
            )
        normalized["explanation_language"] = value
    if "feedback_mode" in changes:
        value = changes["feedback_mode"]
        if value not in _FEEDBACK_MODES:
            raise PreferencesInvalid(f"feedback_mode must be one of {sorted(_FEEDBACK_MODES)}, not {value!r}")
        normalized["feedback_mode"] = value
    if "preferred_drill_forms" in changes:
        value = changes["preferred_drill_forms"]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise PreferencesInvalid("preferred_drill_forms must be a list of drill-form names")
        unknown_forms = sorted(set(value) - _DRILL_FORMS)
        if unknown_forms:
            raise PreferencesInvalid(
                f"unknown drill form(s): {', '.join(unknown_forms)} (allowed: {sorted(_DRILL_FORMS)})"
            )
        # Order-preserving de-dup: a repeated form in the input is not a second
        # preference.
        normalized["preferred_drill_forms"] = list(dict.fromkeys(value))
    return normalized


def _snapshot_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "round_size": payload["round_size"],
        "explanation_language": payload["explanation_language"],
        "preferred_drill_forms": list(payload.get("preferred_drill_forms") or []),
        "timed_limit_seconds": payload["timed_limit_seconds"],
        "feedback_mode": payload["feedback_mode"],
        "preferences_version": payload["preferences_version"],
        "updated_at": payload["updated_at"],
    }


def _fold(store: EventStore) -> dict[str, Any] | None:
    """The latest full snapshot, or ``None`` before any edit.

    A pure fold in canonical ``sequence`` order (foundation 3.3): every
    ``LEARNER_PREFERENCES_UPDATED`` event carries the FULL resulting state, so
    the newest one simply wins -- no delta-chain replay, matching the
    versioned full-snapshot contract (learner §4a).
    """
    latest: dict[str, Any] | None = None
    for event in store.read():  # canonical sequence order
        if event.type != EVENT_PREFERENCES_UPDATED:
            continue
        latest = event.payload
    return _snapshot_from_payload(latest) if latest is not None else None


def preferences_get(store: EventStore) -> dict[str, Any]:
    """The learner's current ``LearnerPreferences`` snapshot (learner §4a).

    Returns the documented defaults with ``preferences_version`` 0 and
    ``updated_at`` ``None`` before the first ``preferences_set`` -- an honest
    no-data value, never a fabricated history.
    """
    found = _fold(store)
    if found is not None:
        return found
    return {**DEFAULT_PREFERENCES, "preferred_drill_forms": [], "preferences_version": 0, "updated_at": None}


def preferences_set(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    *,
    changes: dict[str, Any],
    idempotency_key: str | None = None,
    actor: str = "learner",
) -> dict[str, Any]:
    """Merge ``changes`` over the current snapshot and publish ONE full-snapshot
    ``LEARNER_PREFERENCES_UPDATED`` event with a monotonically increasing
    ``preferences_version`` (learner §4a).

    Validates before any effect (cli 4.5: unknown field or out-of-range/domain
    value is ``PreferencesInvalid``, no trace left). A repeat call with the
    same ``idempotency_key`` and the same normalized ``changes`` returns the
    cached result unchanged (foundation 3.4); the same key with a *different*
    payload raises the kernel's stable ``IdempotencyConflict``.

    Preferences never enter scoring: this function has no parameter for a
    score, Mastery, level or knowledge state, by design (learner §4a MUST NOT).
    """
    normalized_changes = _validate_changes(changes)
    request_hash = payload_hash({"command": "learner.preferences.set", "changes": normalized_changes})
    with UnitOfWork(store, clock) as uow:
        if idempotency_key is not None:
            prior = uow.check_idempotency(idempotency_key, request_hash)
            if isinstance(prior, CachedResult):
                return {**prior.value, "cached": True}

        current = preferences_get(store)
        current_version = int(current["preferences_version"])
        merged = {field: current[field] for field in _FIELDS}
        merged.update(normalized_changes)
        payload: dict[str, Any] = {
            **merged,
            "preferences_version": current_version + 1,
            "updated_at": clock.now().isoformat(),
        }
        event_id = new_ulid(clock, random_source)
        uow.append(
            [
                make_event(
                    id=event_id,
                    type=EVENT_PREFERENCES_UPDATED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=_CORRELATION_ID,
                    payload=payload,
                )
            ]
        )
        result: dict[str, object] = {**payload, "event_id": event_id}
        if idempotency_key is not None:
            uow.record_result(idempotency_key, request_hash, result)
    return {**result, "cached": False}
