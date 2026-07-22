"""Personal-lexicon invariants (learner 0.11; lexical-system §3).

The load-bearing claim: a translation request survives a chat swap but never
by itself becomes evidence of knowledge. These tests prove the pieces of that
-- enrollment != evidence, curriculum/personal separation, deterministic
event-sourced dedup, idempotent retries, and crash-safe session-bound writes.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.errors import SessionRevisionConflict
from english_trainer.kernel.store import EventStore
from english_trainer.learner import lexicon as lexicon_module
from english_trainer.learner.errors import LexiconEntryInvalid, LinkedItemNotFound
from english_trainer.learner.lexicon import (
    EVENT_LEXICON_ENTRY_ADDED,
    lexicon_add,
    lexicon_encounter,
    lexicon_entries,
    lexicon_list,
    normalize_surface,
    personal_lexicon_summary,
    relevant_lexicon_targets,
    resolve_surface_exact,
)
from tests.learner.conftest import make_session

REPO = Path(__file__).resolve().parents[2]


def _lexicon_events(store: EventStore) -> list[Any]:
    return [event for event in store.read() if event.type == EVENT_LEXICON_ENTRY_ADDED]


def _scoring_policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "scoring-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# -- add / list round-trip ---------------------------------------------------


def test_add_and_list_round_trip(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    entry = lexicon_add(store, clock, random_source, surface="serendipity", note_ru="счастливая случайность")
    assert entry["cached"] is False
    assert entry["source"] == "learner"
    assert entry["linked_item_id"] is None

    listed = lexicon_list(store)
    assert len(listed) == 1
    assert listed[0]["surface"] == "serendipity"
    assert listed[0]["note_ru"] == "счастливая случайность"
    assert listed[0]["entry_id"] == entry["entry_id"]


def test_source_must_be_known(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    with pytest.raises(LexiconEntryInvalid):
        lexicon_add(store, clock, random_source, surface="x", source="mastered")


def test_empty_surface_refused(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    with pytest.raises(LexiconEntryInvalid):
        lexicon_add(store, clock, random_source, surface="   ")


# -- NFC / Unicode identity --------------------------------------------------


def test_nfc_equivalent_surfaces_are_one_entry(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    # A word with a combining accent, pre-composed (NFC) vs decomposed (NFD):
    # different bytes, the same word. Built programmatically so the two really
    # differ on disk.
    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert normalize_surface(nfc) == normalize_surface(nfd)

    first = lexicon_add(store, clock, random_source, surface=nfc)
    second = lexicon_add(store, clock, random_source, surface=nfd)
    assert first["entry_id"] == second["entry_id"]
    assert second["cached"] is True
    assert len(_lexicon_events(store)) == 1


def test_case_and_whitespace_collapse_into_one_identity(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    lexicon_add(store, clock, random_source, surface="Follow  Up")
    again = lexicon_add(store, clock, random_source, surface="follow up")
    assert again["cached"] is True
    assert len(lexicon_list(store)) == 1


# -- linked / unlinked -------------------------------------------------------


def test_linked_entry_resolves_against_active_curriculum(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    entry = lexicon_add(
        store,
        clock,
        random_source,
        surface="feasible",
        note_ru="осуществимый",
        linked_item_id="word.feasible",
        program=program,
    )
    assert entry["linked_item_id"] == "word.feasible"
    assert relevant_lexicon_targets(store) == frozenset({"word.feasible"})


def test_unlinked_entry_is_not_a_control_target(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    lexicon_add(store, clock, random_source, surface="whatchamacallit")
    assert relevant_lexicon_targets(store) == frozenset()
    summary = personal_lexicon_summary(store)
    assert summary == {"total": 1, "linked": 0, "unlinked": 1}


def test_dangling_linked_item_is_rejected(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    with pytest.raises(LinkedItemNotFound):
        lexicon_add(
            store, clock, random_source, surface="ghost", linked_item_id="word.nonexistent", program=program
        )
    assert _lexicon_events(store) == []


def test_topic_id_is_not_a_valid_link(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    with pytest.raises(LinkedItemNotFound):
        lexicon_add(
            store,
            clock,
            random_source,
            surface="be",
            linked_item_id="grammar.be.identity",
            program=program,
        )


def test_linked_entry_needs_program(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    with pytest.raises(LinkedItemNotFound):
        lexicon_add(store, clock, random_source, surface="feasible", linked_item_id="word.feasible")


# -- repeat encounters / dedup ----------------------------------------------


def test_retry_of_the_same_call_appends_no_second_event(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    lexicon_add(store, clock, random_source, surface="ubiquitous")
    lexicon_add(store, clock, random_source, surface="ubiquitous")
    assert len(_lexicon_events(store)) == 1


def test_re_encounter_of_linked_item_makes_no_second_record(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    session = make_session(store, clock)
    first = lexicon_encounter(
        store,
        clock,
        random_source,
        session,
        surface="feasible",
        linked_item_id="word.feasible",
        program=program,
        expected_session_revision=1,
        provider="codex",
    )
    revision = first["session_revision"]
    # A genuine later encounter of the same curriculum item (fresh, non-cached
    # call) still creates no second logical record and no second event.
    second = lexicon_encounter(
        store,
        clock,
        random_source,
        session,
        surface="Feasible",  # different surface spelling, same linked id
        linked_item_id="word.feasible",
        program=program,
        expected_session_revision=revision,
        provider="claude-code",
    )
    assert second["cached"] is True
    assert second["entry_id"] == first["entry_id"]
    assert len(_lexicon_events(store)) == 1
    # No fence bump on a de-duplicated re-encounter.
    found = read_aggregate(store._conn, "session", session)
    assert found is not None and found[1] == revision


def test_homonyms_with_distinct_ids_stay_separate(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    lexicon_add(
        store, clock, random_source, surface="engineer", linked_item_id="word.feasible", program=program
    )
    lexicon_add(
        store, clock, random_source, surface="engineer", linked_item_id="role.engineer", program=program
    )
    assert relevant_lexicon_targets(store) == frozenset({"word.feasible", "role.engineer"})
    assert len(lexicon_list(store)) == 2


# -- deterministic fold ------------------------------------------------------


def test_fold_order_is_deterministic(store: EventStore, clock: FixedClock, random_source: SeededRandomSource):
    for surface in ("gamma", "alpha", "beta"):
        clock.advance(seconds=1)
        lexicon_add(store, clock, random_source, surface=surface)
    order = [entry["surface"] for entry in lexicon_entries(store)]
    # Oldest first: added in gamma, alpha, beta order (by added_at then id).
    assert order == ["gamma", "alpha", "beta"]


def test_list_filters(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    lexicon_add(store, clock, random_source, surface="one")
    lexicon_add(
        store, clock, random_source, surface="feasible", linked_item_id="word.feasible", program=program
    )
    assert len(lexicon_list(store, source="learner")) == 2
    assert len(lexicon_list(store, source="encountered")) == 0
    assert [e["linked_item_id"] for e in lexicon_list(store, linked=True)] == ["word.feasible"]
    assert [e["surface"] for e in lexicon_list(store, linked=False)] == ["one"]


# -- enrollment is never evidence -------------------------------------------


def test_addition_never_changes_scoring(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, program: dict[str, Any]
):
    from english_trainer.scoring.engine import fold_scores, snapshot

    policy = _scoring_policy()
    before = snapshot(fold_scores(store, policy))
    lexicon_add(
        store,
        clock,
        random_source,
        surface="feasible",
        note_ru="осуществимый",
        linked_item_id="word.feasible",
        program=program,
    )
    after = snapshot(fold_scores(store, policy))
    assert before == after == {}  # no scoring target created by an enrollment


# -- session fence -----------------------------------------------------------


def test_session_bound_add_bumps_the_fence(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    session = make_session(store, clock)
    result = lexicon_add(
        store, clock, random_source, surface="cromulent", session_id=session, expected_session_revision=1
    )
    assert result["session_revision"] == 2
    found = read_aggregate(store._conn, "session", session)
    assert found is not None and found[1] == 2


def test_session_bound_add_needs_expected_revision(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    session = make_session(store, clock)
    with pytest.raises(LexiconEntryInvalid):
        lexicon_add(store, clock, random_source, surface="x", session_id=session)


def test_stale_session_revision_is_rejected_without_effect(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource
):
    session = make_session(store, clock)
    with pytest.raises(SessionRevisionConflict):
        lexicon_add(
            store, clock, random_source, surface="stale", session_id=session, expected_session_revision=99
        )
    assert _lexicon_events(store) == []
    found = read_aggregate(store._conn, "session", session)
    assert found is not None and found[1] == 1


def test_commit_failure_rolls_back_event_and_revision(
    store: EventStore,
    clock: FixedClock,
    random_source: SeededRandomSource,
    monkeypatch: pytest.MonkeyPatch,
):
    session = make_session(store, clock)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated failure between fence bump and append")

    # Fails inside the UnitOfWork, after bump_session ran: the UoW must roll
    # back BOTH the appended event and the revision bump (invariant 4).
    monkeypatch.setattr(lexicon_module, "make_event", boom)
    with pytest.raises(RuntimeError):
        lexicon_add(
            store, clock, random_source, surface="doomed", session_id=session, expected_session_revision=1
        )
    assert _lexicon_events(store) == []
    found = read_aggregate(store._conn, "session", session)
    assert found is not None and found[1] == 1  # revision untouched


# -- exact-match helper ------------------------------------------------------


def test_resolve_surface_exact(program: dict[str, Any]):
    assert resolve_surface_exact(program, "feasible") == "word.feasible"
    assert resolve_surface_exact(program, "FEASIBLE") == "word.feasible"
    assert resolve_surface_exact(program, "not-in-curriculum") is None
