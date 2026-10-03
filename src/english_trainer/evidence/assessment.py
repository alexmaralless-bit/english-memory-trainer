"""The rubric assessment pipeline for open answers (P.5 [PD-2026-07-22];
evidence 4.1/4.5; rubric@1 ``criterion_reducer``).

:func:`compute_rubric_assessment` is a PURE read: resolve the pinned rubric
profile (explicit ``rubric_ref`` from a rendered exercise or the caller, or
the EXACT (step_type, dimension) default -- never a broad fallback), execute
the closed machine-check opcodes over the exact saved inputs, validate every
subjective observation (criterion in profile, finding allowed, UTF-8 span
inside the saved answer with a matching hash -- one ``rejected`` branch with
stable reasons, nothing "flagged but counted"), reduce findings to four-level
criteria under policy-owned severity ceilings, and aggregate the integer
``score_ppm`` with ROUND_HALF_EVEN.

Completeness is PD-7 C: every required criterion needs at least one accepted
finding or machine result; an incomplete assessment is ``insufficient_evidence``
and non-contributing -- missing assessor coverage is never a false learner
zero. A target-less answer assesses for audit but cannot mint contributing
evidence.

Its live caller is placement (``assessments.placement`` assesses writing items
through the rubric profile the placement pins). Lesson sessions no longer run
it: since the brief/report protocol [PD-2026-09-23] a lesson item's
correctness is the tutor's verdict (evidence@2). The per-step settlement path
(``attempt record`` with observations, ``attempt finalize``) was removed with
that protocol; the ``attempt.state_changed`` facts it wrote stay readable by
every consumer. The agent reports facts; every level and score here is
engine-made.
"""

from __future__ import annotations

import decimal
import hashlib
import re
import unicodedata
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from english_trainer.evidence.attempts import (
    EvidencePrecondition,
)
from english_trainer.evidence.rubric import RUBRIC_KIND, require_valid
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

EXERCISE_RENDERED_EVENT = "exercise.rendered"

#: The rubric-facing step type the RENDER stored inside the immutable snapshot
#: for a form whose own step type no pinned rubric profile enumerates
#: (``reconstruction`` -> ``controlled_production``, ``timed_writing`` ->
#: ``spontaneous_production``; generation@3 ``rubric_step_type_equivalence``,
#: [PD-2026-09-22]). The mapping is owned by lessons and resolved once, at
#: render; evidence may not import lessons (architecture gate), and re-deriving
#: it here would be a second source of truth -- so only the stored field is
#: read. Absent means "the attempt's own step type is what the rubric
#: enumerates", which is every pre-generation@3 snapshot.
RUBRIC_STEP_TYPE_FIELD = "rubric_step_type"

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


def _decimal_context(payload: dict[str, Any]) -> decimal.Context:
    """The fixed Decimal context the rubric policy pins (precision 28,
    ROUND_HALF_EVEN). The score aggregation runs inside it so the ``score_ppm``
    division does not read the mutable ambient thread context -- the same
    hermetic-fold guarantee the scoring engine keeps."""
    section = payload.get("decimal_context") or {}
    return decimal.Context(
        prec=int(section.get("precision", 28)),
        rounding=getattr(decimal, str(section.get("rounding", "ROUND_HALF_EVEN"))),
    )


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


def compute_rubric_assessment(
    store: EventStore,
    registry: PolicyRegistry,
    *,
    pinned: dict[str, Any],
    attempt: dict[str, Any],
    extra_observations: list[dict[str, Any]] | None = None,
    explicit_rubric_ref: str | None = None,
    rubric_step_type: str | None = None,
) -> dict[str, Any]:
    """The whole rubric pipeline as a PURE read: resolve, check, reduce, score.

    Nothing here writes: the caller owns the settlement of the result
    (placement records it in its own aggregate).

    ``explicit_rubric_ref`` / ``rubric_step_type`` carry the rendering context
    for a caller that HAS no rendered exercise to read it from -- a placement
    writing item declares its own profile and is assessed through the
    rubric-facing step type the placement pins. A rendered exercise always
    wins: its stored snapshot is the authoritative record of what was shown.
    """
    if RUBRIC_KIND not in pinned:
        raise EvidencePrecondition(
            "the session pins no rubric policy; re-activate the curriculum so rubric@1 registers"
        )
    payload = require_valid(registry.resolve_pinned(RUBRIC_KIND, pinned[RUBRIC_KIND]))
    attempt_id = str(attempt.get("attempt_id"))
    raw_answer = str(attempt.get("raw_answer") or "")
    step_type = str(attempt.get("step_type"))
    primary = attempt.get("primary_target") or {}
    dimension = primary.get("dimension")

    # Rubric resolution: the rendered exercise's explicit ref wins; otherwise
    # the exact default (materialized into the assessment fact).
    explicit_ref: str | None = None
    machine_checks: list[dict[str, Any]] = []
    mapped_step_type: str | None = None
    instance_id = attempt.get("exercise_instance_id")
    if instance_id:
        for event in store.read():
            if event.type == EXERCISE_RENDERED_EVENT and str(
                event.payload.get("exercise_instance_id")
            ) == str(instance_id):
                explicit_ref = event.payload.get("rubric_ref")
                machine_checks = list(event.payload.get("machine_checks") or [])
                stored = event.payload.get(RUBRIC_STEP_TYPE_FIELD)
                mapped_step_type = str(stored) if isinstance(stored, str) and stored else None
    if explicit_ref is None and explicit_rubric_ref:
        explicit_ref = str(explicit_rubric_ref)
    if mapped_step_type is None and rubric_step_type:
        mapped_step_type = str(rubric_step_type)
    # A `timed_writing` or `reconstruction` attempt is assessed through the
    # rubric-facing step type its snapshot recorded; the attempt keeps its REAL
    # step type everywhere else, so nothing downstream sees a timed writing as
    # spontaneous production.
    rubric_facing_step_type = mapped_step_type or step_type
    profile_id, profile = _resolve_profile(
        payload, explicit_ref=explicit_ref, step_type=rubric_facing_step_type, dimension=dimension
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

    # 3. Reduce criteria; check PD-7 completeness. The weighted-mean arithmetic
    # runs inside the rubric's pinned Decimal context so the bare ``+``/``*``
    # and the final division use precision 28 / ROUND_HALF_EVEN -- not the
    # ambient thread context -- keeping ``score_ppm`` hermetic under replay.
    context_prec = Decimal(1)  # integer quantum for ROUND_HALF_EVEN below
    level_ppm = {level: int(spec["level_ppm"]) for level, spec in payload["level_scale"].items()}
    trace: list[dict[str, Any]] = []
    covered: set[str] = set()
    score_ppm: int | None
    with decimal.localcontext(_decimal_context(payload)):
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
    if mapped_step_type is not None and mapped_step_type != step_type:
        # Recorded only when it differs: replay and audit see WHICH profile the
        # attempt was assessed through without inferring the mapping, and a
        # snapshot that needed no mapping keeps exactly the shape it had.
        assessment[RUBRIC_STEP_TYPE_FIELD] = mapped_step_type
    return assessment
