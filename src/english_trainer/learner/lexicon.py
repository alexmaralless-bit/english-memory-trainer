"""The learner's personal lexicon: layer 3 of the lexical system (learner
contract 0.11; lexical-system §3; roadmap living-layer boundary).

The personal lexicon holds what the learner (or the tutor, on the learner's
behalf) noted about a word or chunk -- it is NEVER knowledge of it. Adding a
unit is ``enrollment``, not evidence: it publishes ``LEARNER_LEXICON_ENTRY_ADDED``
and nothing else. It creates no ``EVIDENCE_ADDED``, moves no Mastery, awards no
XP and opens no review schedule (invariant 1: encountered != learned). A
translation request survives a chat swap -- it shows up in the tutor briefing
and the memory projection -- but by itself it can never become proof of
knowledge.

The lexicon is a deterministic fold over the append-only event log, so there is
no second mutable source of truth. Each entry has a stable *logical identity*:

- a **linked** entry (``linked_item_id`` resolvable in ACTIVE curriculum) is
  identified by that id -- re-encountering the same curriculum item does not
  create a second logical record (invariant 2/E);
- an **unlinked** entry (``linked_item_id is None``) is identified by its
  normalized surface (NFC + whitespace-collapse + casefold, spelled out below)
  -- re-adding the same surface does not duplicate it either.

Homonyms carrying different reliable ids stay separate; the engine never merges
two senses of one surface without a reliable id. This is the minimal safe
semantics for repeat encounters: a retry appends no second event and returns
the stored entry (a subordinate encounter-count fact is a deliberate,
documented non-goal -- see the handoff report's fork list).

The curriculum and the personal lexicon are strictly separate: a
``LearnerLexiconEntry`` never creates or edits a ``LexicalItem`` (lexical-system
§3). ``linked_item_id`` only *references* an existing curriculum item; an
unlinked entry stays a private note and is never a scoring target until the
living-layer maintain workflow promotes it (invariant 2/8).
"""

from __future__ import annotations

import unicodedata
from typing import Any

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.learner.errors import LexiconEntryInvalid, LinkedItemNotFound

# The one domain event this module publishes (learner 3). The learner module
# never publishes a knowledge/level/XP event -- those belong to scoring/evidence.
EVENT_LEXICON_ENTRY_ADDED = "learner.lexicon_entry_added"

# The two admissible sources of a personal-lexicon entry (learner 2):
# ``learner`` -- the learner asked to remember it; ``encountered`` -- the tutor
# used or explained it and the learner did not know it / asked for a translation.
_SOURCES = ("learner", "encountered")


def normalize_surface(surface: str) -> str:
    """The canonical identity form of a surface: NFC, whitespace-collapsed,
    casefolded -- spelled out on purpose (handoff D/E).

    Mirrors ``evidence._normalize_answer`` exactly, so the personal lexicon and
    the objective checker agree on what "the same surface" means.
    """
    collapsed = " ".join(unicodedata.normalize("NFC", surface).split())
    return collapsed.casefold()


def _display_surface(surface: str) -> str:
    """The stored display form: NFC-normalized, ends trimmed, inner spacing kept."""
    return unicodedata.normalize("NFC", surface).strip()


def _identity_key(linked_item_id: str | None, normalized: str) -> str:
    """The logical identity of an entry: the reliable id if linked, else the
    normalized surface. Different ids never merge (homonym safety, handoff E)."""
    if linked_item_id is not None:
        return f"linked:{linked_item_id}"
    return f"surface:{normalized}"


def resolve_linked_item(program: dict[str, Any], linked_item_id: str) -> dict[str, Any]:
    """Resolve ``linked_item_id`` to a lexical item of the ACTIVE program.

    The agent passes the id explicitly; the engine only verifies it exists AND
    is a lexical item (never a topic), refusing a dangling id with a stable
    error. It never guesses a link from the surface and never disambiguates
    homonyms itself (learner 4; lexical-system §3).
    """
    for unit in program.get("lexicon", []):
        if str(unit.get("id")) == linked_item_id:
            return dict(unit)
    if any(str(topic.get("id")) == linked_item_id for topic in program.get("topics", [])):
        raise LinkedItemNotFound(
            f"{linked_item_id!r} is a topic, not a lexical item: a personal-lexicon entry links "
            "only to a LexicalItem (leave --linked-item empty for an unknown word)"
        )
    raise LinkedItemNotFound(
        f"linked_item_id {linked_item_id!r} does not resolve to a lexical item in the active "
        "curriculum: pass an explicit id from the active program, or leave it empty for an unknown word"
    )


def resolve_surface_exact(program: dict[str, Any], surface: str) -> str | None:
    """A deterministic exact-match helper (handoff D): the id of the single
    lexical item whose title/surface equals ``surface`` under
    :func:`normalize_surface`, or ``None`` when there is zero or more than one
    match. It never guesses on ambiguity and is NOT used to auto-link -- the
    agent passes an explicit id -- but it lets a caller offer a suggestion.
    """
    target = normalize_surface(surface)
    matches = [
        str(unit.get("id"))
        for unit in program.get("lexicon", [])
        if normalize_surface(str(unit.get("title") or unit.get("id") or "")) == target
    ]
    return matches[0] if len(matches) == 1 else None


def _entry_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The canonical entry projection from one stored event payload."""
    return {
        "entry_id": payload["entry_id"],
        "surface": payload["surface"],
        "normalized_surface": payload["normalized_surface"],
        "note_ru": payload.get("note_ru"),
        "source": payload["source"],
        "linked_item_id": payload.get("linked_item_id"),
        "added_at": payload["added_at"],
        "session_id": payload.get("session_id"),
        "provider": payload.get("provider"),
        "source_event_id": payload.get("source_event_id"),
    }


def _fold(store: EventStore) -> dict[str, dict[str, Any]]:
    """Deterministic fold: identity_key -> entry (first event wins).

    Pure over the event log in canonical ``sequence`` order, so there is no
    second mutable source of truth. A repeat event for an already-seen identity
    is ignored -- it never creates a second logical entry.
    """
    by_identity: dict[str, dict[str, Any]] = {}
    for event in store.read():  # canonical sequence order (foundation 3.3)
        if event.type != EVENT_LEXICON_ENTRY_ADDED:
            continue
        key = str(event.payload["identity_key"])
        if key in by_identity:
            continue
        by_identity[key] = _entry_from_payload(event.payload)
    return by_identity


def lexicon_entries(store: EventStore) -> list[dict[str, Any]]:
    """Every logical personal-lexicon entry, oldest first (deterministic).

    Ordered by ``(added_at, entry_id)`` -- both derive from the injected clock
    and the time-sortable id, so the order is replayable.
    """
    entries = list(_fold(store).values())
    entries.sort(key=lambda entry: (str(entry["added_at"]), str(entry["entry_id"])))
    return entries


def relevant_lexicon_targets(store: EventStore) -> frozenset[str]:
    """The curriculum targets the personal lexicon marks as relevant (learner 4;
    control §4.5): the ``linked_item_id`` of every linked entry.

    Unlinked entries contribute nothing -- they are never passed to control as a
    target (invariant 2/8). This is the only learner input the composition
    pipeline consumes; it raises ``learner_relevance`` so the target may enter
    growth/lexicon-first practice, and never touches scoring.
    """
    return frozenset(
        str(entry["linked_item_id"]) for entry in _fold(store).values() if entry["linked_item_id"] is not None
    )


def personal_lexicon_summary(store: EventStore) -> dict[str, int]:
    """Honest, separate personal-lexicon counts for ``trainer status`` (learner
    5, handoff H): ``total`` entries, of which ``linked`` / ``unlinked``."""
    entries = list(_fold(store).values())
    linked = sum(1 for entry in entries if entry["linked_item_id"] is not None)
    return {"total": len(entries), "linked": linked, "unlinked": len(entries) - linked}


def lexicon_list(
    store: EventStore,
    *,
    source: str | None = None,
    linked: bool | None = None,
) -> list[dict[str, Any]]:
    """Read-only listing of the personal lexicon, filtered and deterministic.

    ``source`` filters ``learner``/``encountered``; ``linked`` filters
    linked/unlinked entries. Never mutates.
    """
    out: list[dict[str, Any]] = []
    for entry in lexicon_entries(store):
        if source is not None and entry["source"] != source:
            continue
        if linked is True and entry["linked_item_id"] is None:
            continue
        if linked is False and entry["linked_item_id"] is not None:
            continue
        out.append(entry)
    return out


def find_encounter_entry(
    store: EventStore, *, surface: str, linked_item_id: str | None = None
) -> dict[str, Any] | None:
    """The stored personal-lexicon entry for this identity, or ``None``.

    Identity is the same rule :func:`_identity_key` uses everywhere else
    (``linked_item_id`` when given, else the normalized surface). Read-only and
    deterministic -- a caller can learn "already enrolled" ahead of a write
    without duplicating the fold. :func:`build_encounter_events` uses this
    internally to decide whether to emit an event or an empty list; a lesson
    report committer can call it directly (e.g. for a dry-run ``check-report``)
    to report the same fact without building anything.
    """
    identity_key = _identity_key(linked_item_id, normalize_surface(surface))
    return _fold(store).get(identity_key)


def build_encounter_events(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    *,
    session_id: str,
    surface: str,
    provider: str | None = None,
    note_ru: str | None = None,
    linked_item_id: str | None = None,
    program: dict[str, Any] | None = None,
    pinned_versions: dict[str, str] | None = None,
    source_event_id: str | None = None,
    actor: str = "agent",
) -> list[DomainEvent]:
    """Pure builder: the ``learner.lexicon_entry_added`` event(s) one
    ``encountered`` entry needs, with none of the side effects.

    Same validation and identity rules as :func:`lexicon_encounter` /
    :func:`lexicon_add` today -- an empty surface is refused, a
    ``linked_item_id`` must resolve against ``program`` -- but this function
    opens no :class:`UnitOfWork`, bumps no session revision, and performs no
    idempotency check. It only reads the event log (via
    :func:`find_encounter_entry`) to decide whether the identity is already
    enrolled. A caller composing a bigger transaction (e.g. a lesson-report
    committer) appends the returned event(s) itself, alongside the report's
    other facts, inside its own :class:`UnitOfWork`.

    Returns an empty list when the identity (linked id, else normalized
    surface) is already enrolled -- exactly the case :func:`lexicon_add`
    reports as ``cached: True`` and writes nothing for. Otherwise returns a
    list with exactly one event, ready to hand to ``uow.append``.

    ``pinned_versions`` lets the caller carry the session's pinned policy
    versions onto the event, exactly as the session-bound path of
    :func:`lexicon_add` does today (it reads them from the session manifest
    before opening its own UoW); omit it for an unpinned event.
    """
    normalized = normalize_surface(surface)
    if not normalized:
        raise LexiconEntryInvalid("surface is empty after normalization: nothing to remember")
    if linked_item_id is not None:
        if program is None:
            raise LinkedItemNotFound(
                "a linked entry needs the active curriculum to resolve linked_item_id against"
            )
        resolve_linked_item(program, linked_item_id)  # raises on a dangling/non-lexical id

    if find_encounter_entry(store, surface=surface, linked_item_id=linked_item_id) is not None:
        return []

    identity_key = _identity_key(linked_item_id, normalized)
    entry_id = new_ulid(clock, random_source)
    added_at = clock.now().isoformat()
    payload: dict[str, Any] = {
        "entry_id": entry_id,
        "surface": _display_surface(surface),
        "normalized_surface": normalized,
        "note_ru": note_ru,
        "source": "encountered",
        "linked_item_id": linked_item_id,
        "added_at": added_at,
        "session_id": session_id,
        "provider": provider,
        "source_event_id": source_event_id,
        "identity_key": identity_key,
    }
    event = make_event(
        id=new_ulid(clock, random_source),
        type=EVENT_LEXICON_ENTRY_ADDED,
        occurred_at=clock.now(),
        actor=actor,
        provider=provider,
        correlation_id=session_id,
        causation_id=source_event_id,
        payload=payload,
        pinned_versions=pinned_versions or {},
    )
    return [event]


def lexicon_add(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    *,
    surface: str,
    note_ru: str | None = None,
    source: str = "learner",
    linked_item_id: str | None = None,
    program: dict[str, Any] | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    expected_session_revision: int | None = None,
    source_event_id: str | None = None,
    actor: str = "learner",
) -> dict[str, Any]:
    """Add one entry to the personal lexicon (learner 3; lexical-system §3).

    The engine accepts only facts: a surface, an optional Russian note, the
    ``source``, an optional explicit ``linked_item_id`` and provenance. It never
    accepts knowledge_state, Mastery, a score or correctness -- there is no
    parameter for them, by design (invariant 3).

    Adding is enrollment, not evidence: exactly one
    ``LEARNER_LEXICON_ENTRY_ADDED`` and nothing else. No ``EVIDENCE_ADDED``, no
    Mastery/XP/level change, no ReviewSchedule (invariant 1).

    Logical dedup is by identity (linked id, else normalized surface): a repeat
    returns the stored entry and appends no second event -- checked BEFORE the
    session fence, exactly like ``adapters.capture_user_turn`` (invariant 4/E).

    When ``session_id`` is given the write is bound to that session: it requires
    ``expected_session_revision`` and, in ONE UnitOfWork, appends the event and
    bumps the session revision atomically. A commit failure rolls back both --
    it never leaves the event without the bump or vice versa (invariant 4).
    """
    if source not in _SOURCES:
        raise LexiconEntryInvalid(f"source must be one of {_SOURCES}, not {source!r}")
    normalized = normalize_surface(surface)
    if not normalized:
        raise LexiconEntryInvalid("surface is empty after normalization: nothing to remember")
    if linked_item_id is not None:
        if program is None:
            raise LinkedItemNotFound(
                "a linked entry needs the active curriculum to resolve linked_item_id against"
            )
        resolve_linked_item(program, linked_item_id)  # raises on a dangling/non-lexical id
    if session_id is not None and expected_session_revision is None:
        raise LexiconEntryInvalid(
            "a session-bound entry requires expected_session_revision (the coarse session fence)"
        )

    identity_key = _identity_key(linked_item_id, normalized)

    # Logical dedup first -- before touching the (possibly now-advanced) session
    # fence, mirroring capture_user_turn: a re-encounter returns the stored entry
    # and writes nothing, so no second logical record is ever created.
    existing = _fold(store).get(identity_key)
    if existing is not None:
        return {**existing, "cached": True}

    entry_id = new_ulid(clock, random_source)
    added_at = clock.now().isoformat()
    display = _display_surface(surface)
    payload: dict[str, Any] = {
        "entry_id": entry_id,
        "surface": display,
        "normalized_surface": normalized,
        "note_ru": note_ru,
        "source": source,
        "linked_item_id": linked_item_id,
        "added_at": added_at,
        "session_id": session_id,
        "provider": provider,
        "source_event_id": source_event_id,
        "identity_key": identity_key,
    }

    if session_id is not None:
        assert expected_session_revision is not None  # guarded above
        state, revision = load_session_for_update(store, session_id, expected_session_revision)
        pinned = dict((state.get("manifest") or {}).get("pinned_versions") or {})
        with UnitOfWork(store, clock) as uow:
            new_revision = bump_session(uow, session_id, state, revision, clock.now())
            # Both the event append and the fence bump are in this one UoW: a
            # failure rolls back the event AND the revision, never a partial.
            (event,) = uow.append(
                [
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=EVENT_LEXICON_ENTRY_ADDED,
                        occurred_at=clock.now(),
                        actor=actor,
                        provider=provider,
                        correlation_id=session_id,
                        causation_id=source_event_id,
                        payload=payload,
                        pinned_versions=pinned,
                    )
                ]
            )
        return {**_entry_from_payload(event.payload), "session_revision": new_revision, "cached": False}

    with UnitOfWork(store, clock) as uow:
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_LEXICON_ENTRY_ADDED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=entry_id,
                    causation_id=source_event_id,
                    payload=payload,
                )
            ]
        )
    return {**_entry_from_payload(event.payload), "cached": False}


def lexicon_encounter(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    surface: str,
    note_ru: str | None = None,
    linked_item_id: str | None = None,
    program: dict[str, Any] | None = None,
    provider: str | None = None,
    expected_session_revision: int,
    source_event_id: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Record a session-driven ``encountered`` entry (learner 3, criterion 2/4).

    The clearer, validated contract for the tutor path: the tutor uses or
    explains a word, the learner does not know it or asks for a translation, and
    the agent calls this with the plain facts. It requires the active session
    and its fence token. Explaining a word is enrollment, never evidence
    (evidence §4.2).

    Validation, identity and the event payload come from the pure
    :func:`build_encounter_events` builder (the same one a lesson-report
    committer uses), so this stays byte-identical to the historical
    ``source=encountered`` wrapper over :func:`lexicon_add`: this function only
    adds the session-fence behaviour build_encounter_events deliberately leaves
    out -- the CAS check against ``expected_session_revision`` and the atomic
    revision bump, both inside one :class:`UnitOfWork` alongside the event.

    Logical dedup is checked (inside the builder) BEFORE the session fence is
    touched at all, exactly like :func:`lexicon_add`: a re-encounter returns
    the stored entry and never raises on a stale ``expected_session_revision``.
    """
    # A plain peek at the session's pinned policy versions (no CAS check, no
    # write) so a genuinely new event carries them like lexicon_add's
    # session-bound path does -- reading is harmless even for a stale/missing
    # session and must not run before the dedup check below has a chance to
    # short-circuit on a duplicate.
    found = read_aggregate(store._conn, "session", session_id)
    manifest = dict(found[0].get("manifest") or {}) if found is not None else {}
    pinned = dict(manifest.get("pinned_versions") or {})

    events = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session_id,
        surface=surface,
        provider=provider,
        note_ru=note_ru,
        linked_item_id=linked_item_id,
        program=program,
        pinned_versions=pinned,
        source_event_id=source_event_id,
        actor=actor,
    )
    if not events:
        existing = find_encounter_entry(store, surface=surface, linked_item_id=linked_item_id)
        assert existing is not None  # build_encounter_events just confirmed this identity is enrolled
        return {**existing, "cached": True}

    state, revision = load_session_for_update(store, session_id, expected_session_revision)
    with UnitOfWork(store, clock) as uow:
        new_revision = bump_session(uow, session_id, state, revision, clock.now())
        # Both the event append and the fence bump are in this one UoW: a
        # failure rolls back the event AND the revision, never a partial.
        (event,) = uow.append(events)
    return {**_entry_from_payload(event.payload), "session_revision": new_revision, "cached": False}
