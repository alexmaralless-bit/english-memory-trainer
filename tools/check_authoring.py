"""Authoring checker for the authored content that lives outside the topic files
(frames, article frames, reconstruction texts, placement forms). Structural
checks only; ``trainer curriculum validate`` remains the authority -- it also
reports the per-band coverage floors of a placement form as warnings.

Usage: ``python3 tools/check_authoring.py FILE [FILE ...]`` -> prints ``OK`` or problems.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

CARRIES = {
    *(
        f"tense:{t}"
        for t in [
            "present-simple",
            "present-continuous",
            "past-simple",
            "past-continuous",
            "present-perfect",
            "present-perfect-continuous",
            "past-perfect",
            "future-will",
            "future-going-to",
            "future-continuous",
            "passive",
            "conditional-0",
            "conditional-1",
            "conditional-2",
            "conditional-3",
            "reported-speech",
            "modal-perfect",
        ]
    ),
    *(
        f"article:{a}"
        for a in [
            "indefinite-first-mention",
            "definite-second-mention",
            "definite-shared-context",
            "zero-plural",
            "zero-uncountable",
            "fixed-expression",
            "institutional",
            "superlative-ordinal",
            "generic",
            "proper-noun",
            "a-an-sound",
            "of-phrase",
        ]
    ),
    *(
        f"structure:{s}"
        for s in [
            "svo-order",
            "question-do",
            "question-be",
            "question-wh",
            "negative",
            "there-is",
            "here-is",
            "imperative",
            "modal",
            "comparative",
            "superlative",
            "connector",
            "relative-clause",
            "sequencing",
            "time-marker",
            "frequency-adverb",
            "quantifier",
            "preposition-time",
            "preposition-place",
            "possessive",
            "demonstrative",
            "inversion",
            "cleft",
            "participle-clause",
            "ellipsis",
            "hedging",
            "nominalization",
            "reference",
        ]
    ),
}
DOMAINS = set(
    [
        "work",
        "reporting",
        "planning",
        "troubleshooting",
        "communication",
        "requests",
        "meetings",
        "everyday-life",
        "home",
        "food",
        "travel",
        "health",
        "money",
        "leisure",
        "study",
        "academic",
        "technology",
        "data",
        "organization",
    ]
)
BANDS = {"CORE", "HIGH", "USEFUL"}
REGISTERS = {"neutral", "casual", "formal"}
CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}
ID_RE = re.compile(r"^chunk\.[a-z0-9-]+\.[a-z0-9-]+$")
TEXT_ID_RE = re.compile(r"^text\.recon\.[a-z0-9-]+\.[a-z0-9-]+$")
TOPIC_RE = re.compile(r"^grammar\.[a-z0-9.-]+$")
PHASE_MARKER = re.compile(r"(?:post|psot)[-_ ]?(?:beta|mvp)|\[mvp\]", re.IGNORECASE)
CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _check_frames(path: Path, data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    items = data.get("lexical_items")
    if not isinstance(items, list) or not items:
        return [f"{path}: no lexical_items list"]
    ids: Counter[str] = Counter()
    bands: Counter[str] = Counter()
    is_articles = path.name == "frames-articles.yaml"
    for item in items:
        if not isinstance(item, dict):
            problems.append(f"{path}: non-mapping item {item!r}")
            continue
        item_id = str(item.get("id", "?"))
        ids[item_id] += 1
        where = f"{path.name}:{item_id}"
        if not ID_RE.match(item_id):
            problems.append(f"{where}: id must be chunk.<topic-code>.<slug>")
        if item.get("type") != "chunk":
            problems.append(f"{where}: type must be chunk")
        title = str(item.get("title") or "")
        if not title.strip():
            problems.append(f"{where}: empty title")
        if title.count("___") > 2:
            problems.append(f"{where}: more than two slots")
        if item.get("cefr") not in CEFR:
            problems.append(f"{where}: bad cefr")
        band = item.get("curriculum_priority_band")
        if band not in BANDS:
            problems.append(f"{where}: band must be CORE|HIGH|USEFUL")
        bands[str(band)] += 1
        if item.get("register") not in REGISTERS:
            problems.append(f"{where}: register must be neutral|casual|formal")
        if item.get("transparency") not in {"transparent", "semi_opaque"}:
            problems.append(f"{where}: transparency must be transparent|semi_opaque")
        domains = item.get("domains") or []
        if not domains or any(d not in DOMAINS for d in domains):
            problems.append(f"{where}: domains must be 1-3 from the closed list")
        if not CYRILLIC.search(str(item.get("meaning_ru") or "")):
            problems.append(f"{where}: meaning_ru must be Russian")
        if not TOPIC_RE.match(str(item.get("frame_of") or "")):
            problems.append(f"{where}: frame_of must be a grammar topic id")
        carries = item.get("carries") or []
        if not carries or len(carries) > 3 or any(c not in CARRIES for c in carries):
            problems.append(f"{where}: carries must be 1-3 tags from the closed vocabulary")
        examples = item.get("examples") or []
        if len(examples) != 2:
            problems.append(f"{where}: exactly 2 examples required")
        for ex in examples:
            n = len(str(ex).split())
            if n < 5 or n > 16:
                problems.append(f"{where}: example length {n} words (want 6-14)")
            if CYRILLIC.search(str(ex)):
                problems.append(f"{where}: example contains Cyrillic")
        for key in ("frequency_score", "frequency_band", "source_refs"):
            if key in item:
                problems.append(f"{where}: {key} not allowed on frames")
        if item.get("transformations") != ["authored"]:
            problems.append(f"{where}: transformations must be [authored]")
        contrast = item.get("contrast")
        if contrast is not None and (
            not isinstance(contrast, dict) or not contrast.get("frame") or not contrast.get("note_ru")
        ):
            problems.append(f"{where}: contrast needs frame and note_ru")
        trap = item.get("trap")
        if trap is not None and (
            not isinstance(trap, dict)
            or not all(trap.get(k) for k in ("learner_form", "correction", "cause_ru"))
        ):
            problems.append(f"{where}: trap needs learner_form, correction, cause_ru")
        if is_articles and item.get("tier") not in {1, 2}:
            problems.append(f"{where}: article frames need tier 1|2")
        if PHASE_MARKER.search(yaml.safe_dump(item)):
            problems.append(f"{where}: phase marker forbidden")
    for item_id, count in ids.items():
        if count > 1:
            problems.append(f"{path.name}: duplicate id {item_id}")
    total = sum(bands.values())
    core_share = bands["CORE"] / total if total else 0
    if total >= 10 and not 0.2 <= core_share <= 0.4:
        problems.append(f"{path.name}: CORE share {core_share:.0%} (want 20-40%)")
    return problems


def _check_texts(path: Path, data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if data.get("schema_version") != 1:
        problems.append(f"{path}: schema_version must be 1")
    texts = data.get("texts")
    if not isinstance(texts, list) or not texts:
        return [*problems, f"{path}: no texts list"]
    ids: Counter[str] = Counter()
    for entry in texts:
        if not isinstance(entry, dict):
            problems.append(f"{path}: non-mapping text {entry!r}")
            continue
        text_id = str(entry.get("id", "?"))
        ids[text_id] += 1
        where = f"{path.name}:{text_id}"
        if not TEXT_ID_RE.match(text_id):
            problems.append(f"{where}: id must be text.recon.<topic-code>.<slug>")
        if not str(entry.get("title") or "").strip():
            problems.append(f"{where}: empty title")
        if entry.get("cefr") not in CEFR:
            problems.append(f"{where}: bad cefr")
        if not TOPIC_RE.match(str(entry.get("topic") or "")):
            problems.append(f"{where}: topic must be a grammar topic id")
        for t in entry.get("also_targets") or []:
            if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", str(t)):
                problems.append(f"{where}: bad also_targets id {t!r}")
        carries = entry.get("carries") or []
        if not carries or any(c not in CARRIES for c in carries):
            problems.append(f"{where}: carries must be tags from the closed vocabulary")
        if entry.get("domain") not in {"work", "everyday", "academic"}:
            problems.append(f"{where}: domain must be work|everyday|academic")
        if not re.match(r"^[a-z0-9-]+$", str(entry.get("context") or "")):
            problems.append(f"{where}: context must be a kebab id")
        text = str(entry.get("text") or "")
        words = len(text.split())
        if entry.get("word_count") != words:
            problems.append(f"{where}: word_count {entry.get('word_count')} != actual {words}")
        if words < 45 or words > 150:
            problems.append(f"{where}: text length {words} words outside 45-150")
        if CYRILLIC.search(text):
            problems.append(f"{where}: text contains Cyrillic")
        keywords = entry.get("keywords") or []
        if not 6 <= len(keywords) <= 14:
            problems.append(f"{where}: keywords must be 6-14 cues")
        spans = entry.get("target_spans") or []
        if not 4 <= len(spans) <= 12:
            problems.append(f"{where}: target_spans must be 4-12 substrings")
        for span in spans:
            if str(span) not in text:
                problems.append(f"{where}: target span not found verbatim: {span!r}")
        if not CYRILLIC.search(str(entry.get("summary_ru") or "")):
            problems.append(f"{where}: summary_ru must be Russian")
        if entry.get("transformations") != ["authored"]:
            problems.append(f"{where}: transformations must be [authored]")
        if PHASE_MARKER.search(yaml.safe_dump(entry)):
            problems.append(f"{where}: phase marker forbidden")
    for text_id, count in ids.items():
        if count > 1:
            problems.append(f"{path.name}: duplicate id {text_id}")
    return problems


FORM_VERSION_RE = re.compile(r"^placement-[a-z0-9-]+@\d+$")
FORM_SECTIONS = ("grammar", "vocabulary", "reading", "writing")
FORM_BANDS = {"A1", "A2", "B1", "B2", "C1"}
FORM_KINDS = {"choice", "cloze", "true_false", "writing"}
OBJECTIVE_DIMENSIONS = {"recognition", "controlled_production"}
TARGET_REF_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def _check_placement_form(path: Path, data: dict[str, Any]) -> list[str]:
    """Structural check of one authored placement form (spec 1).

    Reference resolution (does ``target_ref`` name a real topic?) and the
    coverage floors need the whole program, so they stay with the validator;
    everything an author can get wrong inside the file alone is checked here.
    """
    problems: list[str] = []
    if data.get("schema_version") != 1:
        problems.append(f"{path}: schema_version must be 1")
    version = str(data.get("form_version") or "")
    if not FORM_VERSION_RE.match(version):
        problems.append(f"{path}: form_version must match placement-<name>@<n>")
    if not str(data.get("title") or "").strip():
        problems.append(f"{path}: empty title")
    minutes = data.get("target_minutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
        problems.append(f"{path}: target_minutes must be a positive integer")
    sections = data.get("sections") or []
    if not sections or any(section not in FORM_SECTIONS for section in sections):
        problems.append(f"{path}: sections must come from {list(FORM_SECTIONS)}")

    passages: set[str] = set()
    for passage in data.get("passages") or []:
        if not isinstance(passage, dict):
            problems.append(f"{path}: non-mapping passage {passage!r}")
            continue
        passage_id = str(passage.get("passage_id") or "?")
        where = f"{path.name}:{passage_id}"
        if passage_id in passages:
            problems.append(f"{where}: duplicate passage_id")
        passages.add(passage_id)
        if passage.get("cefr") not in FORM_BANDS:
            problems.append(f"{where}: cefr must be A1-C1")
        if not str(passage.get("title") or "").strip():
            problems.append(f"{where}: empty title")
        text = str(passage.get("text") or "")
        words = len(text.split())
        if not 60 <= words <= 160:
            problems.append(f"{where}: passage is {words} words, outside 60-160")
        if CYRILLIC.search(text):
            problems.append(f"{where}: passage contains Cyrillic")

    items = data.get("items")
    if not isinstance(items, list) or not items:
        return [*problems, f"{path}: no items list"]
    ids: Counter[str] = Counter()
    for item in items:
        if not isinstance(item, dict):
            problems.append(f"{path}: non-mapping item {item!r}")
            continue
        item_id = str(item.get("item_id", "?"))
        ids[item_id] += 1
        where = f"{path.name}:{item_id}"
        section = str(item.get("section") or "")
        band = str(item.get("band") or "")
        kind = str(item.get("kind") or "")
        if section not in FORM_SECTIONS:
            problems.append(f"{where}: unknown section {section!r}")
        if band not in FORM_BANDS:
            problems.append(f"{where}: band must be A1-C1")
        if (
            section in FORM_SECTIONS
            and band in FORM_BANDS
            and not re.match(rf"^{section[0]}-{band.lower()}-\d{{2}}$", item_id)
        ):
            problems.append(f"{where}: item_id must be {section[0]}-{band.lower()}-<nn>")
        if kind not in FORM_KINDS:
            problems.append(f"{where}: kind must be one of {sorted(FORM_KINDS)}")
        prompt = str(item.get("prompt") or "")
        if not prompt.strip():
            problems.append(f"{where}: empty prompt")
        if CYRILLIC.search(prompt):
            problems.append(f"{where}: prompt must be English")
        if not TARGET_REF_RE.match(str(item.get("target_ref") or "")):
            problems.append(f"{where}: target_ref must be a dotted topic or lexical id")
        dimension = str(item.get("dimension") or "")
        if kind == "writing":
            if dimension != "spontaneous_production":
                problems.append(f"{where}: writing dimension must be spontaneous_production")
            if not str(item.get("rubric_ref") or "").startswith("rubric:"):
                problems.append(f"{where}: writing needs a rubric_ref")
            low, high = item.get("min_words"), item.get("max_words")
            if not isinstance(low, int) or not isinstance(high, int) or not 0 < low < high:
                problems.append(f"{where}: writing needs min_words < max_words")
        elif dimension not in OBJECTIVE_DIMENSIONS:
            problems.append(f"{where}: dimension must be recognition|controlled_production")
        key = item.get("answer_key")
        if kind in {"choice", "cloze", "true_false"} and (
            not isinstance(key, list) or not key or any(not str(k).strip() for k in key)
        ):
            problems.append(f"{where}: answer_key must be a non-empty list")
            key = []
        if kind == "choice":
            options = item.get("options") or []
            if len(options) != 4 or len(set(options)) != 4:
                problems.append(f"{where}: choice needs 4 distinct options")
            elif isinstance(key, list) and len([o for o in options if o in set(key)]) != 1:
                problems.append(f"{where}: exactly one option must equal an answer_key entry")
        if kind == "true_false" and any(str(k).strip().lower() not in {"true", "false"} for k in (key or [])):
            problems.append(f"{where}: true_false answer_key must be true|false")
        if section == "reading" and str(item.get("passage_id") or "") not in passages:
            problems.append(f"{where}: reading item must name a declared passage_id")
        if PHASE_MARKER.search(yaml.safe_dump(item, allow_unicode=True)):
            problems.append(f"{where}: phase marker forbidden")
    for item_id, count in ids.items():
        if count > 1:
            problems.append(f"{path.name}: duplicate item_id {item_id}")
    return problems


def check_file(path: Path) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - reported to the author
        return [f"{path}: YAML error: {exc}"]
    if not isinstance(data, dict):
        return [f"{path}: top level must be a mapping"]
    if "lexical_items" in data:
        return _check_frames(path, data)
    if "texts" in data:
        return _check_texts(path, data)
    if "form_version" in data:
        return _check_placement_form(path, data)
    if "topics" in data:
        return []  # topic files are validated by `trainer curriculum validate` and pytest
    return [f"{path}: unknown file kind (expected lexical_items, texts, topics or form_version)"]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    problems: list[str] = []
    for arg in argv:
        problems.extend(check_file(Path(arg)))
    if problems:
        print("\n".join(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
