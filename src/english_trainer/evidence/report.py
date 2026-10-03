"""Pure builders for the tutor-verdict lesson report [PD-2026-09-23].

The lesson report (``lesson_report@1``) changes the PRODUCER of the evidence
facts, not their contract: the report commit writes the same
``attempt.recorded`` / ``evidence.added`` / ``evidence.error_observed`` shapes
the step-by-step protocol wrote, so every consumer (scoring, the automaticity
axis, the scheduler, control's saturation and recurring-error folds, the XP
ledger, audit) reads them unchanged. The one new fact is the assessment basis:

    assessment = {"basis": "tutor_verdict", "verdict", "correct", "score_ppm",
                  "contributing"}

where ``score_ppm`` comes from the pinned evidence@2 ``verdict_scale`` and
``correct`` is ``verdict == "correct"`` -- a ``partial`` answer is not a
correct one for any boolean consumer (saturation streaks, drill accuracy).

Everything here is a pure function of its arguments, except the two readers
that need the log exactly like the existing recording path does
(:func:`span_already_credited` and :func:`automaticity_updates`). Identifiers
and timestamps are passed in: the caller (``lessons.report``) owns the Clock,
the RandomSource and the UnitOfWork.

Ordering contract for the caller (one UnitOfWork, items in report order):

1. per item: save the attempt aggregate, then append ``attempt.recorded`` +
   ``evidence.added`` (if contributing) + ``automaticity_updates(...)`` +
   the item's ``evidence.error_observed`` facts -- :func:`item_events` builds
   the first two and the errors, :func:`automaticity_updates` the axis facts;
2. APPEND each item's facts before building the next item's: the span
   identity check and the automaticity fold read ``store.read()``, which sees
   the facts already appended inside the open UnitOfWork;
3. review closures (``evidence.reviews.closure_from_verdict`` /
   ``close_insufficient``) after the attempt they close has been appended, so
   the ``scoring.state_transition`` fold sees the evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from english_trainer.evidence.assessment import span_hash as _byte_span_hash
from english_trainer.evidence.attempts import (
    ASSESSED,
    BLOCK_CORRECT_THRESHOLD_PPM,
    DRILL_BLOCK_FORM,
    EVENT_ATTEMPT_RECORDED,
    EVENT_EVIDENCE_ADDED,
    EvidencePrecondition,
    _automaticity_updates,
    _credited_item_spans,
    _item_pair,
)
from english_trainer.evidence.observed import EVENT_ERROR_OBSERVED
from english_trainer.evidence.policy import VERDICTS, allocate_credit
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

TUTOR_VERDICT_BASIS = "tutor_verdict"
# ``session.step_presented.source`` and ``attempt.recorded.source`` of every
# fact the report writes: provenance, never a scoring input.
REPORT_SOURCE = "lesson_report"
REPORTED_BY_TUTOR = "tutor"
SELECTION_BASIS = "declared_item_target"
_PPM = 1_000_000


class ReportInputInvalid(EvidencePrecondition):
    """A report item is not admissible as written -- fix the report.

    ``reason`` is the stable rejection code of the report contract
    (``bad_verdict``, ``empty_answer``, ``learner_form_not_in_answer`` ...).
    """

    code = "INVALID_INPUT"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason


# -- verdict --------------------------------------------------------------


def verdict_score(verdict: str, policy: Mapping[str, Any]) -> int:
    """The verdict's ``score_ppm`` from the pinned ``verdict_scale``.

    ``policy`` is the validated evidence@2 leaf set
    (``evidence.policy.verdict_policy``) or the raw evidence@2 payload; both
    carry ``verdict_scale``. An unknown verdict is refused, never guessed.
    """
    if verdict not in VERDICTS:
        raise ReportInputInvalid("bad_verdict", f"verdict {verdict!r} is not one of {list(VERDICTS)}")
    scale = policy.get("verdict_scale")
    if not isinstance(scale, Mapping) or verdict not in scale:
        raise ReportInputInvalid("bad_verdict", f"the pinned evidence policy has no scale for {verdict!r}")
    value = scale[verdict]
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _PPM:
        raise EvidencePrecondition(f"evidence.verdict_scale.{verdict}: not an integer ppm")
    return value


def verdict_assessment(
    verdict: str, policy: Mapping[str, Any], *, contributing: bool = True
) -> dict[str, Any]:
    """The ``tutor_verdict`` assessment of one answered item."""
    return {
        "basis": TUTOR_VERDICT_BASIS,
        "verdict": verdict,
        "correct": verdict == "correct",
        "score_ppm": verdict_score(verdict, policy),
        # False only for a repeated span: the review closure then reads
        # INSUFFICIENT_EVIDENCE instead of moving the target (evidence.reviews).
        "contributing": contributing,
    }


# -- spans ----------------------------------------------------------------


def answer_span_hash(raw_answer: str) -> str:
    """The attempt-level span identity -- identical to ``record_attempt``'s."""
    return payload_hash({"raw_answer": raw_answer})


def derive_span(raw_answer: str, learner_form: str) -> dict[str, Any] | None:
    """The span of ``learner_form`` inside ``raw_answer``, or ``None``.

    First exact occurrence; UTF-8 half-open byte offsets and the rubric span
    contract's ``span_hash`` (``sha256:<hex>`` of the exact byte slice), so the
    result validates exactly like an agent-submitted ``span_ref``. The tutor
    never sends offsets: the engine derives them from the quoted form.
    """
    if not learner_form:
        return None
    index = raw_answer.find(learner_form)
    if index < 0:
        return None
    start = len(raw_answer[:index].encode("utf-8"))
    end = start + len(learner_form.encode("utf-8"))
    return {"start_utf8": start, "end_utf8": end, "span_hash": _byte_span_hash(raw_answer, start, end)}


def span_already_credited(
    store: EventStore, span_hash: str, primary_target: Mapping[str, Any] | None
) -> bool:
    """Whether this span already earned credit for the primary (target, dimension).

    Semantic identity (evidence 4.1): the same index the drill-block path uses,
    covering single attempts AND credited block items, across sessions. Reads
    ``store.read()``, so inside one UnitOfWork it sees the report's earlier,
    already-appended items.
    """
    pair = _item_pair(None, dict(primary_target) if primary_target is not None else None)
    if pair is None:
        return False
    return (span_hash, *pair) in _credited_item_spans(store)


# -- targets --------------------------------------------------------------


def item_targets(
    target_ref: str, dimension: str, secondary_targets: Sequence[Mapping[str, Any]] = ()
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """``(targets, primary_target)`` for one report item.

    The item's own target is primary; secondary targets follow in canonical
    (sorted, de-duplicated) order, exactly the order ``allocate_credit`` uses.
    A secondary target without a dimension inherits the item's.
    """
    primary = {"target_ref": target_ref, "dimension": dimension}
    seen = {(target_ref, dimension)}
    secondaries: list[tuple[str, str]] = []
    for item in secondary_targets:
        ref = str(item.get("target_ref") or "")
        if not ref:
            continue
        pair = (ref, str(item.get("dimension") or dimension))
        if pair not in seen:
            seen.add(pair)
            secondaries.append(pair)
    targets = [dict(primary), *({"target_ref": ref, "dimension": dim} for ref, dim in sorted(secondaries))]
    return targets, primary


def _hints(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReportInputInvalid("bad_hints", "hints must be a non-negative integer")
    return value


# -- single item ------------------------------------------------------------


def build_attempt_payload(
    *,
    attempt_id: str,
    session_id: str,
    step_id: str,
    item_id: str,
    step_type: str,
    kind: str,
    target_ref: str,
    dimension: str,
    prompt: str,
    raw_answer: str,
    verdict: str,
    policy: Mapping[str, Any],
    recorded_at: str,
    contributing: bool = True,
    secondary_targets: Sequence[Mapping[str, Any]] = (),
    hints: int = 0,
    origin: str = "session",
    review_id: str | None = None,
) -> dict[str, Any]:
    """The ``attempt.recorded`` payload (and attempt aggregate state) of one item.

    Same field set as ``record_attempt`` -- scoring, XP, the review closure and
    the span index read it unchanged -- with ``status: assessed`` and the
    ``tutor_verdict`` assessment. ``contributing=False`` marks a repeated span
    (:func:`span_already_credited`): the attempt records, no evidence follows.
    """
    if not raw_answer or not raw_answer.strip():
        raise ReportInputInvalid("empty_answer", f"item {item_id}: an explanation is not evidence (0.4 4.2)")
    targets, primary_target = item_targets(target_ref, dimension, secondary_targets)
    return {
        "attempt_id": attempt_id,
        "session_id": session_id,
        "step_id": step_id,
        "item_id": item_id,
        "source": REPORT_SOURCE,
        "exercise_instance_id": None,
        "step_type": step_type,
        "mode": step_type,
        "kind": kind,
        "origin": origin,
        "targets": targets,
        "primary_target": primary_target,
        "selection_basis": SELECTION_BASIS,
        "prompt": prompt,
        "raw_answer": raw_answer,
        "span_hash": answer_span_hash(raw_answer),
        "observations": [],
        "hints": _hints(hints),
        # No latency travels with a tutor report (PD-2026-09-23): absent means
        # "not measured", never zero (evidence 4.6).
        "response_latency_ms": None,
        "declared_limit_seconds": None,
        "review_id": review_id,
        "status": ASSESSED,
        "assessment": verdict_assessment(verdict, policy, contributing=contributing),
        "non_contributing": not contributing,
        "recorded_at": recorded_at,
    }


def build_evidence_payload(
    attempt: Mapping[str, Any], *, evidence_id: str, multi_credit: dict[str, str]
) -> dict[str, Any] | None:
    """The ``evidence.added`` payload of a contributing single-item attempt.

    ``None`` for a non-contributing attempt (a repeated span): there is no
    second learning fact in a span that was already counted. Credit is
    allocated by the pinned multi-credit policy, exactly as ``record_attempt``
    does; ``prompt`` rides along so the stored evidence is auditable on its own.
    """
    assessment = dict(attempt.get("assessment") or {})
    if attempt.get("non_contributing") or assessment.get("contributing") is False:
        return None
    targets = [dict(item) for item in attempt.get("targets") or []]
    primary = attempt.get("primary_target")
    primary_target = dict(primary) if isinstance(primary, Mapping) else None
    return {
        "evidence_id": evidence_id,
        "attempt_id": attempt["attempt_id"],
        "session_id": attempt["session_id"],
        "step_id": attempt["step_id"],
        "item_id": attempt.get("item_id"),
        "source": REPORT_SOURCE,
        "exercise_instance_id": None,
        "origin": attempt.get("origin", "session"),
        "mode": attempt.get("mode"),
        "primary_target": primary_target,
        "selection_basis": attempt.get("selection_basis", SELECTION_BASIS),
        "credit_allocations": allocate_credit(targets, primary_target, multi_credit),
        "span_hash": attempt.get("span_hash"),
        "assessment_basis": TUTOR_VERDICT_BASIS,
        "verdict": assessment.get("verdict"),
        "correct": bool(assessment.get("correct")),
        "score_ppm": int(assessment.get("score_ppm") or 0),
        "prompt": attempt.get("prompt"),
        "hints": int(attempt.get("hints") or 0),
        "response_latency_ms": None,
        "declared_limit_seconds": None,
        "recorded_at": attempt.get("recorded_at"),
    }


# -- drill block ------------------------------------------------------------


def build_block_attempt_payload(
    store: EventStore,
    *,
    attempt_id: str,
    session_id: str,
    step_id: str,
    block_id: str,
    step_type: str,
    target_ref: str,
    dimension: str,
    items: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
    recorded_at: str,
    mode: str | None = None,
    origin: str = "session",
    review_id: str | None = None,
) -> dict[str, Any]:
    """The ``attempt.recorded`` payload of a whole drill block (evidence 4.6).

    ``items`` are the report items carrying this ``block_id``, in report order;
    each needs ``item_id``, ``raw_answer`` and ``verdict`` (``prompt`` and a
    per-item ``target_ref`` are optional). Each item is its own source span:
    an item repeating an already-credited span -- earlier in the log (read
    from ``store``) or earlier in this very block -- is recorded
    ``credited: false`` and stays out of the accuracy. Per item,
    ``objective_correct = verdict == "correct"`` is the field the automaticity
    reducer folds; no latency is carried (none is measured).

    The block collapses into ONE binary evidence, as the machine-checked block
    does: ``correct`` when the credited accuracy reaches
    ``BLOCK_CORRECT_THRESHOLD_PPM``; the accuracy itself travels as
    ``block.score_ppm``. The block's derived ``verdict`` (``correct`` /
    ``incorrect``) is what a review closure maps.
    """
    if not items:
        raise ReportInputInvalid("block_unknown", f"block {block_id} has no items")
    primary_target = {"target_ref": target_ref, "dimension": dimension}
    credited_spans = _credited_item_spans(store)
    results: list[dict[str, Any]] = []
    answered = correct_count = duplicates = 0
    for index, item in enumerate(items):
        item_id = str(item.get("item_id") or f"{block_id}#item:{index}")
        answer = item.get("raw_answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ReportInputInvalid(
                "empty_answer", f"item {item_id}: an explanation is not evidence (0.4 4.2)"
            )
        verdict = str(item.get("verdict"))
        verdict_score(verdict, policy)  # refuses an unknown verdict
        item_target = item.get("target_ref") or target_ref
        entry: dict[str, Any] = {
            "index": index,
            "item_id": item_id,
            "prompt_ref": item_id,
            "prompt": item.get("prompt"),
            "raw_answer": answer,
            "target_ref": item_target,
            "contrast": item_target != target_ref,
            "presented": True,
            "objective_correct": None,
            "verdict": verdict,
            "span_hash": answer_span_hash(answer),
            "self_repaired": False,
            "credited": False,
        }
        pair = _item_pair(item_target, primary_target)
        key = (str(entry["span_hash"]), *pair) if pair is not None else None
        if key is not None and key in credited_spans:
            duplicates += 1
        else:
            if key is not None:
                credited_spans.add(key)
            entry["credited"] = True
            entry["objective_correct"] = verdict == "correct"
            answered += 1
            if entry["objective_correct"]:
                correct_count += 1
        results.append(entry)

    contributing = answered > 0
    score_ppm = correct_count * _PPM // answered if answered else 0
    correct = contributing and score_ppm >= BLOCK_CORRECT_THRESHOLD_PPM
    assessment: dict[str, Any] = {
        "basis": TUTOR_VERDICT_BASIS,
        "form": DRILL_BLOCK_FORM,
        # Derived from the per-item verdicts, never reported: the closure map
        # reads it like a single item's verdict.
        "verdict": "correct" if correct else "incorrect",
        "correct": correct,
        "score_ppm": _PPM if correct else 0,
        "contributing": contributing,
        "block": {
            "correct_count": correct_count,
            "answered": answered,
            "duplicate": duplicates,
            "total": len(results),
            "score_ppm": score_ppm,
            "threshold_ppm": BLOCK_CORRECT_THRESHOLD_PPM,
        },
    }
    span_hash = payload_hash({"block_items": [item["span_hash"] for item in results]})
    return {
        "attempt_id": attempt_id,
        "session_id": session_id,
        "step_id": step_id,
        "block_id": block_id,
        "block_mode": mode,
        "source": REPORT_SOURCE,
        "exercise_instance_id": None,
        "step_type": step_type,
        "mode": step_type,
        "form": DRILL_BLOCK_FORM,
        "origin": origin,
        "targets": [dict(primary_target)],
        "primary_target": primary_target,
        "selection_basis": SELECTION_BASIS,
        "raw_answer": None,  # a block has no single span; see items[]
        "span_hash": span_hash,
        "items": results,
        "rounds": [],
        "declared_limit_seconds": None,
        "observations": [],
        "hints": 0,
        "response_latency_ms": None,
        "review_id": review_id,
        "status": ASSESSED,
        "assessment": assessment,
        "non_contributing": not contributing,
        "recorded_at": recorded_at,
    }


def build_block_evidence_payload(
    attempt: Mapping[str, Any], *, evidence_id: str, multi_credit: dict[str, str]
) -> dict[str, Any] | None:
    """The ONE ``evidence.added`` of a contributing block; ``None`` otherwise.

    Only the credited items reach the evidence: they are what the accuracy was
    computed from and what the automaticity reducer folds.
    """
    assessment = dict(attempt.get("assessment") or {})
    if not assessment.get("contributing"):
        return None
    targets = [dict(item) for item in attempt.get("targets") or []]
    primary = attempt.get("primary_target")
    primary_target = dict(primary) if isinstance(primary, Mapping) else None
    block = dict(assessment.get("block") or {})
    return {
        "evidence_id": evidence_id,
        "attempt_id": attempt["attempt_id"],
        "session_id": attempt["session_id"],
        "step_id": attempt["step_id"],
        "block_id": attempt.get("block_id"),
        "source": REPORT_SOURCE,
        "exercise_instance_id": None,
        "origin": attempt.get("origin", "session"),
        "mode": attempt.get("mode"),
        "form": DRILL_BLOCK_FORM,
        "primary_target": primary_target,
        "selection_basis": attempt.get("selection_basis", SELECTION_BASIS),
        "credit_allocations": allocate_credit(targets, primary_target, multi_credit),
        "span_hash": attempt.get("span_hash"),
        "assessment_basis": TUTOR_VERDICT_BASIS,
        "verdict": assessment.get("verdict"),
        "correct": bool(assessment.get("correct")),
        "score_ppm": int(assessment.get("score_ppm") or 0),
        "block_score_ppm": int(block.get("score_ppm") or 0),
        "hints": 0,
        "response_latency_ms": None,
        "items": [dict(item) for item in attempt.get("items") or [] if item.get("credited")],
        "recorded_at": attempt.get("recorded_at"),
    }


# -- errors -----------------------------------------------------------------


def build_error_payload(
    *,
    observed_error_id: str,
    attempt_id: str,
    session_id: str,
    item_id: str,
    target_ref: str,
    dimension: str,
    raw_answer: str,
    error: Mapping[str, Any],
    severity: str,
    observed_at: str,
) -> dict[str, Any]:
    """One ``evidence.error_observed`` payload for a tutor-reported error.

    ``error`` is the report's ``{learner_form, correction, cause,
    topic_error_ref?}``. The span is DERIVED from ``learner_form`` inside the
    item's ``raw_answer`` (a block item's own answer); a form the learner did
    not write is refused (``learner_form_not_in_answer``). Severity is the
    policy default (evidence@2 ``tutor_errors``), never the tutor's. The fact
    carries a top-level ``(target_ref, dimension)`` -- what control's
    recurring-error fold reads.
    """
    learner_form = str(error.get("learner_form") or "")
    span = derive_span(raw_answer, learner_form)
    if span is None:
        raise ReportInputInvalid(
            "learner_form_not_in_answer",
            f"item {item_id}: {learner_form!r} does not occur in the learner's answer",
        )
    correction = error.get("correction")
    cause = error.get("cause")
    topic_error_ref = error.get("topic_error_ref")
    identity = payload_hash(
        {
            "attempt_id": attempt_id,
            "item_id": item_id,
            "learner_form": learner_form,
            "correction": correction,
            "span_ref": span,
        }
    )
    return {
        "observed_error_id": observed_error_id,
        "observation_identity": identity,
        "attempt_id": attempt_id,
        "session_id": session_id,
        "item_id": item_id,
        "source": REPORT_SOURCE,
        "target_ref": target_ref,
        "dimension": dimension,
        # The rubric-anchored fields of an agent observation have no referent
        # in a tutor verdict; present and null so the shape stays one shape.
        "rubric_criterion_ref": None,
        "criterion_id": None,
        "finding_code": None,
        "error_family": None,
        "severity": severity,
        "span_ref": span,
        "learner_form": learner_form,
        "correction": correction,
        "cause": cause,
        "topic_error_ref": topic_error_ref,
        "distractor_error_ref": None,
        "reported_by": REPORTED_BY_TUTOR,
        "contradicts_machine_result": False,
        "observed_at": observed_at,
    }


# -- event assembly -------------------------------------------------------------


def item_events(
    clock: Clock,
    random_source: RandomSource,
    *,
    attempt: dict[str, Any],
    multi_credit: dict[str, str],
    errors: Sequence[Mapping[str, Any]] = (),
    severity: str,
    pinned: dict[str, str],
    provider: str | None = None,
    actor: str = "agent",
) -> list[DomainEvent]:
    """The facts of one report item (or block), in append order.

    ``attempt.recorded`` -> ``evidence.added`` (when contributing, caused by
    the attempt) -> one ``evidence.error_observed`` per error (caused by the
    attempt). For a block, pass the block attempt and put ``item_id`` /
    ``raw_answer`` on each error (the block item it belongs to); for a single
    item they default to the attempt's. Automaticity facts are NOT included:
    call :func:`automaticity_updates` on this list and append both together.
    """
    session_id = str(attempt["session_id"])
    recorded_at = str(attempt.get("recorded_at"))
    recorded = make_event(
        id=new_ulid(clock, random_source),
        type=EVENT_ATTEMPT_RECORDED,
        occurred_at=clock.now(),
        actor=actor,
        provider=provider,
        correlation_id=session_id,
        payload=attempt,
        pinned_versions=pinned,
    )
    events = [recorded]
    is_block = attempt.get("form") == DRILL_BLOCK_FORM
    build = build_block_evidence_payload if is_block else build_evidence_payload
    evidence = build(attempt, evidence_id=new_ulid(clock, random_source), multi_credit=multi_credit)
    if evidence is not None:
        events.append(
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_EVIDENCE_ADDED,
                occurred_at=clock.now(),
                actor=actor,
                provider=provider,
                correlation_id=session_id,
                causation_id=recorded.id,
                payload=evidence,
                pinned_versions=pinned,
            )
        )
    primary = dict(attempt.get("primary_target") or {})
    for error in errors:
        raw_answer = error.get("raw_answer", attempt.get("raw_answer"))
        if not isinstance(raw_answer, str):
            raise ReportInputInvalid(
                "learner_form_not_in_answer", "a block error needs its item's raw_answer"
            )
        payload = build_error_payload(
            observed_error_id=new_ulid(clock, random_source),
            attempt_id=str(attempt["attempt_id"]),
            session_id=session_id,
            item_id=str(error.get("item_id") or attempt.get("item_id") or ""),
            target_ref=str(error.get("target_ref") or primary.get("target_ref") or ""),
            dimension=str(primary.get("dimension") or ""),
            raw_answer=raw_answer,
            error=error,
            severity=severity,
            observed_at=recorded_at,
        )
        events.append(
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_ERROR_OBSERVED,
                occurred_at=clock.now(),
                actor=actor,
                provider=provider,
                correlation_id=session_id,
                causation_id=recorded.id,
                payload=payload,
                pinned_versions=pinned,
            )
        )
    return events


def automaticity_updates(
    store: EventStore, clock: Clock, registry: PolicyRegistry | None, batch: Sequence[DomainEvent]
) -> list[DomainEvent]:
    """The ``AUTOMATICITY_UPDATED`` facts caused by ``batch``'s evidence.

    The recording path's own producer, unchanged: build it after every
    EARLIER item has been appended (the fold reads ``store.read()``) and
    append it together with ``batch``.
    """
    return _automaticity_updates(store, clock, registry, batch)
