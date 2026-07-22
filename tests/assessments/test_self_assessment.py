"""Self-assessment on decline: a per-core-skill object is admitted, a scalar is
rejected, a partial object leaves missing skills unknown (assessments 5 [R-5])."""

from __future__ import annotations

import pytest

from english_trainer.assessments.placement import decline_placement
from english_trainer.assessments.self_assessment import SelfAssessmentInvalid


def _declined_events(store) -> list:
    return [event for event in store.read() if event.type == "placement.declined"]


def test_object_self_assessment_is_written_per_skill(store, registry, clock, random_source) -> None:
    result = decline_placement(
        store,
        registry,
        clock,
        random_source,
        self_assessment={"schema_version": 1, "levels": {"grammar": "A2", "reading": "B1"}},
    )
    assert result["status"] == "DECLINED"
    assert result["self_reported_levels"] == {"grammar": "A2", "reading": "B1"}
    event = _declined_events(store)[-1]
    assert event.payload["self_reported_levels"] == {"grammar": "A2", "reading": "B1"}
    assert event.payload["schema_version"] == 1


def test_scalar_self_assessment_is_rejected(store, registry, clock, random_source) -> None:
    with pytest.raises(SelfAssessmentInvalid):
        decline_placement(store, registry, clock, random_source, self_assessment="A2")


def test_partial_object_leaves_missing_skills_unknown(store, registry, clock, random_source) -> None:
    result = decline_placement(
        store,
        registry,
        clock,
        random_source,
        self_assessment={"schema_version": 1, "levels": {"grammar": "A2"}},
    )
    reported = result["self_reported_levels"]
    assert reported == {"grammar": "A2"}
    # Missing skills get no default and no broadcast of another skill's value.
    for skill in ("vocabulary", "reading", "writing"):
        assert skill not in reported


def test_decline_without_self_assessment_reports_nothing(store, registry, clock, random_source) -> None:
    result = decline_placement(store, registry, clock, random_source, self_assessment=None)
    assert result["status"] == "DECLINED"
    assert result["self_reported_levels"] == {}


def test_unknown_skill_out_of_range_level_and_bad_schema_are_rejected(
    store, registry, clock, random_source
) -> None:
    with pytest.raises(SelfAssessmentInvalid):
        decline_placement(
            store,
            registry,
            clock,
            random_source,
            self_assessment={"schema_version": 1, "levels": {"speaking": "A2"}},
        )
    with pytest.raises(SelfAssessmentInvalid):
        decline_placement(
            store,
            registry,
            clock,
            random_source,
            self_assessment={"schema_version": 1, "levels": {"grammar": "Z9"}},
        )
    with pytest.raises(SelfAssessmentInvalid):
        decline_placement(
            store,
            registry,
            clock,
            random_source,
            self_assessment={"levels": {"grammar": "A2"}},
        )
