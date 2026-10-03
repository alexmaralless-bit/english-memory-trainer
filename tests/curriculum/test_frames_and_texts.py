"""Automaticity layer in the curriculum module (curriculum 2c, 2d; Д1)
[PD-2026-09-22]: frames (``frame_of``/``carries``/``tier``/``contrast``/``trap``
plus the per-topic frame floor) and reconstruction texts -- loading, the
versioned snapshot, total validation and the per-topic read.

Every rule is exercised on a minimal in-memory program (positive and negative),
so a failure names the rule, not the authored corpus. One live-data smoke test
keeps the real ``curriculum/`` honest about parsing and resolvable ``frame_of``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.curriculum.carries import CARRIES, FRAME_FLOOR_BY_TIER
from english_trainer.curriculum.loader import load_program, snapshot_payload
from english_trainer.curriculum.service import texts_for_topic
from english_trainer.curriculum.validate import validate_program
from english_trainer.kernel.encoding import canonical_and_hash

REPO = Path(__file__).resolve().parents[2]
CURRICULUM_DIR = REPO / "curriculum"
FRAMES_GLOB = "frames-*.yaml"


# -- minimal program fixtures -------------------------------------------------


def _topic(topic_id: str, *, frequency_tier: str = "core") -> dict[str, Any]:
    return {
        "id": topic_id,
        "cefr": "A1",
        "track": "grammar-engine",
        "module": "m1",
        "frequency_tier": frequency_tier,
        "can_do": "I can do the thing.",
        "dimensions": ["recognition"],
        "mastery_criteria": {"per_dimension": {"recognition": {"threshold": 70}}},
        "contexts": ["project-update"],
        "lexicon": [],
    }


def _frame(slug: str, topic_id: str, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"chunk.frames.{slug}",
        "type": "chunk",
        "title": "I've already ___",
        "cefr": "A1",
        "curriculum_priority_band": "CORE",
        "register": "neutral",
        "transparency": "transparent",
        "domains": ["work"],
        "meaning_ru": "я уже …",
        "frame_of": topic_id,
        "carries": ["tense:present-perfect"],
        "examples": ["I've already sent the report.", "I've already had lunch."],
        "transformations": ["authored"],
    }
    item.update(overrides)
    return item


def _text(**overrides: Any) -> dict[str, Any]:
    body = (
        "Quick update on the migration for the team this week. We have moved four "
        "of the six tables to the new cluster without downtime. The export job "
        "failed on Tuesday, so the ticket has already been escalated to the vendor "
        "for a proper fix. I have tested the workaround on staging twice and it "
        "holds under the usual load. The last two tables are the largest ones, so "
        "we will document the whole plan before the end of the week for everyone."
    )
    text: dict[str, Any] = {
        "schema_version": 1,
        "id": "text.recon.frames-topic.migration-update",
        "title": "Migration update",
        "cefr": "A1",
        "topic": "grammar.frames-topic",
        "carries": ["tense:present-perfect"],
        "domain": "work",
        "context": "deployment-update",
        "text": body,
        "word_count": len(body.split()),
        "keywords": ["update", "four of six", "export failed", "ticket", "vendor", "workaround"],
        "target_spans": ["have moved", "has already been escalated", "have tested", "will document"],
        "summary_ru": "Апдейт по миграции.",
        "transformations": ["authored"],
    }
    text.update(overrides)
    if "word_count" not in overrides and "text" in overrides:
        text["word_count"] = len(str(overrides["text"]).split())
    return text


def _program(
    *,
    lexicon: list[dict[str, Any]] | None = None,
    texts: list[dict[str, Any]] | None = None,
    frequency_tier: str = "core",
    frames: int | None = None,
) -> dict[str, Any]:
    """A program that validates clean unless a test breaks one field."""
    topic_id = "grammar.frames-topic"
    floor = FRAME_FLOOR_BY_TIER[frequency_tier] if frames is None else frames
    items = lexicon if lexicon is not None else [_frame(f"f{n}", topic_id) for n in range(floor)]
    for index, item in enumerate(items):
        item.setdefault("id", f"chunk.frames.auto{index}")
    topic = _topic(topic_id, frequency_tier=frequency_tier)
    # topic.lexicon owns the link; frame_of mirrors it (curriculum 2c), so the
    # clean fixture carries both directions -- as tools/link_frames.py leaves them.
    topic["lexicon"] = [str(item["id"]) for item in items if item.get("frame_of") == topic_id]
    return {
        "levels": [{"id": "A1"}],
        "tracks": [{"id": "grammar-engine", "from_level": "A1"}],
        "modules": [{"id": "m1", "level": "A1", "tracks": ["grammar-engine"], "topics": [topic_id]}],
        "topics": [topic],
        "lexicon": items,
        "texts": texts if texts is not None else [],
        "provenance": {"source_artifacts": []},
    }


def _errors(program: dict[str, Any]) -> list[str]:
    return validate_program(program).errors


def test_minimal_program_is_clean() -> None:
    assert _errors(_program()) == []
    assert _errors(_program(texts=[_text()])) == []


# -- carries vocabulary -------------------------------------------------------


def test_carries_vocabulary_matches_the_authoring_checker() -> None:
    """The checker content authors run and the validator must never drift."""
    spec = importlib.util.spec_from_file_location(
        "check_authoring_under_test", REPO / "tools" / "check_authoring.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.CARRIES) == set(CARRIES)


def test_unknown_carries_tag_is_an_error() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["carries"] = ["tense:present-perfekt"]
    errors = _errors(_program(lexicon=frames))
    assert any("unknown carries tag 'tense:present-perfekt'" in error for error in errors)


@pytest.mark.parametrize("carries", [[], ["tense:past-simple"] * 4, "tense:past-simple"])
def test_carries_cardinality_is_enforced(carries: Any) -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["carries"] = carries
    errors = _errors(_program(lexicon=frames))
    assert any("carries must be a list of 1-3 tags" in error for error in errors)


def test_carries_without_frame_of_is_allowed() -> None:
    """An existing chunk may carry a fixed article without becoming a frame."""
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames.append(
        {
            "id": "chunk.work.at-the-end-of-the-day",
            "type": "chunk",
            "transparency": "transparent",
            "carries": ["article:fixed-expression"],
        }
    )
    assert _errors(_program(lexicon=frames)) == []


# -- frames -------------------------------------------------------------------


def test_frame_of_requires_chunk_type() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["type"] = "word"
    errors = _errors(_program(lexicon=frames))
    assert any("frame_of requires type chunk" in error for error in errors)


def test_frame_of_must_resolve() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["frame_of"] = "grammar.nowhere"
    errors = _errors(_program(lexicon=frames))
    assert any("frame_of names unknown topic grammar.nowhere" in error for error in errors)


def test_frame_of_requires_carries() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    del frames[0]["carries"]
    errors = _errors(_program(lexicon=frames))
    assert any("frame_of without carries" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [("frequency_score", 12), ("frequency_band", "top-2k"), ("source_refs", ["ngsl@1.2"])],
)
def test_frames_carry_no_corpus_fields(field: str, value: Any) -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0][field] = value
    errors = _errors(_program(lexicon=frames))
    assert any(f"frame must not carry {field}" in error for error in errors)


@pytest.mark.parametrize("tier", [0, 3, "1", True])
def test_tier_must_be_one_or_two(tier: Any) -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["tier"] = tier
    errors = _errors(_program(lexicon=frames))
    assert any("tier must be 1 or 2" in error for error in errors)


def test_valid_tier_is_accepted() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["tier"] = 1
    frames[1]["tier"] = 2
    assert _errors(_program(lexicon=frames)) == []


@pytest.mark.parametrize(
    ("field", "broken"),
    [
        ("contrast", {"frame": "I ___ yesterday"}),
        ("contrast", {"frame": " ", "note_ru": "…"}),
        ("trap", {"learner_form": "I have already send.", "correction": "I've already sent."}),
        ("trap", ["not", "a", "mapping"]),
    ],
)
def test_contrast_and_trap_need_their_keys(field: str, broken: Any) -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0][field] = broken
    errors = _errors(_program(lexicon=frames))
    assert any(f"{field} needs" in error for error in errors)


def test_complete_contrast_and_trap_are_accepted() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    frames[0]["contrast"] = {"frame": "I ___ yesterday", "note_ru": "законченное время → Past Simple"}
    frames[0]["trap"] = {
        "learner_form": "I have already send the report.",
        "correction": "I've already sent the report.",
        "cause_ru": "после have нужна третья форма",
    }
    assert _errors(_program(lexicon=frames)) == []


def test_frame_must_be_listed_in_its_topic_lexicon() -> None:
    """The link is owned by topic.lexicon; frame_of alone is half a link."""
    program = _program()
    orphan = program["topics"][0]["lexicon"].pop()
    errors = _errors(program)
    assert [error for error in errors if orphan in error] == [
        f"lexical item {orphan}: frame_of is grammar.frames-topic, but grammar.frames-topic "
        f"does not list {orphan} in its lexicon (run tools/link_frames.py)"
    ]


def test_topic_may_not_list_a_frame_of_another_topic() -> None:
    program = _program()
    program["topics"][0]["lexicon"].append("chunk.elsewhere.borrowed")
    program["lexicon"].append(
        _frame("borrowed", "grammar.frames-topic", id="chunk.elsewhere.borrowed", frame_of="grammar.other")
    )
    program["topics"].append(_topic("grammar.other"))
    program["modules"][0]["topics"].append("grammar.other")
    expected = (
        "topic grammar.frames-topic: lexicon lists frame chunk.elsewhere.borrowed, "
        "whose frame_of is grammar.other"
    )
    assert expected in _errors(program)


def test_non_frame_lexicon_references_are_untouched_by_the_back_link_rule() -> None:
    program = _program()
    program["lexicon"].append({"id": "word.thing", "type": "word", "title": "thing"})
    program["topics"][0]["lexicon"].append("word.thing")
    assert _errors(program) == []


@pytest.mark.parametrize(("tier", "floor"), [("big-five", 12), ("core", 12), ("tail", 8)])
def test_frame_floor_per_frequency_tier(tier: str, floor: int) -> None:
    assert _errors(_program(frequency_tier=tier)) == []
    errors = _errors(_program(frequency_tier=tier, frames=floor - 1))
    assert any(f"{floor - 1} frames authored, {tier} needs at least {floor}" in error for error in errors)


def test_frame_floor_ignores_non_grammar_tracks() -> None:
    program = _program(frames=0)
    program["tracks"] = [{"id": "grammar-engine", "from_level": "A1"}, {"id": "reading", "from_level": "A1"}]
    program["topics"][0]["track"] = "reading"
    program["modules"][0]["tracks"] = ["reading"]
    assert not any("frames authored" in error for error in _errors(program))


# -- reconstruction texts -----------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"schema_version": 2}, "schema_version must be 1"),
        ({"schema_version": None}, "schema_version must be 1"),
        ({"id": "recon.migration"}, "id must match text.recon"),
        ({"id": "text.recon.Frames.Migration"}, "id must match text.recon"),
        ({"topic": "grammar.nowhere"}, "unknown topic"),
        ({"also_targets": ["grammar.nowhere"]}, "is neither a topic nor a lexical item"),
        ({"carries": []}, "carries must name at least one tag"),
        ({"carries": ["tense:nope"]}, "unknown carries tag"),
        ({"domain": "hobby"}, "domain must be one of"),
        ({"context": "Deployment Update"}, "context must be a kebab id"),
        ({"word_count": 999}, "!= actual"),
        ({"text": "Too short."}, "outside 45-150"),
        ({"summary_ru": "  "}, "missing summary_ru"),
        ({"transformations": ["invented"]}, "unknown transformation"),
        ({"keywords": ["one", "two"]}, "keywords must be 6-14 cues"),
        ({"keywords": [f"cue {n}" for n in range(15)]}, "keywords must be 6-14 cues"),
        ({"target_spans": ["have moved"]}, "target_spans must be 4-12 substrings"),
        (
            {"target_spans": ["have moved", "has already been escalated", "have tested", "we has done"]},
            "target span not found verbatim",
        ),
    ],
)
def test_text_rules(overrides: dict[str, Any], fragment: str) -> None:
    errors = _errors(_program(texts=[_text(**overrides)]))
    assert any(fragment in error for error in errors), errors


def test_text_body_must_be_english_only() -> None:
    body = ("Migration update for the team. " * 10) + "Мы перенесли таблицы."
    errors = _errors(_program(texts=[_text(text=body)]))
    assert any("text must be English only" in error for error in errors)


def test_duplicate_text_ids_are_rejected() -> None:
    errors = _errors(_program(texts=[_text(), _text()]))
    assert any("duplicate reconstruction text id" in error for error in errors)


def test_text_also_targets_may_name_a_lexical_item() -> None:
    frames = [_frame(f"f{n}", "grammar.frames-topic") for n in range(12)]
    program = _program(lexicon=frames, texts=[_text(also_targets=[frames[0]["id"]])])
    assert _errors(program) == []


def test_text_phase_markers_are_rejected() -> None:
    errors = _errors(_program(texts=[_text(title="Migration update [mvp]")]))
    assert any("phase marker" in error for error in errors)


def test_program_without_texts_key_still_validates() -> None:
    """Historical snapshots predate the reconstruction corpus."""
    program = _program()
    del program["texts"]
    assert _errors(program) == []
    assert texts_for_topic(program, "grammar.frames-topic") == []


# -- loading, snapshot and the per-topic read ---------------------------------


def test_loader_reads_texts_and_stamps_schema_version(tmp_path: Path) -> None:
    root = tmp_path / "curriculum"
    (root / "texts" / "reconstruction").mkdir(parents=True)
    (root / "levels.yaml").write_text("levels: []", encoding="utf-8")
    (root / "tracks.yaml").write_text("tracks: []", encoding="utf-8")
    for name, slug in (("b.yaml", "beta"), ("a.yaml", "alpha")):
        (root / "texts" / "reconstruction" / name).write_text(
            yaml.safe_dump(
                {"schema_version": 1, "texts": [{"id": f"text.recon.topic.{slug}", "topic": "grammar.t"}]}
            ),
            encoding="utf-8",
        )
    program = load_program(root)
    # Sorted file order, and the file-level schema_version reaches every entry.
    assert [text["id"] for text in program["texts"]] == [
        "text.recon.topic.alpha",
        "text.recon.topic.beta",
    ]
    assert {text["schema_version"] for text in program["texts"]} == {1}


def test_loader_tolerates_a_missing_texts_directory(tmp_path: Path) -> None:
    root = tmp_path / "curriculum"
    root.mkdir()
    (root / "levels.yaml").write_text("levels: []", encoding="utf-8")
    (root / "tracks.yaml").write_text("tracks: []", encoding="utf-8")
    assert load_program(root)["texts"] == []


def test_texts_are_part_of_the_versioned_snapshot() -> None:
    without = snapshot_payload(_program())
    with_texts = snapshot_payload(_program(texts=[_text()]))
    assert with_texts["texts"]
    assert canonical_and_hash(without)[1] != canonical_and_hash(with_texts)[1]


def test_texts_for_topic_is_deterministic_and_topic_scoped() -> None:
    second = _text(id="text.recon.frames-topic.alpha-update")
    other = _text(id="text.recon.other.something", topic="grammar.other")
    program = _program(texts=[_text(), second, other])
    assert [text["id"] for text in texts_for_topic(program, "grammar.frames-topic")] == [
        "text.recon.frames-topic.alpha-update",
        "text.recon.frames-topic.migration-update",
    ]
    assert texts_for_topic(program, "grammar.nobody") == []


# -- live data smoke ----------------------------------------------------------


def test_live_frames_parse_and_resolve() -> None:
    program = load_program(CURRICULUM_DIR)
    topic_ids = {topic.get("id") for topic in program["topics"]}
    frames = [item for item in program["lexicon"] if item.get("frame_of")]
    assert frames, "no frames authored in curriculum/lexicon/frames-*.yaml"
    assert [path.name for path in sorted((CURRICULUM_DIR / "lexicon").glob(FRAMES_GLOB))]
    dangling = sorted(str(item.get("id")) for item in frames if item.get("frame_of") not in topic_ids)
    assert dangling == []
    uncovered = sorted(
        str(item.get("id"))
        for item in frames
        if not 1 <= len(item.get("carries") or []) <= 3
        or any(tag not in CARRIES for tag in item.get("carries") or [])
    )
    assert uncovered == []


def test_live_frames_are_linked_from_their_topics() -> None:
    """The owner's tools/link_frames.py post-pass keeps both directions equal."""
    program = load_program(CURRICULUM_DIR)
    topics = {str(topic.get("id")): topic for topic in program["topics"]}
    unlinked = sorted(
        str(item.get("id"))
        for item in program["lexicon"]
        if item.get("frame_of") in topics
        and item.get("id") not in (topics[str(item.get("frame_of"))].get("lexicon") or [])
    )
    assert unlinked == []


def test_live_frames_files_parse_individually() -> None:
    for path in sorted((CURRICULUM_DIR / "lexicon").glob(FRAMES_GLOB)):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict) and loaded.get("lexical_items"), path.name


# -- the permanent interleaved tier (scheduler 3a, PD-F) --------------------


def test_permanent_interleave_targets_selects_exactly_the_article_frames() -> None:
    """The one place that knows the rule, checked against the shipped lexicon.

    The scheduler and every projection take this set as an injected value, so
    a silent change here would silently change which targets never leave the
    review queue.
    """
    from english_trainer.curriculum.service import (
        ARTICLE_FRAME_TOPIC_PREFIX,
        permanent_interleave_targets,
    )

    program = load_program(CURRICULUM_DIR)
    targets = permanent_interleave_targets(program)
    by_id = {str(unit["id"]): unit for unit in program["lexicon"]}
    assert targets, "the shipped lexicon authors article-tier frames"
    for target_ref in targets:
        unit = by_id[target_ref]
        assert unit["type"] == "chunk"
        assert str(unit["frame_of"]).startswith(ARTICLE_FRAME_TOPIC_PREFIX)
    # Nothing outside the tier slipped in, and nothing inside it was missed.
    expected = {
        str(unit["id"])
        for unit in program["lexicon"]
        if str(unit.get("frame_of") or "").startswith(ARTICLE_FRAME_TOPIC_PREFIX)
    }
    assert targets == expected
    # A snapshot without a lexicon (a historical program) classifies nothing.
    assert permanent_interleave_targets({"topics": []}) == frozenset()


def test_the_memory_projection_uses_the_same_article_prefix() -> None:
    """``memory`` cannot import ``curriculum`` (layer allowlist), so it spells
    the prefix itself; this guards the two copies against drifting apart."""
    from english_trainer.curriculum.service import ARTICLE_FRAME_TOPIC_PREFIX
    from english_trainer.memory.engine import _ARTICLE_FRAME_PREFIX

    assert _ARTICLE_FRAME_PREFIX == ARTICLE_FRAME_TOPIC_PREFIX
