"""Authored-form fixtures for the placement tests.

Forms are curriculum data now (``curriculum/assessments/*.yaml``), so every
test that needs one carries it here as an explicit, loadable fixture -- the
engine ships no embedded form.

Two fixtures live here:

- :data:`STUB_FORM` -- the six-item form the pre-curriculum increment embedded
  in ``assessments/forms.py``. Kept verbatim (including its legacy
  ``objective`` kind) so the lifecycle, exposure and ceiling tests written
  against it keep asserting exactly what they asserted before.
- :data:`FULL_FORM` -- a small but *measurable* form: five distinct topics per
  band per objective skill, which clears every per-skill floor of the
  placement-derived working level (scoring@2 ``placement.min_topics_by_skill``),
  plus one rubric writing item for the provisional writing rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]

# -- the legacy embedded stub -------------------------------------------------

STUB_FORM: dict[str, Any] = {
    "form_version": "placement-en-core@1",
    "seed": "placement-en-core@1",
    "sections": ["grammar", "vocabulary", "reading", "writing"],
    "items": [
        {
            "item_id": "g-be-1",
            "section": "grammar",
            "kind": "objective",
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "I ___ an engineer.",
            "answer_key": ["am"],
        },
        {
            "item_id": "g-be-2",
            "section": "grammar",
            "kind": "objective",
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "She ___ my manager.",
            "answer_key": ["is"],
        },
        {
            "item_id": "g-be-3",
            "section": "grammar",
            "kind": "objective",
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "They ___ on my team.",
            "answer_key": ["are"],
        },
        {
            "item_id": "v-greeting-1",
            "section": "vocabulary",
            "kind": "objective",
            "target_ref": "vocabulary.core.greeting",
            "dimension": "recognition",
            "prompt": "A common informal greeting is ___.",
            "answer_key": ["hi", "hello"],
        },
        {
            "item_id": "r-gist-1",
            "section": "reading",
            "kind": "objective",
            "target_ref": "reading.gist.short",
            "dimension": "recognition",
            "prompt": "'The meeting is at noon.' -- The meeting is in the morning. (true/false)",
            "answer_key": ["false"],
        },
        {
            "item_id": "w-sentence-1",
            "section": "writing",
            "kind": "writing",
            "target_ref": "writing.sentence.simple",
            "dimension": "spontaneous_production",
            "prompt": "Write one sentence introducing yourself to a new team.",
            "rubric_ref": "rubric:placement-writing-provisional",
        },
    ],
}

STUB_FORM_VERSION = str(STUB_FORM["form_version"])


def stub_program() -> dict[str, Any]:
    """The smallest program that carries the stub form."""
    return {"placement_forms": [STUB_FORM], "topics": [], "lexicon": []}


# -- a measurable, fully authored-shaped form ---------------------------------

PASSAGE_TEXT = (
    "The platform team ships a new dashboard every Thursday. Last week the release was late "
    "because a vendor tool stopped sending data on Tuesday afternoon, and nobody noticed until "
    "the morning stand-up. The team added an alert that pages the on-call engineer when the feed "
    "goes quiet for more than ten minutes. Since then the dashboard has been on time twice in a "
    "row, and the manager asked the team to write a short note about the change so that other "
    "teams can copy it. The note is still a draft, but it already lists the alert, the owner and "
    "the steps to follow when the feed stops again during a holiday week."
)

GRAMMAR_A1 = [f"grammar.fixture.a1-{index}" for index in range(1, 6)]
GRAMMAR_A2 = [f"grammar.fixture.a2-{index}" for index in range(1, 6)]
READING_A2 = [f"reading.fixture.a2-{index}" for index in range(1, 6)]
VOCABULARY_A2 = [f"chunk.fixture.a2-{index}" for index in range(1, 6)]
WRITING_A2 = "written.fixture.a2-note"


def _grammar_items(band: str, targets: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        items.append(
            {
                "item_id": f"g-{band.lower()}-{index:02d}",
                "section": "grammar",
                "band": band,
                "kind": "choice" if index % 2 else "cloze",
                "target_ref": target,
                "dimension": "recognition" if index % 2 else "controlled_production",
                "prompt": f"The team ___ the {band} report on {index} Monday.",
                **({"options": ["writes", "write", "writing", "wrote"]} if index % 2 else {}),
                "answer_key": ["writes"],
            }
        )
    return items


FULL_FORM: dict[str, Any] = {
    "schema_version": 1,
    "form_version": "placement-fixture-a@1",
    "title": "Placement fixture A",
    "target_minutes": 20,
    "sections": ["grammar", "vocabulary", "reading", "writing"],
    "passages": [
        {
            "passage_id": "p-a2-1",
            "cefr": "A2",
            "title": "Dashboard release",
            "text": PASSAGE_TEXT,
        }
    ],
    "items": [
        *_grammar_items("A1", GRAMMAR_A1),
        *_grammar_items("A2", GRAMMAR_A2),
        *[
            {
                "item_id": f"v-a2-{index:02d}",
                "section": "vocabulary",
                "band": "A2",
                "kind": "choice",
                "target_ref": target,
                "dimension": "recognition",
                "prompt": f"Pick the phrase that means 'to start item {index}'.",
                "options": ["kick off", "kick out", "kick in", "kick over"],
                "answer_key": ["kick off"],
            }
            for index, target in enumerate(VOCABULARY_A2, start=1)
        ],
        *[
            {
                "item_id": f"r-a2-{index:02d}",
                "section": "reading",
                "band": "A2",
                "kind": "true_false",
                "passage_id": "p-a2-1",
                "target_ref": target,
                "dimension": "recognition",
                "prompt": f"Statement {index}: the release was late last week.",
                "answer_key": ["true"],
            }
            for index, target in enumerate(READING_A2, start=1)
        ],
        {
            "item_id": "w-a2-01",
            "section": "writing",
            "band": "A2",
            "kind": "writing",
            "target_ref": WRITING_A2,
            "dimension": "spontaneous_production",
            "prompt": "Write a short note to your new team about what you work on.",
            "rubric_ref": "rubric:production.spontaneous",
            "min_words": 60,
            "max_words": 120,
        },
    ],
}

FULL_FORM_VERSION = str(FULL_FORM["form_version"])

#: Every objective item of the fixture form answered correctly, by section.
FULL_FORM_CORRECT: dict[str, dict[str, str]] = {
    "grammar": {item["item_id"]: "writes" for item in FULL_FORM["items"] if item["section"] == "grammar"},
    "vocabulary": {item["item_id"]: "a" for item in FULL_FORM["items"] if item["section"] == "vocabulary"},
    "reading": {item["item_id"]: "да" for item in FULL_FORM["items"] if item["section"] == "reading"},
}


def _topic(topic_id: str, cefr: str, track: str, dimensions: list[str]) -> dict[str, Any]:
    return {
        "id": topic_id,
        "cefr": cefr,
        "track": track,
        "dimensions": dimensions,
        "contexts": ["placement"],
        "lexicon": [],
    }


def full_program() -> dict[str, Any]:
    """A program whose topics/lexicon resolve every target of the fixture form."""
    return {
        "schema_version": 1,
        "levels": [],
        "tracks": [],
        "modules": [],
        "topics": [
            *[_topic(t, "A1", "grammar-engine", ["recognition"]) for t in GRAMMAR_A1],
            *[
                _topic(t, "A2", "grammar-engine", ["recognition", "controlled_production"])
                for t in GRAMMAR_A2
            ],
            *[_topic(t, "A2", "reading", ["recognition"]) for t in READING_A2],
            _topic(WRITING_A2, "A2", "written-production-mediation", ["spontaneous_production"]),
        ],
        "lexicon": [
            {"id": unit, "type": "chunk", "cefr": "A2", "transparency": "transparent"}
            for unit in VOCABULARY_A2
        ],
        "texts": [],
        "placement_forms": [FULL_FORM],
        "provenance": {},
    }


def policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# -- rubric observations for the writing item ---------------------------------

WRITING_ANSWER = (
    "Hi team, I am the new backend engineer on the platform group. I mostly work on the data "
    "pipeline that feeds the release dashboard, and I also help with on-call rotations. Before "
    "this I worked on billing services for four years, so I know that area well. This week I am "
    "reading the runbooks and pairing with Maria on the alerting change. Please ping me if you "
    "need anything from the pipeline side, and I will answer as soon as I can."
)


#: One accepted positive finding per required criterion: enough to settle the
#: fragment, and under ``rubric@1`` that is level 2 of 3 on every criterion.
_ADEQUATE_FINDINGS: tuple[tuple[str, str], ...] = (
    ("target-control", "target_used_in_required_function"),
    ("meaning-clarity", "main_message_is_recoverable"),
    ("context-adaptation", "target_is_adapted_to_new_context"),
    ("language-control", "well_formed_clause"),
    ("independent-expression", "learner_adds_independent_clause"),
)

#: Every required criterion at level 3 (``rubric@1`` caps the raw level at 3
#: units): the accepted findings that add up to a 1_000_000 ppm fragment, which
#: is what the provisional writing rule asks for
#: (``scoring@2 placement.writing.provisional_threshold_ppm``).
_STRONG_FINDINGS: tuple[tuple[str, str], ...] = (
    *_ADEQUATE_FINDINGS,
    ("target-control", "target_surface_present"),
    ("meaning-clarity", "reference_is_clear"),
    ("context-adaptation", "context_specific_detail_is_relevant"),
    ("language-control", "well_formed_clause"),
    ("language-control", "well_formed_clause"),
    ("independent-expression", "learner_adds_relevant_detail"),
)


def _observations(findings: tuple[tuple[str, str], ...], answer: str) -> list[dict[str, Any]]:
    """Accepted positive findings over real, distinct spans of ``answer``.

    The spans are real slices with their real hashes -- the engine validates
    both, so a fabricated observation would be rejected -- and each occurrence
    gets its own span, because the reducer counts distinct occurrences.
    """
    from english_trainer.evidence.assessment import span_hash

    profile = "production.spontaneous"
    assert len(answer.encode("utf-8")) > 60
    observations: list[dict[str, Any]] = []
    for index, (criterion_id, finding_code) in enumerate(findings):
        start = index * 10
        end = start + 20
        observations.append(
            {
                "rubric_criterion_ref": f"rubric:{profile}#criterion:{criterion_id}",
                "finding_code": finding_code,
                "span_ref": {
                    "start_utf8": start,
                    "end_utf8": end,
                    "span_hash": span_hash(answer, start, end),
                },
            }
        )
    return observations


def writing_observations(answer: str = WRITING_ANSWER) -> list[dict[str, Any]]:
    """An adequate fragment: one positive finding per required criterion."""
    return _observations(_ADEQUATE_FINDINGS, answer)


def strong_writing_observations(answer: str = WRITING_ANSWER) -> list[dict[str, Any]]:
    """A strong fragment: every required criterion at the top level."""
    return _observations(_STRONG_FINDINGS, answer)


def activate_fixture_curriculum(
    root: Path,
    program: dict[str, Any] | None = None,
    *,
    version: str = "placement-fixture@1",
    policies: tuple[str, ...] = ("scoring-v2.yaml", "rubric-v1.yaml"),
) -> None:
    """Activate a fixture program (and its policies) in an initialized root.

    The CLI resolves the placement form from the ACTIVE curriculum snapshot, so
    a CLI-level placement test needs one; registering the fixture directly keeps
    the test independent of the authored program under ``curriculum/``.
    """
    from english_trainer.curriculum.service import activate_version, register_version
    from english_trainer.kernel.clock import SystemClock, SystemRandom
    from english_trainer.kernel.policy import PolicyRegistry
    from english_trainer.kernel.store import EventStore, connect
    from english_trainer.storage.layout import resolve_layout

    layout = resolve_layout(root)
    conn = connect(layout.db)
    try:
        clock, random_source = SystemClock(), SystemRandom()
        registry = PolicyRegistry(conn, clock)
        store = EventStore(conn)
        register_version(registry, program or full_program(), version)
        activate_version(store, registry, clock, random_source, version, expected_active=None)
        for filename in policies:
            payload = policy(filename)
            registry.register(str(payload["policy_id"]).split("@")[0], str(payload["policy_id"]), payload)
            registry.activate(str(payload["policy_id"]).split("@")[0], str(payload["policy_id"]))
    finally:
        conn.close()
