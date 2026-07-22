"""Trusted reporting of concrete learner errors as append-only facts.

``record_observed`` does not accept a score, severity or mastery verdict. It
anchors an agent-reported negative rubric finding to an assessed attempt and
an exact UTF-8 span, derives target/dimension and policy-owned severity, and
refuses a claim that contradicts an authoritative machine result. The emitted
``evidence.error_observed`` fact feeds control's recurring-error fold; it is
not itself mastery evidence.
"""

from __future__ import annotations

from typing import Any

from english_trainer.evidence.assessment import span_hash
from english_trainer.evidence.attempts import (
    ASSESSED,
    ATTEMPT_AGGREGATE,
    NOTES_AGGREGATE,
    EvidencePrecondition,
)
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

EVENT_ERROR_OBSERVED = "evidence.error_observed"


def _pinned_versions(store: EventStore, session_id: str) -> tuple[dict[str, str], str | None]:
    for event in store.read():
        if event.type == "session.started" and event.correlation_id == session_id:
            manifest = dict(event.payload.get("manifest") or {})
            return (
                {str(k): str(v) for k, v in (manifest.get("pinned_versions") or {}).items()},
                manifest.get("provider"),
            )
    raise EvidencePrecondition(f"session {session_id} does not exist")


def _validated_span(raw_answer: str, span: Any) -> dict[str, Any]:
    if not isinstance(span, dict):
        raise EvidencePrecondition("observed error requires span_ref")
    try:
        start = int(span["start_utf8"])
        end = int(span["end_utf8"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidencePrecondition("span_out_of_bounds") from exc
    data = raw_answer.encode("utf-8")
    if not (0 <= start < end <= len(data)):
        raise EvidencePrecondition("span_out_of_bounds")
    try:
        data[:start].decode("utf-8")
        data[:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidencePrecondition("span_not_utf8_boundary") from exc
    expected = span_hash(raw_answer, start, end)
    if str(span.get("span_hash") or "") != expected:
        raise EvidencePrecondition("span_hash_mismatch")
    return {"start_utf8": start, "end_utf8": end, "span_hash": expected}


def _criterion(ref: str, rubric: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    marker = "#criterion:"
    if not ref.startswith("rubric:") or marker not in ref:
        raise EvidencePrecondition("criterion_ref_unavailable")
    criterion_id = ref.split(marker, 1)[1]
    definition = (rubric.get("criterion_catalog") or {}).get(criterion_id)
    if not isinstance(definition, dict):
        raise EvidencePrecondition("criterion_ref_unavailable")
    return criterion_id, definition


def _contradicts_machine_result(
    store: EventStore,
    attempt: dict[str, Any],
    criterion_ref: str,
    finding_code: str,
) -> bool:
    assessment = dict(attempt.get("assessment") or {})
    if assessment.get("basis") == "objective_check":
        return bool(assessment.get("correct"))
    instance_id = attempt.get("exercise_instance_id")
    machine_checks: dict[str, dict[str, Any]] = {}
    if instance_id is not None:
        for event in store.read():
            if event.type == "exercise.rendered" and str(event.payload.get("exercise_instance_id")) == str(
                instance_id
            ):
                machine_checks = {
                    str(check.get("check_id") or ""): dict(check)
                    for check in event.payload.get("machine_checks") or []
                }
                break
    criterion_id = criterion_ref.split("#criterion:", 1)[1]
    for result in assessment.get("machine_results") or []:
        if str(result.get("criterion_id") or "") != criterion_id:
            continue
        check = machine_checks.get(str(result.get("check_id") or ""))
        if check is not None and check.get("on_fail") == finding_code and result.get("result") == "passed":
            return True
    return False


def record_observed(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    expected_session_revision: int,
    kind: str,
    attempt_id: str,
    observation: dict[str, Any],
    note: str | None = None,
    provider: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Record one concrete error observation against an assessed attempt."""
    session_state, session_revision = load_session_for_update(store, session_id, expected_session_revision)
    if kind != "error":
        raise EvidencePrecondition(
            "observed kind must be 'error' in this policy slice; vocabulary/chunk capture "
            "belongs to the living-layer workflow"
        )
    found = read_aggregate(store._conn, ATTEMPT_AGGREGATE, attempt_id)
    if found is None:
        raise EvidencePrecondition(f"attempt {attempt_id} does not exist")
    attempt = dict(found[0])
    if str(attempt.get("session_id")) != session_id:
        raise EvidencePrecondition(f"attempt {attempt_id} belongs to another session")
    if attempt.get("status") != ASSESSED:
        raise EvidencePrecondition(
            f"attempt {attempt_id} is {attempt.get('status')}; settle it before recording errors"
        )
    target = attempt.get("primary_target")
    if not isinstance(target, dict) or not target.get("target_ref") or not target.get("dimension"):
        raise EvidencePrecondition("an observed error requires a targeted attempt")
    for forbidden in (
        "severity",
        "score_ppm",
        "correct",
        "criterion_satisfied",
        "criterion_level",
        "mastery_delta",
    ):
        if forbidden in observation:
            raise EvidencePrecondition("agent_supplied_classification")

    pinned, manifest_provider = _pinned_versions(store, session_id)
    if "rubric" not in pinned:
        raise EvidencePrecondition("rubric_ref_unavailable")
    rubric = registry.resolve_pinned("rubric", pinned["rubric"])
    criterion_ref = str(observation.get("rubric_criterion_ref") or "")
    criterion_id, definition = _criterion(criterion_ref, rubric)
    assessment_ref = str((attempt.get("assessment") or {}).get("rubric_ref") or "")
    if assessment_ref and not criterion_ref.startswith(assessment_ref + "#criterion:"):
        raise EvidencePrecondition("criterion_not_in_profile")
    finding_code = str(observation.get("finding_code") or "")
    negative = (definition.get("negative_findings") or {}).get(finding_code)
    if not isinstance(negative, dict):
        raise EvidencePrecondition("finding_code_not_allowed: observed errors require a negative finding")
    span = _validated_span(str(attempt.get("raw_answer") or ""), observation.get("span_ref"))
    if _contradicts_machine_result(store, attempt, criterion_ref, finding_code):
        raise EvidencePrecondition("contradicts_machine_result")

    family_id = str(negative.get("error_family") or "")
    family = (rubric.get("error_families") or {}).get(family_id) or {}
    severity = str(family.get("severity") or "")
    if not family_id or not severity:
        raise EvidencePrecondition("error_ref_unavailable")
    identity = payload_hash(
        {
            "attempt_id": attempt_id,
            "criterion_ref": criterion_ref,
            "finding_code": finding_code,
            "span_ref": span,
        }
    )
    for event in store.read():
        if event.type == EVENT_ERROR_OBSERVED and event.payload.get("observation_identity") == identity:
            return {
                "observed_error_id": event.payload["observed_error_id"],
                "event_id": event.id,
                "already": True,
            }

    observed_error_id = new_ulid(clock, random_source)
    observed_at = clock.now().isoformat()
    event = make_event(
        id=new_ulid(clock, random_source),
        type=EVENT_ERROR_OBSERVED,
        occurred_at=clock.now(),
        actor=actor,
        provider=provider or manifest_provider,
        correlation_id=session_id,
        payload={
            "observed_error_id": observed_error_id,
            "observation_identity": identity,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "target_ref": str(target["target_ref"]),
            "dimension": str(target["dimension"]),
            "rubric_criterion_ref": criterion_ref,
            "criterion_id": criterion_id,
            "finding_code": finding_code,
            "error_family": family_id,
            "severity": severity,
            "span_ref": span,
            "topic_error_ref": observation.get("topic_error_ref"),
            "distractor_error_ref": observation.get("distractor_error_ref"),
            "reported_by": "agent",
            "contradicts_machine_result": False,
            "observed_at": observed_at,
        },
        pinned_versions=pinned,
    )
    with UnitOfWork(store, clock) as uow:
        new_session_revision = bump_session(uow, session_id, session_state, session_revision, clock.now())
        if note is not None and note.strip():
            entry = {
                "author_provider": provider or manifest_provider,
                "created_at": observed_at,
                "text": note.strip(),
                "observed_error_id": observed_error_id,
            }
            existing = uow.get_aggregate(NOTES_AGGREGATE, session_id)
            if existing is None:
                uow.save_aggregate(NOTES_AGGREGATE, session_id, {"notes": [entry]}, expected_revision=0)
            else:
                state, revision = existing
                uow.save_aggregate(
                    NOTES_AGGREGATE,
                    session_id,
                    {"notes": [*state.get("notes", []), entry]},
                    expected_revision=revision,
                )
        uow.append([event])
    return {
        "observed_error_id": observed_error_id,
        "event_id": event.id,
        "already": False,
        "session_revision": new_session_revision,
    }
