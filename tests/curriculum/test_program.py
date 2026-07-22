"""Curriculum module (2.1): loading the real program, total validation,
versioned registration and CAS activation with an atomic event."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from english_trainer.curriculum.loader import load_program, snapshot_payload
from english_trainer.curriculum.service import (
    CURRICULUM_KIND,
    activate_version,
    active_version,
    get_topic,
    lexicon_query,
    register_version,
)
from english_trainer.curriculum.validate import validate_program
from english_trainer.kernel.encoding import canonical_and_hash
from english_trainer.kernel.errors import StaleRevision
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

REPO = Path(__file__).resolve().parents[2]
CURRICULUM_DIR = REPO / "curriculum"


@pytest.fixture(scope="module")
def program() -> dict[str, Any]:
    return load_program(CURRICULUM_DIR)


# -- the real program ---------------------------------------------------------


def test_real_program_loads_completely(program: dict[str, Any]) -> None:
    assert len(program["levels"]) == 6
    assert len(program["tracks"]) == 10
    # Floors, not exact counts: the program grows in parallel deliveries
    # (P.1e adds B1-C2 skeletons); exact-count claims belong to per-delivery
    # handoff verification, not to a test that must stay green while
    # authoring is in flight.
    assert len(program["modules"]) >= 35
    assert len(program["topics"]) >= 155  # 153 A1-A2 bodies + B1+ skeletons
    assert len(program["lexicon"]) >= 886  # 838 + 48 word-formation additions (P.4d)
    assert {a["id"] for a in program["provenance"]["source_artifacts"]} == {
        "wordfreq@3.1.1",
        "ngsl@1.2",
        "bsl@1.2",
    }


def test_real_program_validates_clean(program: dict[str, Any]) -> None:
    report = validate_program(program)
    assert report.errors == []
    # The B1 skeletons are honestly unauthored -- warnings, never errors.
    assert any("not yet authored" in warning for warning in report.warnings)


def test_snapshot_is_canonical_and_deterministic(program: dict[str, Any]) -> None:
    payload = snapshot_payload(program)

    def no_floats(value: Any) -> bool:
        if isinstance(value, float):
            return False
        if isinstance(value, dict):
            return all(no_floats(v) for v in value.values())
        if isinstance(value, list):
            return all(no_floats(v) for v in value)
        return True

    assert no_floats(payload)  # the float ban holds at the snapshot boundary
    _, first = canonical_and_hash(payload)
    _, second = canonical_and_hash(snapshot_payload(load_program(CURRICULUM_DIR)))
    assert first == second  # same files, same snapshot hash


# -- synthetic violations -----------------------------------------------------


def _minimal_program() -> dict[str, Any]:
    criteria = {
        "schema_version": 1,
        "per_dimension": {
            "recognition": {"active_threshold": 70, "independent_attempts": 2},
            "transfer": {"active_threshold": 75, "independent_attempts": 2},
        },
        "mastered": {
            "all_required_active": True,
            "retention_stability_days": 30,
            "retention_confirmations": 2,
        },
    }
    return {
        "levels": [{"id": "A1", "can_do": "x"}, {"id": "B1", "can_do": "y"}],
        "tracks": [
            {"id": "grammar-engine", "title": "G", "from_level": "A1"},
            {"id": "toefl", "title": "T", "from_level": "B1"},
            {"id": "vocabulary-chunks", "title": "V", "from_level": "A1"},
        ],
        "modules": [
            {"id": "m1", "level": "A1", "can_do": "x", "tracks": ["grammar-engine"], "topics": ["t1"]}
        ],
        "topics": [
            {
                "id": "t1",
                "cefr": "A1",
                "track": "grammar-engine",
                "module": "m1",
                "can_do": "Do a thing.",
                "advisory_prerequisites": {},
                "dimensions": ["recognition", "transfer"],
                "frequency_tier": "core",
                "lexicon": ["w1"],
                "contexts": ["ctx"],
                "mastery_criteria": copy.deepcopy(criteria),
            }
        ],
        "lexicon": [
            {
                "id": "w1",
                "type": "word",
                "title": "thing",
                "cefr": "A1",
                "transformations": ["authored"],
            }
        ],
        "provenance": {"source_artifacts": [{"id": "wordfreq@3.1.1"}]},
    }


def test_minimal_program_is_valid() -> None:
    assert validate_program(_minimal_program()).errors == []


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda p: p["topics"].append(dict(p["topics"][0])), "duplicate topic id"),
        (lambda p: p["topics"][0].update(can_do="  "), "missing can_do"),
        (lambda p: p["topics"][0].update(track="ghost"), "unknown track"),
        (lambda p: p["topics"][0].update(track="toefl"), "below track floor"),
        (lambda p: p["topics"][0].update(track="vocabulary-chunks"), "lexicon-only"),
        (
            lambda p: p["topics"][0].update(advisory_prerequisites={"strong": ["ghost"]}),
            "dangling strong prerequisite",
        ),
        (lambda p: p["topics"][0].update(lexicon=["ghost"]), "dangling lexicon reference"),
        (lambda p: p["topics"][0].update(frequency_tier="mega"), "needs frequency_tier"),
        (lambda p: p["topics"][0].update(dimensions=[]), "empty or missing dimensions"),
        (lambda p: p["topics"][0]["mastery_criteria"]["per_dimension"].pop("transfer"), "cover"),
        (
            lambda p: p["lexicon"].append(
                {"id": "c1", "type": "chunk", "title": "on it", "transformations": ["authored"]}
            ),
            "without valid transparency",
        ),
        (
            lambda p: p["lexicon"].append(
                {
                    "id": "i1",
                    "type": "idiom",
                    "title": "piece of cake",
                    "transparency": "opaque",
                    "transformations": ["authored"],
                }
            ),
            "without literal_trap_ru",
        ),
        (lambda p: p["lexicon"][0].update(frequency_band="high"), "frequency fields without source_refs"),
        (lambda p: p["lexicon"][0].update(source_refs=["ghost@1"]), "not in provenance manifest"),
        (lambda p: p["lexicon"][0].update(transformations=["invented"]), "unknown transformation"),
        (
            lambda p: p["lexicon"][0].update(formation={"affix": "un-", "base": "", "affix_type": "prefix"}),
            "formation needs affix and base",
        ),
        (
            lambda p: p["lexicon"][0].update(
                formation={"affix": "un-", "base": "thing", "affix_type": "inside"}
            ),
            "affix_type must be",
        ),
        # Phase markers are banned from the program [PD-2026-07-22]: a stale
        # deferral once entered an activated snapshot and its hash.
        (lambda p: p["tracks"][0].update(phase="[post-mvp]"), "phase fields are banned"),
        (lambda p: p["tracks"][0].update(note="deferred to psot-beta"), "phase marker"),
        (lambda p: p["topics"][0].update(can_do="Do this later (post-mvp)."), "phase marker"),
    ],
)
def test_validator_catches_each_violation(mutate: Any, fragment: str) -> None:
    program = _minimal_program()
    mutate(program)
    report = validate_program(program)
    assert any(fragment in error for error in report.errors), report.errors


def test_validator_catches_cycles_and_level_inversions() -> None:
    program = _minimal_program()
    second = copy.deepcopy(program["topics"][0])
    second.update(id="t2", advisory_prerequisites={"soft": ["t1"]})
    program["modules"][0]["topics"].append("t2")
    program["topics"].append(second)
    program["topics"][0]["advisory_prerequisites"] = {"strong": ["t2"]}  # t1 -> t2 -> t1
    report = validate_program(program)
    assert any("cycle" in error for error in report.errors)

    program = _minimal_program()
    high = copy.deepcopy(program["topics"][0])
    high.update(id="t9", cefr="B1", track="grammar-engine", module="m9")
    program["modules"].append({"id": "m9", "level": "B1", "can_do": "x", "tracks": [], "topics": ["t9"]})
    program["topics"].append(high)
    program["topics"][0]["advisory_prerequisites"] = {"strong": ["t9"]}
    report = validate_program(program)
    assert any("higher level" in error for error in report.errors)


# -- service: versioning and activation --------------------------------------


def test_register_and_pinned_resolve_roundtrip(store: EventStore, clock, program: dict[str, Any]) -> None:
    registry = PolicyRegistry(store._conn, clock)
    register_version(registry, program, "v1")
    resolved = registry.resolve_pinned(CURRICULUM_KIND, "v1")
    assert len(resolved["topics"]) == len(program["topics"])  # the pin returns exactly what went in
    assert resolved["schema_version"] == 1


def test_activation_is_cas_and_atomic_with_its_event(store: EventStore, clock, random_source) -> None:
    program = _minimal_program()
    registry = PolicyRegistry(store._conn, clock)
    register_version(registry, program, "v1")

    event = activate_version(store, registry, clock, random_source, "v1", expected_active=None)
    assert event is not None
    assert active_version(registry) == "v1"
    assert event.payload == {"version": "v1", "previous": None}
    assert event.pinned_versions == {"curriculum": "v1"}
    assert store._conn.execute("SELECT COUNT(*) AS n FROM outbox;").fetchone()["n"] == 1

    # Replay of the same request: correct expectation, same version -> no-op.
    assert activate_version(store, registry, clock, random_source, "v1", expected_active="v1") is None
    assert store.count() == 1  # no second activation event

    # Stale expectation: refused, nothing changes.
    register_version(registry, program, "v2")
    with pytest.raises(StaleRevision):
        activate_version(store, registry, clock, random_source, "v2", expected_active=None)
    assert active_version(registry) == "v1"
    assert store.count() == 1

    # Correct CAS moves the pointer and records the previous version.
    event2 = activate_version(store, registry, clock, random_source, "v2", expected_active="v1")
    assert event2 is not None and event2.payload == {"version": "v2", "previous": "v1"}
    assert active_version(registry) == "v2"


# -- reads --------------------------------------------------------------------


def test_get_topic_and_lexicon_query(program: dict[str, Any]) -> None:
    topic = get_topic(program, "grammar.present-perfect.result")
    assert topic is not None and topic["frequency_tier"] == "big-five"
    assert get_topic(program, "ghost") is None

    idioms = lexicon_query(program, item_type="idiom", limit=5)
    assert len(idioms) == 5
    assert all(item["type"] == "idiom" for item in idioms)
    assert [i["id"] for i in idioms] == sorted(i["id"] for i in idioms)  # deterministic order
