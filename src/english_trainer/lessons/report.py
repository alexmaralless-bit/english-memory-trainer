"""The lesson report (``lesson_report@1``) -- check and commit [PD-2026-09-23].

The tutor runs the lesson from the brief (:mod:`lessons.brief`) and files ONE
report at the end. Two entry points:

``check_report``
    Read-only, never writes. Validates the document against the session (schema,
    session id, brief hash) and every item against the PINNED program and the
    session's pending review assignments, and shows what a commit would do:
    per item ``accepted``/``rejected`` with stable reason codes and the effects
    (``score_ppm``, ``contributing`` incl. the ``duplicate_span`` flag, the
    review outcome), the reviews left unaddressed, the advisory requirements,
    the lexicon entries (new vs already enrolled) and the warnings.

``commit_report``
    Re-runs the check; ANY rejected item (or a report-level error) refuses the
    whole report and writes nothing. Otherwise ONE UnitOfWork writes, in order:
    ``lesson.reported`` (the full report + ``report_hash`` + the validation
    summary) -> per item/block ``session.step_presented`` (``source:
    lesson_report``) -> the attempt aggregate + ``attempt.recorded`` /
    ``evidence.added`` / automaticity / ``evidence.error_observed`` facts
    (``evidence.report`` builders) -> the review closure of an addressed review
    -> ``INSUFFICIENT_EVIDENCE`` for every review still pending (the skip
    reason, else ``not_attempted``) -> the personal-lexicon events -> the
    session's ``STARTED/IN_PROGRESS -> IN_PROGRESS -> FINISHED`` close
    (``sessions.close_reported_session``). Idempotent by key: the same key with
    the same report returns the cached result; with a different report it is an
    ``IdempotencyConflict``. No session-revision token is asked of the caller.

Decisions recorded here:

- The engine never re-grades: the verdict is the tutor's (evidence@2 maps it
  to ``score_ppm`` and to the review outcome). A repeated answer span is NOT a
  rejection: it is recorded, earns no second credit (``contributing: false``)
  and is shown explicitly by the check.
- Requirements (central-topic items, addressed reviews) are warnings only.
- An EMPTY report (no items) is accepted with an ``empty_report`` warning and
  finishes the session: a talk-only lesson closes honestly, with its pending
  reviews settled ``INSUFFICIENT_EVIDENCE`` and the report itself kept as
  provenance. Nothing is scored from it.
- ``brief_hash`` binds the report to the brief it was written against. The
  brief is deterministic (``lessons.brief``), so a mismatch means learner state
  moved since the brief was issued: a WARNING (``brief_changed``), never a
  refusal -- every item is validated against the pinned program and the live
  assignments anyway.
- The personal-lexicon writer lives in ``learner``, which ``lessons`` may not
  import yet (tests/architecture): the caller injects
  ``learner.build_encounter_events`` / ``learner.find_encounter_entry``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from english_trainer.control.policy import CONTROL_KIND
from english_trainer.evidence.attempts import (
    ATTEMPT_AGGREGATE,
    BLOCK_CORRECT_THRESHOLD_PPM,
    _credited_item_spans,
    _item_pair,
    close_pending_attempts,
    pending_attempts,
)
from english_trainer.evidence.policy import (
    VERDICTS,
    EvidencePolicyInvalid,
    multi_credit_policy,
    verdict_policy,
)
from english_trainer.evidence.report import (
    REPORT_SOURCE,
    TUTOR_VERDICT_BASIS,
    answer_span_hash,
    automaticity_updates,
    build_attempt_payload,
    build_block_attempt_payload,
    derive_span,
    item_events,
    item_targets,
    span_already_credited,
)
from english_trainer.evidence.reviews import (
    _outcome_from_assessment,
    close_insufficient,
    closure_from_verdict,
    pending_assignments,
)
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import CachedResult, UnitOfWork
from english_trainer.lessons.brief import (
    BLOCK_MODES,
    EVENT_LESSON_REPORTED,
    ITEM_KINDS,
    REPORT_SCHEMA,
    REVIEW_SKIP_REASONS,
    STEP_TYPE_BY_DIMENSION,
    brief_refs,
    build_brief,
    known_program_refs,
)
from english_trainer.lessons.sessions import (
    EVENT_STEP_PRESENTED,
    IN_PROGRESS,
    STARTED,
    PermanentInterleave,
    SessionPrecondition,
    close_reported_session,
    get_plan,
    get_session,
)
from english_trainer.scoring.policy import DIMENSIONS

CHECK_SCHEMA = "lesson_report_check@1"
COMMAND = "session.report"
_PPM = 1_000_000
_DRILL_BLOCK = "drill_block"
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "session_id",
        "brief_hash",
        "items",
        "blocks",
        "reviews_skipped",
        "teaching",
        "lexicon",
        "summary",
    }
)


class ReportRejected(SessionPrecondition):
    """The report is not admissible as written; nothing was written.

    ``check`` is the full :func:`check_report` result -- every rejected item
    with its reason codes -- so the tutor fixes the report and retries. A
    ``SessionPrecondition`` (CLI: PRECONDITION_FAILED, exit 6).
    """

    code = "REPORT_REJECTED"

    def __init__(self, message: str, check: dict[str, Any]) -> None:
        super().__init__(message)
        self.check = check


class EncounterLookup(Protocol):
    """``learner.find_encounter_entry`` -- injected (lessons may not import learner)."""

    def __call__(
        self, store: EventStore, *, surface: str, linked_item_id: str | None = None
    ) -> dict[str, Any] | None: ...


class EncounterBuilder(Protocol):
    """``learner.build_encounter_events`` -- injected (lessons may not import learner)."""

    def __call__(
        self,
        store: EventStore,
        clock: Clock,
        random_source: RandomSource,
        *,
        session_id: str,
        surface: str,
        provider: str | None = None,
        note_ru: str | None = None,
        linked_item_id: str | None = None,
        program: dict[str, Any] | None = None,
        pinned_versions: dict[str, str] | None = None,
        source_event_id: str | None = None,
        actor: str = "agent",
    ) -> list[DomainEvent]: ...


# -- evaluation ---------------------------------------------------------------


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@dataclass
class _Unit:
    """One thing the commit writes: a single item, or a whole drill block."""

    kind: str  # "item" | "block"
    item: dict[str, Any] | None = None
    block: dict[str, Any] | None = None
    members: list[dict[str, Any]] = field(default_factory=list)
    dimension: str = ""
    review_id: str | None = None


@dataclass
class _Evaluation:
    check: dict[str, Any]
    units: list[_Unit]
    pinned: dict[str, str]
    program: dict[str, Any]
    leaves: dict[str, Any]
    brief: dict[str, Any]
    state: dict[str, Any]
    revision: int
    report_hash: str | None


def _surface_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _active_session(store: EventStore, session_id: str) -> tuple[dict[str, Any], int]:
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, revision = found
    if state.get("status") not in (STARTED, IN_PROGRESS):
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; a report is filed only for an active session"
        )
    return dict(state), revision


def _require_list(report: Mapping[str, Any], key: str, errors: list[dict[str, str]]) -> list[Any]:
    value = report.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(_reason("bad_schema", f"{key} must be a list"))
        return []
    return value


def _evaluate(
    store: EventStore,
    registry: PolicyRegistry,
    session_id: str,
    report: Any,
    *,
    encounter_lookup: EncounterLookup | None,
    permanent_interleave: PermanentInterleave | None,
) -> _Evaluation:
    state, revision = _active_session(store, session_id)
    manifest = dict(state.get("manifest") or {})
    pinned = {str(k): str(v) for k, v in dict(manifest.get("pinned_versions") or {}).items()}
    try:
        leaves = verdict_policy(registry, pinned)
    except EvidencePolicyInvalid as exc:
        raise SessionPrecondition(
            f"session {session_id} cannot take a lesson report: {exc}; abandon it and start a new session"
        ) from exc
    program: dict[str, Any] = (
        registry.resolve_pinned("curriculum", pinned["curriculum"]) if "curriculum" in pinned else {}
    )
    brief = build_brief(store, registry, session_id, permanent_interleave=permanent_interleave)
    current_brief_hash = str(brief["report_contract"]["brief_hash"])
    limits = dict(leaves["report_limits"])
    table = dict(leaves["review_outcome_by_verdict"])

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, Any]] = []
    report_hash: str | None = None
    check: dict[str, Any] = {
        "schema": CHECK_SCHEMA,
        "session_id": session_id,
        "valid": False,
        "report_hash": None,
        "brief_hash": {"reported": None, "current": current_brief_hash, "matches": False},
        "errors": errors,
        "items": [],
        "blocks": [],
        "reviews": {"addressed": [], "skipped": [], "unaddressed": []},
        "reviews_unaddressed": [],
        "requirements": [],
        "lexicon": [],
        "warnings": warnings,
        "summary": {},
    }

    def refused() -> _Evaluation:
        return _Evaluation(check, [], pinned, program, leaves, brief, state, revision, report_hash)

    if not isinstance(report, Mapping):
        errors.append(_reason("bad_schema", "the report must be a JSON object"))
        return refused()
    try:
        report_hash = payload_hash(dict(report))
    except (TypeError, ValueError) as exc:
        errors.append(_reason("bad_schema", f"the report is not canonical JSON: {exc}"))
        return refused()
    check["report_hash"] = report_hash
    if report.get("schema") != REPORT_SCHEMA:
        errors.append(
            _reason("bad_schema", f"schema must be {REPORT_SCHEMA!r}, got {report.get('schema')!r}")
        )
    if report.get("session_id") != session_id:
        errors.append(
            _reason(
                "session_mismatch", f"report is for session {report.get('session_id')!r}, not {session_id}"
            )
        )
    items_raw = _require_list(report, "items", errors)
    blocks_raw = _require_list(report, "blocks", errors)
    skipped_raw = _require_list(report, "reviews_skipped", errors)
    teaching_raw = _require_list(report, "teaching", errors)
    lexicon_raw = _require_list(report, "lexicon", errors)
    summary = report.get("summary")
    if summary is not None and not isinstance(summary, Mapping):
        errors.append(_reason("bad_schema", "summary must be an object"))
    if len(items_raw) > int(limits["max_items"]):
        errors.append(
            _reason("too_many_items", f"{len(items_raw)} items exceed the limit of {limits['max_items']}")
        )
    reported_brief_hash = report.get("brief_hash")
    check["brief_hash"] = {
        "reported": reported_brief_hash,
        "current": current_brief_hash,
        "matches": reported_brief_hash == current_brief_hash,
    }
    if errors:
        return refused()

    unknown_fields = sorted(str(key) for key in report if key not in _TOP_LEVEL_FIELDS)
    if unknown_fields:
        warnings.append({"code": "unknown_field", "message": f"ignored fields: {unknown_fields}"})
    if not reported_brief_hash:
        warnings.append({"code": "brief_hash_missing", "message": "the report names no brief_hash"})
    elif reported_brief_hash != current_brief_hash:
        warnings.append(
            {
                "code": "brief_changed",
                "message": "learner state moved since this brief was issued; items are checked against "
                "the pinned program and the live review assignments regardless",
            }
        )
    if not items_raw:
        warnings.append(
            {
                "code": "empty_report",
                "message": "no answered items: the session finishes with nothing scored and every due "
                "review closes INSUFFICIENT_EVIDENCE",
            }
        )
    stale = pending_attempts(store, session_id)
    if stale:
        warnings.append(
            {
                "code": "pending_attempts",
                "message": f"{len(stale)} unassessed step-protocol attempt(s) close without contribution",
            }
        )

    known = known_program_refs(program)
    lexicon_ids = {str(unit.get("id")) for unit in program.get("lexicon", []) if isinstance(unit, dict)}
    pending = {str(item["review_id"]): item for item in pending_assignments(store, session_id)}
    claimed: dict[str, str] = {}  # review_id -> item/block id that addressed it
    credited = _credited_item_spans(store)

    # -- blocks -----------------------------------------------------------
    block_rows: list[dict[str, Any]] = []
    blocks: dict[str, dict[str, Any]] = {}
    block_valid: dict[str, bool] = {}
    for index, raw in enumerate(blocks_raw):
        reasons: list[dict[str, str]] = []
        entry = dict(raw) if isinstance(raw, Mapping) else {}
        block_id = entry.get("block_id")
        if not isinstance(raw, Mapping) or not isinstance(block_id, str) or not block_id:
            reasons.append(_reason("block_unknown", f"blocks[{index}] needs a non-empty block_id"))
            block_id = f"#block:{index}"
        elif block_id in blocks:
            reasons.append(_reason("block_unknown", f"block_id {block_id!r} is declared twice"))
        if str(entry.get("target_ref") or "") not in known:
            reasons.append(
                _reason(
                    "unknown_target", f"block target {entry.get('target_ref')!r} is not in the pinned program"
                )
            )
        if entry.get("mode", "blocked") not in BLOCK_MODES:
            reasons.append(_reason("block_unknown", f"block mode must be one of {list(BLOCK_MODES)}"))
        if entry.get("dimension") is not None and entry.get("dimension") not in DIMENSIONS:
            reasons.append(_reason("bad_dimension", f"block dimension must be one of {list(DIMENSIONS)}"))
        blocks.setdefault(str(block_id), entry)
        block_valid[str(block_id)] = not reasons and block_valid.get(str(block_id), True)
        block_rows.append({"block_id": block_id, "index": index, "reasons": reasons})

    members_of: dict[str, list[dict[str, Any]]] = {block_id: [] for block_id in blocks}

    # -- items (structure first; spans/reviews in unit order below) -----------
    item_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    units: list[_Unit] = []
    block_unit: dict[str, _Unit] = {}
    for index, raw in enumerate(items_raw):
        reasons = []
        item = dict(raw) if isinstance(raw, Mapping) else {}
        item_id = item.get("item_id")
        if not isinstance(raw, Mapping) or not isinstance(item_id, str) or not item_id:
            reasons.append(_reason("bad_item", f"items[{index}] needs a non-empty string item_id"))
            item_id = f"#item:{index}"
        elif item_id in seen_ids:
            reasons.append(_reason("duplicate_item_id", f"item_id {item_id!r} is used twice"))
        seen_ids.add(str(item_id))
        target_ref = item.get("target_ref")
        if not isinstance(target_ref, str) or target_ref not in known:
            reasons.append(_reason("unknown_target", f"{target_ref!r} is not a target of the pinned program"))
        dimension = item.get("dimension")
        if dimension not in DIMENSIONS:
            reasons.append(_reason("bad_dimension", f"dimension must be one of {list(DIMENSIONS)}"))
        answer = item.get("raw_answer")
        if not isinstance(answer, str) or not answer.strip():
            reasons.append(
                _reason("empty_answer", "raw_answer is the learner's verbatim answer; it is required")
            )
            answer = ""
        elif len(answer) > int(limits["max_answer_chars"]):
            reasons.append(
                _reason("answer_too_long", f"raw_answer exceeds {limits['max_answer_chars']} characters")
            )
        if item.get("verdict") not in VERDICTS:
            reasons.append(_reason("bad_verdict", f"verdict must be one of {list(VERDICTS)}"))
        hints = item.get("hints", 0)
        if not _is_int(hints) or hints < 0:
            reasons.append(_reason("bad_hints", "hints must be a non-negative integer"))
        kind = item.get("kind")
        if kind not in ITEM_KINDS:
            warnings.append(
                {
                    "code": "unknown_kind",
                    "item_id": item_id,
                    "message": f"kind {kind!r} not in {list(ITEM_KINDS)}",
                }
            )
        if not isinstance(item.get("prompt"), str) or not str(item.get("prompt")).strip():
            warnings.append(
                {
                    "code": "missing_prompt",
                    "item_id": item_id,
                    "message": "store the prompt the learner answered",
                }
            )
        secondaries = item.get("secondary_targets") or []
        if not isinstance(secondaries, list):
            reasons.append(_reason("bad_item", "secondary_targets must be a list"))
            secondaries = []
        for secondary in secondaries:
            if not isinstance(secondary, Mapping) or str(secondary.get("target_ref") or "") not in known:
                reasons.append(
                    _reason("unknown_target", f"secondary target {secondary!r} is not in the program")
                )
            elif secondary.get("dimension") is not None and secondary.get("dimension") not in DIMENSIONS:
                reasons.append(
                    _reason("bad_dimension", f"secondary dimension of {secondary.get('target_ref')}")
                )
        errors_raw = item.get("errors") or []
        if not isinstance(errors_raw, list):
            reasons.append(_reason("bad_item", "errors must be a list"))
            errors_raw = []
        if len(errors_raw) > int(limits["max_errors_per_item"]):
            reasons.append(
                _reason("too_many_errors", f"more than {limits['max_errors_per_item']} errors on one item")
            )
        for error in errors_raw:
            form = error.get("learner_form") if isinstance(error, Mapping) else None
            if not isinstance(form, str) or derive_span(answer, form) is None:
                reasons.append(
                    _reason(
                        "learner_form_not_in_answer",
                        f"{form!r} must be quoted verbatim from this item's raw_answer",
                    )
                )
        review_id = item.get("review_id")
        if review_id is not None and not isinstance(review_id, str):
            reasons.append(_reason("review_mismatch", "review_id must be a string or null"))
            review_id = None
        block_id = item.get("block_id")
        row: dict[str, Any] = {
            "item_id": item_id,
            "index": index,
            "block_id": block_id,
            "reasons": reasons,
            "effects": None,
        }
        item_rows.append(row)
        if block_id is not None:
            if not isinstance(block_id, str) or block_id not in blocks:
                reasons.append(_reason("block_unknown", f"block_id {block_id!r} is not declared in blocks[]"))
                continue
            if not block_valid.get(block_id, False):
                reasons.append(_reason("block_unknown", f"block {block_id!r} is itself rejected"))
            if secondaries:
                warnings.append(
                    {
                        "code": "secondary_ignored_in_block",
                        "item_id": item_id,
                        "message": "a block item is credited to its own target only",
                    }
                )
            members_of[block_id].append({**item, "_row": row})
            if block_id not in block_unit:
                block_unit[block_id] = _Unit(kind="block", block=blocks[block_id])
                units.append(block_unit[block_id])
            continue
        units.append(_Unit(kind="item", item={**item, "_row": row}, dimension=str(dimension or "")))

    # -- units in report order: reviews, spans, effects ------------------------
    def claim_review(review_id: str | None, target_ref: Any, dimension: Any, owner: str) -> str | None:
        """The problem with addressing ``review_id`` from ``owner``, else None."""
        if review_id is None:
            return None
        assignment = pending.get(review_id)
        if assignment is None:
            return f"review {review_id!r} is not a pending review assignment of this session"
        if review_id in claimed:
            return f"review {review_id!r} is already addressed by {claimed[review_id]}"
        if assignment.get("target_ref") != target_ref or assignment.get("dimension") != dimension:
            return (
                f"review {review_id!r} is for {assignment.get('target_ref')}/{assignment.get('dimension')}, "
                f"not {target_ref}/{dimension}"
            )
        claimed[review_id] = owner
        return None

    duplicate_count = 0
    for unit in units:
        if unit.kind == "item":
            assert unit.item is not None
            item = unit.item
            row = item["_row"]
            problem = claim_review(
                item.get("review_id"), item.get("target_ref"), item.get("dimension"), row["item_id"]
            )
            if problem is not None:
                row["reasons"].append(_reason("review_mismatch", problem))
            unit.review_id = item.get("review_id") if problem is None else None
            if row["reasons"]:
                continue
            span = answer_span_hash(str(item["raw_answer"]))
            key = (span, str(item["target_ref"]), str(item["dimension"]))
            duplicate = key in credited
            credited.add(key)
            if duplicate:
                duplicate_count += 1
                warnings.append(
                    {
                        "code": "duplicate_span",
                        "item_id": row["item_id"],
                        "message": "this exact answer already earned credit for this target/dimension; "
                        "it is recorded without contribution",
                    }
                )
            verdict = str(item["verdict"])
            assessment = {
                "basis": TUTOR_VERDICT_BASIS,
                "verdict": verdict,
                "correct": verdict == "correct",
                "contributing": not duplicate,
            }
            targets, _ = item_targets(
                str(item["target_ref"]), str(item["dimension"]), item.get("secondary_targets") or []
            )
            row["effects"] = {
                "step_type": STEP_TYPE_BY_DIMENSION[str(item["dimension"])],
                "score_ppm": int(leaves["verdict_scale"][verdict]),
                "correct": verdict == "correct",
                "contributing": not duplicate,
                "duplicate_span": duplicate,
                "credit_targets": targets,
                "errors": len(item.get("errors") or []),
                "review_outcome": _review_effect(unit.review_id, assessment, table),
            }
            continue

        # a drill block
        assert unit.block is not None
        block = unit.block
        block_id = str(block["block_id"])
        members = members_of[block_id]
        unit.members = members
        target_ref = str(block.get("target_ref"))
        dimension = str(block.get("dimension") or members[0].get("dimension") or "")
        unit.dimension = dimension
        block_reasons = next(row["reasons"] for row in block_rows if row["block_id"] == block_id)
        member_reviews = {str(m["review_id"]) for m in members if m.get("review_id") is not None}
        review_id = block.get("review_id")
        if review_id is None and len(member_reviews) == 1:
            review_id = next(iter(member_reviews))
        if member_reviews - ({str(review_id)} if review_id is not None else set()):
            block_reasons.append(_reason("review_mismatch", "block items name a review the block does not"))
        else:
            problem = claim_review(
                str(review_id) if review_id is not None else None, target_ref, dimension, f"block {block_id}"
            )
            if problem is not None:
                block_reasons.append(_reason("review_mismatch", problem))
            else:
                unit.review_id = str(review_id) if review_id is not None else None
        for member in members:
            if member.get("dimension") != dimension:
                member["_row"]["reasons"].append(
                    _reason("bad_dimension", f"block {block_id} items share the dimension {dimension!r}")
                )
        if block_reasons or any(member["_row"]["reasons"] for member in members):
            continue
        primary = {"target_ref": target_ref, "dimension": dimension}
        answered = correct_count = duplicates = 0
        for member in members:
            span = answer_span_hash(str(member["raw_answer"]))
            pair = _item_pair(member.get("target_ref"), primary)
            key3 = (span, *pair) if pair is not None else None
            duplicate = key3 is not None and key3 in credited
            if duplicate:
                duplicates += 1
                duplicate_count += 1
                warnings.append(
                    {
                        "code": "duplicate_span",
                        "item_id": member["_row"]["item_id"],
                        "block_id": block_id,
                        "message": "this block answer already earned credit; it stays out of the accuracy",
                    }
                )
            else:
                if key3 is not None:
                    credited.add(key3)
                answered += 1
                if member.get("verdict") == "correct":
                    correct_count += 1
            member["_row"]["effects"] = {
                "block_id": block_id,
                "credited": not duplicate,
                "duplicate_span": duplicate,
                "objective_correct": (member.get("verdict") == "correct") if not duplicate else None,
                "errors": len(member.get("errors") or []),
            }
        contributing = answered > 0
        score = correct_count * _PPM // answered if answered else 0
        correct = contributing and score >= BLOCK_CORRECT_THRESHOLD_PPM
        verdict = "correct" if correct else "incorrect"
        next(row for row in block_rows if row["block_id"] == block_id)["effects"] = {
            "target_ref": target_ref,
            "dimension": dimension,
            "mode": block.get("mode", "blocked"),
            "items": len(members),
            "credited_items": answered,
            "duplicates": duplicates,
            "accuracy_ppm": score,
            "threshold_ppm": BLOCK_CORRECT_THRESHOLD_PPM,
            "verdict": verdict,
            "correct": correct,
            "score_ppm": _PPM if correct else 0,
            "contributing": contributing,
            "review_outcome": _review_effect(
                unit.review_id,
                {
                    "basis": TUTOR_VERDICT_BASIS,
                    "verdict": verdict,
                    "correct": correct,
                    "contributing": contributing,
                },
                table,
            ),
        }

    for row in block_rows:
        declared = str(row["block_id"])
        if declared in members_of and not members_of[declared] and not row["reasons"]:
            warnings.append(
                {"code": "empty_block", "block_id": declared, "message": "a block without items is ignored"}
            )

    # -- skipped / unaddressed reviews ---------------------------------------
    skipped: list[dict[str, Any]] = []
    skip_problems: list[dict[str, Any]] = []
    for index, raw in enumerate(skipped_raw):
        entry = dict(raw) if isinstance(raw, Mapping) else {}
        review_id = entry.get("review_id")
        reason = entry.get("reason")
        if not isinstance(review_id, str) or review_id not in pending:
            skip_problems.append(
                {
                    "index": index,
                    "review_id": review_id,
                    "reasons": [
                        _reason("review_mismatch", f"{review_id!r} is not a pending review of this session")
                    ],
                }
            )
            continue
        if not isinstance(reason, str) or not reason.strip():
            skip_problems.append(
                {
                    "index": index,
                    "review_id": review_id,
                    "reasons": [_reason("review_mismatch", "a skip needs a reason")],
                }
            )
            continue
        if review_id in claimed:
            warnings.append(
                {
                    "code": "review_skipped_and_addressed",
                    "review_id": review_id,
                    "message": f"addressed by {claimed[review_id]}; the skip entry is ignored",
                }
            )
            continue
        if any(item["review_id"] == review_id for item in skipped):
            continue
        if reason not in REVIEW_SKIP_REASONS:
            warnings.append(
                {
                    "code": "unknown_skip_reason",
                    "review_id": review_id,
                    "message": f"reason {reason!r} kept verbatim",
                }
            )
        skipped.append({"review_id": review_id, "reason": reason, "outcome": "INSUFFICIENT_EVIDENCE"})
    skipped_ids = {item["review_id"] for item in skipped}
    unaddressed = [
        {
            "review_id": review_id,
            "target_ref": assignment.get("target_ref"),
            "dimension": assignment.get("dimension"),
            "outcome": "INSUFFICIENT_EVIDENCE",
            "reason": "not_attempted",
        }
        for review_id, assignment in sorted(pending.items())
        if review_id not in claimed and review_id not in skipped_ids
    ]
    for entry in unaddressed:
        warnings.append(
            {
                "code": "review_unaddressed",
                "review_id": entry["review_id"],
                "message": "closes INSUFFICIENT_EVIDENCE(not_attempted); report it or skip it with a reason",
            }
        )
    addressed = []
    for row in [*item_rows, *block_rows]:
        effect = (row.get("effects") or {}).get("review_outcome")
        if effect:
            owner = {"block_id": row["block_id"]} if "item_id" not in row else {"item_id": row["item_id"]}
            addressed.append({**effect, **owner})

    # -- lexicon -------------------------------------------------------------
    lexicon_rows: list[dict[str, Any]] = []
    seen_surfaces: set[str] = set()
    if lexicon_raw and encounter_lookup is None:
        warnings.append(
            {"code": "lexicon_unchecked", "message": "no lexicon reader was wired; enrollment status unknown"}
        )
    for index, raw in enumerate(lexicon_raw):
        entry = dict(raw) if isinstance(raw, Mapping) else {}
        surface = entry.get("surface")
        linked = entry.get("linked_item_id")
        reasons = []
        if not isinstance(surface, str) or not surface.strip():
            reasons.append(_reason("empty_surface", f"lexicon[{index}] needs a non-empty surface"))
        if linked is not None and (not isinstance(linked, str) or linked not in lexicon_ids):
            reasons.append(
                _reason(
                    "unknown_target", f"linked_item_id {linked!r} is not a lexical item of the pinned program"
                )
            )
        status = "rejected"
        if not reasons:
            identity = f"id:{linked}" if linked else f"surface:{_surface_key(str(surface))}"
            if identity in seen_surfaces:
                status = "duplicate_in_report"
            elif encounter_lookup is None:
                status = "unchecked"
            else:
                found = encounter_lookup(store, surface=str(surface), linked_item_id=linked)
                status = "already_enrolled" if found is not None else "new"
            seen_surfaces.add(identity)
        lexicon_rows.append(
            {
                "index": index,
                "surface": surface,
                "linked_item_id": linked,
                "status": status,
                "reasons": reasons,
            }
        )

    for index, raw in enumerate(teaching_raw):
        ref = raw.get("target_ref") if isinstance(raw, Mapping) else None
        if ref is not None and ref not in known:
            warnings.append(
                {
                    "code": "teaching_unknown_target",
                    "index": index,
                    "message": f"{ref!r} is not in the program",
                }
            )

    # -- requirements (advisory) -----------------------------------------------
    requirement_rows: list[dict[str, Any]] = []
    for requirement in brief["requirements"]["items"]:
        requirement_id = requirement["requirement_id"]
        if requirement_id == "central_topic_items":
            central = requirement["target_ref"]
            count = 0
            for unit in units:
                if unit.kind == "item" and unit.item is not None and not unit.item["_row"]["reasons"]:
                    refs = {unit.item.get("target_ref")} | {
                        s.get("target_ref")
                        for s in unit.item.get("secondary_targets") or []
                        if isinstance(s, Mapping)
                    }
                    count += 1 if central in refs else 0
                elif unit.kind == "block" and unit.block is not None:
                    count += sum(
                        1
                        for member in unit.members
                        if not member["_row"]["reasons"]
                        and central in {member.get("target_ref"), unit.block.get("target_ref")}
                    )
            met = count >= int(requirement["min_items"])
            requirement_rows.append({**requirement, "observed_items": count, "met": met})
        elif requirement_id == "reviews_addressed":
            open_ids = [entry["review_id"] for entry in unaddressed]
            requirement_rows.append({**requirement, "unaddressed": open_ids, "met": not open_ids})
        else:
            requirement_rows.append({**requirement, "met": None})
    for requirement in requirement_rows:
        if requirement["met"] is False:
            warnings.append(
                {
                    "code": "requirement_unmet",
                    "requirement_id": requirement["requirement_id"],
                    "message": "advisory requirement not met; the report is still accepted",
                }
            )

    # -- verdict ---------------------------------------------------------------
    for row in [*item_rows, *block_rows]:
        row["status"] = "rejected" if row["reasons"] else "accepted"
        if row["reasons"]:
            row["effects"] = None
    rejected_items = [row for row in item_rows if row["status"] == "rejected"]
    rejected_blocks = [row for row in block_rows if row["status"] == "rejected"]
    rejected_lexicon = [row for row in lexicon_rows if row["status"] == "rejected"]
    check["items"] = item_rows
    check["blocks"] = block_rows
    check["reviews"] = {"addressed": addressed, "skipped": skipped, "unaddressed": unaddressed}
    check["reviews_unaddressed"] = [entry["review_id"] for entry in unaddressed]
    check["skip_problems"] = skip_problems
    check["requirements"] = requirement_rows
    check["lexicon"] = lexicon_rows
    check["valid"] = not (rejected_items or rejected_blocks or rejected_lexicon or skip_problems)
    accepted = [row for row in item_rows if row["status"] == "accepted"]
    check["summary"] = {
        "items_total": len(item_rows),
        "items_accepted": len(accepted),
        "items_rejected": len(rejected_items),
        "blocks": len(block_rows),
        "contributing_items": sum(
            1
            for row in accepted
            if (row["effects"] or {}).get("contributing", (row["effects"] or {}).get("credited", False))
        ),
        "duplicate_spans": duplicate_count,
        "reviews_addressed": len(addressed),
        "reviews_skipped": len(skipped),
        "reviews_unaddressed": len(unaddressed),
        "lexicon_new": sum(1 for row in lexicon_rows if row["status"] == "new"),
    }
    return _Evaluation(check, units, pinned, program, leaves, brief, state, revision, report_hash)


def _review_effect(
    review_id: str | None, assessment: dict[str, Any], table: Mapping[str, str]
) -> dict[str, Any] | None:
    if review_id is None:
        return None
    outcome, reason = _outcome_from_assessment(assessment, table)
    return {"review_id": review_id, "outcome": outcome, "reason": reason}


def _public_check(check: dict[str, Any]) -> dict[str, Any]:
    """The check result without the evaluator's private back-references."""
    cleaned: dict[str, Any] = payload_safe(check)
    return cleaned


def payload_safe(value: Any) -> Any:
    """A deep copy without keys starting with ``_`` (internal annotations)."""
    if isinstance(value, dict):
        return {key: payload_safe(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [payload_safe(item) for item in value]
    return value


def check_report(
    store: EventStore,
    registry: PolicyRegistry,
    session_id: str,
    report: Any,
    *,
    encounter_lookup: EncounterLookup | None = None,
    permanent_interleave: PermanentInterleave | None = None,
) -> dict[str, Any]:
    """Validate ``report`` for ``session_id`` WITHOUT writing anything.

    Returns the check document (``lesson_report_check@1``): ``valid``,
    ``report_hash``, ``brief_hash``, report-level ``errors``, per-item and
    per-block ``status``/``reasons``/``effects``, ``reviews`` (addressed /
    skipped / unaddressed with the outcome each would get),
    ``reviews_unaddressed``, advisory ``requirements``, ``lexicon`` entries
    (``new`` / ``already_enrolled`` / ...), ``warnings`` and a ``summary``.

    Raises :class:`SessionPrecondition` when the session does not exist, is
    not active, or pinned no evidence@2 (no verdict scale to apply).
    """
    evaluation = _evaluate(
        store,
        registry,
        session_id,
        report,
        encounter_lookup=encounter_lookup,
        permanent_interleave=permanent_interleave,
    )
    return _public_check(evaluation.check)


# -- commit -------------------------------------------------------------------


def _stable_step_id(session_id: str, namespace: str, local_id: str) -> str:
    """A deterministic step id for a reported item/block (no randomness)."""
    return "report-" + payload_hash({"session_id": session_id, namespace: local_id})[:32]


def _expected_seconds(registry: PolicyRegistry, pinned: dict[str, str], step_type: str) -> int:
    if CONTROL_KIND not in pinned:
        return 0
    table = (registry.resolve_pinned(CONTROL_KIND, pinned[CONTROL_KIND]).get("budget") or {}).get(
        "expected_seconds_by_step_type"
    ) or {}
    value = table.get(step_type)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _predictions(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
    program: dict[str, Any],
    clock: Clock,
    permanent_interleave: PermanentInterleave | None,
) -> dict[tuple[str, str], str]:
    """The review predictions at the report instant (control 4.10 calibration)."""
    if not {"scheduler", "scoring"} <= set(pinned) or not program:
        return {}
    from english_trainer.scheduler.engine import due_backlog

    backlog = due_backlog(
        store,
        registry.resolve_pinned("scheduler", pinned["scheduler"]),
        registry.resolve_pinned("scoring", pinned["scoring"]),
        program,
        clock.now(),
        registry=registry,
        permanent_interleave_targets=(
            permanent_interleave(program) if permanent_interleave is not None else None
        ),
    )
    return {(str(c["target_ref"]), str(c["dimension"])): str(c["retrievability"]) for c in backlog}


def commit_report(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    report: Any,
    *,
    provider: str,
    idempotency_key: str,
    encounter_builder: EncounterBuilder | None = None,
    encounter_lookup: EncounterLookup | None = None,
    permanent_interleave: PermanentInterleave | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Write the whole report and finish the session in ONE transaction.

    Raises :class:`ReportRejected` (writing nothing) when the check is not
    valid, :class:`IdempotencyConflict` when ``idempotency_key`` was used for
    a different report, and :class:`SessionPrecondition` when the session is
    not active / cannot take a report. A retry with the same key and report
    returns the cached result with ``cached: True``.
    """
    if not idempotency_key:
        raise SessionPrecondition("a lesson report commit needs an idempotency key")
    try:
        report_hash: str | None = payload_hash(dict(report)) if isinstance(report, Mapping) else None
    except (TypeError, ValueError):
        report_hash = None
    request_hash = payload_hash({"command": COMMAND, "session_id": session_id, "report_hash": report_hash})
    with UnitOfWork(store, clock) as probe:
        prior = probe.check_idempotency(idempotency_key, request_hash)
    if isinstance(prior, CachedResult):
        return {**dict(prior.value), "cached": True}

    evaluation = _evaluate(
        store,
        registry,
        session_id,
        report,
        encounter_lookup=encounter_lookup,
        permanent_interleave=permanent_interleave,
    )
    check = _public_check(evaluation.check)
    if not check["valid"] or check["errors"]:
        rejected = [row["item_id"] for row in check["items"] if row["status"] == "rejected"]
        raise ReportRejected(
            f"the report was refused and nothing was written: report errors "
            f"{[error['code'] for error in check['errors']]}, rejected items {rejected}",
            check,
        )
    assert isinstance(report, Mapping) and evaluation.report_hash is not None
    lexicon_entries = [dict(entry) for entry in report.get("lexicon") or []]
    if lexicon_entries and encounter_builder is None:
        raise SessionPrecondition("the report carries lexicon entries but no lexicon writer was wired")

    pinned = evaluation.pinned
    program = evaluation.program
    leaves = evaluation.leaves
    table = dict(leaves["review_outcome_by_verdict"])
    severity = str(leaves["tutor_errors"]["default_severity"])
    multi_credit = multi_credit_policy(registry, pinned)
    plan_id, plan_state, _ = get_plan(store, session_id)
    predictions = _predictions(store, registry, pinned, program, clock, permanent_interleave)
    skipped = {entry["review_id"]: entry["reason"] for entry in check["reviews"]["skipped"]}
    now_iso = clock.now().isoformat()

    def step_event(payload: dict[str, Any]) -> DomainEvent:
        return make_event(
            id=new_ulid(clock, random_source),
            type=EVENT_STEP_PRESENTED,
            occurred_at=clock.now(),
            actor=actor,
            provider=provider,
            correlation_id=session_id,
            payload=payload,
            pinned_versions=pinned,
        )

    def step_payload(
        step_id: str,
        step_type: str,
        targets: list[dict[str, Any]],
        review_id: str | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_id": step_id,
            "session_id": session_id,
            "session_plan_id": plan_id,
            "composition_revision": int(plan_state.get("composition_revision") or 1),
            "plan_version": int(plan_state.get("plan_version") or 1),
            "kind": "review" if review_id is not None else "report_item",
            "bucket": "review" if review_id is not None else "reported",
            "step_type": step_type,
            "candidate_id": None,
            "expected_seconds": _expected_seconds(registry, pinned, step_type),
            "targets": targets,
            "context_id": None,
            "presented_at": now_iso,
            "active_safety_version": plan_state.get("active_safety_version"),
            "source": REPORT_SOURCE,
            **extra,
        }
        if review_id is not None:
            payload["review_assignment_id"] = review_id
            primary = targets[0]
            prediction = predictions.get((str(primary["target_ref"]), str(primary["dimension"])))
            if prediction is not None:
                payload["predicted_retrievability"] = prediction
        return payload

    item_results: list[dict[str, Any]] = []
    block_results: list[dict[str, Any]] = []
    review_results: list[dict[str, Any]] = []
    lexicon_results: list[dict[str, Any]] = []
    cached_now: CachedResult | None = None
    with UnitOfWork(store, clock) as uow:
        cached_now = uow.check_idempotency(idempotency_key, request_hash)
        if cached_now is None:
            reported_payload = {
                "session_id": session_id,
                "schema": REPORT_SCHEMA,
                "report_hash": evaluation.report_hash,
                "brief_hash": report.get("brief_hash"),
                "brief_hash_current": check["brief_hash"]["current"],
                "brief_refs": brief_refs(evaluation.brief),
                "items": [dict(item) for item in report.get("items") or []],
                "blocks": [dict(block) for block in report.get("blocks") or []],
                "reviews_skipped": [dict(entry) for entry in report.get("reviews_skipped") or []],
                "teaching": [dict(entry) for entry in report.get("teaching") or []],
                "lexicon": lexicon_entries,
                "summary": dict(report["summary"]) if isinstance(report.get("summary"), Mapping) else None,
                "validation": {
                    "check_schema": CHECK_SCHEMA,
                    "summary": check["summary"],
                    "warnings": sorted({str(w["code"]) for w in check["warnings"]}),
                    "reviews_unaddressed": check["reviews_unaddressed"],
                    "requirements": [
                        {"requirement_id": r["requirement_id"], "met": r["met"]}
                        for r in check["requirements"]
                    ],
                },
            }
            (reported,) = uow.append(
                [
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=EVENT_LESSON_REPORTED,
                        occurred_at=clock.now(),
                        actor=actor,
                        provider=provider,
                        correlation_id=session_id,
                        payload=reported_payload,
                        pinned_versions=pinned,
                    )
                ]
            )
            closed_attempts = close_pending_attempts(
                store, uow, clock, random_source, session_id, reason="lesson_reported", actor="engine"
            )

            for unit in evaluation.units:
                if unit.kind == "item":
                    assert unit.item is not None
                    item = unit.item
                    item_id = str(item["item_id"])
                    dimension = str(item["dimension"])
                    step_type = STEP_TYPE_BY_DIMENSION[dimension]
                    step_id = _stable_step_id(session_id, "item_id", item_id)
                    secondary = [dict(s) for s in item.get("secondary_targets") or []]
                    targets, primary = item_targets(str(item["target_ref"]), dimension, secondary)
                    uow.append(
                        [
                            step_event(
                                step_payload(
                                    step_id,
                                    step_type,
                                    [{**targets[0], "role": "target"}, *targets[1:]],
                                    unit.review_id,
                                    {"item_id": item_id, "item_kind": item.get("kind")},
                                )
                            )
                        ]
                    )
                    raw_answer = str(item["raw_answer"])
                    duplicate = span_already_credited(store, answer_span_hash(raw_answer), primary)
                    attempt = build_attempt_payload(
                        attempt_id=new_ulid(clock, random_source),
                        session_id=session_id,
                        step_id=step_id,
                        item_id=item_id,
                        step_type=step_type,
                        kind=str(item.get("kind") or ""),
                        target_ref=str(item["target_ref"]),
                        dimension=dimension,
                        prompt=str(item.get("prompt") or ""),
                        raw_answer=raw_answer,
                        verdict=str(item["verdict"]),
                        policy=leaves,
                        recorded_at=clock.now().isoformat(),
                        contributing=not duplicate,
                        secondary_targets=secondary,
                        hints=int(item.get("hints") or 0),
                        review_id=unit.review_id,
                    )
                    uow.save_aggregate(ATTEMPT_AGGREGATE, attempt["attempt_id"], attempt, expected_revision=0)
                    batch = item_events(
                        clock,
                        random_source,
                        attempt=attempt,
                        multi_credit=multi_credit,
                        errors=[dict(error) for error in item.get("errors") or []],
                        severity=severity,
                        pinned=pinned,
                        provider=provider,
                        actor=actor,
                    )
                    uow.append([*batch, *automaticity_updates(store, clock, registry, batch)])
                    item_results.append(
                        {
                            "item_id": item_id,
                            "step_id": step_id,
                            "attempt_id": attempt["attempt_id"],
                            "score_ppm": attempt["assessment"]["score_ppm"],
                            "contributing": not duplicate,
                        }
                    )
                else:
                    assert unit.block is not None
                    block = unit.block
                    block_id = str(block["block_id"])
                    target_ref = str(block["target_ref"])
                    step_id = _stable_step_id(session_id, "block_id", block_id)
                    contrasts = sorted(
                        {str(m["target_ref"]) for m in unit.members if m.get("target_ref") != target_ref}
                    )
                    targets = [
                        {"target_ref": target_ref, "dimension": unit.dimension, "role": "target"},
                        *(
                            {"target_ref": ref, "dimension": unit.dimension, "role": "contrast"}
                            for ref in contrasts
                        ),
                    ]
                    uow.append(
                        [
                            step_event(
                                step_payload(
                                    step_id,
                                    _DRILL_BLOCK,
                                    targets,
                                    unit.review_id,
                                    {
                                        "block_id": block_id,
                                        "item_ids": [str(m["item_id"]) for m in unit.members],
                                        "drill_mode": block.get("mode", "blocked"),
                                    },
                                )
                            )
                        ]
                    )
                    attempt = build_block_attempt_payload(
                        store,
                        attempt_id=new_ulid(clock, random_source),
                        session_id=session_id,
                        step_id=step_id,
                        block_id=block_id,
                        step_type=_DRILL_BLOCK,
                        target_ref=target_ref,
                        dimension=unit.dimension,
                        items=[
                            {
                                "item_id": m["item_id"],
                                "prompt": m.get("prompt"),
                                "raw_answer": m["raw_answer"],
                                "verdict": m["verdict"],
                                "target_ref": m.get("target_ref"),
                            }
                            for m in unit.members
                        ],
                        policy=leaves,
                        recorded_at=clock.now().isoformat(),
                        mode=str(block.get("mode", "blocked")),
                        review_id=unit.review_id,
                    )
                    uow.save_aggregate(ATTEMPT_AGGREGATE, attempt["attempt_id"], attempt, expected_revision=0)
                    errors = [
                        {
                            **dict(error),
                            "item_id": m["item_id"],
                            "raw_answer": m["raw_answer"],
                            "target_ref": m.get("target_ref") or target_ref,
                        }
                        for m in unit.members
                        for error in m.get("errors") or []
                    ]
                    batch = item_events(
                        clock,
                        random_source,
                        attempt=attempt,
                        multi_credit=multi_credit,
                        errors=errors,
                        severity=severity,
                        pinned=pinned,
                        provider=provider,
                        actor=actor,
                    )
                    uow.append([*batch, *automaticity_updates(store, clock, registry, batch)])
                    block_results.append(
                        {
                            "block_id": block_id,
                            "step_id": step_id,
                            "attempt_id": attempt["attempt_id"],
                            "verdict": attempt["assessment"]["verdict"],
                            "accuracy_ppm": attempt["assessment"]["block"]["score_ppm"],
                            "contributing": attempt["assessment"]["contributing"],
                        }
                    )
                if unit.review_id is not None:
                    review_results.append(
                        closure_from_verdict(
                            store,
                            uow,
                            clock,
                            random_source,
                            session_id,
                            unit.review_id,
                            attempt=attempt,
                            outcome_by_verdict=table,
                            pinned=pinned,
                            provider=provider,
                            actor=actor,
                        )
                    )

            for review_id, reason in skipped.items():
                review_results.append(
                    close_insufficient(
                        store,
                        uow,
                        clock,
                        random_source,
                        session_id,
                        review_id,
                        reason=reason,
                        pinned=pinned,
                        provider=provider,
                    )
                )
            for assignment in pending_assignments(store, session_id):
                review_results.append(
                    close_insufficient(
                        store,
                        uow,
                        clock,
                        random_source,
                        session_id,
                        str(assignment["review_id"]),
                        reason="not_attempted",
                        pinned=pinned,
                        provider=provider,
                    )
                )

            assert encounter_builder is not None or not lexicon_entries
            for entry in lexicon_entries:
                assert encounter_builder is not None
                events = encounter_builder(
                    store,
                    clock,
                    random_source,
                    session_id=session_id,
                    surface=str(entry["surface"]),
                    provider=provider,
                    note_ru=entry.get("note_ru"),
                    linked_item_id=entry.get("linked_item_id"),
                    program=program,
                    pinned_versions=pinned,
                    source_event_id=reported.id,
                    actor=actor,
                )
                stored = uow.append(events) if events else []
                lexicon_results.append(
                    {
                        "surface": entry["surface"],
                        "linked_item_id": entry.get("linked_item_id"),
                        "status": "enrolled" if stored else "already_enrolled",
                        "entry_id": stored[0].payload.get("entry_id") if stored else None,
                    }
                )

            state, revision = uow.get_aggregate("session", session_id) or (
                evaluation.state,
                evaluation.revision,
            )
            finished, new_revision = close_reported_session(
                uow,
                clock,
                random_source,
                session_id,
                state,
                revision,
                report_hash=evaluation.report_hash,
                actor=actor,
            )
            result: dict[str, Any] = {
                "session_id": session_id,
                "status": "FINISHED",
                "session_revision": new_revision,
                "report_hash": evaluation.report_hash,
                "brief_hash": check["brief_hash"],
                "reported_event_id": reported.id,
                "finished_event_id": finished.id,
                "items": item_results,
                "blocks": block_results,
                "reviews": [
                    {"review_id": r["review_id"], "outcome": r["outcome"], "reason": r["reason"]}
                    for r in review_results
                ],
                "lexicon": lexicon_results,
                "closed_attempts": closed_attempts,
                "warnings": check["warnings"],
                "summary": check["summary"],
            }
            uow.record_result(idempotency_key, request_hash, result)
    if cached_now is not None:
        return {**dict(cached_now.value), "cached": True}
    return {**result, "cached": False}


__all__ = [
    "CHECK_SCHEMA",
    "EncounterBuilder",
    "EncounterLookup",
    "ReportRejected",
    "check_report",
    "commit_report",
]
