"""Placement forms as a curriculum data kind (flows/placement; Д15): loading
from ``curriculum/assessments``, the snapshot hash, and total validation --
structural rules as errors, the authoring coverage floors as warnings.

Every rule is exercised on a minimal in-memory form (positive and negative), so
a failure names the rule rather than the authored corpus. One live-data test
validates whatever forms are actually authored under ``curriculum/``.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.curriculum.loader import load_program, rubric_profile_refs, snapshot_payload
from english_trainer.curriculum.validate import validate_program
from english_trainer.kernel.encoding import canonical_and_hash

REPO = Path(__file__).resolve().parents[2]
CURRICULUM_DIR = REPO / "curriculum"
RUBRIC_REFS = frozenset({"rubric:production.spontaneous"})

PASSAGE = (
    "The platform team ships a new dashboard every Thursday. Last week the release was late "
    "because a vendor tool stopped sending data on Tuesday afternoon, and nobody noticed until "
    "the morning stand-up. The team added an alert that pages the on-call engineer when the feed "
    "goes quiet for more than ten minutes. Since then the dashboard has been on time twice in a "
    "row, and the manager asked the team to write a short note about the change so that other "
    "teams can copy it, which is still a draft today."
)


def _topic(topic_id: str, track: str = "grammar-engine") -> dict[str, Any]:
    return {
        "id": topic_id,
        "cefr": "A1",
        "track": track,
        "module": "m1",
        "frequency_tier": "core",
        "can_do": "I can do the thing.",
        "dimensions": ["recognition"],
        "mastery_criteria": {"per_dimension": {"recognition": {"threshold": 70}}},
        "contexts": ["project-update"],
        "lexicon": [],
    }


def _form(**overrides: Any) -> dict[str, Any]:
    form: dict[str, Any] = {
        "schema_version": 1,
        "form_version": "placement-test-a@1",
        "title": "Placement test A",
        "target_minutes": 35,
        "sections": ["grammar", "reading", "writing"],
        "passages": [{"passage_id": "p-a1-1", "cefr": "A1", "title": "Dashboard release", "text": PASSAGE}],
        "items": [
            {
                "item_id": "g-a1-01",
                "section": "grammar",
                "band": "A1",
                "kind": "choice",
                "target_ref": "grammar.forms-topic",
                "dimension": "recognition",
                "prompt": "I ___ an engineer on the platform team.",
                "options": ["am", "is", "are", "be"],
                "answer_key": ["am"],
            },
            {
                "item_id": "g-a1-02",
                "section": "grammar",
                "band": "A1",
                "kind": "cloze",
                "target_ref": "grammar.forms-topic",
                "dimension": "controlled_production",
                "prompt": "We ___ (finish) the migration already.",
                "answer_key": ["have finished", "'ve finished"],
            },
            {
                "item_id": "r-a1-01",
                "section": "reading",
                "band": "A1",
                "kind": "true_false",
                "passage_id": "p-a1-1",
                "target_ref": "reading.forms-topic",
                "dimension": "recognition",
                "prompt": "The vendor fixed the issue before the demo.",
                "answer_key": ["false"],
            },
            {
                "item_id": "w-a1-01",
                "section": "writing",
                "band": "A1",
                "kind": "writing",
                "target_ref": "written.forms-topic",
                "dimension": "spontaneous_production",
                "prompt": "Introduce yourself to a new team.",
                "rubric_ref": "rubric:production.spontaneous",
                "min_words": 60,
                "max_words": 120,
            },
        ],
    }
    form.update(overrides)
    return form


def _frame(index: int, topic_id: str) -> dict[str, Any]:
    """A frame of the grammar topic: the frame floor is unrelated to forms, but
    a Grammar Engine topic without frames would fail validation for that reason
    and hide the rule under test."""
    return {
        "id": f"chunk.forms.f{index}",
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


def _program(forms: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    topics = [
        _topic("grammar.forms-topic"),
        _topic("reading.forms-topic", "reading"),
        _topic("written.forms-topic", "written-production-mediation"),
    ]
    frames = [_frame(index, "grammar.forms-topic") for index in range(12)]
    topics[0]["lexicon"] = [frame["id"] for frame in frames]
    return {
        "levels": [{"id": "A1"}],
        "tracks": [
            {"id": "grammar-engine", "from_level": "A1"},
            {"id": "reading", "from_level": "A1"},
            {"id": "written-production-mediation", "from_level": "A1"},
        ],
        "modules": [
            {
                "id": "m1",
                "level": "A1",
                "tracks": ["grammar-engine", "reading", "written-production-mediation"],
                "topics": [topic["id"] for topic in topics],
            }
        ],
        "topics": topics,
        "lexicon": frames,
        "texts": [],
        "placement_forms": [_form()] if forms is None else forms,
        "provenance": {"source_artifacts": []},
    }


def _errors(program: dict[str, Any]) -> list[str]:
    return validate_program(program, rubric_refs=RUBRIC_REFS).errors


def _broken(mutate: Any) -> list[str]:
    form = _form()
    mutate(form)
    return _errors(_program([form]))


def _item(form: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(item for item in form["items"] if item["item_id"] == item_id)


# -- loading and the snapshot -------------------------------------------------


def test_forms_load_from_the_assessments_directory_sorted(tmp_path: Path) -> None:
    (tmp_path / "levels.yaml").write_text("levels: []", encoding="utf-8")
    (tmp_path / "tracks.yaml").write_text("tracks: []", encoding="utf-8")
    forms_dir = tmp_path / "assessments"
    forms_dir.mkdir()
    for name, version in (("placement-b.yaml", "placement-b@1"), ("placement-a.yaml", "placement-a@1")):
        (forms_dir / name).write_text(
            yaml.safe_dump({**_form(), "form_version": version}, allow_unicode=True), encoding="utf-8"
        )
    (forms_dir / "_draft.yaml").write_text("form_version: draft@1", encoding="utf-8")

    program = load_program(tmp_path)
    # File order is deterministic, and a leading underscore stays out.
    assert [form["form_version"] for form in program["placement_forms"]] == [
        "placement-a@1",
        "placement-b@1",
    ]


def test_a_missing_assessments_directory_is_tolerated(tmp_path: Path) -> None:
    (tmp_path / "levels.yaml").write_text("levels: []", encoding="utf-8")
    (tmp_path / "tracks.yaml").write_text("tracks: []", encoding="utf-8")
    assert load_program(tmp_path)["placement_forms"] == []


def test_forms_enter_the_snapshot_hash() -> None:
    base = _program()
    changed = copy.deepcopy(base)
    _item(changed["placement_forms"][0], "g-a1-01")["prompt"] = "She ___ an engineer."
    without = copy.deepcopy(base)
    without["placement_forms"] = []

    base_hash = canonical_and_hash(snapshot_payload(base))[1]
    assert base_hash != canonical_and_hash(snapshot_payload(changed))[1]
    assert base_hash != canonical_and_hash(snapshot_payload(without))[1]


# -- the clean form -----------------------------------------------------------


def test_a_well_formed_program_validates() -> None:
    assert _errors(_program()) == []


def test_coverage_floors_are_warnings_not_errors() -> None:
    report = validate_program(_program(), rubric_refs=RUBRIC_REFS)
    assert report.ok  # a partially authored form still activates
    assert any("coverage floor is 8" in warning for warning in report.warnings)
    assert any("has no passage of its own" in warning for warning in report.warnings)


def test_repeated_targets_inside_a_band_are_warned_about() -> None:
    report = validate_program(_program(), rubric_refs=RUBRIC_REFS)
    # Both A1 grammar items aim at the same topic: two items, one distinct target.
    assert any("tests 1 distinct target(s) with 2 items" in warning for warning in report.warnings)


# -- structural rules ---------------------------------------------------------


def test_schema_version_must_be_one() -> None:
    assert any("schema_version must be 1" in e for e in _broken(lambda f: f.update(schema_version=2)))


@pytest.mark.parametrize("version", ["core-a@1", "placement-core-a", "placement-Core@1"])
def test_form_version_pattern_is_enforced(version: str) -> None:
    errors = _broken(lambda f: f.update(form_version=version))
    assert any("form_version must match" in e for e in errors)


def test_duplicate_form_versions_are_refused() -> None:
    errors = _errors(_program([_form(), _form()]))
    assert any("duplicate placement form_version" in e for e in errors)


def test_a_missing_title_or_bad_duration_is_an_error() -> None:
    assert any("missing title" in e for e in _broken(lambda f: f.update(title=" ")))
    assert any("target_minutes" in e for e in _broken(lambda f: f.update(target_minutes=0)))


def test_unknown_sections_are_refused() -> None:
    errors = _broken(lambda f: f.update(sections=["grammar", "listening"]))
    assert any("unknown section 'listening'" in e for e in errors)


def test_duplicate_item_ids_are_refused() -> None:
    def mutate(form: dict[str, Any]) -> None:
        form["items"].append({**_item(form, "g-a1-01")})

    assert any("duplicate item_id g-a1-01" in e for e in _broken(mutate))


def test_the_item_id_pattern_follows_section_and_band() -> None:
    errors = _broken(lambda f: _item(f, "g-a1-01").update(item_id="gram-a1-1"))
    assert any("item_id must match g-a1-<nn>" in e for e in errors)


def test_c2_is_not_placed() -> None:
    errors = _broken(lambda f: _item(f, "g-a1-01").update(band="C2"))
    assert any("band must be one of" in e for e in errors)


def test_kinds_are_closed() -> None:
    errors = _broken(lambda f: _item(f, "g-a1-01").update(kind="matching"))
    assert any("kind must be one of" in e for e in errors)


def test_a_dangling_target_ref_is_refused() -> None:
    errors = _broken(lambda f: _item(f, "g-a1-01").update(target_ref="grammar.nope"))
    assert any("is neither a topic nor a lexical item" in e for e in errors)


def test_a_lexical_target_resolves() -> None:
    program = _program()
    program["lexicon"].append({"id": "chunk.core.kick-off", "type": "chunk", "transparency": "transparent"})
    _item(program["placement_forms"][0], "g-a1-01")["target_ref"] = "chunk.core.kick-off"
    assert _errors(program) == []


def test_dimension_is_checked_per_kind() -> None:
    objective = _broken(lambda f: _item(f, "g-a1-01").update(dimension="spontaneous_production"))
    assert any("dimension must be one of" in e for e in objective)
    writing = _broken(lambda f: _item(f, "w-a1-01").update(dimension="recognition"))
    assert any("writing dimension must be spontaneous_production" in e for e in writing)


def test_choice_needs_four_options_with_exactly_one_correct() -> None:
    three = _broken(lambda f: _item(f, "g-a1-01").update(options=["am", "is", "are"]))
    assert any("exactly 4 non-empty options" in e for e in three)
    repeated = _broken(lambda f: _item(f, "g-a1-01").update(options=["am", "am", "are", "be"]))
    assert any("options must be distinct" in e for e in repeated)
    none_correct = _broken(lambda f: _item(f, "g-a1-01").update(answer_key=["was"]))
    assert any("exactly one option must equal an answer_key entry" in e for e in none_correct)
    two_correct = _broken(lambda f: _item(f, "g-a1-01").update(answer_key=["am", "is"]))
    assert any("exactly one option must equal an answer_key entry" in e for e in two_correct)


def test_objective_items_need_a_non_empty_answer_key() -> None:
    assert any(
        "answer_key must be a non-empty list" in e
        for e in _broken(lambda f: _item(f, "g-a1-02").update(answer_key=[]))
    )


def test_true_false_keys_are_closed() -> None:
    errors = _broken(lambda f: _item(f, "r-a1-01").update(answer_key=["maybe"]))
    assert any("true_false answer_key must be true|false" in e for e in errors)


def test_a_reading_item_must_reference_a_declared_passage() -> None:
    missing = _broken(lambda f: _item(f, "r-a1-01").pop("passage_id"))
    assert any("must name its passage_id" in e for e in missing)
    unknown = _broken(lambda f: _item(f, "r-a1-01").update(passage_id="p-zz-9"))
    assert any("is not declared by the form" in e for e in unknown)


def test_passage_length_and_language_are_checked() -> None:
    short = _broken(lambda f: f["passages"][0].update(text="Too short."))
    assert any("words, outside 60-160" in e for e in short)
    cyrillic = _broken(lambda f: f["passages"][0].update(text=PASSAGE + " Конец."))
    assert any("must be English only" in e for e in cyrillic)


def test_duplicate_passage_ids_are_refused() -> None:
    errors = _broken(lambda f: f["passages"].append(dict(f["passages"][0])))
    assert any("duplicate passage_id" in e for e in errors)


def test_a_writing_item_needs_a_resolvable_rubric_and_a_word_range() -> None:
    unknown = _broken(lambda f: _item(f, "w-a1-01").update(rubric_ref="rubric:nope"))
    assert any("does not resolve in rubric@1" in e for e in unknown)
    missing = _broken(lambda f: _item(f, "w-a1-01").pop("rubric_ref"))
    assert any("needs a rubric_ref" in e for e in missing)
    inverted = _broken(lambda f: _item(f, "w-a1-01").update(min_words=120, max_words=60))
    assert any("word range must be" in e for e in inverted)


def test_rubric_refs_are_only_checked_when_the_policy_is_available() -> None:
    form = _form()
    _item(form, "w-a1-01")["rubric_ref"] = "rubric:unknown-profile"
    assert validate_program(_program([form])).ok  # no rubric policy passed in


def test_phase_markers_are_banned_in_forms() -> None:
    errors = _broken(lambda f: _item(f, "g-a1-01").update(prompt="I ___ an engineer [MVP]"))
    assert any("phase marker" in e for e in errors)


# -- parity with the authoring checker and the live corpus --------------------


def test_the_authoring_checker_accepts_the_clean_form(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "check_authoring_forms", REPO / "tools" / "check_authoring.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    path = tmp_path / "placement-test-a.yaml"
    path.write_text(yaml.safe_dump(_form(), allow_unicode=True), encoding="utf-8")
    assert module.check_file(path) == []

    broken = _form()
    _item(broken, "g-a1-01")["options"] = ["am", "is", "are"]
    path.write_text(yaml.safe_dump(broken, allow_unicode=True), encoding="utf-8")
    assert any("4 distinct options" in problem for problem in module.check_file(path))


def test_the_authored_forms_validate() -> None:
    """Whatever is authored under curriculum/assessments must be activatable."""
    program = load_program(CURRICULUM_DIR)
    report = validate_program(program, rubric_refs=rubric_profile_refs(CURRICULUM_DIR))
    assert report.errors == []
