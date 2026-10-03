"""The rubric assessment pipeline (P.5): observation validation, machine
opcodes, the severity-ceiling reducer and PD-7 completeness.

``compute_rubric_assessment`` is a pure read; its live caller is placement
(writing items). The per-step settlement path (``attempt record`` with
observations, ``attempt finalize``) was removed with the step-delivery
protocol [PD-2026-09-23], so the pipeline is exercised here directly over an
attempt document -- the same inputs the placement hands it."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from english_trainer.evidence.assessment import (
    compute_rubric_assessment,
    criterion_level,
    run_machine_operation,
    span_hash,
)
from english_trainer.evidence.attempts import EvidencePrecondition
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from tests.evidence.conftest import REPO

PINNED = {"rubric": "rubric@1"}


@pytest.fixture
def rubric_registry(store: EventStore, clock) -> PolicyRegistry:
    reg = PolicyRegistry(store._conn, clock)
    payload = yaml.safe_load((REPO / "curriculum" / "policies" / "rubric-v1.yaml").read_text("utf-8"))
    reg.register("rubric", "rubric@1", payload)
    reg.activate("rubric", "rubric@1")
    return reg


ANSWER = "Well, I usually review deployment checklists before the release, so nothing breaks."


def _observation(criterion: str, finding: str, *, start: int = 0, end: int | None = None) -> dict[str, Any]:
    end = end if end is not None else len(ANSWER.encode("utf-8"))
    return {
        "rubric_criterion_ref": f"rubric:conversation.free#criterion:{criterion}",
        "finding_code": finding,
        "span_ref": {"start_utf8": start, "end_utf8": end, "span_hash": span_hash(ANSWER, start, end)},
    }


def _full_coverage() -> list[dict[str, Any]]:
    """One positive finding per required criterion of conversation.free
    (finding codes exactly as the catalog declares them)."""
    return [
        _observation("meaning-clarity", "main_message_is_recoverable"),
        _observation("target-control", "target_used_in_required_function"),
        _observation("register-fit", "register_matches_context"),
        _observation("language-control", "well_formed_clause"),
        _observation("independent-expression", "learner_adds_independent_clause"),
    ]


def _attempt(
    observations: list[dict[str, Any]],
    *,
    step_type: str = "free_conversation",
    primary_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": "attempt-1",
        "raw_answer": ANSWER,
        "step_type": step_type,
        "primary_target": primary_target,
        "observations": observations,
    }


def test_machine_opcodes_are_deterministic() -> None:
    assert run_machine_operation("nonempty_after_trim", {}, "  hi ")
    assert not run_machine_operation("nonempty_after_trim", {}, "   ")
    assert run_machine_operation(
        "token_count_between", {"minimum_inclusive": 3, "maximum_inclusive": 20}, ANSWER
    )
    assert run_machine_operation(
        "required_literal_sequence_any", {"literals": ["Deployment CHECKLISTS"]}, ANSWER
    )  # folded comparison by default
    assert not run_machine_operation(
        "required_literal_sequence_any",
        {"literals": ["Deployment CHECKLISTS"], "comparison": "exact_nfc_v1"},
        ANSWER,
    )
    assert run_machine_operation(
        "required_section_label_sequence", {"labels": ["usually", "release"]}, ANSWER
    )
    assert not run_machine_operation(
        "required_section_label_sequence", {"labels": ["release", "usually"]}, ANSWER
    )
    with pytest.raises(EvidencePrecondition, match="closed"):
        run_machine_operation("regex_match", {"pattern": ".*"}, ANSWER)


def test_severity_ceiling_caps_the_level() -> None:
    definition = {
        "positive_findings": {"good": {"units": 3, "max_occurrences": 1}},
        "negative_findings": {"bad": {"error_family": "fam"}},
    }
    families = {"fam": {"severity": "major"}}
    severities = {"major": {"level_ceiling": 1}}
    strong = criterion_level(definition, [{"finding_code": "good"}], families, severities)
    assert strong == 3
    capped = criterion_level(
        definition, [{"finding_code": "good"}, {"finding_code": "bad"}], families, severities
    )
    assert capped == 1  # policy-owned ceiling, no global double subtraction


def test_a_fully_covered_answer_scores_and_is_deterministic(store, rubric_registry) -> None:
    attempt = _attempt(_full_coverage())
    result = compute_rubric_assessment(store, rubric_registry, pinned=PINNED, attempt=attempt)
    assert result["basis"] == "rubric" and result["pinned_rubric_version"] == "rubric@1"
    assert result["disposition"] == "scored" and result["rejected_observations"] == []
    # Every required criterion got one finding; levels come from finding units
    # (2 or 3 per the catalog), so the score lands strictly inside the scale.
    assert 0 < result["score_ppm"] <= 1_000_000
    assert len(result["criteria"]) == 5  # the full per-criterion trace
    assert result["uncovered_required"] == []
    again = compute_rubric_assessment(store, rubric_registry, pinned=PINNED, attempt=attempt)
    assert again == result  # a pure read: same inputs, same assessment


def test_rejected_observations_do_not_count(store, rubric_registry) -> None:
    bad_span = _observation("meaning-clarity", "message_recoverable_first_reading")
    bad_span["span_ref"]["span_hash"] = "sha256:" + "0" * 64
    wrong_criterion = {
        "rubric_criterion_ref": "rubric:writing.academic-argument#criterion:claim-development",
        "finding_code": "claim_present",
        "span_ref": bad_span["span_ref"],
    }
    result = compute_rubric_assessment(
        store, rubric_registry, pinned=PINNED, attempt=_attempt([bad_span, wrong_criterion])
    )
    # Both rejected -> zero required coverage -> non-contributing
    # insufficient_evidence: assessor failure is never a learner zero (PD-7 C).
    assert len(result["rejected_observations"]) == 2
    assert result["disposition"] == "insufficient_evidence"
    assert result["score_ppm"] is None and result["contributing"] is False


def test_a_step_type_without_an_exact_default_is_refused(store, rubric_registry) -> None:
    # new_material_intro deliberately has no default rubric (PD-6 B): generic
    # prose scoring of an intro step would be hidden best-match.
    attempt = _attempt(
        [], step_type="new_material_intro", primary_target={"target_ref": "grammar.be.identity"}
    )
    with pytest.raises(EvidencePrecondition, match="no exact default"):
        compute_rubric_assessment(store, rubric_registry, pinned=PINNED, attempt=attempt)


def test_an_unpinned_rubric_is_refused(store, rubric_registry) -> None:
    with pytest.raises(EvidencePrecondition, match="pins no rubric"):
        compute_rubric_assessment(store, rubric_registry, pinned={}, attempt=_attempt(_full_coverage()))


def test_targetless_assessment_is_audit_only(store, rubric_registry) -> None:
    # A free-conversation answer with no target scores for audit, but it can
    # never contribute mastery evidence (invariant 14: no target, no evidence).
    result = compute_rubric_assessment(
        store, rubric_registry, pinned=PINNED, attempt=_attempt(_full_coverage())
    )
    assert result["disposition"] == "scored" and result["contributing"] is False
