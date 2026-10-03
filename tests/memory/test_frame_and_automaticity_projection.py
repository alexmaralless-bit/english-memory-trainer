"""Frames, automaticity and reconstruction texts in the Obsidian projection
(memory 0.6; lexical-system 1c; scoring 3d; curriculum 2d).

Uses the shared ``store``/``registry`` fixtures from ``conftest.py``: its
``PROGRAM`` carries one frame (``chunk.be-identity.im-a``, owned by
``grammar.be.identity``, with a full ``contrast``/``trap``/``carries``/``tier``
authoring shape) and one reconstruction text for the same topic, so both
sections have real data to render without a bespoke program per test.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.memory.engine import render_pages
from english_trainer.scoring.automaticity import AUTOMATICITY_KIND

FRAME_PAGE = "knowledge/chunks/chunk.be-identity.im-a.md"
TOPIC_PAGE = "topics/grammar.be.identity.md"


def _drill_block(
    *, target: str, session: str, correct: int = 6, total: int = 6, latency: int | None = 1000
) -> dict[str, Any]:
    """A drill-block ``evidence.added`` payload in the shape evidence 4.6 emits
    (same shape as ``tests/scoring/test_automaticity_axis.py``'s ``_block``)."""
    items = [
        {
            "index": index,
            "prompt_ref": f"x#item:{index}",
            "raw_answer": "a",
            "presented": True,
            "objective_correct": index < correct,
            "latency_ms": latency,
            "self_repaired": False,
        }
        for index in range(total)
    ]
    return {
        "evidence_id": f"{target}-{session}-{correct}",
        "session_id": session,
        "form": "drill_block",
        "mode": "controlled_production",
        "origin": "session",
        "assessment_basis": "objective_check",
        "primary_target": {"target_ref": target, "dimension": "controlled_production"},
        "credit_allocations": [
            {"target_ref": target, "dimension": "controlled_production", "contribution": "1.0", "used": True}
        ],
        "correct": True,
        "score_ppm": 1_000_000,
        "block_score_ppm": correct * 1_000_000 // total,
        "hints": 0,
        "response_latency_ms": None,
        "items": items,
    }


def _emit(
    store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    event_type: str,
    payload: dict[str, Any],
    pinned: dict[str, str] | None = None,
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=new_ulid(clock, rnd),
                    payload=payload,
                    pinned_versions=pinned,
                )
            ]
        )


# -- frame pages (lexical-system 1c) ------------------------------------------


def test_frame_page_carries_contrast_trap_slot_and_topic_link(
    store: EventStore, registry: PolicyRegistry
) -> None:
    page = render_pages(store, registry)[FRAME_PAGE]
    assert "я … (профессия/роль)" in page  # meaning_ru
    assert "название профессии или роли" in page  # slot_hint_ru
    assert "I'm a project manager." in page  # examples
    assert "`tense:present-simple`" in page
    assert "`article:indefinite-first-mention`" in page
    assert "I'm the ___" in page  # contrast frame
    assert "уже известна собеседнику" in page  # contrast note_ru
    assert "I'm project manager." in page  # trap learner_form
    assert "в русском перед названием профессии" in page  # trap cause_ru
    assert "Ярус: 2" in page
    assert "[[grammar.be.identity]]" in page  # link back to the owning topic


def test_topic_page_groups_its_frames_by_carries_tag(store: EventStore, registry: PolicyRegistry) -> None:
    page = render_pages(store, registry)[TOPIC_PAGE]
    assert "## Фреймы" in page
    assert "### article:indefinite-first-mention" in page
    assert "### tense:present-simple" in page
    assert "[[chunk.be-identity.im-a]]" in page
    assert "ярус 2" in page  # article-tier frame shows its tier next to the link


def test_non_frame_lexicon_page_has_no_frame_sections(store: EventStore, registry: PolicyRegistry) -> None:
    # `reaction.no-way` is an ordinary chunk (no `frame_of`): no contrast/trap
    # sections, no crash on the missing fields. Its type is `informal_chunk`,
    # which -- like `chunk` -- lands in the chunks zone (subdir picks on the
    # substring "chunk").
    page = render_pages(store, registry)["knowledge/chunks/reaction.no-way.md"]
    assert "## Контраст" not in page
    assert "## Ловушка" not in page
    assert "## Автоматизм" in page  # every target page still gets the axis


# -- reconstruction texts (curriculum 2d) -------------------------------------


def test_topic_page_lists_its_reconstruction_text(store: EventStore, registry: PolicyRegistry) -> None:
    page = render_pages(store, registry)[TOPIC_PAGE]
    assert "## Тексты для реконструкции" in page
    assert "text.recon.be-identity.roles" in page
    assert "Project roles" in page
    assert "work" in page
    assert "8 слов" in page


# -- automaticity (scoring 3d) -------------------------------------------------


def test_automaticity_block_is_not_measured_before_any_drill_block(
    store: EventStore, registry: PolicyRegistry
) -> None:
    page = render_pages(store, registry)[FRAME_PAGE]
    assert "## Автоматизм" in page
    assert "нет измерений автоматизма" in page
    dashboard = render_pages(store, registry)["current/automaticity.md"]
    assert "**not_measured**:" in dashboard


def test_automaticity_block_reaches_proceduralized_after_three_clean_blocks(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, random_source: SeededRandomSource
) -> None:
    for index in range(3):
        _emit(
            store,
            clock,
            random_source,
            "evidence.added",
            _drill_block(target="chunk.be-identity.im-a", session=f"s{index}"),
            pinned={AUTOMATICITY_KIND: "automaticity@1"},
        )
    pages = render_pages(store, registry)
    page = pages[FRAME_PAGE]
    assert "Состояние: **proceduralized**" in page
    assert "Точность: 100.00%" in page
    assert "3 блок(ов)" in page and "3 сесси(й)" in page
    assert "Latency: 1000 ms" in page

    dashboard = pages["current/automaticity.md"]
    assert "**proceduralized**: 1" in dashboard
    assert "[[chunk.be-identity.im-a]]" in dashboard

    # A second render over the same events is byte-identical -- no wall clock,
    # no re-derivation drift.
    assert render_pages(store, registry) == pages
