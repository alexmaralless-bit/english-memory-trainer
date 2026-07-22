"""The rubric assessment pipeline for open attempts (P.5 [PD-2026-07-22];
evidence 4.1/4.5; rubric@1 ``criterion_reducer``).

``finalize_attempt`` settles a recorded open attempt: resolve the pinned
rubric profile (explicit ``rubric_ref`` from the rendered exercise, or the
EXACT (step_type, dimension) default -- never a broad fallback), execute the
closed machine-check opcodes over the exact saved inputs, validate every
subjective observation (criterion in profile, finding allowed, UTF-8 span
inside the saved answer with a matching hash -- one ``rejected`` branch with
stable reasons, nothing "flagged but counted"), reduce findings to four-level
criteria under policy-owned severity ceilings, and aggregate the integer
``score_ppm`` with ROUND_HALF_EVEN.

Completeness is PD-7 C: every required criterion needs at least one accepted
finding or machine result. An explicitly finalized incomplete attempt settles
``assessed / insufficient_evidence``, non-contributing -- missing assessor
coverage is never a false learner zero, and it stops blocking finish. A
target-less turn (free conversation without a derived target) assesses for
audit but cannot mint contributing evidence.

Settlement is atomic: the attempt aggregate leaves ``recorded``, the
state-change event captures the full calculation (accepted and rejected
observations, machine results, per-criterion trace, ``score_ppm``, rubric ref
and pin), and ``EVIDENCE_ADDED`` rides the same UnitOfWork when contributing.
Re-finalizing an assessed attempt is idempotent and returns the stored
result. The agent reports facts; every level and score here is engine-made.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from english_trainer.evidence.attempts import (
    ASSESSED,
    ATTEMPT_AGGREGATE,
    EVENT_ATTEMPT_STATE_CHANGED,
    EVENT_EVIDENCE_ADDED,
    RECORDED,
    EvidencePrecondition,
    _session_manifest,
)
from english_trainer.evidence.rubric import RUBRIC_KIND, require_valid
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

EXERCISE_RENDERED_EVENT = "exercise.rendered"

_WORD_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)


# -- deterministic text algorithms (rubric@1 normalization_algorithms) -------


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _folded(text: str) -> str:
    return " ".join(_nfc(text).casefold().split())


def _lines_normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _tokens(text: str) -> list[str]:
    return _WORD_TOKEN.findall(_nfc(text))


def span_hash(raw_answer: str, start: int, end: int) -> str:
    return "sha256:" + hashlib.sha256(raw_answer.encode("utf-8")[start:end]).hexdigest()


def _is_utf8_boundary(data: bytes, offset: int) -> bool:
    if offset in (0, len(data)):
        return True
    return (data[offset] & 0xC0) != 0x80


# -- machine opcodes (closed set, PD-3 A) ------------------------------------


def run_machine_operation(operation: str, params: dict[str, Any], raw_answer: str) -> bool:
    """Execute one closed opcode; True = passed. Anything else is not a
    machine check and never enters here (PD-3 A)."""
    if operation == "nonempty_after_trim":
        return bool(raw_answer.strip())
    if operation == "unicode_scalar_count_between":
        count = len(_nfc(raw_answer))
        return int(params["minimum_inclusive"]) <= count <= int(params["maximum_inclusive"])
    if operation == "token_count_between":
        count = len(_tokens(raw_answer))
        return int(params["minimum_inclusive"]) <= count <= int(params["maximum_inclusive"])
    if operation == "paragraph_count_between":
        paragraphs = [p for p in _lines_normalized(raw_answer).split("\n\n") if p.strip()]
        return int(params["minimum_inclusive"]) <= len(paragraphs) <= int(params["maximum_inclusive"])
    if operation in (
        "required_literal_sequence_any",
        "required_literal_sequence_all",
        "forbidden_literal_sequence_none",
        "required_target_surface_any",
    ):
        literals = [str(x) for x in (params.get("literals") or params.get("surfaces") or [])]
        exact = str(params.get("comparison", "folded_text_v1")) == "exact_nfc_v1"
        haystack = _nfc(raw_answer) if exact else _folded(raw_answer)
        found = [(lit if exact else _folded(lit)) in haystack for lit in literals]
        if operation == "required_literal_sequence_all":
            return all(found) and bool(found)
        if operation == "forbidden_literal_sequence_none":
            return not any(found)
        return any(found)  # ..._any / target_surface_any
    if operation == "required_section_label_sequence":
        labels = [str(x) for x in params.get("labels", [])]
        haystack = _folded(raw_answer)
        position = 0
        for label in labels:
            index = haystack.find(_folded(label), position)
            if index < 0:
                return False
            position = index + len(_folded(label))
        return True
    raise EvidencePrecondition(f"unknown machine operation {operation!r} (the opcode set is closed)")


# -- observation validation ---------------------------------------------------


def _criterion_id_of(ref: str, profile_id: str) -> str | None:
    prefix = f"rubric:{profile_id}#criterion:"
    return ref[len(prefix) :] if ref.startswith(prefix) else None


def validate_observation(
    obs: dict[str, Any],
    *,
    profile_id: str,
    profile_criteria: dict[str, dict[str, Any]],
    catalog: dict[str, Any],
    raw_answer: str,
    seen: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(accepted, None)`` or ``(None, stable_rejection_reason)``."""
    ref = str(obs.get("rubric_criterion_ref") or "")
    criterion_id = _criterion_id_of(ref, profile_id)
    if criterion_id is None:
        return None, "criterion_ref_unavailable"
    if criterion_id not in profile_criteria:
        return None, "criterion_not_in_profile"
    definition = catalog.get(criterion_id) or {}
    code = str(obs.get("finding_code") or "")
    if code not in (definition.get("positive_findings") or {}) and code not in (
        definition.get("negative_findings") or {}
    ):
        return None, "finding_code_not_allowed"
    span = obs.get("span_ref") or {}
    try:
        start, end = int(span["start_utf8"]), int(span["end_utf8"])
    except (KeyError, TypeError, ValueError):
        return None, "span_out_of_bounds"
    data = raw_answer.encode("utf-8")
    if not (0 <= start < end <= len(data)):
        return None, "span_out_of_bounds"
    if not (_is_utf8_boundary(data, start) and _is_utf8_boundary(data, end)):
        return None, "span_not_utf8_boundary"
    if str(span.get("span_hash") or "") != span_hash(raw_answer, start, end):
        return None, "span_hash_mismatch"
    identity = payload_hash(
        {
            "criterion": ref,
            "finding": code,
            "span": [start, end],
            "error": obs.get("topic_error_ref") or obs.get("distractor_error_ref"),
            "requirement": obs.get("requirement_ref"),
            "source": obs.get("source_fact_ref"),
        }
    )
    if identity in seen:
        return None, "duplicate_observation"
    seen.add(identity)
    for forbidden in ("criterion_satisfied", "criterion_level", "criterion_score", "score_ppm", "correct"):
        if forbidden in obs:
            return None, "agent_supplied_classification"
    return {
        "rubric_criterion_ref": ref,
        "criterion_id": criterion_id,
        "finding_code": code,
        "span_ref": {"start_utf8": start, "end_utf8": end, "span_hash": span["span_hash"]},
        "topic_error_ref": obs.get("topic_error_ref"),
        "distractor_error_ref": obs.get("distractor_error_ref"),
        "requirement_ref": obs.get("requirement_ref"),
        "source_fact_ref": obs.get("source_fact_ref"),
        "reported_by": "agent",
    }, None


# -- the reducer (finding_units_with_severity_ceiling_v1) ---------------------


def criterion_level(
    definition: dict[str, Any],
    accepted: list[dict[str, Any]],
    error_families: dict[str, Any],
    severities: dict[str, Any],
) -> int:
    positive = definition.get("positive_findings") or {}
    negative = definition.get("negative_findings") or {}
    units = 0
    counts: dict[str, int] = {}
    ceilings = [3]
    for finding in accepted:
        code = finding["finding_code"]
        if code in positive:
            spec = positive[code]
            if counts.get(code, 0) < int(spec.get("max_occurrences", 1)):
                counts[code] = counts.get(code, 0) + 1
                units += int(spec.get("units", 0))
        elif code in negative:
            family_id = str(negative[code].get("error_family") or "")
            severity = str((error_families.get(family_id) or {}).get("severity") or "")
            ceiling = (severities.get(severity) or {}).get("level_ceiling")
            if ceiling is not None:
                ceilings.append(int(ceiling))
    return min(min(3, units), min(ceilings))


def _resolve_profile(
    payload: dict[str, Any],
    *,
    explicit_ref: str | None,
    step_type: str,
    dimension: str | None,
) -> tuple[str, dict[str, Any]]:
    profiles = payload["rubric_profiles"]
    if explicit_ref:
        profile_id = explicit_ref.removeprefix("rubric:")
        profile = profiles.get(profile_id)
        if profile is None:
            raise EvidencePrecondition(f"rubric ref {explicit_ref!r} does not resolve (no fallback)")
    else:
        entries = [
            e
            for e in payload["default_rubric_map"]["entries"]
            if e["step_type"] == step_type and (dimension is None or e["dimension"] == dimension)
        ]
        if len(entries) != 1:
            raise EvidencePrecondition(
                f"no exact default rubric for (step_type={step_type}, dimension={dimension}); "
                "specialized tasks need an explicit rubric_ref (PD-6 B, no broad fallback)"
            )
        profile_id = str(entries[0]["rubric_ref"]).removeprefix("rubric:")
        profile = profiles[profile_id]
    if step_type not in (profile.get("allowed_step_types") or []):
        raise EvidencePrecondition(
            f"profile rubric:{profile_id} does not allow step type {step_type} "
            "(fix applicability, never assess through an incompatible profile)"
        )
    return profile_id, profile


def finalize_attempt(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    attempt_id: str,
    *,
    extra_observations: list[dict[str, Any]] | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Assess and atomically settle a recorded open attempt."""
    manifest = _session_manifest(store, session_id)
    found = read_aggregate(store._conn, ATTEMPT_AGGREGATE, attempt_id)
    if found is None:
        raise EvidencePrecondition(f"attempt {attempt_id} does not exist")
    attempt, revision = found
    if str(attempt.get("session_id")) != session_id:
        raise EvidencePrecondition(f"attempt {attempt_id} belongs to another session")
    if attempt.get("status") == ASSESSED:
        prior = attempt.get("assessment") or {}
        return {
            "attempt_id": attempt_id,
            "status": ASSESSED,
            "already": True,
            "score_ppm": prior.get("score_ppm"),
            "disposition": prior.get("disposition", "scored"),
            "contributing": bool(prior.get("contributing")),
        }
    if attempt.get("status") != RECORDED:
        raise EvidencePrecondition(f"attempt {attempt_id} is {attempt.get('status')}; nothing to finalize")

    pinned = dict(manifest.get("pinned_versions") or {})
    if RUBRIC_KIND not in pinned:
        raise EvidencePrecondition(
            "the session pins no rubric policy; re-activate the curriculum so rubric@1 registers"
        )
    payload = require_valid(registry.resolve_pinned(RUBRIC_KIND, pinned[RUBRIC_KIND]))
    raw_answer = str(attempt.get("raw_answer") or "")
    step_type = str(attempt.get("step_type"))
    primary = attempt.get("primary_target") or {}
    dimension = primary.get("dimension")

    # Rubric resolution: the rendered exercise's explicit ref wins; otherwise
    # the exact default (materialized into the assessment fact).
    explicit_ref: str | None = None
    machine_checks: list[dict[str, Any]] = []
    instance_id = attempt.get("exercise_instance_id")
    if instance_id:
        for event in store.read():
            if event.type == EXERCISE_RENDERED_EVENT and str(
                event.payload.get("exercise_instance_id")
            ) == str(instance_id):
                explicit_ref = event.payload.get("rubric_ref")
                machine_checks = list(event.payload.get("machine_checks") or [])
    profile_id, profile = _resolve_profile(
        payload, explicit_ref=explicit_ref, step_type=step_type, dimension=dimension
    )
    profile_criteria = {str(c["criterion_id"]): c for c in profile["criteria"]}
    catalog = payload["criterion_catalog"]
    families = payload["error_families"]
    severities = payload["error_severities"]

    # 1. Machine checks (engine-reported, authoritative).
    machine_results: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for check in machine_checks:
        ref = str(check.get("rubric_criterion_ref") or "")
        criterion_id = _criterion_id_of(ref, profile_id)
        if criterion_id is None or criterion_id not in profile_criteria:
            continue  # a check for another profile's criterion cannot apply here
        operation = str(check.get("operation"))
        params = dict(check.get("params") or {})
        passed = run_machine_operation(operation, params, raw_answer)
        finding = check.get("on_pass") if passed else check.get("on_fail")
        result = {
            "rubric_criterion_ref": ref,
            "criterion_id": criterion_id,
            "check_id": check.get("check_id"),
            "operation": operation,
            "configuration_hash": payload_hash({"operation": operation, "params": params}),
            "result": "passed" if passed else "failed",
            "finding_code": finding,
            "reported_by": "engine",
        }
        machine_results.append(result)
        if finding:
            accepted.append({**result, "span_ref": None})

    # 2. Subjective observations (stored at record + supplied at finalize).
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    observations = list(attempt.get("observations") or []) + list(extra_observations or [])
    for obs in observations:
        ok, reason = validate_observation(
            obs,
            profile_id=profile_id,
            profile_criteria=profile_criteria,
            catalog=catalog,
            raw_answer=raw_answer,
            seen=seen,
        )
        if ok is not None:
            accepted.append(ok)
        else:
            rejected.append({"observation": obs, "reason": reason})

    # 3. Reduce criteria; check PD-7 completeness.
    context_prec = Decimal(1)  # integer quantum for ROUND_HALF_EVEN below
    level_ppm = {level: int(spec["level_ppm"]) for level, spec in payload["level_scale"].items()}
    trace: list[dict[str, Any]] = []
    covered: set[str] = set()
    numerator = Decimal(0)
    total_weight = Decimal(0)
    for criterion_id, selected in sorted(profile_criteria.items()):
        relevant = [f for f in accepted if f.get("criterion_id") == criterion_id]
        if relevant:
            covered.add(criterion_id)
        level = criterion_level(catalog[criterion_id], relevant, families, severities)
        weight = Decimal(int(selected["weight_units"]))
        numerator += weight * Decimal(level_ppm[str(level)])
        total_weight += weight
        trace.append(
            {
                "criterion_id": criterion_id,
                "weight_units": int(selected["weight_units"]),
                "level": level,
                "level_ppm": level_ppm[str(level)],
                "findings": len(relevant),
            }
        )
    required = {cid for cid, sel in profile_criteria.items() if sel.get("required")}
    complete = required <= covered

    if complete:
        score_ppm = int((numerator / total_weight).quantize(context_prec, rounding=ROUND_HALF_EVEN))
        disposition = "scored"
        contributing = bool(primary.get("target_ref"))
    else:
        score_ppm = None
        disposition = "insufficient_evidence"
        contributing = False  # missing assessor coverage is never a learner zero (PD-7 C)

    assessment: dict[str, Any] = {
        "basis": "rubric",
        "rubric_ref": f"rubric:{profile_id}",
        "pinned_rubric_version": pinned[RUBRIC_KIND],
        "disposition": disposition,
        "score_ppm": score_ppm,
        "contributing": contributing,
        "criteria": trace,
        "accepted_observations": accepted,
        "rejected_observations": rejected,
        "machine_results": machine_results,
        "uncovered_required": sorted(required - covered),
        "fingerprint": payload_hash(
            {"attempt": attempt_id, "profile": profile_id, "accepted": accepted, "trace": trace}
        ),
    }

    finalized_at = clock.now().isoformat()
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            ATTEMPT_AGGREGATE,
            attempt_id,
            {**attempt, "status": ASSESSED, "assessment": assessment, "assessed_at": finalized_at},
            expected_revision=revision,
        )
        events = [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_ATTEMPT_STATE_CHANGED,
                occurred_at=clock.now(),
                actor=actor,
                provider=manifest.get("provider"),
                correlation_id=session_id,
                payload={
                    "attempt_id": attempt_id,
                    "session_id": session_id,
                    "from_status": RECORDED,
                    "to_status": ASSESSED,
                    "reason": disposition,
                    "non_contributing": not contributing,
                    "assessment": assessment,
                },
                pinned_versions=pinned,
            )
        ]
        if contributing:
            events.append(
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_EVIDENCE_ADDED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    causation_id=events[0].id,
                    payload={
                        "evidence_id": new_ulid(clock, random_source),
                        "attempt_id": attempt_id,
                        "session_id": session_id,
                        "step_id": attempt.get("step_id"),
                        "exercise_instance_id": instance_id,
                        "origin": attempt.get("origin"),
                        "mode": step_type,
                        "primary_target": primary,
                        "selection_basis": attempt.get("selection_basis"),
                        "credit_allocations": [
                            {
                                "target_ref": primary.get("target_ref"),
                                "dimension": primary.get("dimension"),
                                "contribution": "1.0",
                                "used": True,
                                "reason": "primary",
                            }
                        ],
                        "span_hash": attempt.get("span_hash"),
                        "assessment_basis": "rubric",
                        "score_ppm": score_ppm,
                        "rubric_ref": f"rubric:{profile_id}",
                        "pinned_rubric_version": pinned[RUBRIC_KIND],
                        "hints": attempt.get("hints", 0),
                        "recorded_at": finalized_at,
                    },
                    pinned_versions=pinned,
                )
            )
        uow.append(events)
    return {
        "attempt_id": attempt_id,
        "status": ASSESSED,
        "already": False,
        "score_ppm": score_ppm,
        "disposition": disposition,
        "contributing": contributing,
        "rejected": len(rejected),
        "criteria": trace,
    }
