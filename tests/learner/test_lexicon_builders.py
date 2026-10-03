"""``build_encounter_events`` -- the pure event builder behind ``lexicon_encounter``
(learner 3; staging/concepts/2026-09-23-lesson-brief-report-concept.md, step 5
of "Путь записи").

The load-bearing claim under test: the builder produces exactly the same
``learner.lexicon_entry_added`` event a live ``lexicon_encounter`` call writes
today, with zero side effects of its own -- no UnitOfWork, no session-fence
bump, no idempotency, not even a write when the identity is a duplicate. A
future ``lessons/report.py::commit_report`` appends the returned event(s)
itself, inside its own transaction, alongside the rest of one report item's
facts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.errors import SessionRevisionConflict
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.learner.errors import LexiconEntryInvalid, LinkedItemNotFound
from english_trainer.learner.lexicon import (
    EVENT_LEXICON_ENTRY_ADDED,
    build_encounter_events,
    find_encounter_entry,
    lexicon_encounter,
)
from tests.learner.conftest import EPOCH, PROGRAM, make_session

SEED = 20260923


def _fresh_store(tmp_path: Path, name: str) -> EventStore:
    conn = connect(tmp_path / name)
    migrate(conn)
    return EventStore(conn)


def _lexicon_events(store: EventStore) -> list[Any]:
    return [event for event in store.read() if event.type == EVENT_LEXICON_ENTRY_ADDED]


# -- builder output equals what lexicon_encounter writes ---------------------


def test_builder_output_equals_lexicon_encounter_write(tmp_path: Path):
    # Two fully independent stores, wired with identical (epoch, seed) clock
    # and randomness: same new_ulid consumption order on both sides means the
    # generated entry_id/event id must land on the same bytes, not just an
    # equal-shaped payload.
    store_a = _fresh_store(tmp_path, "a.db")
    store_b = _fresh_store(tmp_path, "b.db")
    clock_a, clock_b = FixedClock(EPOCH), FixedClock(EPOCH)
    random_a, random_b = SeededRandomSource(SEED), SeededRandomSource(SEED)
    session_a = make_session(store_a, clock_a)
    session_b = make_session(store_b, clock_b)  # same manifest: pinned curriculum "v-test"

    result = lexicon_encounter(
        store_a,
        clock_a,
        random_a,
        session_a,
        surface="Feasible",
        note_ru="осуществимый",
        linked_item_id="word.feasible",
        program=PROGRAM,
        provider="claude-code",
        expected_session_revision=1,
    )
    stored_a = _lexicon_events(store_a)
    assert len(stored_a) == 1

    events = build_encounter_events(
        store_b,
        clock_b,
        random_b,
        session_id=session_b,
        surface="Feasible",
        note_ru="осуществимый",
        linked_item_id="word.feasible",
        program=PROGRAM,
        provider="claude-code",
        pinned_versions={"curriculum": "v-test"},
    )
    assert len(events) == 1
    with UnitOfWork(store_b, clock_b) as uow:
        (appended,) = uow.append(events)

    assert appended.payload == stored_a[0].payload
    assert appended.id == stored_a[0].id
    assert appended.pinned_versions == stored_a[0].pinned_versions
    assert appended.type == EVENT_LEXICON_ENTRY_ADDED
    assert result["entry_id"] == appended.payload["entry_id"]
    assert result["cached"] is False


def test_builder_does_not_bump_session_revision(tmp_path: Path):
    store = _fresh_store(tmp_path, "solo.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    events = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="serendipity",
    )
    assert len(events) == 1

    found = read_aggregate(store._conn, "session", session)
    assert found is not None and found[1] == 1  # still revision 1: no bump, no CAS check


# -- linked vs unlinked -------------------------------------------------------


def test_builder_linked_entry(tmp_path: Path):
    store = _fresh_store(tmp_path, "linked.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    (event,) = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="feasible",
        linked_item_id="word.feasible",
        program=PROGRAM,
    )
    assert event.payload["linked_item_id"] == "word.feasible"
    assert event.payload["identity_key"] == "linked:word.feasible"


def test_builder_unlinked_entry(tmp_path: Path):
    store = _fresh_store(tmp_path, "unlinked.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    (event,) = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="whatchamacallit",
    )
    assert event.payload["linked_item_id"] is None
    assert event.payload["identity_key"] == "surface:whatchamacallit"


# -- invalid linked item -------------------------------------------------------


def test_builder_rejects_dangling_linked_item(tmp_path: Path):
    store = _fresh_store(tmp_path, "dangling.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    with pytest.raises(LinkedItemNotFound):
        build_encounter_events(
            store,
            clock,
            random_source,
            session_id=session,
            surface="ghost",
            linked_item_id="word.nonexistent",
            program=PROGRAM,
        )
    assert _lexicon_events(store) == []


def test_builder_rejects_topic_id_as_linked_item(tmp_path: Path):
    store = _fresh_store(tmp_path, "topic-link.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    with pytest.raises(LinkedItemNotFound):
        build_encounter_events(
            store,
            clock,
            random_source,
            session_id=session,
            surface="be",
            linked_item_id="grammar.be.identity",
            program=PROGRAM,
        )


def test_builder_requires_program_for_a_linked_item(tmp_path: Path):
    store = _fresh_store(tmp_path, "no-program.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    with pytest.raises(LinkedItemNotFound):
        build_encounter_events(
            store,
            clock,
            random_source,
            session_id=session,
            surface="feasible",
            linked_item_id="word.feasible",
        )


def test_builder_rejects_empty_surface(tmp_path: Path):
    store = _fresh_store(tmp_path, "empty.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    with pytest.raises(LexiconEntryInvalid):
        build_encounter_events(store, clock, random_source, session_id=session, surface="   ")
    assert _lexicon_events(store) == []


# -- duplicate handling --------------------------------------------------------


def test_builder_returns_no_event_for_an_already_enrolled_identity(tmp_path: Path):
    store = _fresh_store(tmp_path, "dup.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    assert find_encounter_entry(store, surface="ubiquitous") is None
    (event,) = build_encounter_events(store, clock, random_source, session_id=session, surface="ubiquitous")
    with UnitOfWork(store, clock) as uow:
        uow.append([event])
    assert len(_lexicon_events(store)) == 1

    existing = find_encounter_entry(store, surface="ubiquitous")
    assert existing is not None
    assert existing["entry_id"] == event.payload["entry_id"]

    # A second build for the identical identity (even a different surface
    # spelling) reports the duplicate deterministically: an empty list, no
    # random draw, no write -- exactly what lexicon_add/lexicon_encounter
    # report as `cached: True`.
    again = build_encounter_events(store, clock, random_source, session_id=session, surface="Ubiquitous")
    assert again == []
    assert len(_lexicon_events(store)) == 1


def test_builder_duplicate_check_follows_linked_identity(tmp_path: Path):
    store = _fresh_store(tmp_path, "dup-linked.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    (event,) = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="feasible",
        linked_item_id="word.feasible",
        program=PROGRAM,
    )
    with UnitOfWork(store, clock) as uow:
        uow.append([event])

    # A different surface spelling, same linked id -- still the same logical
    # identity, so no second event.
    again = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="FEASIBLE (adj.)",
        linked_item_id="word.feasible",
        program=PROGRAM,
    )
    assert again == []
    assert len(_lexicon_events(store)) == 1


def test_lexicon_encounter_re_encounter_matches_builder_dedup(tmp_path: Path):
    """lexicon_encounter's own dedup (cached=True, no fence bump) is exactly
    what find_encounter_entry/build_encounter_events already report -- the two
    surfaces of the same identity rule stay in lockstep after the refactor."""
    store = _fresh_store(tmp_path, "encounter-dup.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    first = lexicon_encounter(
        store,
        clock,
        random_source,
        session,
        surface="feasible",
        linked_item_id="word.feasible",
        program=PROGRAM,
        expected_session_revision=1,
    )
    assert first["cached"] is False
    revision_after_first = read_aggregate(store._conn, "session", session)
    assert revision_after_first is not None and revision_after_first[1] == 2

    # A stale expected_session_revision on the re-encounter must not raise:
    # dedup short-circuits before the fence is ever consulted.
    second = lexicon_encounter(
        store,
        clock,
        random_source,
        session,
        surface="Feasible",
        linked_item_id="word.feasible",
        program=PROGRAM,
        expected_session_revision=99,
    )
    assert second["cached"] is True
    assert second["entry_id"] == first["entry_id"]
    assert len(_lexicon_events(store)) == 1
    revision_after_second = read_aggregate(store._conn, "session", session)
    assert revision_after_second is not None and revision_after_second[1] == 2  # unchanged

    # A stale revision for a genuinely NEW identity still raises, exactly as
    # before the refactor.
    with pytest.raises(SessionRevisionConflict):
        lexicon_encounter(
            store,
            clock,
            random_source,
            session,
            surface="brand-new-surface",
            expected_session_revision=99,
        )
    assert len(_lexicon_events(store)) == 1


# -- the builder writes nothing by itself -------------------------------------


def test_builder_writes_nothing_by_itself(tmp_path: Path):
    store = _fresh_store(tmp_path, "pure.db")
    clock = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    session = make_session(store, clock)

    before_events = list(store.read())
    before_session = read_aggregate(store._conn, "session", session)

    events = build_encounter_events(
        store,
        clock,
        random_source,
        session_id=session,
        surface="pull an all-nighter",
        note_ru="не спать всю ночь ради дела",
        provider="claude-code",
        source_event_id="EVT-1",
    )
    assert len(events) == 1  # the builder computed a real event to return...

    after_events = list(store.read())
    after_session = read_aggregate(store._conn, "session", session)
    assert after_events == before_events  # ...but appended nothing to the log
    assert after_session == before_session  # ...and touched no aggregate

    # The returned event is a fully-formed, ready-to-append DomainEvent: only
    # a caller's own UnitOfWork.append gives it a sequence number.
    assert events[0].sequence is None
    assert events[0].payload["surface"] == "pull an all-nighter"
    assert events[0].payload["source"] == "encountered"
    assert events[0].causation_id == "EVT-1"
