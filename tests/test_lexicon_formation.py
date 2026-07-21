"""Formation invariants (P.4d, PD-2026-07-21): the generating link
"affix + base -> word" must be well-formed and honest -- a fake derivation
would teach a false pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR = REPO_ROOT / "curriculum" / "lexicon"
TOPICS_DIR = REPO_ROOT / "curriculum" / "topics"

AFFIX_TYPES = {"prefix", "suffix"}
# The affix families the word-formation topics teach (P.1d + P.4d).
TAUGHT_AFFIXES = {
    "un-",
    "re-",
    "mis-",
    "dis-",
    "over-",
    "under-",
    "out-",
    "-er",
    "-tion",
    "-ment",
    "-able",
    "-ness",
}


@pytest.fixture(scope="module")
def lexicon() -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for path in sorted(LEXICON_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        for item in yaml.safe_load(path.read_text(encoding="utf-8"))["lexical_items"]:
            items[item["id"]] = item
    return items


@pytest.fixture(scope="module")
def formation_items(lexicon: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item_id: item for item_id, item in lexicon.items() if "formation" in item}


def test_formation_coverage_is_substantial(formation_items: dict[str, dict[str, Any]]) -> None:
    # 48 new items + 18 marked existing ones; a regression that silently drops
    # the field must fail loudly.
    assert len(formation_items) >= 66


def test_formation_shape_and_surface_consistency(formation_items: dict[str, dict[str, Any]]) -> None:
    offenders: list[str] = []
    for item_id, item in formation_items.items():
        formation = item["formation"]
        affix = str(formation.get("affix") or "")
        base = str(formation.get("base") or "")
        affix_type = formation.get("affix_type")
        title = str(item.get("title") or "")
        if not affix or not base:
            offenders.append(f"{item_id}: empty affix/base")
            continue
        if affix_type not in AFFIX_TYPES:
            offenders.append(f"{item_id}: affix_type {affix_type!r}")
            continue
        if affix not in TAUGHT_AFFIXES:
            offenders.append(f"{item_id}: affix {affix!r} is not taught by any word-formation topic")
        # The surface word must actually carry the affix on the right side --
        # otherwise the "generating link" is a lie about the word's shape.
        stem = affix.strip("-")
        if affix_type == "prefix" and not title.startswith(stem):
            offenders.append(f"{item_id}: prefix {affix} not visible in {title!r}")
        if affix_type == "suffix" and not title.endswith(stem):
            offenders.append(f"{item_id}: suffix {affix} not visible in {title!r}")
        if base == title:
            offenders.append(f"{item_id}: base equals the derived word")
    assert not offenders


def test_word_formation_topics_reference_formation_marked_items(
    formation_items: dict[str, dict[str, Any]],
    lexicon: dict[str, dict[str, Any]],
) -> None:
    # The topics teaching the patterns must point at items that carry the
    # pattern; a placeholder ref would make the lesson exhibit nothing.
    for name in ("a1.yaml", "a2.yaml"):
        for topic in yaml.safe_load((TOPICS_DIR / name).read_text(encoding="utf-8"))["topics"]:
            if topic["track"] != "word-formation":
                continue
            refs = topic.get("lexicon", [])
            assert refs, f"{topic['id']}: no lexicon refs"
            for reference in refs:
                assert reference in lexicon, f"{topic['id']}: dangling {reference}"
                assert reference in formation_items, f"{topic['id']}: {reference} carries no formation field"


def test_new_items_have_no_invented_frequencies(lexicon: dict[str, dict[str, Any]]) -> None:
    # P.4b rule: frequency fields require corpus provenance. The P.4d additions
    # had no corpus pass, so they must carry neither score nor band.
    for item_id, item in lexicon.items():
        if "formation" in item and "corpus-enriched" not in item.get("transformations", []):
            assert item.get("frequency_score") is None, item_id
            assert item.get("frequency_band") is None, item_id
