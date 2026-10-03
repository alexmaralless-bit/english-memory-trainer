"""The placement-derived working level (scoring@2 ``placement``): the band
rule, the low-confidence basis, its replacement by session evidence, and the
byte-for-byte unchanged behaviour of scoring@1 (canon 4/4b; learning-model 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.scoring.aggregates import (
    measured_working_level,
    placement_bands,
    placement_levels,
    placement_skill_levels,
    placement_writing_band,
    placement_writing_level,
    provisional_working_estimate,
    self_reported_levels,
    working_levels,
)
from english_trainer.scoring.engine import ACTIVE, TargetState
from english_trainer.scoring.policy import validate_scoring_policy

REPO = Path(__file__).resolve().parents[2]
POLICIES = REPO / "curriculum" / "policies"
PLACEMENT_SCORED_EVENT = "placement.scored"


def _policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((POLICIES / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


V1 = _policy("scoring-v1.yaml")
V2 = _policy("scoring-v2.yaml")

GRAMMAR_A1 = [f"grammar.level.a1-{n}" for n in range(1, 6)]
GRAMMAR_A2 = [f"grammar.level.a2-{n}" for n in range(1, 6)]
#: A reading band is three questions on ONE passage -- three distinct topics is
#: everything a real form offers, so the reading floor is 3 (PD-2026-09-22).
READING_B1 = [f"reading.level.b1-{n}" for n in range(1, 4)]
#: A C1 vocabulary band is four lexical items in the shipped forms.
VOCABULARY_C1 = [f"chunk.level.c1-{n}" for n in range(1, 5)]


def _program() -> dict[str, Any]:
    return {
        "topics": [
            *[{"id": t, "cefr": "A1", "track": "grammar-engine"} for t in GRAMMAR_A1],
            *[{"id": t, "cefr": "A2", "track": "grammar-engine"} for t in GRAMMAR_A2],
            *[{"id": t, "cefr": "B1", "track": "reading"} for t in READING_B1],
        ],
        "lexicon": [
            {"id": "chunk.level.a2-1", "cefr": "A2"},
            *[{"id": unit, "cefr": "C1"} for unit in VOCABULARY_C1],
        ],
    }


def _rows(
    targets: list[str],
    band: str,
    *,
    correct: bool = True,
    section: str = "grammar",
) -> list[dict[str, Any]]:
    return [
        {
            "item_id": f"{section[0]}-{band.lower()}-{index:02d}",
            "section": section,
            "band": band,
            "target_ref": target,
            "dimension": "recognition",
            "correct": correct,
        }
        for index, target in enumerate(targets, start=1)
    ]


def _writing_row(band: str, score_ppm: int | None, **overrides: Any) -> dict[str, Any]:
    return {
        "item_id": f"w-{band.lower()}-01",
        "section": "writing",
        "band": band,
        "kind": "writing",
        "target_ref": "written.level.note",
        "dimension": "spontaneous_production",
        "basis": "rubric",
        "correct": None,
        "contributing": True,
        "provisional": True,
        "score_ppm": score_ppm,
        **overrides,
    }


# -- the policies -------------------------------------------------------------


def test_both_shipped_scoring_policies_are_valid() -> None:
    assert validate_scoring_policy(V1) == []
    assert validate_scoring_policy(V2) == []


def test_scoring_v1_has_no_placement_section() -> None:
    """Old pins must keep behaving exactly as they did."""
    assert "placement" not in V1
    assert V2["placement"] == {
        # Per-skill floors [PD-2026-09-22]: a band offers 5-8 grammar topics,
        # 4-5 lexical items, 3 reading questions -- one shared floor of 5 would
        # leave reading unmeasurable and cap vocabulary at B2.
        "min_topics_by_skill": {"grammar": 5, "vocabulary": 4, "reading": 3},
        "confidence": "low",
        "basis": "placement",
        # Writing has no objective floor at all: the provisional rule instead.
        "writing": {"provisional_threshold_ppm": 700000, "confidence": "very_low"},
    }
    # Everything else is the same policy.
    assert {k: v for k, v in V2.items() if k not in ("policy_id", "placement")} == {
        k: v for k, v in V1.items() if k != "policy_id"
    }


def _placement(**overrides: Any) -> dict[str, Any]:
    section = {k: (dict(v) if isinstance(v, dict) else v) for k, v in V2["placement"].items()}
    section.update(overrides)
    return section


@pytest.mark.parametrize(
    "section",
    [
        # A floor that measures nothing, a floor for a skill that does not exist,
        # a missing core skill, a floor for writing (which has none by contract).
        _placement(min_topics_by_skill={"grammar": 0, "vocabulary": 4, "reading": 3}),
        _placement(min_topics_by_skill={"grammar": 5, "vocabulary": 4, "reading": 3, "listening": 3}),
        _placement(min_topics_by_skill={"grammar": 5, "vocabulary": 4}),
        _placement(min_topics_by_skill={"grammar": 5, "vocabulary": 4, "reading": 3, "writing": 1}),
        _placement(min_topics_by_skill=5),
        _placement(confidence="certain"),
        _placement(basis="evidence"),
        # The writing rule: missing, out of the ppm scale, or an unknown level.
        _placement(writing=None),
        _placement(writing={"provisional_threshold_ppm": 1_000_001, "confidence": "very_low"}),
        _placement(writing={"provisional_threshold_ppm": -1, "confidence": "very_low"}),
        _placement(writing={"provisional_threshold_ppm": "700000", "confidence": "very_low"}),
        _placement(writing={"provisional_threshold_ppm": 700000, "confidence": "certain"}),
        "not-a-mapping",
    ],
)
def test_a_broken_placement_section_never_activates(section: Any) -> None:
    assert validate_scoring_policy({**V2, "placement": section}) != []


def test_a_zero_writing_threshold_is_admissible() -> None:
    """0 ppm is a deliberate (if generous) authored setting, not a mistake."""
    threshold = {"provisional_threshold_ppm": 0, "confidence": "very_low"}
    assert validate_scoring_policy({**V2, "placement": _placement(writing=threshold)}) == []


# -- the band rule ------------------------------------------------------------


def test_the_highest_band_with_five_fully_correct_topics_wins() -> None:
    rows = [*_rows(GRAMMAR_A1, "A1"), *_rows(GRAMMAR_A2, "A2")]
    assert placement_bands(rows, _program(), V2) == {"grammar": "A2"}


def test_a_band_below_the_floor_does_not_count() -> None:
    rows = [*_rows(GRAMMAR_A1, "A1"), *_rows(GRAMMAR_A2[:4], "A2")]
    assert placement_bands(rows, _program(), V2) == {"grammar": "A1"}


def test_one_wrong_item_disqualifies_the_whole_topic() -> None:
    rows = [*_rows(GRAMMAR_A1, "A1")]
    rows.append({**rows[0], "item_id": "g-a1-06", "correct": False})
    assert placement_bands(rows, _program(), V2) == {}


def test_an_unresolvable_target_is_ignored_not_guessed() -> None:
    rows = _rows([f"grammar.unknown-{n}" for n in range(5)], "A1")
    assert placement_bands(rows, _program(), V2) == {}


def test_a_partial_weight_cell_does_not_measure_a_skill() -> None:
    """``written-production-mediation`` recognition feeds reading at 0.5: a
    partial contribution to Mastery is not a measured reading band."""
    program = {
        "topics": [
            {"id": f"written.level.{n}", "cefr": "A2", "track": "written-production-mediation"}
            for n in range(5)
        ],
        "lexicon": [],
    }
    rows = _rows([f"written.level.{n}" for n in range(5)], "A2")
    assert placement_bands(rows, program, V2) == {}


# -- the per-skill floors [PD-2026-09-22] -------------------------------------


def test_three_distinct_reading_topics_measure_the_reading_band() -> None:
    """The reading floor is 3: a band is three questions on one passage."""
    rows = _rows(READING_B1, "B1", section="reading")
    assert placement_bands(rows, _program(), V2) == {"reading": "B1"}


def test_two_reading_topics_are_below_the_reading_floor() -> None:
    rows = _rows(READING_B1[:2], "B1", section="reading")
    assert placement_bands(rows, _program(), V2) == {}


def test_four_correct_c1_items_measure_the_vocabulary_band() -> None:
    """The C1 vocabulary band carries four items: the floor of 5 would have
    capped every learner's measurable vocabulary at B2."""
    rows = _rows(VOCABULARY_C1, "C1", section="vocabulary")
    assert placement_bands(rows, _program(), V2) == {"vocabulary": "C1"}


def test_three_correct_c1_items_are_below_the_vocabulary_floor() -> None:
    rows = _rows(VOCABULARY_C1[:3], "C1", section="vocabulary")
    assert placement_bands(rows, _program(), V2) == {}


def test_the_grammar_floor_is_still_five() -> None:
    assert placement_bands(_rows(GRAMMAR_A1[:4], "A1"), _program(), V2) == {}
    assert placement_bands(_rows(GRAMMAR_A1, "A1"), _program(), V2) == {"grammar": "A1"}


def test_a_skill_without_a_floor_is_never_measured_objectively() -> None:
    """Writing has no ``min_topics_by_skill`` entry: even five fully correct
    writing topics cannot produce a measured band (learning-model 6)."""
    program = {
        "topics": [
            {"id": f"written.level.{n}", "cefr": "A2", "track": "written-interaction"} for n in range(5)
        ],
        "lexicon": [],
    }
    rows = [
        {**row, "dimension": "spontaneous_production"}
        for row in _rows([f"written.level.{n}" for n in range(5)], "A2", section="writing")
    ]
    assert placement_bands(rows, program, V2) == {}


# -- the provisional writing rule [PD-2026-09-22] -----------------------------


def test_a_writing_fragment_at_the_threshold_gives_a_provisional_band() -> None:
    rows = [_writing_row("A2", 700000), _writing_row("B1", 700000)]
    assert placement_writing_band(rows, V2) == "B1"  # the highest qualifying band


def test_a_writing_fragment_below_the_threshold_says_nothing() -> None:
    rows = [_writing_row("B1", 699999)]
    assert placement_writing_band(rows, V2) is None


def test_only_the_qualifying_bands_count_never_a_consolation_band() -> None:
    rows = [_writing_row("A2", 900000), _writing_row("B1", 500000)]
    assert placement_writing_band(rows, V2) == "A2"


def test_an_unassessed_writing_fragment_is_not_a_level() -> None:
    rows = [_writing_row("B1", None, basis="writing_unassessed", contributing=False)]
    assert placement_writing_band(rows, V2) is None


def test_objective_rows_never_reach_the_writing_rule() -> None:
    assert placement_writing_band(_rows(GRAMMAR_A1, "A1"), V2) is None


def test_scoring_v1_has_no_provisional_writing_rule() -> None:
    assert placement_writing_band([_writing_row("B1", 900000)], V1) is None


def test_scoring_v1_derives_no_level_from_a_placement() -> None:
    rows = [*_rows(GRAMMAR_A1, "A1"), *_rows(GRAMMAR_A2, "A2")]
    assert placement_bands(rows, _program(), V1) == {}
    assert placement_skill_levels(rows, _program(), V1) == {}


def test_the_decorated_level_carries_the_policy_confidence_and_basis() -> None:
    rows = _rows(GRAMMAR_A1, "A1")
    assert placement_skill_levels(rows, _program(), V2) == {
        "grammar": {"level": "A1", "confidence": "low", "basis": "placement"}
    }


# -- the fold over the log ----------------------------------------------------


def _scored_event(store, clock, random_source, rows: list[dict[str, Any]]) -> None:
    from english_trainer.kernel.envelopes import make_event
    from english_trainer.kernel.ids import new_ulid
    from english_trainer.kernel.uow import UnitOfWork

    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=PLACEMENT_SCORED_EVENT,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=new_ulid(clock, random_source),
                    payload={"placement_id": "p", "scored_items": rows},
                    pinned_versions={"scoring": "scoring@2"},
                )
            ]
        )


def test_the_last_scored_placement_wins(store, clock, random_source) -> None:
    assert placement_levels(store, _program(), V2) == {}
    _scored_event(store, clock, random_source, [*_rows(GRAMMAR_A1, "A1"), *_rows(GRAMMAR_A2, "A2")])
    assert placement_levels(store, _program(), V2) == {"grammar": "A2"}
    # A later, weaker placement replaces it: one designated measurement, not a
    # running total.
    clock.advance(seconds=60)
    _scored_event(store, clock, random_source, _rows(GRAMMAR_A1, "A1"))
    assert placement_levels(store, _program(), V2) == {"grammar": "A1"}


# -- working_levels -----------------------------------------------------------


def _active(targets: list[str]) -> dict[str, TargetState]:
    return {target: TargetState(knowledge_state=ACTIVE) for target in targets}


def test_a_placement_band_fills_a_skill_without_evidence() -> None:
    levels = working_levels({}, _program(), V2, placement={"grammar": "A2"})
    assert levels["grammar"] == {
        "level": "A2",
        "confidence": "low",
        "basis": "placement",
        # An objective placement band is a measurement, not a provisional claim.
        "provisional": False,
        "active_topics": 0,
    }
    # Unmeasured skills stay unknown, so the overall level stays unknown.
    assert levels["reading"]["level"] is None
    assert levels["reading"]["basis"] is None
    assert measured_working_level(levels) is None


def test_session_evidence_replaces_the_placement_basis() -> None:
    levels = working_levels(_active(GRAMMAR_A1), _program(), V2, placement={"grammar": "A2"})
    # Five ACTIVE A1 topics reach the medium confidence floor: evidence wins,
    # even though it names a LOWER band than the placement did.
    assert levels["grammar"] == {
        "level": "A1",
        "confidence": "medium",
        "basis": "evidence",
        "provisional": False,
        "active_topics": 5,
    }


def test_without_a_placement_the_result_is_the_scoring_v1_shape() -> None:
    v1_levels = working_levels(_active(GRAMMAR_A1), _program(), V1)
    v2_levels = working_levels(_active(GRAMMAR_A1), _program(), V2)
    assert v1_levels == v2_levels
    assert v1_levels["grammar"]["basis"] == "evidence"


def test_a_placement_band_is_ignored_under_an_old_pin() -> None:
    levels = working_levels({}, _program(), V1, placement={"grammar": "A2"})
    assert levels["grammar"]["level"] is None
    assert levels["grammar"]["basis"] is None


def test_a_placement_writing_band_is_ignored_under_an_old_pin() -> None:
    levels = working_levels({}, _program(), V1, placement_writing="B1")
    assert levels["writing"]["level"] is None
    assert levels["writing"]["provisional"] is False


# -- the provisional writing level in the rows [PD-2026-09-22] ---------------


def _all_objective(placement_writing: str | None = "B1") -> dict[str, dict[str, Any]]:
    """Every objective skill measured by a placement, writing provisional."""
    return working_levels(
        {},
        _program(),
        V2,
        placement={"grammar": "B2", "vocabulary": "B1", "reading": "B1"},
        placement_writing=placement_writing,
    )


def test_the_writing_row_is_flagged_provisional_with_its_own_confidence() -> None:
    levels = _all_objective()
    assert levels["writing"] == {
        "level": "B1",
        # The placement's own writing confidence: weaker than an objective band.
        "confidence": "very_low",
        "basis": "placement",
        "provisional": True,
        "active_topics": 0,
    }


def test_a_provisional_writing_row_keeps_the_measured_level_unknown() -> None:
    """Every objective skill is measured, yet the overall MEASURED level stays
    unknown: a full writing band needs >= 2 independent non-placement items."""
    assert measured_working_level(_all_objective()) is None


def test_the_provisional_estimate_consumes_the_placement_writing_level() -> None:
    estimate = provisional_working_estimate(_all_objective())
    assert estimate["level"] == "B1"  # not higher than the weakest skill
    assert estimate["provisional"] is True
    assert estimate["skills"]["writing"] == {
        "level": "B1",
        "confidence": "very_low",
        "basis": "placement",
        "provisional": True,
    }
    assert estimate["skills"]["grammar"] == {
        "level": "B2",
        "confidence": "low",  # an objective placement band, not a fragment
        "basis": "placement",
        "provisional": False,
    }


def test_without_a_writing_claim_the_estimate_stays_unknown() -> None:
    estimate = provisional_working_estimate(_all_objective(placement_writing=None))
    assert estimate["level"] is None
    assert estimate["skills"]["writing"]["level"] is None


def test_the_estimate_falls_back_to_the_self_report_per_skill() -> None:
    estimate = provisional_working_estimate(
        _all_objective(placement_writing=None), self_reported={"writing": "A2", "grammar": "C1"}
    )
    assert estimate["skills"]["writing"] == {
        "level": "A2",
        "confidence": "very_low",
        "basis": "self_report",
        "provisional": True,
    }
    # A measured skill is never overwritten by what the learner claims.
    assert estimate["skills"]["grammar"]["level"] == "B2"
    assert estimate["level"] == "A2"


def test_the_placement_writing_level_outranks_the_self_report() -> None:
    """Measured where present, else provisional -- and the placement's own
    fragment is a stronger claim than an unverified self-report."""
    estimate = provisional_working_estimate(_all_objective(), self_reported={"writing": "C1"})
    assert estimate["skills"]["writing"]["basis"] == "placement"
    assert estimate["level"] == "B1"


def test_the_measured_estimate_carries_no_provisional_flag() -> None:
    levels = working_levels(_active(GRAMMAR_A1), _program(), V2)
    estimate = provisional_working_estimate(levels)
    assert estimate["provisional"] is False
    assert estimate["skills"]["grammar"] == {
        "level": "A1",
        "confidence": "medium",
        "basis": "evidence",
        "provisional": False,
    }


# -- the folds over the log ---------------------------------------------------


def test_the_provisional_writing_level_is_read_off_the_last_placement(store, clock, random_source) -> None:
    assert placement_writing_level(store, V2) is None
    _scored_event(store, clock, random_source, [_writing_row("B1", 800000)])
    assert placement_writing_level(store, V2) == "B1"
    # A later placement replaces it -- including with "no claim at all".
    clock.advance(seconds=60)
    _scored_event(store, clock, random_source, [_writing_row("B1", 100000)])
    assert placement_writing_level(store, V2) is None


def _declined_event(store, clock, random_source, reported: dict[str, str]) -> None:
    from english_trainer.kernel.envelopes import make_event
    from english_trainer.kernel.ids import new_ulid
    from english_trainer.kernel.uow import UnitOfWork

    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="placement.declined",
                    occurred_at=clock.now(),
                    actor="agent",
                    correlation_id=new_ulid(clock, random_source),
                    payload={"placement_id": "p", "self_reported_levels": reported},
                    pinned_versions={"assessments": "assessments@1"},
                )
            ]
        )


def test_the_self_report_is_read_off_the_last_declined_placement(store, clock, random_source) -> None:
    assert self_reported_levels(store) == {}
    _declined_event(store, clock, random_source, {"grammar": "A2", "reading": "B1"})
    assert self_reported_levels(store) == {"grammar": "A2", "reading": "B1"}
    # A later decline replaces the earlier claim outright.
    clock.advance(seconds=60)
    _declined_event(store, clock, random_source, {"grammar": "B1"})
    assert self_reported_levels(store) == {"grammar": "B1"}
