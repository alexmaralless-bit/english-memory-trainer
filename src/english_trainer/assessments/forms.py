"""Fixed, authored, versioned placement forms (assessments 3; flows/placement).

Forms are **authored** fixed item sets with a deterministic seed, never
generated on the fly -- comparability of results between forms and between
re-takes is the whole point (flows/placement, MUST). Each item declares its own
``target_ref`` and ``dimension`` (evidence 4.1 precedence); the engine derives
nothing about aim from the learner's answer.

This increment ships ONE small, representative form -- a handful of objective
items across grammar/vocabulary/reading plus one provisional writing item --
sufficient to exercise the lifecycle, exposure and scoring hand-off end to end.
The full A1-B1 form content (and the second form the two-form rule needs) is
authored in the content phase (П, OPEN-17); only the mechanism lives here.
"""

from __future__ import annotations

from typing import Any

# Item kinds. Objective items are checked by the engine against an answer key
# (deterministic normalization); the writing item records a provisional
# observation and contributes no measured level until the placement rubric
# integration lands (deferred -- see assessments.placement).
OBJECTIVE = "objective"
WRITING = "writing"

# The single shipped form. Sections follow the core-skill order; items keep a
# stable authored order so exposure ids and replay are reproducible.
_PLACEMENT_EN_CORE_V1: dict[str, Any] = {
    "form_version": "placement-en-core@1",
    "seed": "placement-en-core@1",
    "sections": ["grammar", "vocabulary", "reading", "writing"],
    "items": [
        # Grammar: one target measured by three items so a fully-correct
        # placement demonstrably reaches the ACTIVE ceiling (never MASTERED).
        {
            "item_id": "g-be-1",
            "section": "grammar",
            "kind": OBJECTIVE,
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "I ___ an engineer.",
            "answer_key": ["am"],
        },
        {
            "item_id": "g-be-2",
            "section": "grammar",
            "kind": OBJECTIVE,
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "She ___ my manager.",
            "answer_key": ["is"],
        },
        {
            "item_id": "g-be-3",
            "section": "grammar",
            "kind": OBJECTIVE,
            "target_ref": "grammar.be.identity",
            "dimension": "recognition",
            "prompt": "They ___ on my team.",
            "answer_key": ["are"],
        },
        # Vocabulary: one core lexical target.
        {
            "item_id": "v-greeting-1",
            "section": "vocabulary",
            "kind": OBJECTIVE,
            "target_ref": "vocabulary.core.greeting",
            "dimension": "recognition",
            "prompt": "A common informal greeting is ___.",
            "answer_key": ["hi", "hello"],
        },
        # Reading: short-gist true/false.
        {
            "item_id": "r-gist-1",
            "section": "reading",
            "kind": OBJECTIVE,
            "target_ref": "reading.gist.short",
            "dimension": "recognition",
            "prompt": "'The meeting is at noon.' -- The meeting is in the morning. (true/false)",
            "answer_key": ["false"],
        },
        # Writing: a short rubric fragment. Provisional-only in this increment.
        {
            "item_id": "w-sentence-1",
            "section": "writing",
            "kind": WRITING,
            "target_ref": "writing.sentence.simple",
            "dimension": "spontaneous_production",
            "prompt": "Write one sentence introducing yourself to a new team.",
            "rubric_ref": "rubric:placement-writing-provisional",
        },
    ],
}

_FORMS: dict[str, dict[str, Any]] = {
    _PLACEMENT_EN_CORE_V1["form_version"]: _PLACEMENT_EN_CORE_V1,
}

DEFAULT_FORM_VERSION = _PLACEMENT_EN_CORE_V1["form_version"]


class UnknownForm(Exception):
    """The requested form selector does not resolve to an authored form."""


def select_form(form_selector: str | None) -> dict[str, Any]:
    """Resolve ``form_selector`` to an authored form (default when ``None``).

    No on-the-fly generation: an unknown selector is refused, never synthesized.
    """
    version = form_selector or DEFAULT_FORM_VERSION
    form = _FORMS.get(version)
    if form is None:
        raise UnknownForm(f"no authored placement form {version!r}; forms are fixed (assessments 3)")
    return form


def form_sections(form: dict[str, Any]) -> list[str]:
    return list(form["sections"])


def section_items(form: dict[str, Any], section: str) -> list[dict[str, Any]]:
    return [dict(item) for item in form["items"] if item["section"] == section]


def form_item(form: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in form["items"]:
        if item["item_id"] == item_id:
            return dict(item)
    return None


def item_exposure_id(form_version: str, item_id: str) -> str:
    """The stable exposure key for one item of a form (assessments 3).

    Keyed by ``(form_version, item_id)`` so exposure history follows the exact
    authored item across placements and re-takes.
    """
    return f"exposure:{form_version}#{item_id}"
