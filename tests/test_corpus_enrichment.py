"""Focused regression tests for the pinned P.4e NAWL corpus pass."""

from __future__ import annotations

from tools.enrich_lexicon import enrich_line, load_lemma_families


def test_nawl_windows_1252_teaching_file_decodes() -> None:
    data = "café,cafés\nanalysis,analyses\n".encode("cp1252")

    assert load_lemma_families(data) == {"café", "cafés", "analysis", "analyses"}


def test_nawl_membership_is_recorded_beside_wordfreq_frequency() -> None:
    line = (
        "  - {id: word.thesis, type: word, title: thesis, cefr: B2, "
        "curriculum_priority_band: CORE, register: formal, domains: [academic-writing], "
        'meaning_ru: "тезис", examples: ["The thesis answers the question."], '
        "transformations: [authored]}"
    )

    enriched = enrich_line(
        line,
        zipf_of=lambda _word: 4.75,
        freq_of=lambda _word: 0.0,
        thresholds=[
            {"band": "high", "min_zipf": 4.5},
            {"band": "mid", "min_zipf": None},
        ],
        ngsl=set(),
        bsl=set(),
        nawl={"thesis"},
        covered_types={"word"},
        stats={},
    )

    assert "frequency_score: 4.75" in enriched
    assert "frequency_band: high" in enriched
    assert "source_refs: [wordfreq@3.1.1, nawl@1.2]" in enriched
    assert "transformations: [authored, corpus-enriched]" in enriched
