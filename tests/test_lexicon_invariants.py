"""Invariants the lexicon data must satisfy, as stated in the contracts.

These do not need network access or the corpus package: they check the
committed data against wiki/modules/curriculum.md 3.2 and
wiki/product/lexical-system.md 1. Reproducing the frequency values
themselves is a separate, network-bound check:

    python tools/enrich_lexicon.py --cache <dir outside repo> --check
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR = REPO_ROOT / "curriculum" / "lexicon"
TOPICS_DIR = REPO_ROOT / "curriculum" / "topics"

# Closed vocabulary, curriculum contract 3.2. Extending it is a contract edit.
TRANSFORMATIONS = {
    "identity",
    "authored",
    "corpus-enriched",
    "lemma-form-sum",
    "reclassified-from-chunk",
}
REQUIRED_FIELDS = ("type", "title", "cefr", "curriculum_priority_band", "register", "meaning_ru")
MULTI_WORD_TYPES = {"chunk", "phrasal-verb", "informal_chunk"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def items() -> list[dict]:
    out: list[dict] = []
    for path in sorted(LEXICON_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        out.extend(_load(path)["lexical_items"])
    return out


@pytest.fixture(scope="module")
def declared_artifacts() -> set[str]:
    return {a["id"] for a in _load(LEXICON_DIR / "_provenance.yaml")["source_artifacts"]}


@pytest.fixture(scope="module")
def topic_ids() -> set[str]:
    return {t["id"] for path in TOPICS_DIR.glob("*.yaml") for t in _load(path)["topics"]}


@pytest.fixture(scope="module")
def links() -> list[dict]:
    return _load(LEXICON_DIR / "_suggested-topic-links.yaml")["links"]


def test_ids_are_unique(items):
    seen = [i["id"] for i in items]
    assert len(seen) == len(set(seen)), "duplicate lexical item ids"


def test_required_fields_present(items):
    missing = [(i["id"], f) for i in items for f in REQUIRED_FIELDS if not i.get(f)]
    assert not missing


def test_every_item_has_its_own_example(items):
    assert not [i["id"] for i in items if not i.get("examples")]


def test_transformations_use_the_closed_vocabulary(items):
    unknown = {t for i in items for t in i.get("transformations", [])} - TRANSFORMATIONS
    assert not unknown, f"tokens outside the contract vocabulary: {sorted(unknown)}"


def test_frequency_always_carries_provenance(items):
    """A derived frequency without source_refs is unverifiable and therefore invalid."""
    assert not [i["id"] for i in items if "frequency_score" in i and not i.get("source_refs")]


def test_source_refs_point_at_declared_artifacts(items, declared_artifacts):
    dangling = {r for i in items for r in i.get("source_refs", [])} - declared_artifacts
    assert not dangling, f"source_refs naming artifacts absent from _provenance.yaml: {sorted(dangling)}"


def test_multi_word_units_carry_no_frequency(items):
    """A word corpus does not observe phrase frequencies; a composed estimate is not one.

    See the P.4b report: reversing the word order leaves the estimate unchanged.
    """
    offenders = [
        i["id"]
        for i in items
        if "frequency_score" in i and (i["type"] in MULTI_WORD_TYPES or " " in str(i["title"]))
    ]
    assert not offenders


def test_common_words_are_never_incidental(items):
    """INCIDENTAL excludes a unit from review entirely; corpus-common units must not sit there."""
    offenders = [
        i["id"]
        for i in items
        if i["curriculum_priority_band"] == "INCIDENTAL" and i.get("frequency_band") in {"very_high", "high"}
    ]
    assert not offenders


def test_advisory_links_resolve(items, links, topic_ids):
    known = {i["id"] for i in items}
    assert not [ln["lexical_item"] for ln in links if ln["lexical_item"] not in known]
    assert not sorted({t for ln in links for t in ln["topics"] if t not in topic_ids})


def test_chunks_and_priority_items_have_an_advisory_link(items, links):
    linked = {ln["lexical_item"] for ln in links}
    unlinked = [
        i["id"]
        for i in items
        if i["id"] not in linked
        and (i["type"] == "chunk" or i["curriculum_priority_band"] in {"CORE", "HIGH"})
    ]
    assert not unlinked


def test_every_a1_a2_module_has_at_least_five_work_frames(items, links):
    by_id = {i["id"]: i for i in items}
    module_of = {
        t["id"]: t["module"]
        for path in TOPICS_DIR.glob("*.yaml")
        for t in _load(path)["topics"]
        if t["cefr"] in {"A1", "A2"}
    }
    per_module: dict[str, set[str]] = {}
    for link in links:
        if by_id.get(link["lexical_item"], {}).get("type") != "chunk":
            continue
        for topic in link["topics"]:
            if topic not in module_of:
                continue
            per_module.setdefault(module_of[topic], set()).add(link["lexical_item"])
    thin = {m: len(c) for m, c in per_module.items() if len(c) < 5}
    assert not thin
    assert len(per_module) == 16, f"expected all 16 A1-A2 modules covered, got {len(per_module)}"
