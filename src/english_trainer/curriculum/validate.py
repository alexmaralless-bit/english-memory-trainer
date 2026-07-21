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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CEFR_ORDER = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}
AUTHORED_LEVELS: tuple[str, ...] = ("A1", "A2")

MULTIWORD_TYPES = {"chunk", "idiom", "phrasal-verb", "informal_chunk"}
TRANSPARENCY_VALUES = {"transparent", "semi_opaque", "opaque"}
FREQUENCY_TIERS = {"big-five", "core", "tail"}
TRANSFORMATIONS = {"identity", "authored", "corpus-enriched", "lemma-form-sum", "reclassified-from-chunk"}
AFFIX_TYPES = {"prefix", "suffix"}
LEXICON_ONLY_TRACKS = {"vocabulary-chunks"}


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_program(
    program: dict[str, Any], authored_levels: tuple[str, ...] = AUTHORED_LEVELS
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    levels = {level.get("id") for level in program["levels"]}
    tracks = {track.get("id"): track for track in program["tracks"]}
    modules = {module.get("id"): module for module in program["modules"]}
    topics = {topic.get("id"): topic for topic in program["topics"]}
    lexicon = {item.get("id"): item for item in program["lexicon"]}
    artifacts = {artifact.get("id") for artifact in program["provenance"].get("source_artifacts", [])}

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
            if dimensions is None and criteria is None:
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

    return ValidationReport(errors=errors, warnings=warnings)
