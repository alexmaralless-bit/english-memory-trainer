"""Learner-facing lesson profiles and deterministic lesson proposals.

``mode`` and ``step_type`` are internal control concepts.  A
:class:`LessonProfile` is what the tutor announces to the learner: what kind
of lesson this is, why it was chosen, and what the learner will do.

The proposal is deliberately read-only and deterministic.  Starting a lesson
may compare its hash with ``expected_proposal_hash`` so a recommendation cannot
silently change between the preview and the learner's consent.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from english_trainer.kernel.encoding import payload_hash

LessonProfile = Literal[
    "program_lesson",
    "free_conversation",
    "practice",
    "spaced_review",
    "error_clinic",
    "transfer_simulation",
    "writing_workshop",
    "reading_workshop",
    "vocabulary_lesson",
    "diagnostic",
    "drill",
]

LESSON_PROFILES: tuple[LessonProfile, ...] = (
    "program_lesson",
    "free_conversation",
    "practice",
    "spaced_review",
    "error_clinic",
    "transfer_simulation",
    "writing_workshop",
    "reading_workshop",
    "vocabulary_lesson",
    "diagnostic",
    # [PD-2026-09-22] the eleventh profile: a proceduralization lesson, where
    # the volume of practice exceeds the volume of explanation and the full
    # "why" is saved for the closing debrief (learning-model 9.1).
    "drill",
)

PROFILE_LABELS: dict[LessonProfile, str] = {
    "program_lesson": "Program lesson",
    "free_conversation": "Free conversation",
    "practice": "Practice lesson",
    "spaced_review": "Spaced review",
    "error_clinic": "Error clinic",
    "transfer_simulation": "Transfer simulation",
    "writing_workshop": "Writing workshop",
    "reading_workshop": "Reading workshop",
    "vocabulary_lesson": "Vocabulary lesson",
    "diagnostic": "Diagnostic lesson",
    "drill": "Drill lesson",
}

_PHASES: dict[LessonProfile, tuple[tuple[str, str], ...]] = {
    "program_lesson": (
        ("orientation", "Name the topic, format, purpose, and route through the lesson."),
        ("connection", "Activate a small amount of relevant known language."),
        ("explanation", "Build a clear mental model with contrasts and examples."),
        ("guided_practice", "Retrieve the target with support and immediate feedback."),
        ("independent_use", "Use the target without a model in a meaningful context."),
        ("recap", "Summarise the rule, errors, and the next review cue."),
    ),
    "free_conversation": (
        ("orientation", "Agree on the theme and the correction rhythm."),
        ("conversation", "Sustain an understandable conversation with known language."),
        ("language_noticing", "Notice a small number of useful new units in context."),
        ("feedback", "Correct focus errors and briefly recap useful language."),
    ),
    "practice": (
        ("orientation", "Name the skill being practised and the success criterion."),
        ("worked_example", "Inspect one solved example when support is useful."),
        ("retrieval", "Complete varied retrieval tasks without answer leakage."),
        ("feedback", "Explain errors and retry the difficult form."),
        ("recap", "Record what is stable and what needs another review."),
    ),
    "spaced_review": (
        ("orientation", "Explain why these due items were selected."),
        ("retrieval", "Recall due material before seeing the answer."),
        ("feedback", "Correct, explain, and retry failed retrievals."),
        ("transfer", "Use recovered material in a fresh context."),
        ("recap", "Summarise retention risks and the next review."),
    ),
    "error_clinic": (
        ("orientation", "Name the recurring error pattern without blame."),
        ("diagnosis", "Contrast the learner form with the intended form."),
        ("repair", "Practise the smallest useful correction."),
        ("transfer", "Use the repaired form in a new sentence or exchange."),
        ("recap", "Create a compact self-check."),
    ),
    "transfer_simulation": (
        ("orientation", "Set the real-life role, goal, and constraints."),
        ("preparation", "Recall the language needed for the scenario."),
        ("simulation", "Complete the scenario with minimal tutor intervention."),
        ("debrief", "Analyse choices, errors, and alternative phrasings."),
        ("retry", "Repeat the difficult moment with a changed condition."),
    ),
    "writing_workshop": (
        ("orientation", "Name the text, audience, purpose, and success criteria."),
        ("model_analysis", "Notice useful structure in a short authored model."),
        ("draft", "Produce a purposeful first draft."),
        ("revision", "Revise content and language using focused feedback."),
        ("recap", "Extract reusable writing decisions."),
    ),
    "reading_workshop": (
        ("orientation", "Name the reading purpose and text strategy."),
        ("prediction", "Activate relevant knowledge without pre-teaching every answer."),
        ("reading", "Read an authored text for meaning."),
        ("analysis", "Retrieve evidence, infer meaning, and notice language."),
        ("recap", "Summarise meaning and transferable reading moves."),
    ),
    "vocabulary_lesson": (
        ("orientation", "Name the lexical field and communicative purpose."),
        ("meaning_and_form", "Connect meaning, form, pronunciation, and register."),
        ("contrast", "Separate close meanings and expose common traps."),
        ("retrieval", "Recall the units in varied short contexts."),
        ("use", "Use selected units in an original message."),
        ("recap", "Create compact memory cues and review targets."),
    ),
    "diagnostic": (
        ("orientation", "Explain what will be sampled and that this is not teaching."),
        ("sampling", "Elicit independent performance across selected dimensions."),
        ("clarification", "Resolve ambiguous evidence without coaching the answer."),
        ("summary", "Report evidence, uncertainty, and the recommended next lesson."),
    ),
    # The canonical drill agenda (control 4.2a [PD-2026-09-22]). The order is
    # normative, not decorative: a blocked round has to establish the pattern
    # before an interleaved round can make it survive competing forms, and the
    # explanation is deliberately last.
    "drill": (
        ("retrieval_warmup", "Recall due material from memory before anything new appears."),
        ("frame_set", "Introduce the frame set with the rule stated in one line."),
        ("drill_blocked", "Round 1: one pattern, massed, until the form comes without searching."),
        ("drill_interleaved", "Round 2: the same pattern mixed with the forms it competes against."),
        ("reconstruction", "Rebuild an authored text from its key words."),
        ("timed_writing", "Write to the announced time limit without stopping to polish."),
        ("debrief", "Now explain the why in full, and name what the next session repeats."),
    ),
}


def require_profile(value: str) -> LessonProfile:
    """Return a valid profile or raise a stable, user-facing ``ValueError``."""
    if value not in LESSON_PROFILES:
        expected = ", ".join(LESSON_PROFILES)
        raise ValueError(f"unknown lesson profile {value!r}; expected one of {expected}")
    return value


def duration_class(duration_minutes: int) -> Literal["micro", "full"]:
    """10-19 minutes is a micro-lesson; 20+ minutes is a full lesson."""
    if duration_minutes < 10:
        raise ValueError("a lesson needs at least 10 minutes")
    return "micro" if duration_minutes < 20 else "full"


def resolved_topic_title(topic: dict[str, Any]) -> str:
    """Resolve a learner-facing title for every topic.

    Authored ``title`` wins.  Existing curriculum remains compatible through a
    deterministic fallback derived from the stable id; validation can therefore
    guarantee that every loaded topic has a usable title while authors enrich
    important topics gradually.
    """
    authored = str(topic.get("title") or "").strip()
    if authored:
        return authored
    tail = str(topic.get("id") or "English topic").rsplit(".", 1)[-1]
    return tail.replace("-", " ").replace("_", " ").strip().title()


def _topic_by_id(program: dict[str, Any], target_ref: str) -> dict[str, Any] | None:
    for topic in program.get("topics", []):
        if str(topic.get("id")) == target_ref:
            return cast(dict[str, Any], topic)
    for item in program.get("lexicon", []):
        if str(item.get("id")) == target_ref:
            return cast(dict[str, Any], item)
    return None


def _recommended_target(
    program: dict[str, Any],
    profile: LessonProfile,
    presented_targets: frozenset[str],
    known_targets: frozenset[str],
) -> dict[str, Any] | None:
    topics = [cast(dict[str, Any], topic) for topic in program.get("topics", [])]
    if profile == "vocabulary_lesson":
        lexical_items = [
            cast(dict[str, Any], item)
            for item in program.get("lexicon", [])
            if str(item.get("usage_policy", "safe_to_use")) != "recognition_only"
            and str(item.get("currency", "current")) == "current"
        ]
        candidates = [item for item in lexical_items if str(item.get("id")) not in presented_targets]
        return candidates[0] if candidates else (lexical_items[0] if lexical_items else None)
    if profile == "program_lesson":
        candidates = [topic for topic in topics if str(topic.get("id")) not in presented_targets]
        return candidates[0] if candidates else (topics[0] if topics else None)
    known = [topic for topic in topics if str(topic.get("id")) in known_targets]
    if known:
        return known[0]
    if profile == "free_conversation":
        return None
    presented = [topic for topic in topics if str(topic.get("id")) in presented_targets]
    return presented[0] if presented else None


def build_lesson_proposal(
    *,
    program: dict[str, Any],
    duration_minutes: int,
    profile: str = "program_lesson",
    target_ref: str | None = None,
    theme: str | None = None,
    presented_targets: frozenset[str] = frozenset(),
    known_targets: frozenset[str] = frozenset(),
    explicit_request: bool = False,
) -> dict[str, Any]:
    """Build the announcement/consent contract shown before a lesson starts."""
    selected_profile = require_profile(profile)
    selected = (
        _topic_by_id(program, target_ref)
        if target_ref is not None
        else _recommended_target(program, selected_profile, presented_targets, known_targets)
    )
    if target_ref is not None and selected is None:
        raise ValueError(f"unknown curriculum target {target_ref!r}")

    central_ref = str(selected.get("id")) if selected is not None else None
    central_title = resolved_topic_title(selected) if selected is not None else None
    newness = "none"
    if central_ref is not None:
        if central_ref in known_targets:
            newness = "known"
        elif central_ref in presented_targets:
            newness = "seen"
        else:
            newness = "new"
    lesson_kind = duration_class(duration_minutes)
    label = PROFILE_LABELS[selected_profile]
    subject = theme.strip() if theme and theme.strip() else central_title
    title = f"{label}: {subject}" if subject else label
    phases = _PHASES[selected_profile]
    agenda = [
        {
            "phase_id": phase_id,
            "name": phase_id.replace("_", " ").title(),
            "purpose": purpose,
        }
        for phase_id, purpose in phases
    ]
    reason_kind = "learner_request" if explicit_request else "system_recommendation"
    if explicit_request:
        reason = "You chose this lesson profile, topic, or theme."
    elif selected_profile == "program_lesson" and central_ref is not None:
        reason = "This is the next suitable central topic in the authored program."
    elif selected_profile == "spaced_review":
        reason = "This profile retrieves material near its review point."
    elif selected_profile == "drill":
        reason = (
            "This profile turns a known pattern into an automatic one: more practice than "
            "explanation, and the full explanation at the end."
        )
    else:
        reason = "This profile best matches the current lesson request and available learner state."

    proposal: dict[str, Any] = {
        "schema_version": 1,
        "profile": selected_profile,
        "title": title,
        "duration_minutes": duration_minutes,
        "duration_class": lesson_kind,
        "central_topic": (
            {
                "target_ref": central_ref,
                "title": central_title,
                "can_do": selected.get("can_do"),
                "newness": newness,
            }
            if selected is not None
            else None
        ),
        "theme": theme.strip() if theme and theme.strip() else None,
        "reason": reason,
        "reason_kind": reason_kind,
        # A direct request is consent.  A system recommendation remains a
        # proposal for the tutor to announce and confirm before delivery.
        "requires_confirmation": not explicit_request,
        "agenda": agenda,
        "language_envelope": {
            "basis": "known_language_and_current_curriculum",
            "new_units_min": 0 if selected_profile in ("spaced_review", "diagnostic") else 1,
            "new_units_max": 3 if selected_profile == "free_conversation" else 5,
            "correction_rhythm": (
                "focus_immediately_batch_secondary_errors"
                if selected_profile == "free_conversation"
                else "explain_then_retry"
            ),
        },
    }
    proposal["proposal_hash"] = payload_hash(proposal)
    return proposal


def build_lesson_arc(proposal: dict[str, Any]) -> dict[str, Any]:
    """Turn a proposal into the stable LessonArc persisted with the session."""
    return {
        "schema_version": 1,
        "arc_id": str(proposal["proposal_hash"]),
        "profile": proposal["profile"],
        "title": proposal["title"],
        "duration_class": proposal["duration_class"],
        "central_topic": proposal.get("central_topic"),
        "theme": proposal.get("theme"),
        "reason": proposal["reason"],
        "reason_kind": proposal["reason_kind"],
        "agenda": [dict(item) for item in proposal["agenda"]],
        "language_envelope": dict(proposal["language_envelope"]),
        "proposal_hash": proposal["proposal_hash"],
    }


def phase_for_step(
    arc: dict[str, Any],
    index: int,
    total: int,
    step_type: str,
    *,
    agenda_slot: int | None = None,
) -> dict[str, Any]:
    """Assign a planned step to an arc phase without changing step semantics.

    ``agenda_slot`` is the exact phase a profile with a *normative* agenda (the
    `drill` profile) already decided on; proportional slotting would drift as
    soon as one optional step is missing. Profiles without one keep the
    historical behaviour byte-for-byte.
    """
    agenda = list(arc.get("agenda") or [])
    if not agenda:
        return {"phase_id": "activity", "name": "Activity"}
    if agenda_slot is not None and 0 <= agenda_slot < len(agenda):
        return dict(agenda[agenda_slot])
    if step_type == "new_material_intro":
        preferred = next(
            (
                item
                for item in agenda
                # ``frame_set`` is the drill profile's explanation slot: one line
                # of rule, not a lecture.
                if item["phase_id"] in ("explanation", "meaning_and_form", "frame_set")
            ),
            agenda[min(index, len(agenda) - 1)],
        )
        return dict(preferred)
    # Preserve orientation for the tutor announcement rather than manufacturing
    # a fake engine step.  Activities occupy the remaining phases in order.
    activity_phases = [
        item for item in agenda if item["phase_id"] not in ("orientation", "recap", "summary")
    ] or agenda
    slot = min((index * len(activity_phases)) // max(total, 1), len(activity_phases) - 1)
    return dict(activity_phases[slot])
