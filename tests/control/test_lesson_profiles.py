from __future__ import annotations

import pytest

from english_trainer.control.lesson_profiles import (
    LESSON_PROFILES,
    build_lesson_arc,
    build_lesson_proposal,
    duration_class,
)

PROGRAM = {
    "topics": [
        {
            "id": "grammar.articles.identity",
            "title": "A, an, and the",
            "can_do": "Use basic articles.",
        },
        {
            "id": "grammar.do-questions",
            "title": "Questions with do",
            "can_do": "Ask routine questions.",
        },
    ],
    "lexicon": [
        {
            "id": "word.ticket",
            "title": "ticket",
            "usage_policy": "safe_to_use",
            "currency": "current",
        }
    ],
}


def test_profiles_are_learner_facing_and_duration_is_explicit() -> None:
    assert len(LESSON_PROFILES) == 11  # [PD-2026-09-22] `drill` is the eleventh
    assert duration_class(10) == "micro"
    assert duration_class(19) == "micro"
    assert duration_class(20) == "full"
    with pytest.raises(ValueError, match="at least 10"):
        duration_class(9)


def test_direct_topic_request_is_consent_and_builds_a_complete_arc() -> None:
    proposal = build_lesson_proposal(
        program=PROGRAM,
        duration_minutes=30,
        profile="program_lesson",
        target_ref="grammar.articles.identity",
        presented_targets=frozenset(),
        known_targets=frozenset(),
        explicit_request=True,
    )
    assert proposal["requires_confirmation"] is False
    assert proposal["reason_kind"] == "learner_request"
    assert proposal["central_topic"]["newness"] == "new"
    assert proposal["title"] == "Program lesson: A, an, and the"
    assert len(proposal["agenda"]) >= 6
    arc = build_lesson_arc(proposal)
    assert arc["proposal_hash"] == proposal["proposal_hash"]
    assert arc["central_topic"]["target_ref"] == "grammar.articles.identity"


def test_system_recommendation_needs_confirmation_and_selects_one_topic() -> None:
    proposal = build_lesson_proposal(
        program=PROGRAM,
        duration_minutes=15,
        presented_targets=frozenset({"grammar.articles.identity"}),
        known_targets=frozenset({"grammar.articles.identity"}),
    )
    assert proposal["requires_confirmation"] is True
    assert proposal["reason_kind"] == "system_recommendation"
    assert proposal["central_topic"]["target_ref"] == "grammar.do-questions"
    assert proposal["duration_class"] == "micro"


def test_unknown_requested_target_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown curriculum target"):
        build_lesson_proposal(
            program=PROGRAM,
            duration_minutes=20,
            target_ref="grammar.made-up",
            explicit_request=True,
        )


def test_free_conversation_does_not_invent_an_unseen_central_topic() -> None:
    proposal = build_lesson_proposal(
        program=PROGRAM,
        duration_minutes=20,
        profile="free_conversation",
        presented_targets=frozenset({"grammar.articles.identity"}),
        known_targets=frozenset(),
    )

    assert proposal["central_topic"] is None
    assert proposal["language_envelope"]["new_units_max"] == 3


def test_vocabulary_profile_recommends_a_safe_lexical_item() -> None:
    proposal = build_lesson_proposal(
        program=PROGRAM,
        duration_minutes=20,
        profile="vocabulary_lesson",
    )

    assert proposal["central_topic"]["target_ref"] == "word.ticket"
    assert proposal["title"] == "Vocabulary lesson: ticket"
