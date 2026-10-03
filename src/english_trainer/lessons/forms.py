"""The automaticity-loop forms (generation@3 [PD-2026-09-22]) as the tutor
sees them in the lesson brief.

Three step types arrive with the automaticity layer, and each has exactly one
learner-facing form:

``drill_block``
    2-3 rounds of ``round_size`` short productions of one pattern, reported
    as ONE block of items (evidence 4.6). Round 0 is massed on the primary
    target's frames; a later round interleaves the step's ``role: contrast``
    targets when the step says ``interleaved``.

``reconstruction``
    An authored text of the pinned curriculum snapshot, shown once and then
    rebuilt from its keywords (``target_spans`` travel with it).

``timed_writing``
    A prompt plus the limit announced to the learner; recorded, never scored.

What remains here is the tutor-facing, read-only part: the round arithmetic
read from the SESSION-PINNED generation policy and :func:`directive_view`, the
authored material (frames, the chosen reconstruction text) the brief attaches
to each advisory plan step. The render-time snapshot validation went away with
the step-delivery protocol [PD-2026-09-23]: the tutor builds the items itself
and reports them.

Boundary note: lessons may not import curriculum (architecture gate rule 1), so
the reconstruction-text lookup is re-stated here as the pure read it is --
match the owning ``topic``, order by id, exactly as ``curriculum 2d`` and
``curriculum.service.texts_for_topic`` define it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DRILL_BLOCK = "drill_block"
RECONSTRUCTION = "reconstruction"
TIMED_WRITING = "timed_writing"

#: The three step types the automaticity layer adds; for each of them the form
#: name equals the step type (generation@3 ``form_step_type_binding``).
AUTOMATICITY_STEP_TYPES = frozenset({DRILL_BLOCK, RECONSTRUCTION, TIMED_WRITING})

#: The schema version of ``generation`` that first declares these forms.
AUTOMATICITY_GENERATION_VERSION = 3

#: Policy fallbacks, used only when the pinned policy omits a key. They mirror
#: the authored generation@3 values so the two can never disagree silently.
DEFAULT_ROUND_SIZE = 6
DEFAULT_ROUNDS_MIN = 2
DEFAULT_TIMED_LIMIT_SECONDS = 240
DEFAULT_TEXT_WINDOW = 10
DEFAULT_FRAMES_MAX_PRIMARY = 12
DEFAULT_FRAMES_MAX_PER_CONTRAST = 4

_BLOCKED = "blocked"
_INTERLEAVED = "interleaved"


def generation_schema_version(pinned: Mapping[str, Any]) -> int:
    """The integer after ``@`` of the pinned generation version, or 0.

    Used for capability gates (``>= 2`` is the pedagogy layer, ``>= 3`` the
    automaticity layer). A prefix comparison against the exact string would
    have silently disabled every pedagogy feature the moment generation@3
    became the active policy.
    """
    version = str(pinned.get("generation") or "")
    _, _, suffix = version.partition("@")
    try:
        return int(suffix)
    except ValueError:
        return 0


def supports_automaticity_forms(pinned: Mapping[str, Any]) -> bool:
    return generation_schema_version(pinned) >= AUTOMATICITY_GENERATION_VERSION


def _section(policy: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    section = (policy or {}).get(name)
    return dict(section) if isinstance(section, dict) else {}


def _int_setting(policy: Mapping[str, Any] | None, section: str, key: str, fallback: int) -> int:
    value = _section(policy, section).get(key)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else fallback


def round_size_for(step: Mapping[str, Any], policy: Mapping[str, Any] | None) -> int:
    """Items per drill round: the step's declared size, else the policy default.

    The step's size is what control already resolved from
    ``briefing.preferences.round_size`` at composition time; the engine never
    re-reads the preference at render, or a preference changed mid-session
    would invalidate a block the learner is already answering.
    """
    declared = step.get("round_size")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared > 0:
        return declared
    return _int_setting(policy, DRILL_BLOCK, "default_round_size", DEFAULT_ROUND_SIZE)


def timed_limit_for(step: Mapping[str, Any], policy: Mapping[str, Any] | None) -> int:
    declared = step.get("declared_limit_seconds")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared > 0:
        return declared
    return _int_setting(policy, TIMED_WRITING, "default_limit_seconds", DEFAULT_TIMED_LIMIT_SECONDS)


def _step_targets(step: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets = step.get("targets")
    if isinstance(targets, list):
        return [dict(item) for item in targets if isinstance(item, dict)]
    ref = step.get("target_ref")
    if ref is None:
        return []
    return [{"target_ref": str(ref), "dimension": step.get("dimension"), "role": "target"}]


def primary_target_of(step: Mapping[str, Any]) -> dict[str, Any] | None:
    """The drilled target: the first non-contrast entry, else the first entry."""
    targets = _step_targets(step)
    for target in targets:
        if str(target.get("role") or "target") != "contrast":
            return target
    return targets[0] if targets else None


def contrast_targets_of(step: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [t for t in _step_targets(step) if str(t.get("role") or "") == "contrast"]


# -- the tutor-facing directive ---------------------------------------------


def frames_for_target(
    program: Mapping[str, Any],
    target_ref: str,
    *,
    role: str,
    limit: int,
) -> list[dict[str, Any]]:
    """The authored frames of a topic, as the tutor needs to see them.

    A frame is a ``chunk`` whose ``frame_of`` points back at the topic
    (curriculum 2c). The link is owned by ``topic.lexicon``, so a unit claiming
    a topic that does not list it is ignored here rather than trusted.
    """
    topic = next(
        (
            item
            for item in program.get("topics", [])
            if isinstance(item, dict) and item.get("id") == target_ref
        ),
        None,
    )
    listed = {str(ref) for ref in (topic or {}).get("lexicon") or []}
    frames = [
        unit
        for unit in program.get("lexicon", [])
        if isinstance(unit, dict)
        and str(unit.get("frame_of") or "") == target_ref
        and (not listed or str(unit.get("id")) in listed)
    ]
    frames.sort(key=lambda unit: str(unit.get("id")))
    out: list[dict[str, Any]] = []
    for unit in frames[:limit]:
        out.append(
            {
                "frame_ref": str(unit.get("id")),
                "role": role,
                "target_ref": target_ref,
                "title": unit.get("title"),
                "meaning_ru": unit.get("meaning_ru"),
                "slot_hint_ru": unit.get("slot_hint_ru"),
                "examples": list(unit.get("examples") or []),
                "contrast": unit.get("contrast"),
                "trap": unit.get("trap"),
                "carries": list(unit.get("carries") or []),
            }
        )
    return out


def choose_reconstruction_text(
    program: Mapping[str, Any],
    topic_id: str,
    *,
    recent_text_ids: list[str],
) -> dict[str, Any] | None:
    """The text this reconstruction step rebuilds (deterministic).

    The first authored text of the topic that was not used in the recent window
    of reconstruction presentations, else the first by id. Both branches are
    functions of the pinned snapshot and the event log, so a replay picks the
    same text the learner saw.
    """
    texts = [
        text
        for text in program.get("texts") or []
        if isinstance(text, dict) and text.get("topic") == topic_id
    ]
    texts.sort(key=lambda text: str(text.get("id")))
    if not texts:
        return None
    recent = set(recent_text_ids)
    for text in texts:
        if str(text.get("id")) not in recent:
            return dict(text)
    return dict(texts[0])


def directive_view(
    step: Mapping[str, Any],
    program: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
    *,
    recent_text_ids: list[str],
) -> dict[str, Any] | None:
    """The generation directive as the tutor receives it for a new step type.

    A computed view on the delivered step, never a second source of truth: the
    persisted plan keeps the directive control composed, and
    ``generation_directive_hash`` keeps covering exactly that. What is added
    here is the authored material the tutor must build the items from -- frames
    for a drill block, the chosen text for a reconstruction -- which the plan
    deliberately does not copy.
    """
    step_type = str(step.get("step_type") or "")
    if step_type not in AUTOMATICITY_STEP_TYPES:
        return None
    directive = dict(step.get("generation_directive") or {})
    primary = primary_target_of(step)
    contrasts = contrast_targets_of(step)
    directive["form"] = step_type
    directive["primary_target"] = primary
    directive["contrast_targets"] = contrasts

    if step_type == DRILL_BLOCK:
        directive["mode"] = str(step.get("drill_mode") or directive.get("mode") or _BLOCKED)
        directive["round_size"] = round_size_for(step, policy)
        rounds = step.get("rounds")
        directive["rounds"] = (
            int(rounds)
            if isinstance(rounds, int) and not isinstance(rounds, bool)
            else _int_setting(policy, DRILL_BLOCK, "rounds_min", DEFAULT_ROUNDS_MIN)
        )
        primary_limit = _int_setting(policy, DRILL_BLOCK, "frames_max_primary", DEFAULT_FRAMES_MAX_PRIMARY)
        contrast_limit = _int_setting(
            policy, DRILL_BLOCK, "frames_max_per_contrast", DEFAULT_FRAMES_MAX_PER_CONTRAST
        )
        frames: list[dict[str, Any]] = []
        if primary and primary.get("target_ref"):
            frames += frames_for_target(
                program, str(primary["target_ref"]), role="target", limit=primary_limit
            )
        if directive["mode"] == _INTERLEAVED:
            for contrast in contrasts:
                if contrast.get("target_ref"):
                    frames += frames_for_target(
                        program, str(contrast["target_ref"]), role="contrast", limit=contrast_limit
                    )
        directive["frames"] = frames
        if step.get("declared_limit_seconds") is not None:
            directive["declared_limit_seconds"] = timed_limit_for(step, policy)
    elif step_type == RECONSTRUCTION:
        topic_id = str(primary["target_ref"]) if primary and primary.get("target_ref") else ""
        text = choose_reconstruction_text(program, topic_id, recent_text_ids=recent_text_ids)
        directive["text"] = text
        directive["text_id"] = str(text["id"]) if text else None
    else:
        directive["declared_limit_seconds"] = timed_limit_for(step, policy)
        directive["expected_targets"] = [
            str(target["target_ref"]) for target in _step_targets(step) if target.get("target_ref")
        ]
    return directive
