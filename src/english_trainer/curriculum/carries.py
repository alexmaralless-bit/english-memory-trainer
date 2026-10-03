"""The closed ``carries`` vocabulary of the automaticity layer (curriculum 2c;
lexical-system 1c) [PD-2026-09-22].

A ``carries`` tag names the grammar load a lexical unit actually puts in the
learner's mouth: a tense/aspect, an article use, or a structural pattern. The
vocabulary is **closed** -- an unknown tag is a validation error, never a new
category invented in a data file -- because the scheduler and the reconstruction
drills select by tag, and a typo would silently create an empty bucket.

The same vocabulary is duplicated in ``tools/check_authoring.py`` (the
standalone structural checker content authors run before the package is
importable); ``tests/curriculum/test_frames_and_texts.py`` asserts the two are
identical so they cannot drift.
"""

from __future__ import annotations

TENSE_CARRIES: frozenset[str] = frozenset(
    f"tense:{name}"
    for name in (
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
    )
)

ARTICLE_CARRIES: frozenset[str] = frozenset(
    f"article:{name}"
    for name in (
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
    )
)

STRUCTURE_CARRIES: frozenset[str] = frozenset(
    f"structure:{name}"
    for name in (
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
    )
)

CARRIES: frozenset[str] = TENSE_CARRIES | ARTICLE_CARRIES | STRUCTURE_CARRIES

# How many tags one unit may carry: a frame that claims more than three targets
# is not a frame, it is a sentence.
MAX_CARRIES = 3

# Frames per Grammar Engine topic, by frequency tier (curriculum 2c). Below the
# floor the topic cannot be drilled to automaticity, so it is an error, not a
# warning.
FRAME_FLOOR_BY_TIER: dict[str, int] = {"big-five": 12, "core": 12, "tail": 8}

__all__ = [
    "ARTICLE_CARRIES",
    "CARRIES",
    "FRAME_FLOOR_BY_TIER",
    "MAX_CARRIES",
    "STRUCTURE_CARRIES",
    "TENSE_CARRIES",
]
