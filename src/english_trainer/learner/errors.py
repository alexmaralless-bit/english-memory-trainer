"""Learner-module error types with stable codes (learner contract 0.11).

Each error carries a machine-stable ``code`` the CLI puts in the envelope's
``error_code`` (cli 4.2). Renaming one is a breaking change.
"""

from __future__ import annotations

from english_trainer.kernel.errors import KernelError


class LearnerError(KernelError):
    """Base for learner-module errors."""

    code = "LEARNER_ERROR"


class LexiconEntryInvalid(LearnerError):
    """The personal-lexicon entry is malformed -- fix the input, do not retry.

    Maps to the CLI's INVALID_INPUT (exit 3): an empty surface or an unknown
    ``source`` never becomes an entry.
    """

    code = "LEXICON_ENTRY_INVALID"


class LinkedItemNotFound(LearnerError):
    """``linked_item_id`` does not resolve to a lexical item in ACTIVE curriculum.

    A dangling or non-lexical id is refused with a stable error (learner 4;
    lexical-system §3 [invariant 2]): the engine never guesses a link by surface
    and never links to a topic. Maps to the CLI's NOT_FOUND (exit 4).
    """

    code = "LINKED_ITEM_NOT_FOUND"


class PreferencesInvalid(LearnerError):
    """A ``LearnerPreferences`` patch is malformed (learner §4a [PD-2026-09-22]).

    An unknown field, an out-of-range ``round_size``/``timed_limit_seconds``, or
    an unknown ``explanation_language``/``feedback_mode``/drill form is refused
    before it ever touches state (cli 4.5). Maps to the CLI's INVALID_INPUT
    (exit 3).
    """

    code = "PREFERENCES_INVALID"
