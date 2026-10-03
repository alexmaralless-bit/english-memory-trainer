"""Authored placement forms: resolution, presentation and grading (assessments 3).

Forms are **authored** fixed item sets with a deterministic seed, never
generated on the fly -- comparability of results between forms and between
re-takes is the whole point (flows/placement, MUST). Each item declares its own
``target_ref`` and ``dimension`` (evidence 4.1 precedence); the engine derives
nothing about aim from the learner's answer.

The forms themselves are **curriculum data** (``curriculum/assessments/*.yaml``,
loaded into ``program["placement_forms"]`` and hashed into the curriculum
snapshot). This module is a pure function over such a loaded program: it
resolves which form a learner sits (default / rotation / explicit selector),
exposes the learner-facing view of an item (never the answer key), and grades
an answer deterministically per item kind. No Python-embedded form content
lives here -- only test fixtures still carry an inline form.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

#: The key the curriculum loader publishes authored forms under.
FORMS_KEY = "placement_forms"

# Item kinds (closed, spec 1). ``objective`` is the legacy kind of the
# pre-curriculum stub form, kept graded so historical placements still replay.
CHOICE = "choice"
CLOZE = "cloze"
TRUE_FALSE = "true_false"
WRITING = "writing"
OBJECTIVE = "objective"
ITEM_KINDS: tuple[str, ...] = (CHOICE, CLOZE, TRUE_FALSE, WRITING)
OBJECTIVE_KINDS: tuple[str, ...] = (CHOICE, CLOZE, TRUE_FALSE, OBJECTIVE)

#: Option letters a choice item may be answered with, in option order.
OPTION_LETTERS = "abcdefgh"

# A true/false item is answered in either language the tutor speaks; the
# mapping is closed and deterministic, never a fuzzy match.
_TRUE_WORDS = frozenset({"true", "t", "yes", "y", "да", "верно"})
_FALSE_WORDS = frozenset({"false", "f", "no", "n", "нет", "неверно"})


class UnknownForm(Exception):
    """The requested form selector does not resolve to an authored form."""


def _normalize_answer(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


# -- resolution ---------------------------------------------------------------


def program_forms(program: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every authored form of a loaded program, ordered by ``form_version``."""
    forms = [dict(form) for form in program.get(FORMS_KEY) or [] if isinstance(form, Mapping)]
    forms.sort(key=lambda form: str(form.get("form_version")))
    return forms


def select_form(
    program: Mapping[str, Any],
    form_selector: str | None = None,
    *,
    seen: Mapping[str, str] | None = None,
    cooldown_days: int = 0,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve the form this placement sits, plus the record of *why*.

    No on-the-fly generation: an unknown selector is refused, never
    synthesized. Without a selector the default is the lowest ``form_version``
    the learner has never been shown; once every form has been seen, the least
    recently seen one is rotated in and the ``form_cooldown_days`` window is
    reported (never enforced as a block -- placement blocks nothing; a re-seen
    item is already zero-weighted by the exposure rule).
    """
    forms = program_forms(program)
    if not forms:
        raise UnknownForm(
            "the curriculum snapshot carries no placement forms; author "
            "curriculum/assessments/*.yaml and run `trainer curriculum activate`"
        )
    history = dict(seen or {})
    if form_selector:
        for form in forms:
            if str(form.get("form_version")) == form_selector:
                return form, _selection(form, "explicit_selector", history, cooldown_days, now)
        raise UnknownForm(f"no authored placement form {form_selector!r}; forms are fixed (assessments 3)")
    for form in forms:  # ascending form_version
        if str(form.get("form_version")) not in history:
            return form, _selection(form, "unseen", history, cooldown_days, now)
    least_recent = min(
        forms, key=lambda form: (history[str(form.get("form_version"))], str(form.get("form_version")))
    )
    return least_recent, _selection(least_recent, "least_recently_seen", history, cooldown_days, now)


def _selection(
    form: Mapping[str, Any],
    basis: str,
    history: Mapping[str, str],
    cooldown_days: int,
    now: datetime | None,
) -> dict[str, Any]:
    version = str(form.get("form_version"))
    last_seen = history.get(version)
    elapsed = True
    if last_seen is not None and now is not None and cooldown_days > 0:
        elapsed = datetime.fromisoformat(last_seen) + timedelta(days=cooldown_days) <= now
    return {
        "form_version": version,
        "basis": basis,
        "last_seen_at": last_seen,
        "cooldown_days": int(cooldown_days),
        "cooldown_elapsed": bool(elapsed),
    }


# -- shape --------------------------------------------------------------------


def form_sections(form: Mapping[str, Any]) -> list[str]:
    return [str(section) for section in form["sections"]]


def section_items(form: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    return [dict(item) for item in form["items"] if str(item.get("section")) == section]


def form_item(form: Mapping[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in form["items"]:
        if str(item.get("item_id")) == item_id:
            return dict(item)
    return None


def form_passages(form: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The reading passages, presented once before their questions."""
    return [
        {
            "passage_id": str(passage.get("passage_id")),
            "cefr": passage.get("cefr"),
            "title": passage.get("title"),
            "text": passage.get("text"),
        }
        for passage in form.get("passages") or []
    ]


def public_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """The learner-facing view of an item: everything needed to present it
    verbatim, and **never** the answer key."""
    view: dict[str, Any] = {
        "item_id": str(item.get("item_id")),
        "section": str(item.get("section")),
        "band": item.get("band"),
        "kind": str(item.get("kind")),
        "prompt": item.get("prompt"),
        "target_ref": item.get("target_ref"),
        "dimension": item.get("dimension"),
    }
    if item.get("kind") == CHOICE:
        view["options"] = [str(option) for option in item.get("options") or []]
    if item.get("passage_id"):
        view["passage_id"] = str(item["passage_id"])
    if item.get("kind") == WRITING:
        view["rubric_ref"] = item.get("rubric_ref")
        view["min_words"] = item.get("min_words")
        view["max_words"] = item.get("max_words")
    return view


def item_exposure_id(form_version: str, item_id: str) -> str:
    """The stable exposure key for one item of a form (assessments 3).

    Keyed by ``(form_version, item_id)`` so exposure history follows the exact
    authored item across placements and re-takes.
    """
    return f"exposure:{form_version}#{item_id}"


# -- deterministic grading ----------------------------------------------------


def _matches_key(answer: str, answer_key: Any) -> bool:
    variants: Sequence[Any] = answer_key if isinstance(answer_key, list) else [answer_key]
    normalized = _normalize_answer(answer)
    return any(_normalize_answer(str(variant)) == normalized for variant in variants)


def _chosen_option(raw_answer: str, options: Sequence[Any]) -> str:
    """The option the learner picked: an ``a``-``d`` letter or the option text.

    A bare letter is resolved against the authored option order (the same order
    the tutor presents), so ``b`` and the full option text are the same answer.
    """
    normalized = _normalize_answer(raw_answer).rstrip(").:")
    if len(normalized) == 1 and normalized in OPTION_LETTERS:
        index = OPTION_LETTERS.index(normalized)
        if index < len(options):
            return str(options[index])
    return raw_answer


def _true_false(raw_answer: str) -> str | None:
    normalized = _normalize_answer(raw_answer).rstrip(".!")
    if normalized in _TRUE_WORDS:
        return "true"
    if normalized in _FALSE_WORDS:
        return "false"
    return None


def grade_item(item: Mapping[str, Any], raw_answer: str) -> bool:
    """Grade one objective item against its authored key. Total and pure.

    ``choice`` accepts the option letter or the option text, ``true_false``
    accepts true/false/yes/no/да/нет, ``cloze`` (and the legacy ``objective``
    kind) compares the normalized answer against every authored variant.
    A ``writing`` item is never graded here -- it is settled by the rubric.
    """
    kind = str(item.get("kind"))
    answer_key = item.get("answer_key")
    if kind == CHOICE:
        return _matches_key(_chosen_option(raw_answer, item.get("options") or []), answer_key)
    if kind == TRUE_FALSE:
        value = _true_false(raw_answer)
        return False if value is None else _matches_key(value, answer_key)
    if kind in (CLOZE, OBJECTIVE):
        return _matches_key(raw_answer, answer_key)
    return False
