"""Authored forms as curriculum data: selection/rotation, per-kind grading, the
writing rubric hand-off and the placement-derived starting level (spec 1-4)."""

from __future__ import annotations

from typing import Any

import pytest

from english_trainer.assessments.forms import (
    UnknownForm,
    grade_item,
    program_forms,
    select_form,
)
from english_trainer.assessments.placement import (
    EVENT_SCORED,
    answer_placement,
    form_exposure_history,
    start_placement,
    submit_placement,
)
from english_trainer.kernel.encoding import payload_hash
from english_trainer.scoring.aggregates import (
    measured_working_level,
    placement_levels,
    placement_writing_level,
    provisional_working_estimate,
    self_reported_levels,
    working_levels,
)
from english_trainer.scoring.engine import fold_scores
from tests.assessments.fixtures import (
    FULL_FORM,
    FULL_FORM_CORRECT,
    FULL_FORM_VERSION,
    WRITING_ANSWER,
    full_program,
    policy,
    strong_writing_observations,
    writing_observations,
)

FORM_B: dict[str, Any] = {**FULL_FORM, "form_version": "placement-fixture-b@1"}
TWO_FORMS = {**full_program(), "placement_forms": [FULL_FORM, FORM_B]}


# -- selection ----------------------------------------------------------------


def test_forms_are_ordered_by_version_and_the_default_is_the_lowest_unseen() -> None:
    assert [form["form_version"] for form in program_forms(TWO_FORMS)] == [
        FULL_FORM_VERSION,
        "placement-fixture-b@1",
    ]
    form, selection = select_form(TWO_FORMS)
    assert form["form_version"] == FULL_FORM_VERSION
    assert selection["basis"] == "unseen"
    assert selection["last_seen_at"] is None


def test_a_seen_form_rotates_to_the_next_unseen_one() -> None:
    _form, selection = select_form(TWO_FORMS, seen={FULL_FORM_VERSION: "2026-09-01T10:00:00+00:00"})
    assert selection["form_version"] == "placement-fixture-b@1"
    assert selection["basis"] == "unseen"


def test_all_forms_seen_rotates_to_the_least_recently_seen_and_reports_the_cooldown(
    clock,
) -> None:
    seen = {
        FULL_FORM_VERSION: "2026-07-01T12:00:00+00:00",
        "placement-fixture-b@1": "2026-07-20T12:00:00+00:00",
    }
    form, selection = select_form(TWO_FORMS, seen=seen, cooldown_days=30, now=clock.now())
    assert form["form_version"] == FULL_FORM_VERSION  # the older exposure
    assert selection["basis"] == "least_recently_seen"
    assert selection["cooldown_elapsed"] is False  # 2026-07-22 is inside 30 days

    later = {**seen, FULL_FORM_VERSION: "2026-05-01T12:00:00+00:00"}
    _form, elapsed = select_form(TWO_FORMS, seen=later, cooldown_days=30, now=clock.now())
    assert elapsed["cooldown_elapsed"] is True


def test_an_explicit_selector_is_honoured_and_an_unknown_one_is_refused() -> None:
    form, selection = select_form(TWO_FORMS, "placement-fixture-b@1")
    assert form["form_version"] == "placement-fixture-b@1"
    assert selection["basis"] == "explicit_selector"
    with pytest.raises(UnknownForm):
        select_form(TWO_FORMS, "placement-nope@9")


def test_a_program_without_forms_is_refused_never_synthesized() -> None:
    with pytest.raises(UnknownForm):
        select_form({"placement_forms": []})


def test_rotation_reads_the_exposure_history_from_the_log(store, clock, random_source, full_registry) -> None:
    full_registry.register("curriculum", "two-forms@1", TWO_FORMS)
    full_registry.activate("curriculum", "two-forms@1")
    first = start_placement(store, full_registry, clock, random_source)
    assert first["form_version"] == FULL_FORM_VERSION
    answer_placement(
        store, clock, random_source, first["placement_id"], section="grammar", answers={"g-a1-01": "a"}
    )
    submit_placement(store, full_registry, clock, random_source, first["placement_id"])

    assert set(form_exposure_history(store)) == {FULL_FORM_VERSION}
    second = start_placement(store, full_registry, clock, random_source)
    # The second take gets the OTHER form: a memorized form is not a measurement.
    assert second["form_version"] == "placement-fixture-b@1"


# -- grading ------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["writes", "a", "A", "a)", "A.", " writes "])
def test_choice_accepts_the_letter_or_the_option_text(answer: str) -> None:
    item = next(i for i in FULL_FORM["items"] if i["item_id"] == "g-a1-01")
    assert grade_item(item, answer) is True


@pytest.mark.parametrize("answer", ["b", "write", "d", "kick off", ""])
def test_choice_refuses_a_wrong_letter_or_text(answer: str) -> None:
    item = next(i for i in FULL_FORM["items"] if i["item_id"] == "g-a1-01")
    assert grade_item(item, answer) is False


@pytest.mark.parametrize("answer", ["true", "TRUE", "yes", "y", "да", "верно"])
def test_true_false_accepts_both_languages(answer: str) -> None:
    item = next(i for i in FULL_FORM["items"] if i["item_id"] == "r-a2-01")
    assert grade_item(item, answer) is True


@pytest.mark.parametrize("answer", ["false", "no", "нет", "maybe"])
def test_true_false_rejects_the_other_value(answer: str) -> None:
    item = next(i for i in FULL_FORM["items"] if i["item_id"] == "r-a2-01")
    assert grade_item(item, answer) is False


def test_cloze_compares_every_authored_variant() -> None:
    item = {"kind": "cloze", "answer_key": ["have finished", "'ve finished"]}
    assert grade_item(item, "'VE   finished") is True
    assert grade_item(item, "finished") is False


def test_a_writing_item_is_never_graded_objectively() -> None:
    item = next(i for i in FULL_FORM["items"] if i["item_id"] == "w-a2-01")
    assert grade_item(item, WRITING_ANSWER) is False


# -- the whole form -----------------------------------------------------------


def _sit(
    store,
    registry,
    clock,
    random_source,
    *,
    answers: dict[str, dict[str, str]],
    observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = start_placement(store, registry, clock, random_source)
    placement_id = started["placement_id"]
    for section, section_answers in answers.items():
        answer_placement(
            store,
            clock,
            random_source,
            placement_id,
            section=section,
            answers=section_answers,
            observations=observations if section == "writing" else None,
        )
    return submit_placement(store, registry, clock, random_source, placement_id)


def test_a_fully_correct_form_measures_a_low_confidence_level_per_skill(
    store, full_registry, clock, random_source
) -> None:
    result = _sit(store, full_registry, clock, random_source, answers=dict(FULL_FORM_CORRECT))
    assert result["evidence_count"] == 20
    assert result["skills"] == {
        "grammar": {"level": "A2", "confidence": "low", "basis": "placement"},
        "reading": {"level": "A2", "confidence": "low", "basis": "placement"},
        "vocabulary": {"level": "A2", "confidence": "low", "basis": "placement"},
    }
    # Every scored row carries the band it measured, so the level is replayable.
    assert {row["band"] for row in result["scored_items"]} == {"A1", "A2"}


def test_a_partly_correct_form_falls_back_to_the_lower_band(
    store, full_registry, clock, random_source
) -> None:
    answers = {section: dict(items) for section, items in FULL_FORM_CORRECT.items()}
    # Two A2 grammar topics answered wrong -> only three fully-correct A2 topics,
    # below the floor of five, while A1 stays complete.
    answers["grammar"]["g-a2-01"] = "wrong"
    answers["grammar"]["g-a2-02"] = "wrong"
    result = _sit(store, full_registry, clock, random_source, answers=answers)
    assert result["skills"]["grammar"] == {"level": "A1", "confidence": "low", "basis": "placement"}
    # The other skills are untouched by the grammar gap.
    assert result["skills"]["reading"]["level"] == "A2"


def test_one_wrong_item_disqualifies_its_topic_entirely(store, full_registry, clock, random_source) -> None:
    answers = {"grammar": dict(FULL_FORM_CORRECT["grammar"])}
    for item_id in ("g-a1-01", "g-a2-01"):
        answers["grammar"][item_id] = "wrong"
    result = _sit(store, full_registry, clock, random_source, answers=answers)
    # Four fully-correct topics per band: neither band reaches the floor.
    assert "grammar" not in result["skills"]


# -- the writing hand-off -----------------------------------------------------


def _evidence(store) -> list[dict[str, Any]]:
    return [event.payload for event in store.read() if event.type == "evidence.added"]


def test_writing_observations_become_rubric_evidence_flagged_provisional(
    store, full_registry, clock, random_source
) -> None:
    result = _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={"writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": writing_observations()},
    )
    row = result["scored_items"][0]
    assert row["basis"] == "rubric"
    assert row["disposition"] == "scored"
    assert row["rubric_ref"] == "rubric:production.spontaneous"
    assert row["provisional"] is True
    assert row["contributing"] is True
    assert row["score_ppm"] > 0

    payload = _evidence(store)[0]
    assert payload["origin"] == "placement"
    assert payload["assessment_basis"] == "rubric"
    assert payload["rubric_step_type"] == "spontaneous_production"
    assert payload["provisional"] is True
    assert payload["pinned_rubric_version"] == "rubric@1"
    # A rubric fragment adds Mastery under the rubric cap, and no outcome: one
    # fragment never promotes a knowledge state.
    assert result["outcome_count"] == 0
    scores = fold_scores(store, policy("scoring-v2.yaml"))
    target = scores["written.fixture.a2-note"]
    assert target.knowledge_state == "NEW"
    assert target.mastery["spontaneous_production"] > 0


def test_writing_without_observations_contributes_nothing(store, full_registry, clock, random_source) -> None:
    result = _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={"writing": {"w-a2-01": WRITING_ANSWER}},
    )
    row = result["scored_items"][0]
    assert row["basis"] == "writing_unassessed"
    assert row["contributing"] is False
    assert result["evidence_count"] == 0
    assert _evidence(store) == []


def test_a_fabricated_observation_is_rejected_by_the_engine(
    store, full_registry, clock, random_source
) -> None:
    broken = writing_observations()
    broken[0]["span_ref"]["span_hash"] = "sha256:" + "0" * 64
    result = _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={"writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": broken},
    )
    row = result["scored_items"][0]
    # A required criterion lost its only finding: incomplete coverage settles
    # non-contributing, never as a learner zero (PD-7 C).
    assert row["disposition"] == "insufficient_evidence"
    assert row["contributing"] is False
    assert row["uncovered_required"] == ["target-control"]


def test_observations_for_a_non_writing_item_are_refused(store, full_registry, clock, random_source) -> None:
    from english_trainer.assessments.placement import PlacementPrecondition

    started = start_placement(store, full_registry, clock, random_source)
    with pytest.raises(PlacementPrecondition):
        answer_placement(
            store,
            clock,
            random_source,
            started["placement_id"],
            section="grammar",
            answers={"g-a1-01": "a"},
            observations={"g-a1-01": writing_observations()},
        )


def test_the_scored_event_carries_the_rows_the_level_is_derived_from(
    store, full_registry, clock, random_source
) -> None:
    _sit(store, full_registry, clock, random_source, answers=dict(FULL_FORM_CORRECT))
    scored = [event for event in store.read() if event.type == EVENT_SCORED][-1]
    rows = scored.payload["scored_items"]
    assert len(rows) == 20
    assert scored.payload["skills"]["grammar"]["basis"] == "placement"


# -- the provisional writing level end to end [PD-2026-09-22] ----------------


def _aggregates(store) -> dict[str, Any]:
    """The level rows a `trainer status` would print, straight off the log."""
    scoring_policy = policy("scoring-v2.yaml")
    program = full_program()
    levels = working_levels(
        fold_scores(store, scoring_policy),
        program,
        scoring_policy,
        placement=placement_levels(store, program, scoring_policy),
        placement_writing=placement_writing_level(store, scoring_policy),
    )
    return {
        "skills": levels,
        "measured_working_level": measured_working_level(levels),
        "provisional_working_estimate": provisional_working_estimate(
            levels, self_reported=self_reported_levels(store)
        ),
    }


def test_a_strong_fragment_gives_a_provisional_writing_level_only(
    store, full_registry, clock, random_source
) -> None:
    _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={**FULL_FORM_CORRECT, "writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": strong_writing_observations()},
    )
    aggregates = _aggregates(store)
    assert aggregates["skills"]["writing"] == {
        "level": "A2",
        "confidence": "very_low",
        "basis": "placement",
        "provisional": True,
        "active_topics": 0,
    }
    # Provisional is not measured: the measured field stays honestly unknown.
    assert aggregates["measured_working_level"] is None
    estimate = aggregates["provisional_working_estimate"]
    assert estimate["level"] == "A2"
    assert estimate["provisional"] is True


def test_an_adequate_fragment_stays_below_the_provisional_threshold(
    store, full_registry, clock, random_source
) -> None:
    """616_667 ppm is a settled fragment, not a claim about a band: under the
    700_000 ppm threshold nothing at all is written."""
    result = _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={**FULL_FORM_CORRECT, "writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": writing_observations()},
    )
    writing_row = next(row for row in result["scored_items"] if row["section"] == "writing")
    assert writing_row["score_ppm"] < 700000
    aggregates = _aggregates(store)
    assert aggregates["skills"]["writing"]["level"] is None
    assert aggregates["skills"]["writing"]["provisional"] is False
    assert aggregates["provisional_working_estimate"]["level"] is None


def test_the_aggregates_are_byte_stable_under_replay(store, full_registry, clock, random_source) -> None:
    """Same log, same pinned policy -> the same bytes, every time."""
    _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={**FULL_FORM_CORRECT, "writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": strong_writing_observations()},
    )
    first = payload_hash(_aggregates(store))
    second = payload_hash(_aggregates(store))
    assert first == second


def test_scoring_v1_derives_neither_band_from_the_same_log(
    store, full_registry, clock, random_source
) -> None:
    """An old pin keeps its behaviour: no objective band, no writing estimate."""
    _sit(
        store,
        full_registry,
        clock,
        random_source,
        answers={**FULL_FORM_CORRECT, "writing": {"w-a2-01": WRITING_ANSWER}},
        observations={"w-a2-01": strong_writing_observations()},
    )
    v1 = policy("scoring-v1.yaml")
    assert placement_levels(store, full_program(), v1) == {}
    assert placement_writing_level(store, v1) is None
