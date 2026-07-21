"""Body-level invariants for A1-A2 curriculum topics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR = REPO_ROOT / "curriculum" / "lexicon"
TOPICS_DIR = REPO_ROOT / "curriculum" / "topics"

BIG_FIVE_GRAMMAR_TOPIC_IDS = {
    "grammar.present-simple.routines",
    "grammar.do-questions",
    "grammar.frequency-adverbs",
    "grammar.present-continuous.status",
    "grammar.present-simple-continuous.choice",
    "grammar.past-simple.events",
    "grammar.past-simple.negatives-questions",
    "grammar.past-irregular-basics",
    "grammar.past-time-sequencing",
    "grammar.past-irregular-events",
    "grammar.will.basic-decisions",
    "grammar.future-time-expressions",
    "grammar.future-forms.planning",
    "grammar.future-expressions.deadlines",
    "grammar.present-perfect.result",
    "grammar.past-participle.forms",
    "grammar.present-perfect-past-simple.choice",
}
# Frequent non-tense grammar (PD-2026-07-21, P.2 review): full dimensions and
# big-five-level priority. The first, binary tier model pushed these into
# recognition-only, contradicting their productive can_do statements.
CORE_GRAMMAR_TOPIC_IDS = {
    "grammar.be.identity",
    "grammar.pronouns.possessives",
    "grammar.basic-word-order",
    "grammar.articles.identity",
    "grammar.time-dates",
    "grammar.there-is-are.systems",
    "grammar.have-has.objects",
    "grammar.nouns-singular-plural",
    "grammar.demonstratives.references",
    "grammar.quantifiers.basic",
    "grammar.prepositions.location",
    "grammar.can-cant.ability-requests",
    "grammar.imperatives.instructions",
    "grammar.basic-questions.clarification",
    "grammar.going-to.plans",
    "grammar.prepositions.time",
    "grammar.here-is-are.presenting",
    "grammar.sequencing.delivery",
    "grammar.modals.requirements",
    "grammar.comparatives.options",
    "grammar.superlatives.selection",
    "grammar.quantifiers.requirements",
    "grammar.connectors.cause-contrast",
}
# Rare verb forms only: recognition + transfer at the home level; production
# arrives with their B1-B2 continuations (the can_do names the target ability).
TAIL_GRAMMAR_TOPIC_IDS = {
    "grammar.zero-conditional.processes",
    "grammar.first-conditional.troubleshooting",
    "grammar.passive.basic-process",
    "grammar.past-continuous.incident-context",
    "grammar.when-while.sequence",
}
FULL_GRAMMAR_DIMENSIONS = {
    "recognition",
    "controlled_production",
    "spontaneous_production",
    "transfer",
}
TAIL_GRAMMAR_DIMENSIONS = {"recognition", "transfer"}
TIER_BY_TOPIC_ID = (
    dict.fromkeys(BIG_FIVE_GRAMMAR_TOPIC_IDS, "big-five")
    | dict.fromkeys(CORE_GRAMMAR_TOPIC_IDS, "core")
    | dict.fromkeys(TAIL_GRAMMAR_TOPIC_IDS, "tail")
)
REQUIRED_BODY_FIELDS = {
    "contexts",
    "dimensions",
    "examples",
    "explanation_language",
    "lexicon",
    "mastery_criteria",
    "typical_errors",
}
EXPECTED_THRESHOLDS = {
    "recognition": 70,
    "controlled_production": 75,
    "spontaneous_production": 75,
    "transfer": 75,
}


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def topics() -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for path in (TOPICS_DIR / "a1.yaml", TOPICS_DIR / "a2.yaml"):
        loaded.extend(_load(path)["topics"])
    return loaded


@pytest.fixture(scope="module")
def lexicon_by_id() -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for path in sorted(LEXICON_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        for item in _load(path)["lexical_items"]:
            items[item["id"]] = item
    return items


def test_all_a1_a2_topics_have_body_fields(topics: list[dict[str, Any]]) -> None:
    missing = {topic["id"]: sorted(REQUIRED_BODY_FIELDS - set(topic)) for topic in topics}
    assert not {topic_id: fields for topic_id, fields in missing.items() if fields}


def test_topic_body_lists_are_non_empty_and_specific(topics: list[dict[str, Any]]) -> None:
    offenders: list[tuple[str, str]] = []
    for topic in topics:
        if not topic["contexts"]:
            offenders.append((topic["id"], "contexts"))
        if not topic["lexicon"]:
            offenders.append((topic["id"], "lexicon"))
        if len(topic["examples"]) < 2:
            offenders.append((topic["id"], "examples"))
        if not 3 <= len(topic["typical_errors"]) <= 5:
            offenders.append((topic["id"], "typical_errors"))
        if topic["explanation_language"] != "ru-allowed":
            offenders.append((topic["id"], "explanation_language"))
    assert not offenders


def test_mastery_criteria_cover_exactly_required_dimensions(topics: list[dict[str, Any]]) -> None:
    offenders: list[str] = []
    for topic in topics:
        dimensions = set(topic["dimensions"])
        criteria = topic["mastery_criteria"]
        per_dimension = criteria.get("per_dimension", {})
        if criteria.get("schema_version") != 1:
            offenders.append(f"{topic['id']}: schema_version")
        if set(per_dimension) != dimensions:
            offenders.append(f"{topic['id']}: per_dimension")
        for dimension in dimensions:
            dimension_criteria = per_dimension.get(dimension, {})
            if dimension_criteria.get("active_threshold") != EXPECTED_THRESHOLDS[dimension]:
                offenders.append(f"{topic['id']}: {dimension} active_threshold")
            if dimension_criteria.get("independent_attempts") != 2:
                offenders.append(f"{topic['id']}: {dimension} independent_attempts")
        mastered = criteria.get("mastered", {})
        if mastered.get("all_required_active") is not True:
            offenders.append(f"{topic['id']}: all_required_active")
        if mastered.get("retention_stability_days") != 30:
            offenders.append(f"{topic['id']}: retention_stability_days")
        if mastered.get("retention_confirmations") != 2:
            offenders.append(f"{topic['id']}: retention_confirmations")
    assert not offenders


def test_grammar_frequency_tiers_match_required_dimensions(topics: list[dict[str, Any]]) -> None:
    offenders: list[str] = []
    grammar_topics = [topic for topic in topics if topic["track"] == "grammar-engine"]
    for topic in grammar_topics:
        topic_id = topic["id"]
        tier = topic.get("frequency_tier")
        dimensions = set(topic["dimensions"])
        expected_tier = TIER_BY_TOPIC_ID.get(topic_id)
        if expected_tier is None:
            offenders.append(f"{topic_id}: not classified in any tier set")
            continue
        if tier != expected_tier:
            offenders.append(f"{topic_id}: frequency_tier={tier!r}, expected {expected_tier!r}")
        expected_dimensions = TAIL_GRAMMAR_DIMENSIONS if expected_tier == "tail" else FULL_GRAMMAR_DIMENSIONS
        if dimensions != expected_dimensions:
            offenders.append(f"{topic_id}: dimensions={sorted(dimensions)}")
    assert not offenders


def test_tier_sets_partition_the_grammar_track(topics: list[dict[str, Any]]) -> None:
    # The three classification sets must cover the grammar track exactly: an
    # unclassified topic or a stale entry for a removed topic both fail loudly.
    grammar_ids = {topic["id"] for topic in topics if topic["track"] == "grammar-engine"}
    classified = set(TIER_BY_TOPIC_ID)
    assert grammar_ids == classified, (
        f"unclassified={sorted(grammar_ids - classified)}, stale={sorted(classified - grammar_ids)}"
    )
    total = len(BIG_FIVE_GRAMMAR_TOPIC_IDS) + len(CORE_GRAMMAR_TOPIC_IDS) + len(TAIL_GRAMMAR_TOPIC_IDS)
    assert total == len(TIER_BY_TOPIC_ID)  # the three sets are disjoint


def test_topic_lexicon_references_resolve(
    topics: list[dict[str, Any]],
    lexicon_by_id: dict[str, dict[str, Any]],
) -> None:
    dangling = {
        reference for topic in topics for reference in topic["lexicon"] if reference not in lexicon_by_id
    }
    assert not dangling


def test_opaque_lexicon_is_not_required_for_production_topics(
    topics: list[dict[str, Any]],
    lexicon_by_id: dict[str, dict[str, Any]],
) -> None:
    offenders = [
        (topic["id"], reference)
        for topic in topics
        if "controlled_production" in topic["dimensions"]
        for reference in topic["lexicon"]
        if lexicon_by_id[reference].get("transparency") == "opaque"
    ]
    assert not offenders


def test_vocabulary_and_chunks_remains_lexicon_only(topics: list[dict[str, Any]]) -> None:
    assert not [topic["id"] for topic in topics if topic["track"] == "vocabulary-chunks"]
