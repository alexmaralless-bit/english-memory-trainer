"""Pedagogy v2 composition (control@2/generation@2): one central topic per
program lesson, explicit arguments as consent [PD-2026-09-23], and teaching
recorded as report provenance -- never as evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.lessons.brief import EVENT_LESSON_REPORTED
from english_trainer.lessons.report import check_report, commit_report
from english_trainer.lessons.sessions import (
    get_plan,
    propose_session,
    start_session,
)
from tests.lessons.report_support import enable_reports, report

REPO = Path(__file__).resolve().parents[2]


def _activate_v2(registry: PolicyRegistry) -> None:
    for kind, filename, version in (
        ("control", "control-v2.yaml", "control@2"),
        ("generation", "generation-v2.yaml", "generation@2"),
    ):
        payload = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
        registry.register(kind, version, payload)
        registry.activate(kind, version)


def test_v2_program_lesson_has_one_central_topic_and_arc(
    store, registry: PolicyRegistry, clock, random_source
) -> None:
    _activate_v2(registry)
    manifest = start_session(
        store,
        registry,
        clock,
        random_source,
        provider="codex",
        lesson_profile="program_lesson",
        target_ref="grammar.be.identity",
    )
    arc = manifest["lesson_arc"]
    assert arc["profile"] == "program_lesson"
    assert arc["central_topic"]["target_ref"] == "grammar.be.identity"
    _, plan, _ = get_plan(store, manifest["session_id"])
    pending = [step for step in plan["steps"] if step["presented_at"] is None]
    assert pending
    assert {step.get("target_ref") for step in pending} == {"grammar.be.identity"}
    assert {step["lesson_arc_id"] for step in pending} == {arc["arc_id"]}
    assert {"new_material_intro", "recognition_check", "controlled_production"} <= {
        step["step_type"] for step in pending
    }


def test_explicit_arguments_are_consent_and_a_proposal_hash_is_ignored(
    store, registry: PolicyRegistry, clock, random_source
) -> None:
    """[PD-2026-09-23]: explicit profile/topic are the learner's consent; no
    proposal hash gates `start` (it went stale on unrelated facts)."""
    _activate_v2(registry)
    proposal = propose_session(
        store,
        registry,
        clock,
        lesson_profile="program_lesson",
        target_ref="grammar.be.identity",
    )
    assert proposal["requires_confirmation"] is False
    manifest = start_session(
        store,
        registry,
        clock,
        random_source,
        provider="codex",
        lesson_profile="program_lesson",
        target_ref="grammar.be.identity",
    )
    assert manifest["lesson_arc"]["central_topic"]["target_ref"] == "grammar.be.identity"
    assert manifest["brief"]["schema"] == "lesson_brief@1"
    # The proposal-hash argument is gone from `start` altogether.
    with pytest.raises(TypeError):
        start_session(  # type: ignore[call-arg]
            store,
            registry,
            clock,
            random_source,
            provider="codex",
            expected_proposal_hash=proposal["proposal_hash"],
        )


def test_teaching_rides_the_report_as_provenance_and_is_not_evidence(
    store, registry: PolicyRegistry, clock, random_source
) -> None:
    _activate_v2(registry)
    enable_reports(registry)
    manifest = start_session(
        store,
        registry,
        clock,
        random_source,
        provider="codex",
        lesson_profile="program_lesson",
        target_ref="grammar.be.identity",
    )
    session_id = str(manifest["session_id"])
    teaching = [{"target_ref": "grammar.be.identity", "summary": "be: am/is/are по лицам"}]
    body = report(session_id, manifest["brief"], [], teaching=teaching)
    unknown = report(
        session_id, manifest["brief"], [], teaching=[{"target_ref": "grammar.nope", "summary": "x"}]
    )
    codes = [warning["code"] for warning in check_report(store, registry, session_id, unknown)["warnings"]]
    assert "teaching_unknown_target" in codes
    commit_report(
        store, registry, clock, random_source, session_id, body, provider="codex", idempotency_key="k"
    )
    (reported,) = [event for event in store.read() if event.type == EVENT_LESSON_REPORTED]
    assert reported.payload["teaching"] == teaching
    assert not any(event.type in ("evidence.added", "attempt.recorded") for event in store.read())
