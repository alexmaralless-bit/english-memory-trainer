"""The personal-lexicon page of the Obsidian projection (memory 0.6; learner §4).

A readable projection of layer 3: it names entries, says plainly that adding a
word is enrollment and not knowledge, and re-renders byte-identically.
"""

from __future__ import annotations

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.learner.lexicon import lexicon_add
from english_trainer.memory.engine import render_pages

_PAGE = "knowledge/personal-lexicon.md"


def test_personal_lexicon_page_is_empty_but_present(store: EventStore, registry: PolicyRegistry) -> None:
    pages = render_pages(store, registry)
    assert _PAGE in pages
    assert "пока пусто" in pages[_PAGE]


def test_personal_lexicon_page_lists_entries_and_marks_enrollment(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, random_source: SeededRandomSource
) -> None:
    lexicon_add(
        store,
        clock,
        random_source,
        surface="feasible",
        note_ru="осуществимый",
        source="encountered",
        linked_item_id="reaction.no-way",  # any active LexicalItem id resolves
        program={"topics": [], "lexicon": [{"id": "reaction.no-way"}]},
    )
    lexicon_add(store, clock, random_source, surface="blorptastic")
    page = render_pages(store, registry)[_PAGE]
    assert "feasible" in page and "blorptastic" in page
    # The page is explicit that this is enrollment, not evidence.
    assert "не знание" in page or "enrollment" in page
    # A linked entry points at its curriculum item; an unlinked one says so.
    assert "[[reaction.no-way]]" in page
    assert "нет в программе" in page


def test_page_bytes_are_deterministic(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, random_source: SeededRandomSource
) -> None:
    lexicon_add(store, clock, random_source, surface="serendipity")
    first = render_pages(store, registry)[_PAGE]
    second = render_pages(store, registry)[_PAGE]
    assert first == second  # re-rendering unchanged state is byte-identical
