"""Deterministic placement end-to-end integration scenario (roadmap 2.6).

The test follows the same public assessment functions used by the placement
CLI. It activates a real curriculum snapshot and executable policies, then
proves lifecycle, scoring ceiling, exposure, expiry and self-assessment in one
replayable flow.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.assessments import (
    EVENT_CHECKPOINT,
    EVENT_DECLINED,
    EVENT_EXPIRED,
    EVENT_RESUMED,
    EVENT_SCORED,
    EVENT_STARTED,
    EVENT_SUBMITTED,
    PlacementPrecondition,
    SelfAssessmentInvalid,
    abandon_placement,
    active_placement_id,
    answer_placement,
    decline_placement,
    get_placement,
    resume_placement,
    start_placement,
    submit_placement,
    sweep_expired_placements,
)
from english_trainer.curriculum.service import activate_version, register_version
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.scoring.engine import ACTIVE, fold_scores, snapshot

REPO = Path(__file__).resolve().parents[2]
EPOCH = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
SEED = 20260722
RESUME_WINDOW = timedelta(hours=48)
GRAMMAR_TARGET = "grammar.be.identity"
FORM_TARGETS = {
    GRAMMAR_TARGET,
    "vocabulary.core.greeting",
    "reading.gist.short",
    "writing.sentence.simple",
}
GRAMMAR_ANSWERS = {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "levels": [],
    "tracks": [],
    "modules": [],
    "topics": [
        {
            "id": GRAMMAR_TARGET,
            "cefr": "A1",
            "track": "grammar-engine",
            "dimensions": ["recognition"],
            "contexts": ["placement"],
            "lexicon": [],
        },
        {
            "id": "vocabulary.core.greeting",
            "cefr": "A1",
            "track": "vocabulary-chunks",
            "dimensions": ["recognition"],
            "contexts": ["placement"],
            "lexicon": [],
        },
        {
            "id": "reading.gist.short",
            "cefr": "A1",
            "track": "reading",
            "dimensions": ["recognition"],
            "contexts": ["placement"],
            "lexicon": [],
        },
        {
            "id": "writing.sentence.simple",
            "cefr": "A1",
            "track": "written-production-mediation",
            "dimensions": ["spontaneous_production"],
            "contexts": ["placement"],
            "lexicon": [],
        },
    ],
    "lexicon": [],
    "provenance": {},
}


def _policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _activate_test_program(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
) -> dict[str, Any]:
    """Use the public service path called by ``curriculum activate``."""
    version = "placement-demo@1"
    register_version(registry, PROGRAM, version)
    event = activate_version(store, registry, clock, random_source, version, expected_active=None)
    assert event is not None and event.payload["version"] == version

    registry.register("generation", "generation@1", {"policy_id": "generation@1"})
    registry.activate("generation", "generation@1")
    for filename, kind, policy_version in (
        ("control-v1.yaml", "control", "control@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
    ):
        registry.register(kind, policy_version, _policy(filename))
        registry.activate(kind, policy_version)
    return _policy("scoring-v1.yaml")


def _refusal(exception: type[Exception], action: Callable[[], object]) -> dict[str, str]:
    with pytest.raises(exception) as raised:
        action()
    return {
        "code": str(getattr(raised.value, "code", type(raised.value).__name__)),
        "message": str(raised.value),
    }


def _events(
    store: EventStore,
    *,
    event_type: str | None = None,
    placement_id: str | None = None,
) -> list[Any]:
    return [
        event
        for event in store.read()
        if (event_type is None or event.type == event_type)
        and (placement_id is None or event.correlation_id == placement_id)
    ]


def _run_scenario(root: Path) -> dict[str, Any]:
    root.mkdir()
    connection = connect(root / "placement.db")
    migrate(connection)
    try:
        store = EventStore(connection)
        clock = FixedClock(EPOCH)
        random_source = SeededRandomSource(SEED)
        registry = PolicyRegistry(connection, clock)
        scoring_policy = _activate_test_program(store, registry, clock, random_source)

        # First take: legal lifecycle, stable illegal-transition refusals, a
        # fresh incorrect answer, idempotent submit, and the placement ceiling.
        first = start_placement(store, registry, clock, random_source, actor="agent")
        first_id = str(first["placement_id"])
        assert first["status"] == "STARTED"
        assert first["form_version"] == "placement-en-core@1"
        assert {str(item["target_ref"]) for item in first["items"]} == FORM_TARGETS
        assert {str(topic["id"]) for topic in PROGRAM["topics"]} >= FORM_TARGETS
        assert active_placement_id(store) == first_id

        second_active = _refusal(
            PlacementPrecondition,
            lambda: start_placement(store, registry, clock, random_source),
        )
        submit_started = _refusal(
            PlacementPrecondition,
            lambda: submit_placement(store, registry, clock, random_source, first_id),
        )
        assert second_active["code"] == "PLACEMENT_PRECONDITION"
        assert submit_started["code"] == "PLACEMENT_PRECONDITION"

        grammar_checkpoint = answer_placement(
            store,
            clock,
            random_source,
            first_id,
            section="grammar",
            answers=GRAMMAR_ANSWERS,
        )
        assert grammar_checkpoint["status"] == "IN_PROGRESS"
        assert grammar_checkpoint["next_section"] == "vocabulary"

        clock.advance(seconds=3600)
        resumed = resume_placement(store, registry, clock, random_source, first_id)
        assert resumed["status"] == "IN_PROGRESS"
        assert resumed["next_section"] == "vocabulary"
        assert resumed["boundary_at"] == (EPOCH + RESUME_WINDOW).isoformat()

        wrong_checkpoint = answer_placement(
            store,
            clock,
            random_source,
            first_id,
            section="vocabulary",
            answers={"v-greeting-1": "goodbye"},
        )
        assert wrong_checkpoint["next_section"] == "reading"

        first_submit = submit_placement(store, registry, clock, random_source, first_id)
        assert first_submit["status"] == "SCORED"
        assert first_submit["already"] is False
        assert first_submit["evidence_count"] == 3
        assert first_submit["outcome_count"] == 3
        vocabulary_row = next(row for row in first_submit["scored_items"] if row["item_id"] == "v-greeting-1")
        assert vocabulary_row == {
            "item_id": "v-greeting-1",
            "section": "vocabulary",
            "target_ref": "vocabulary.core.greeting",
            "dimension": "recognition",
            "item_exposure_id": "exposure:placement-en-core@1#v-greeting-1",
            "applied_exposure_weight": "1",
            "kind": "objective",
            "basis": "objective_check",
            "correct": False,
            "contributing": False,
        }

        event_count_after_submit = len(_events(store))
        repeated_submit = submit_placement(store, registry, clock, random_source, first_id)
        assert repeated_submit["already"] is True
        assert len(_events(store)) == event_count_after_submit
        assert repeated_submit["scored_items"] == first_submit["scored_items"]

        first_evidence = _events(store, event_type="evidence.added", placement_id=first_id)
        assert len(first_evidence) == 3
        assert all(event.payload["origin"] == "placement" for event in first_evidence)
        assert all(event.payload["applied_exposure_weight"] == "1" for event in first_evidence)
        first_lifecycle = [
            event.type
            for event in _events(store, placement_id=first_id)
            if event.type.startswith("placement.")
        ]
        assert first_lifecycle == [
            EVENT_STARTED,
            EVENT_CHECKPOINT,
            EVENT_RESUMED,
            EVENT_CHECKPOINT,
            EVENT_SUBMITTED,
            EVENT_SCORED,
        ]
        first_state = get_placement(store, first_id)
        assert first_state is not None and first_state[0]["status"] == "SCORED"

        answer_terminal = _refusal(
            PlacementPrecondition,
            lambda: answer_placement(
                store,
                clock,
                random_source,
                first_id,
                section="grammar",
                answers=GRAMMAR_ANSWERS,
            ),
        )
        abandon_terminal = _refusal(
            PlacementPrecondition,
            lambda: abandon_placement(store, clock, random_source, first_id),
        )
        assert answer_terminal["code"] == "PLACEMENT_PRECONDITION"
        assert abandon_terminal["code"] == "PLACEMENT_PRECONDITION"
        assert active_placement_id(store) is None

        score_after_first = snapshot(fold_scores(store, scoring_policy))
        grammar_score = score_after_first[GRAMMAR_TARGET]
        assert grammar_score["knowledge_state"] == ACTIVE
        assert grammar_score["knowledge_state"] != "MASTERED"
        assert grammar_score["evidence_count"] == 3
        assert any("placement-ceiling" in entry for entry in grammar_score["audit"])
        assert "vocabulary.core.greeting" not in score_after_first

        # Second take: the same exposed grammar items are checkpointed again,
        # but the scored event captures zero weight and contributes no evidence.
        clock.advance(seconds=60)
        second = start_placement(store, registry, clock, random_source, actor="agent")
        second_id = str(second["placement_id"])
        second_checkpoint = answer_placement(
            store,
            clock,
            random_source,
            second_id,
            section="grammar",
            answers=GRAMMAR_ANSWERS,
        )
        second_submit = submit_placement(store, registry, clock, random_source, second_id)
        assert second_submit["evidence_count"] == 0
        assert second_submit["outcome_count"] == 0
        assert all(row["applied_exposure_weight"] == "0" for row in second_submit["scored_items"])
        assert all(row["contributing"] is False for row in second_submit["scored_items"])
        assert snapshot(fold_scores(store, scoring_policy)) == score_after_first
        assert not _events(store, event_type="evidence.added", placement_id=second_id)

        checkpoint_event = _events(store, event_type=EVENT_CHECKPOINT, placement_id=second_id)[0]
        scored_event = _events(store, event_type=EVENT_SCORED, placement_id=second_id)[0]
        assert checkpoint_event.payload["item_exposure_ids"] == [
            "exposure:placement-en-core@1#g-be-1",
            "exposure:placement-en-core@1#g-be-2",
            "exposure:placement-en-core@1#g-be-3",
        ]
        assert all(row["applied_exposure_weight"] == "0" for row in scored_event.payload["scored_items"])

        # Expiry through resume: event time is the replayable boundary, not the
        # later clock at which recovery happens. Repeated recovery/sweep is inert.
        clock.advance(seconds=60)
        expiring = start_placement(store, registry, clock, random_source, actor="agent")
        expiring_id = str(expiring["placement_id"])
        answer_placement(
            store,
            clock,
            random_source,
            expiring_id,
            section="reading",
            answers={"r-gist-1": "false"},
        )
        expiring_state = get_placement(store, expiring_id)
        assert expiring_state is not None
        last_activity_at = datetime.fromisoformat(str(expiring_state[0]["last_activity_at"]))
        expected_boundary = last_activity_at + RESUME_WINDOW
        clock.advance(seconds=int(RESUME_WINDOW.total_seconds()) + 61)
        expired_resume = _refusal(
            PlacementPrecondition,
            lambda: resume_placement(store, registry, clock, random_source, expiring_id),
        )
        assert expired_resume["code"] == "PLACEMENT_PRECONDITION"
        expired_event = _events(store, event_type=EVENT_EXPIRED, placement_id=expiring_id)[0]
        assert expired_event.payload["boundary_at"] == expected_boundary.isoformat()
        assert expired_event.payload["last_activity_at"] == last_activity_at.isoformat()
        assert expired_event.occurred_at == expected_boundary
        expired_state = get_placement(store, expiring_id)
        assert expired_state is not None and expired_state[0]["status"] == "EXPIRED"
        expired_count = len(_events(store, event_type=EVENT_EXPIRED))
        _refusal(
            PlacementPrecondition,
            lambda: resume_placement(store, registry, clock, random_source, expiring_id),
        )
        assert sweep_expired_placements(store, registry, clock, random_source) == []
        assert len(_events(store, event_type=EVENT_EXPIRED)) == expired_count

        # Expiry through the sweeper is independently exercised and idempotent.
        swept = start_placement(store, registry, clock, random_source, actor="agent")
        swept_id = str(swept["placement_id"])
        answer_placement(
            store,
            clock,
            random_source,
            swept_id,
            section="writing",
            answers={"w-sentence-1": "I am an engineer on the platform team."},
        )
        swept_state = get_placement(store, swept_id)
        assert swept_state is not None
        swept_boundary = datetime.fromisoformat(str(swept_state[0]["last_activity_at"])) + RESUME_WINDOW
        clock.advance(seconds=int(RESUME_WINDOW.total_seconds()) + 300)
        assert sweep_expired_placements(store, registry, clock, random_source) == [swept_id]
        sweep_event_count = len(_events(store))
        assert sweep_expired_placements(store, registry, clock, random_source) == []
        assert len(_events(store)) == sweep_event_count
        swept_event = _events(store, event_type=EVENT_EXPIRED, placement_id=swept_id)[0]
        assert swept_event.payload["boundary_at"] == swept_boundary.isoformat()
        assert swept_event.occurred_at == swept_boundary

        # Decline admits a partial per-skill object, never a scalar or a silent
        # broadcast. Rejection is stable and produces no declined event.
        declined_before_scalar = len(_events(store, event_type=EVENT_DECLINED))
        scalar_refusal = _refusal(
            SelfAssessmentInvalid,
            lambda: decline_placement(
                store,
                registry,
                clock,
                random_source,
                self_assessment="A2",
            ),
        )
        assert scalar_refusal["code"] == "SELF_ASSESSMENT_INVALID"
        assert len(_events(store, event_type=EVENT_DECLINED)) == declined_before_scalar

        declined = decline_placement(
            store,
            registry,
            clock,
            random_source,
            self_assessment={"schema_version": 1, "levels": {"grammar": "A2", "reading": "B1"}},
        )
        assert declined["self_reported_levels"] == {"grammar": "A2", "reading": "B1"}
        assert "vocabulary" not in declined["self_reported_levels"]
        assert "writing" not in declined["self_reported_levels"]
        declined_state = get_placement(store, str(declined["placement_id"]))
        assert declined_state is not None
        assert declined_state[0]["self_reported_levels"] == {"grammar": "A2", "reading": "B1"}

        placement_event_types = {
            EVENT_STARTED,
            EVENT_CHECKPOINT,
            EVENT_RESUMED,
            EVENT_SUBMITTED,
            EVENT_SCORED,
            EVENT_EXPIRED,
            EVENT_DECLINED,
        }
        placement_events = [event for event in store.read() if event.type in placement_event_types]
        outboxed_ids = {event.id for event in store.read_outboxed_since(0)}
        assert {event.id for event in placement_events} <= outboxed_ids

        return {
            "fixed_clock_start": EPOCH.isoformat(),
            "fixed_clock_end": clock.now().isoformat(),
            "seed": SEED,
            "program_version": "placement-demo@1",
            "form_targets": sorted(FORM_TARGETS),
            "first": {
                "placement_id": first_id,
                "form_version": first["form_version"],
                "pinned_versions": first["pinned_versions"],
                "grammar_checkpoint": grammar_checkpoint,
                "resume": resumed,
                "wrong_checkpoint": wrong_checkpoint,
                "submit": first_submit,
                "repeat_already": repeated_submit["already"],
                "score": score_after_first,
            },
            "illegal_transitions": {
                "second_active_start": second_active,
                "submit_started": submit_started,
                "answer_terminal": answer_terminal,
                "abandon_terminal": abandon_terminal,
            },
            "second": {
                "placement_id": second_id,
                "checkpoint": second_checkpoint,
                "submit": second_submit,
                "checkpoint_event_id": checkpoint_event.id,
                "scored_event_id": scored_event.id,
            },
            "resume_expiry": {
                "placement_id": expiring_id,
                "refusal": expired_resume,
                "event_id": expired_event.id,
                "boundary_at": expired_event.payload["boundary_at"],
                "sweep_after_resume": [],
            },
            "sweep_expiry": {
                "placement_id": swept_id,
                "event_id": swept_event.id,
                "boundary_at": swept_event.payload["boundary_at"],
                "second_sweep": [],
            },
            "self_assessment": {
                "scalar_refusal": scalar_refusal,
                "declined": declined,
            },
            "placement_events": [
                {
                    "id": event.id,
                    "sequence": event.sequence,
                    "type": event.type,
                    "correlation_id": event.correlation_id,
                }
                for event in placement_events
            ],
        }
    finally:
        connection.close()


def test_placement_end_to_end_is_replayable_and_deterministic(tmp_path: Path) -> None:
    first = _run_scenario(tmp_path / "first")
    second = _run_scenario(tmp_path / "second")

    assert canonical_json(first) == canonical_json(second)
