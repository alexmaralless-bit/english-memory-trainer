"""The learner module: what belongs to the person, not to their knowledge.

Owns the personal lexicon (layer 3 of the lexical system). What is *measured*
is computed by scoring; what is *noted* is stored here. Adding a word is
enrollment, never evidence -- this module publishes no knowledge/level/XP event
(learner contract 0.11).
"""

from __future__ import annotations

from english_trainer.learner.errors import (
    LearnerError,
    LexiconEntryInvalid,
    LinkedItemNotFound,
)
from english_trainer.learner.lexicon import (
    EVENT_LEXICON_ENTRY_ADDED,
    build_encounter_events,
    find_encounter_entry,
    lexicon_add,
    lexicon_encounter,
    lexicon_entries,
    lexicon_list,
    normalize_surface,
    personal_lexicon_summary,
    relevant_lexicon_targets,
    resolve_linked_item,
    resolve_surface_exact,
)

__all__ = [
    "EVENT_LEXICON_ENTRY_ADDED",
    "LearnerError",
    "LexiconEntryInvalid",
    "LinkedItemNotFound",
    "build_encounter_events",
    "find_encounter_entry",
    "lexicon_add",
    "lexicon_encounter",
    "lexicon_entries",
    "lexicon_list",
    "normalize_surface",
    "personal_lexicon_summary",
    "relevant_lexicon_targets",
    "resolve_linked_item",
    "resolve_surface_exact",
]
