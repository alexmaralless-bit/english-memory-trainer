"""Total validation of a loaded program (curriculum 5; roadmap 2.1).

One pass, every finding addressed by id -- an author fixes a list, not a
stacktrace. Errors block activation; warnings do not (the SHOULD rules and the
honestly-not-yet-authored parts).

The body rules (dimensions, mastery criteria, frequency tiers) apply to the
levels whose bodies have been authored -- A1/A2 today (P.2). A topic of a later
level without a body is a *warning*: the skeleton is intentionally ahead of the
authoring, and pretending otherwise would either block activation forever or
silently accept an empty A1 body.

Structural rules (unique ids, resolvable references, acyclic advisory graph,
level inversions, track floors) apply to everything unconditionally.

The automaticity layer [PD-2026-09-22] adds two families here: frames (chunks
with ``frame_of``/``carries``/``tier``, plus the per-topic frame floor) and
reconstruction texts (curriculum 2d) -- both validated in the same single pass,
so ``trainer curriculum validate`` stays the one address for authoring errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from english_trainer.curriculum.carries import CARRIES, FRAME_FLOOR_BY_TIER, MAX_CARRIES

CEFR_ORDER = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}
# The whole program is authored now (P.2e bodies accepted): body completeness
# is enforced at every level, so a future skeleton without its mastery_criteria
# is a hard error, not a silent warning.
AUTHORED_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")

MULTIWORD_TYPES = {"chunk", "idiom", "phrasal-verb", "informal_chunk"}
TRANSPARENCY_VALUES = {"transparent", "semi_opaque", "opaque"}
FREQUENCY_TIERS = {"big-five", "core", "tail"}
TRANSFORMATIONS = {"identity", "authored", "corpus-enriched", "lemma-form-sum", "reclassified-from-chunk"}
AFFIX_TYPES = {"prefix", "suffix"}
LEXICON_ONLY_TRACKS = {"vocabulary-chunks"}

# Phase markers are banned from the program [PD-2026-07-22]: priority governs
# order and intensity, never scope. A stale deferral field once slipped into an
# activated snapshot (its hash included), so the ban is a validator invariant,
# not a review convention. Covers spelling variants and the observed typo family.
PHASE_MARKER = re.compile(r"(?:post|psot)[-_ ]?(?:beta|mvp)|\[mvp\]", re.IGNORECASE)

# -- automaticity layer (curriculum 2c, 2d) [PD-2026-09-22] -------------------
FRAME_TRACK = "grammar-engine"
TIER_VALUES = {1, 2}
TEXT_SCHEMA_VERSION = 1
TEXT_ID = re.compile(r"^text\.recon\.[a-z0-9-]+\.[a-z0-9-]+$")
TEXT_CONTEXT = re.compile(r"^[a-z0-9-]+$")
TEXT_DOMAINS = {"work", "everyday", "academic"}
TEXT_WORD_RANGE = (45, 150)
TEXT_KEYWORD_RANGE = (6, 14)
TEXT_SPAN_RANGE = (4, 12)
CYRILLIC = re.compile(r"[\u0400-\u04ff]")

# -- placement forms (flows/placement; assessments 3) -------------------------
FORM_SCHEMA_VERSION = 1
FORM_VERSION = re.compile(r"^placement-[a-z0-9-]+@\d+$")
FORM_SECTIONS: tuple[str, ...] = ("grammar", "vocabulary", "reading", "writing")
# C2 is not placed: a placement measures the working band, and C2 is claimed by
# sustained evidence, never by a 35-minute diagnostic.
FORM_BANDS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1")
FORM_ITEM_KINDS: tuple[str, ...] = ("choice", "cloze", "true_false", "writing")
OBJECTIVE_DIMENSIONS = {"recognition", "controlled_production"}
WRITING_DIMENSION = "spontaneous_production"
CHOICE_OPTION_COUNT = 4
TRUE_FALSE_KEYS = {"true", "false"}
PASSAGE_WORD_RANGE = (60, 160)
WRITING_WORD_RANGE = (20, 400)
#: Per-form coverage floors (spec 2): the working level needs at least five
#: distinct topics per band, so a form that tests fewer cannot measure that
#: band. Reported as WARNINGS -- a partially authored form must still validate.
FORM_COVERAGE_FLOOR: dict[str, dict[str, int]] = {
    "grammar": {"A1": 8, "A2": 8, "B1": 8, "B2": 6, "C1": 5},
    "vocabulary": {"A1": 5, "A2": 5, "B1": 5, "B2": 5, "C1": 4},
    "reading": {"A2": 3, "B1": 3, "B2": 3, "C1": 3},
    "writing": {"A2": 1, "B1": 1},
}


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_program(
    program: dict[str, Any],
    authored_levels: tuple[str, ...] = AUTHORED_LEVELS,
    *,
    rubric_refs: frozenset[str] | None = None,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    levels = {level.get("id") for level in program["levels"]}
    tracks = {track.get("id"): track for track in program["tracks"]}
    modules = {module.get("id"): module for module in program["modules"]}
    topics = {topic.get("id"): topic for topic in program["topics"]}
    lexicon = {item.get("id"): item for item in program["lexicon"]}
    artifacts = {artifact.get("id") for artifact in program["provenance"].get("source_artifacts", [])}

    # -- no phase markers, no phase fields [PD-2026-07-22] --------------------
    def _reject_phase(value: Any, path: str) -> None:
        if isinstance(value, str):
            if PHASE_MARKER.search(value):
                errors.append(f"{path}: phase marker {value!r} is banned (PD-2026-07-22)")
        elif isinstance(value, dict):
            for key, item in value.items():
                if str(key) == "phase":
                    errors.append(f"{path}.phase: phase fields are banned (PD-2026-07-22)")
                _reject_phase(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _reject_phase(item, f"{path}[{index}]")

    for section in ("levels", "tracks", "modules", "topics", "lexicon"):
        _reject_phase(program[section], section)
    _reject_phase(program.get("texts") or [], "texts")
    _reject_phase(program.get("placement_forms") or [], "placement_forms")

    # -- unique ids -----------------------------------------------------------
    for kind, items in (
        ("topic", program["topics"]),
        ("lexical item", program["lexicon"]),
        ("module", program["modules"]),
        ("track", program["tracks"]),
    ):
        seen: set[str] = set()
        for item in items:
            item_id = item.get("id")
            if not item_id:
                errors.append(f"{kind} without an id")
            elif item_id in seen:
                errors.append(f"duplicate {kind} id: {item_id}")
            else:
                seen.add(item_id)

    # -- tracks ---------------------------------------------------------------
    for track_id, track in tracks.items():
        if track.get("from_level") not in levels:
            errors.append(f"track {track_id}: unknown from_level {track.get('from_level')!r}")

    # -- modules --------------------------------------------------------------
    topic_module_membership: dict[str, str] = {}
    for module_id, module in modules.items():
        if module.get("level") not in levels:
            errors.append(f"module {module_id}: unknown level {module.get('level')!r}")
        for track_id in module.get("tracks", []):
            if track_id not in tracks:
                errors.append(f"module {module_id}: unknown track {track_id}")
        for topic_id in module.get("topics", []):
            if topic_id not in topics:
                errors.append(f"module {module_id}: unknown topic {topic_id}")
                continue
            if topic_id in topic_module_membership:
                errors.append(
                    f"topic {topic_id}: listed in both {topic_module_membership[topic_id]} and {module_id}"
                )
            topic_module_membership[topic_id] = module_id

    # -- topics: structure ----------------------------------------------------
    for topic_id, topic in topics.items():
        cefr = topic.get("cefr")
        track_id = topic.get("track")
        if cefr not in levels or cefr not in CEFR_ORDER:
            errors.append(f"topic {topic_id}: unknown cefr {cefr!r}")
            continue
        if not str(topic.get("can_do") or "").strip():
            errors.append(f"topic {topic_id}: missing can_do")
        for field_name in ("core_points", "contrasts", "scope_limits"):
            value = topic.get(field_name)
            if value is not None and (
                not isinstance(value, list) or not value or any(not str(item).strip() for item in value)
            ):
                errors.append(f"topic {topic_id}: {field_name} must be a non-empty list of strings")
        error_patterns = topic.get("error_patterns")
        if error_patterns is not None:
            if not isinstance(error_patterns, list) or not error_patterns:
                errors.append(f"topic {topic_id}: error_patterns must be a non-empty list")
            else:
                for index, pattern in enumerate(error_patterns):
                    if not isinstance(pattern, dict) or any(
                        not str(pattern.get(field) or "").strip()
                        for field in ("learner_form", "correction", "explanation")
                    ):
                        errors.append(
                            f"topic {topic_id}: error_patterns[{index}] needs "
                            "learner_form, correction, and explanation"
                        )
        insights = topic.get("memory_insights")
        if insights is not None:
            if not isinstance(insights, list) or not insights:
                errors.append(f"topic {topic_id}: memory_insights must be a non-empty list")
            else:
                for index, insight in enumerate(insights):
                    if not isinstance(insight, dict) or any(
                        not str(insight.get(field) or "").strip() for field in ("kind", "text", "origin")
                    ):
                        errors.append(
                            f"topic {topic_id}: memory_insights[{index}] needs kind, text, and origin"
                        )
                        continue
                    sources = insight.get("sources") or []
                    if insight.get("origin") == "reference_research" and not sources:
                        errors.append(f"topic {topic_id}: researched memory_insights[{index}] needs sources")
                    for source_index, source in enumerate(sources):
                        if not isinstance(source, dict) or any(
                            not str(source.get(field) or "").strip() for field in ("title", "url")
                        ):
                            errors.append(
                                f"topic {topic_id}: memory_insights[{index}]."
                                f"sources[{source_index}] needs title and url"
                            )
        if track_id not in tracks:
            errors.append(f"topic {topic_id}: unknown track {track_id!r}")
        else:
            if track_id in LEXICON_ONLY_TRACKS:
                errors.append(f"topic {topic_id}: track {track_id} is lexicon-only and carries no topics")
            floor = tracks[track_id].get("from_level")
            if floor in CEFR_ORDER and CEFR_ORDER[cefr] < CEFR_ORDER[floor]:
                errors.append(f"topic {topic_id}: level {cefr} is below track floor {floor} of {track_id}")
        declared_module = topic.get("module")
        if declared_module not in modules:
            errors.append(f"topic {topic_id}: unknown module {declared_module!r}")
        elif topic_module_membership.get(topic_id) != declared_module:
            errors.append(
                f"topic {topic_id}: declares module {declared_module} but module lists say "
                f"{topic_module_membership.get(topic_id)!r}"
            )
        elif modules[declared_module].get("level") != cefr:
            errors.append(
                f"topic {topic_id}: cefr {cefr} does not match module level "
                f"{modules[declared_module].get('level')!r}"
            )

        prerequisites = topic.get("advisory_prerequisites") or {}
        for strength in ("strong", "soft"):
            for prerequisite_id in prerequisites.get(strength, []):
                prerequisite = topics.get(prerequisite_id)
                if prerequisite is None:
                    errors.append(f"topic {topic_id}: dangling {strength} prerequisite {prerequisite_id}")
                elif CEFR_ORDER.get(prerequisite.get("cefr"), 99) > CEFR_ORDER[cefr]:
                    errors.append(
                        f"topic {topic_id} ({cefr}): prerequisite {prerequisite_id} is at higher level "
                        f"{prerequisite.get('cefr')}"
                    )

        for reference in topic.get("lexicon", []):
            if reference not in lexicon:
                errors.append(f"topic {topic_id}: dangling lexicon reference {reference}")
                continue
            # The frame link is owned by topic.lexicon and mirrored by frame_of
            # (curriculum 2c) -- two independent one-way references would drift
            # at the first edit, so both directions must name the same topic.
            frame_topic = lexicon[reference].get("frame_of")
            if frame_topic is not None and frame_topic != topic_id:
                errors.append(
                    f"topic {topic_id}: lexicon lists frame {reference}, whose frame_of is {frame_topic}"
                )

    # -- advisory graph acyclicity -------------------------------------------
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(topics, WHITE)

    def edges(topic_id: str) -> list[str]:
        prerequisites = topics[topic_id].get("advisory_prerequisites") or {}
        return [
            prerequisite_id
            for strength in ("strong", "soft")
            for prerequisite_id in prerequisites.get(strength, [])
            if prerequisite_id in topics
        ]

    def visit(topic_id: str, stack: list[str]) -> None:
        color[topic_id] = GRAY
        stack.append(topic_id)
        for nxt in edges(topic_id):
            if color[nxt] == GRAY:
                cycle = [*stack[stack.index(nxt) :], nxt]
                errors.append("advisory-graph cycle: " + " -> ".join(cycle))
            elif color[nxt] == WHITE:
                visit(nxt, stack)
        stack.pop()
        color[topic_id] = BLACK

    for topic_id in topics:
        if color[topic_id] == WHITE:
            visit(topic_id, [])

    # -- topics: authored bodies ---------------------------------------------
    for topic_id, topic in topics.items():
        cefr = topic.get("cefr")
        authored = cefr in authored_levels
        dimensions = topic.get("dimensions")
        criteria = topic.get("mastery_criteria")
        if not authored:
            # A skeleton may already carry dimensions (P.1e authors them with
            # the skeleton); the body marker is mastery_criteria. Keying the
            # warning on dimensions would silently hide every unauthored body
            # and let P.2e be forgotten (P.1e handoff finding 2).
            if criteria is None:
                warnings.append(f"topic {topic_id}: body not yet authored (level {cefr})")
            continue
        if not dimensions:
            errors.append(f"topic {topic_id}: empty or missing dimensions")
        if not isinstance(criteria, dict):
            errors.append(f"topic {topic_id}: missing mastery_criteria")
        elif dimensions:
            per_dimension = set((criteria.get("per_dimension") or {}).keys())
            if per_dimension != set(dimensions):
                errors.append(
                    f"topic {topic_id}: mastery_criteria cover {sorted(per_dimension)}, "
                    f"dimensions are {sorted(dimensions)}"
                )
        if topic.get("track") == "grammar-engine" and topic.get("frequency_tier") not in FREQUENCY_TIERS:
            errors.append(
                f"topic {topic_id}: grammar topic needs frequency_tier in {sorted(FREQUENCY_TIERS)}"
            )
        if not topic.get("contexts"):
            warnings.append(f"topic {topic_id}: no real-life context attached (SHOULD)")

    # -- lexicon --------------------------------------------------------------
    for item_id, item in lexicon.items():
        item_type = item.get("type")
        transparency = item.get("transparency")
        if item_type in MULTIWORD_TYPES:
            if transparency not in TRANSPARENCY_VALUES:
                errors.append(f"lexical item {item_id}: multiword unit without valid transparency")
            elif transparency == "opaque" and not str(item.get("literal_trap_ru") or "").strip():
                errors.append(f"lexical item {item_id}: opaque unit without literal_trap_ru")
        if (item.get("frequency_score") is not None or item.get("frequency_band")) and not item.get(
            "source_refs"
        ):
            errors.append(f"lexical item {item_id}: frequency fields without source_refs")
        for reference in item.get("source_refs", []):
            if reference not in artifacts:
                errors.append(f"lexical item {item_id}: source_ref {reference} not in provenance manifest")
        for token in item.get("transformations", []):
            if token not in TRANSFORMATIONS:
                errors.append(f"lexical item {item_id}: unknown transformation {token!r}")
        formation = item.get("formation")
        if formation is not None:
            if not str(formation.get("affix") or "").strip() or not str(formation.get("base") or "").strip():
                errors.append(f"lexical item {item_id}: formation needs affix and base")
            if formation.get("affix_type") not in AFFIX_TYPES:
                errors.append(f"lexical item {item_id}: formation affix_type must be prefix|suffix")

        # -- automaticity layer: frames and carries (curriculum 2c) ----------
        # `carries` is legal on any unit (an existing chunk may carry a fixed
        # article without being a topic frame); `frame_of` is what makes a unit
        # a frame, and a frame without a carried target would be undrillable.
        carries = item.get("carries")
        if carries is not None:
            if not isinstance(carries, list) or not 1 <= len(carries) <= MAX_CARRIES:
                errors.append(f"lexical item {item_id}: carries must be a list of 1-{MAX_CARRIES} tags")
            else:
                for tag in carries:
                    if tag not in CARRIES:
                        errors.append(f"lexical item {item_id}: unknown carries tag {tag!r}")
        frame_of = item.get("frame_of")
        if frame_of is not None:
            if item_type != "chunk":
                errors.append(f"lexical item {item_id}: frame_of requires type chunk, not {item_type!r}")
            if frame_of not in topics:
                errors.append(f"lexical item {item_id}: frame_of names unknown topic {frame_of}")
            elif item_id not in (topics[frame_of].get("lexicon") or []):
                errors.append(
                    f"lexical item {item_id}: frame_of is {frame_of}, but {frame_of} does not list "
                    f"{item_id} in its lexicon (run tools/link_frames.py)"
                )
            if not carries:
                errors.append(f"lexical item {item_id}: frame_of without carries")
            for corpus_field in ("frequency_score", "frequency_band", "source_refs"):
                if item.get(corpus_field) is not None:
                    errors.append(
                        f"lexical item {item_id}: frame must not carry {corpus_field} "
                        "(the corpus does not cover phrases)"
                    )
        tier = item.get("tier")
        if tier is not None and (isinstance(tier, bool) or tier not in TIER_VALUES):
            errors.append(f"lexical item {item_id}: tier must be 1 or 2, not {tier!r}")
        for structured, keys in (
            ("contrast", ("frame", "note_ru")),
            ("trap", ("learner_form", "correction", "cause_ru")),
        ):
            value = item.get(structured)
            if value is None:
                continue
            if not isinstance(value, dict) or any(not str(value.get(key) or "").strip() for key in keys):
                errors.append(f"lexical item {item_id}: {structured} needs {', '.join(keys)}")

    # -- frame coverage per Grammar Engine topic (curriculum 2c) --------------
    # Below the floor the topic cannot be drilled to automaticity at all, so a
    # missing frame set is an error, not a SHOULD.
    frame_counts: dict[str, int] = {}
    for item in lexicon.values():
        frame_of = item.get("frame_of")
        if frame_of:
            frame_counts[str(frame_of)] = frame_counts.get(str(frame_of), 0) + 1
    for topic_id, topic in topics.items():
        if topic.get("track") != FRAME_TRACK:
            continue
        frequency_tier = str(topic.get("frequency_tier") or "")
        floor = FRAME_FLOOR_BY_TIER.get(frequency_tier)
        if floor is None:
            continue
        authored_frames = frame_counts.get(str(topic_id), 0)
        if authored_frames < floor:
            errors.append(
                f"topic {topic_id}: {authored_frames} frames authored, "
                f"{frequency_tier} needs at least {floor}"
            )

    # -- reconstruction texts (curriculum 2d) --------------------------------
    seen_text_ids: set[str] = set()
    for index, text in enumerate(program.get("texts") or []):
        if not isinstance(text, dict):
            errors.append(f"reconstruction text #{index}: entry must be a mapping")
            continue
        text_id = str(text.get("id") or "")
        where = f"reconstruction text {text_id or f'#{index}'}"
        if not text_id:
            errors.append(f"{where}: missing id")
        elif not TEXT_ID.match(text_id):
            errors.append(f"{where}: id must match text.recon.<topic-code>.<slug>")
        elif text_id in seen_text_ids:
            errors.append(f"duplicate reconstruction text id: {text_id}")
        else:
            seen_text_ids.add(text_id)
        if text.get("schema_version") != TEXT_SCHEMA_VERSION:
            errors.append(f"{where}: schema_version must be {TEXT_SCHEMA_VERSION}")
        if text.get("topic") not in topics:
            errors.append(f"{where}: unknown topic {text.get('topic')!r}")
        for target in text.get("also_targets") or []:
            if target not in topics and target not in lexicon:
                errors.append(f"{where}: also_targets {target} is neither a topic nor a lexical item")
        text_carries = text.get("carries") or []
        if not text_carries:
            errors.append(f"{where}: carries must name at least one tag")
        for tag in text_carries:
            if tag not in CARRIES:
                errors.append(f"{where}: unknown carries tag {tag!r}")
        if text.get("domain") not in TEXT_DOMAINS:
            errors.append(f"{where}: domain must be one of {sorted(TEXT_DOMAINS)}")
        if not TEXT_CONTEXT.match(str(text.get("context") or "")):
            errors.append(f"{where}: context must be a kebab id")
        body = text.get("text")
        if not isinstance(body, str) or not body.strip():
            errors.append(f"{where}: missing text")
            body = ""
        else:
            # The learner rebuilds the text from keywords: the stored word count
            # is the drill's target, so a drifted count silently moves the goal.
            words = len(body.split())
            if text.get("word_count") != words:
                errors.append(f"{where}: word_count {text.get('word_count')!r} != actual {words}")
            low, high = TEXT_WORD_RANGE
            if not low <= words <= high:
                errors.append(f"{where}: text length {words} words outside {low}-{high}")
            if CYRILLIC.search(body):
                errors.append(f"{where}: text must be English only")
        keywords = text.get("keywords") or []
        low, high = TEXT_KEYWORD_RANGE
        if not low <= len(keywords) <= high:
            errors.append(f"{where}: keywords must be {low}-{high} cues, got {len(keywords)}")
        spans = text.get("target_spans") or []
        low, high = TEXT_SPAN_RANGE
        if not low <= len(spans) <= high:
            errors.append(f"{where}: target_spans must be {low}-{high} substrings, got {len(spans)}")
        for span in spans:
            if str(span) not in body:
                errors.append(f"{where}: target span not found verbatim in text: {span!r}")
        if not str(text.get("summary_ru") or "").strip():
            errors.append(f"{where}: missing summary_ru")
        for token in text.get("transformations") or []:
            if token not in TRANSFORMATIONS:
                errors.append(f"{where}: unknown transformation {token!r}")

    _validate_placement_forms(program, topics, lexicon, errors, warnings, rubric_refs)

    return ValidationReport(errors=errors, warnings=warnings)


def _validate_placement_forms(
    program: dict[str, Any],
    topics: dict[Any, Any],
    lexicon: dict[Any, Any],
    errors: list[str],
    warnings: list[str],
    rubric_refs: frozenset[str] | None,
) -> None:
    """Placement forms as curriculum data (flows/placement; assessments 3).

    Structural rules are ERRORS (a malformed form would mis-measure a learner
    and is never activated); the per-band coverage floors of the authoring spec
    are WARNINGS, so a form that is still being authored validates and can be
    exercised end to end.
    """
    seen_versions: set[str] = set()
    for index, form in enumerate(program.get("placement_forms") or []):
        if not isinstance(form, dict):
            errors.append(f"placement form #{index}: entry must be a mapping")
            continue
        version = str(form.get("form_version") or "")
        where = f"placement form {version or f'#{index}'}"
        if not version:
            errors.append(f"{where}: missing form_version")
        elif not FORM_VERSION.match(version):
            errors.append(f"{where}: form_version must match placement-<name>@<n>")
        elif version in seen_versions:
            errors.append(f"duplicate placement form_version: {version}")
        else:
            seen_versions.add(version)
        if form.get("schema_version") != FORM_SCHEMA_VERSION:
            errors.append(f"{where}: schema_version must be {FORM_SCHEMA_VERSION}")
        if not str(form.get("title") or "").strip():
            errors.append(f"{where}: missing title")
        minutes = form.get("target_minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            errors.append(f"{where}: target_minutes must be a positive integer")

        sections = form.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append(f"{where}: sections must be a non-empty list")
            sections = []
        else:
            if len(set(sections)) != len(sections):
                errors.append(f"{where}: sections must not repeat")
            for section in sections:
                if section not in FORM_SECTIONS:
                    errors.append(f"{where}: unknown section {section!r}")

        passages: dict[str, dict[str, Any]] = {}
        for passage_index, passage in enumerate(form.get("passages") or []):
            if not isinstance(passage, dict):
                errors.append(f"{where}: passages[{passage_index}] must be a mapping")
                continue
            passage_id = str(passage.get("passage_id") or "")
            if not passage_id:
                errors.append(f"{where}: passages[{passage_index}] has no passage_id")
                continue
            if passage_id in passages:
                errors.append(f"{where}: duplicate passage_id {passage_id}")
            passages[passage_id] = passage
            if passage.get("cefr") not in FORM_BANDS:
                errors.append(f"{where}: passage {passage_id} cefr must be one of {list(FORM_BANDS)}")
            if not str(passage.get("title") or "").strip():
                errors.append(f"{where}: passage {passage_id} has no title")
            body = passage.get("text")
            if not isinstance(body, str) or not body.strip():
                errors.append(f"{where}: passage {passage_id} has no text")
                continue
            words = len(body.split())
            low, high = PASSAGE_WORD_RANGE
            if not low <= words <= high:
                errors.append(f"{where}: passage {passage_id} is {words} words, outside {low}-{high}")
            if CYRILLIC.search(body):
                errors.append(f"{where}: passage {passage_id} must be English only")

        items = form.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{where}: items must be a non-empty list")
            continue
        seen_items: set[str] = set()
        # (section, band) -> the target refs tested there, for the coverage floors.
        coverage: dict[tuple[str, str], list[str]] = {}
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{where}: items[{item_index}] must be a mapping")
                continue
            item_id = str(item.get("item_id") or "")
            item_where = f"{where}: item {item_id or f'#{item_index}'}"
            if not item_id:
                errors.append(f"{item_where} has no item_id")
            elif item_id in seen_items:
                errors.append(f"{where}: duplicate item_id {item_id}")
            else:
                seen_items.add(item_id)

            section = str(item.get("section") or "")
            band = str(item.get("band") or "")
            if section not in FORM_SECTIONS:
                errors.append(f"{item_where}: unknown section {section!r}")
            elif sections and section not in sections:
                errors.append(f"{item_where}: section {section} is not declared by the form")
            if band not in FORM_BANDS:
                errors.append(f"{item_where}: band must be one of {list(FORM_BANDS)}")
            if item_id and section in FORM_SECTIONS and band in FORM_BANDS:
                pattern = rf"^{section[0]}-{band.lower()}-\d{{2}}$"
                if not re.match(pattern, item_id):
                    errors.append(f"{item_where}: item_id must match {section[0]}-{band.lower()}-<nn>")

            kind = str(item.get("kind") or "")
            if kind not in FORM_ITEM_KINDS:
                errors.append(f"{item_where}: kind must be one of {list(FORM_ITEM_KINDS)}")
            if not str(item.get("prompt") or "").strip():
                errors.append(f"{item_where}: missing prompt")

            target_ref = str(item.get("target_ref") or "")
            if not target_ref:
                errors.append(f"{item_where}: missing target_ref")
            elif target_ref not in topics and target_ref not in lexicon:
                errors.append(f"{item_where}: target_ref {target_ref} is neither a topic nor a lexical item")
            if section in FORM_SECTIONS and band in FORM_BANDS and target_ref:
                coverage.setdefault((section, band), []).append(target_ref)

            dimension = str(item.get("dimension") or "")
            if kind == "writing":
                if dimension != WRITING_DIMENSION:
                    errors.append(f"{item_where}: writing dimension must be {WRITING_DIMENSION}")
            elif kind in FORM_ITEM_KINDS and dimension not in OBJECTIVE_DIMENSIONS:
                errors.append(f"{item_where}: dimension must be one of {sorted(OBJECTIVE_DIMENSIONS)}")

            raw_key = item.get("answer_key")
            answer_key: list[Any] = list(raw_key) if isinstance(raw_key, list) else []
            objective_key = bool(answer_key) and all(
                isinstance(value, str) and value.strip() for value in answer_key
            )
            if kind in ("choice", "cloze", "true_false") and not objective_key:
                errors.append(f"{item_where}: answer_key must be a non-empty list of strings")
            if kind == "choice":
                options = item.get("options")
                if (
                    not isinstance(options, list)
                    or len(options) != CHOICE_OPTION_COUNT
                    or any(not isinstance(option, str) or not option.strip() for option in options)
                ):
                    errors.append(
                        f"{item_where}: choice needs exactly {CHOICE_OPTION_COUNT} non-empty options"
                    )
                elif len(set(options)) != len(options):
                    errors.append(f"{item_where}: choice options must be distinct")
                elif objective_key:
                    keys = set(answer_key)
                    correct = [option for option in options if option in keys]
                    if len(correct) != 1:
                        errors.append(
                            f"{item_where}: exactly one option must equal an answer_key entry "
                            f"(found {len(correct)})"
                        )
            if kind == "true_false" and objective_key:
                bad = [value for value in answer_key if str(value).strip().lower() not in TRUE_FALSE_KEYS]
                if bad:
                    errors.append(f"{item_where}: true_false answer_key must be true|false, got {bad}")
            if section == "reading":
                passage_id = str(item.get("passage_id") or "")
                if not passage_id:
                    errors.append(f"{item_where}: a reading item must name its passage_id")
                elif passage_id not in passages:
                    errors.append(f"{item_where}: passage_id {passage_id} is not declared by the form")
            if kind == "writing":
                rubric_ref = str(item.get("rubric_ref") or "")
                if not rubric_ref:
                    errors.append(f"{item_where}: a writing item needs a rubric_ref")
                elif rubric_refs is not None and rubric_ref not in rubric_refs:
                    errors.append(f"{item_where}: rubric_ref {rubric_ref} does not resolve in rubric@1")
                low, high = WRITING_WORD_RANGE
                min_words = item.get("min_words")
                max_words = item.get("max_words")
                if isinstance(min_words, bool) or not isinstance(min_words, int) or min_words < low:
                    errors.append(f"{item_where}: min_words must be an integer of at least {low}")
                elif isinstance(max_words, bool) or not isinstance(max_words, int):
                    errors.append(f"{item_where}: max_words must be an integer")
                elif not min_words < max_words <= high:
                    errors.append(f"{item_where}: word range must be min < max <= {high}")

        # -- coverage floors (spec 2): warnings, never activation blockers.
        for section, floors in FORM_COVERAGE_FLOOR.items():
            if sections and section not in sections:
                continue
            for band, floor in floors.items():
                tested = coverage.get((section, band), [])
                if len(tested) < floor:
                    warnings.append(
                        f"{where}: {section}/{band} has {len(tested)} item(s), the coverage floor is {floor}"
                    )
                distinct = len(set(tested))
                if distinct < len(tested):
                    warnings.append(
                        f"{where}: {section}/{band} tests {distinct} distinct target(s) with "
                        f"{len(tested)} items; a band is measured by DISTINCT topics"
                    )
        if "reading" in (sections or []):
            by_band = {str(passage.get("cefr")) for passage in passages.values()}
            for band in FORM_COVERAGE_FLOOR["reading"]:
                if band not in by_band:
                    warnings.append(f"{where}: reading band {band} has no passage of its own")
