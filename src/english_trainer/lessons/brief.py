"""The lesson brief (``lesson_brief@1``) -- what the engine hands the tutor at
the start of a lesson [PD-2026-09-23].

The brief/report protocol replaces step-by-step delivery: the engine
PROPOSES (lesson, central topic, due reviews, an advisory plan, requirements)
and RECORDS (one ``lesson_report@1`` at the end, :mod:`lessons.report`); the
tutor runs the lesson in between without calling the engine. The brief is
therefore everything the tutor needs in one document:

- ``lesson`` -- profile, title, reason, agenda, language envelope, duration;
- ``central_topic`` -- the target plus the facts of the PINNED program
  (can-do, examples, typical errors, authored explanation points, the frames
  with ``frame_of``/``carries``, and the reconstruction text a drill rebuilds);
- ``reviews_due`` -- the session's review assignments (review id, target,
  dimension, urgency, a meaning hint) the report can address by ``review_id``;
- ``plan`` -- the composed plan as ADVISORY steps (drill fields and the
  authored material of the automaticity forms included);
- ``learner`` -- levels, known language, personal lexicon, recent errors
  folded from ``evidence.error_observed``, re-entry, the last summary and the
  preferences;
- ``requirements`` -- lessons@2's advisory requirements (warnings only);
- ``report_contract`` -- the report schema, the evidence@2 verdict scale and
  limits, the vocabularies, and ``brief_hash``.

Determinism. The brief is a pure function of the event log, the operational
aggregates and the pinned policies. Every clock-dependent part (the due
backlog, the re-entry gap) is evaluated at the session's own ``started_at``,
never at "now", so ``session resume`` rebuilds a byte-identical brief -- and
the same ``brief_hash`` -- as long as no learner fact landed in between.
``brief_hash`` is the payload hash of the brief without that one field
(:func:`brief_hash_of`).

This module also owns the read-only learner folds the legacy
``resume.build_briefing`` shares (moved here so the new flow does not depend
on the step-delivery modules); ``resume`` imports them from here.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any

from english_trainer.evidence.attempts import EVENT_ATTEMPT_RECORDED
from english_trainer.evidence.observed import EVENT_ERROR_OBSERVED
from english_trainer.evidence.policy import EVIDENCE_KIND, VERDICTS, EvidencePolicyInvalid, verdict_policy
from english_trainer.evidence.reviews import REVIEW_AGGREGATE
from english_trainer.kernel.aggregates import list_aggregates
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.forms import (
    AUTOMATICITY_STEP_TYPES,
    DEFAULT_FRAMES_MAX_PRIMARY,
    DEFAULT_TEXT_WINDOW,
    DRILL_BLOCK,
    RECONSTRUCTION,
    choose_reconstruction_text,
    directive_view,
    frames_for_target,
)
from english_trainer.lessons.sessions import (
    EVENT_FINISHED,
    PermanentInterleave,
    SessionPrecondition,
    get_plan,
    get_session,
)
from english_trainer.scheduler.engine import due_backlog
from english_trainer.scoring.aggregates import (
    learning_score,
    measured_working_level,
    placement_levels,
    placement_writing_level,
    provisional_working_estimate,
    self_reported_levels,
    working_levels,
    xp_ledger,
)
from english_trainer.scoring.engine import (
    ACTIVE,
    AT_RISK,
    EVIDENCE_ADDED_EVENT,
    MASTERED,
    REVIEW_OUTCOME_EVENT,
    TargetState,
    fold_scores,
)
from english_trainer.scoring.policy import DIMENSIONS

BRIEF_SCHEMA = "lesson_brief@1"
REPORT_SCHEMA = "lesson_report@1"
# Written by ``lessons.report.commit_report``; defined here because the brief
# folds it (the last lesson summary, the recently rebuilt reconstruction texts).
EVENT_LESSON_REPORTED = "lesson.reported"

# The report vocabularies (lesson_report@1). ``kind`` is descriptive (what the
# tutor did); the scored dimension travels separately.
ITEM_KINDS: tuple[str, ...] = ("recall", "recognition", "production", "review", "drill_item", "conversation")
BLOCK_MODES: tuple[str, ...] = ("blocked", "interleaved")
REVIEW_SKIP_REASONS: tuple[str, ...] = ("no_time", "learner_declined")
# Stable rejection codes of one report item (or block / skip / lexicon entry).
REJECTION_CODES: tuple[str, ...] = (
    "unknown_target",
    "bad_dimension",
    "empty_answer",
    "answer_too_long",
    "bad_verdict",
    "bad_hints",
    "review_mismatch",
    "learner_form_not_in_answer",
    "too_many_errors",
    "block_unknown",
    "duplicate_item_id",
    "bad_item",
    "empty_surface",
)
# Report-level refusals (the whole document is not a lesson_report@1 for this
# session); items are then not evaluated one by one.
REPORT_ERROR_CODES: tuple[str, ...] = ("bad_schema", "session_mismatch", "too_many_items")

# The scored dimension decides the step type the report item is recorded as:
# the same (step_type, dimension) pairing control composes, so saturation's
# transfer staleness and the automaticity axis read reported items unchanged.
STEP_TYPE_BY_DIMENSION: dict[str, str] = {
    "recognition": "recognition_check",
    "controlled_production": "controlled_production",
    "spontaneous_production": "spontaneous_production",
    "transfer": "transfer_task",
}

# Topics the learner has activated: ACTIVE state or beyond, plus AT_RISK -- a
# formerly-steady topic now decaying -- so the tutor sees the whole activated
# repertoire and which parts of it are slipping, not a silently dropped one.
_ACTIVE_PLUS = (ACTIVE, MASTERED, AT_RISK)

# Lexicon ``type``s that are multi-word chunks rather than single words. Mirrors
# ``curriculum.validate.MULTIWORD_TYPES``; duplicated here on purpose -- the
# lessons layer must not import curriculum (tests/architecture allowlist).
_MULTIWORD_TYPES = frozenset({"chunk", "idiom", "phrasal-verb", "informal_chunk"})

# Events that count as learner activity when measuring the re-entry gap.
_ACTIVITY_EVENTS = (EVENT_ATTEMPT_RECORDED, EVIDENCE_ADDED_EVENT, REVIEW_OUTCOME_EVENT)

# How many recent items each learner bucket carries.
RECENT_LIMIT = 10

# Consumed from the learner module via the event log (events are the module
# boundary; lessons must not import learner -- tests/architecture allowlist).
LEARNER_LEXICON_ENTRY_ADDED = "learner.lexicon_entry_added"
LEARNER_PREFERENCES_UPDATED = "learner.preferences_updated"

# Mirrors learner.preferences.DEFAULT_PREFERENCES (learner 4a) -- duplicated on
# purpose, exactly like the lexicon constant above; lessons must not import
# learner.
PREFERENCES_DEFAULTS: dict[str, Any] = {
    "round_size": 6,
    "explanation_language": "ru",
    "preferred_drill_forms": [],
    "timed_limit_seconds": 240,
    "feedback_mode": "stage_dependent",
}

# lessons@2's advisory requirements, used when the session pinned an older
# lessons policy (the requirements are warnings either way).
_DEFAULT_REQUIREMENTS: dict[str, Any] = {
    "central_topic_min_items": 1,
    "reviews_must_be_addressed": True,
    "severity": "warning",
}

# Optional authored topic fields the tutor explains from (curriculum 2b).
_TOPIC_FACT_FIELDS: tuple[str, ...] = (
    "core_points",
    "contrasts",
    "error_patterns",
    "scope_limits",
    "memory_insights",
)


# -- learner folds (shared with the legacy resume briefing) -------------------


def active_topics(scores: dict[str, TargetState], program: dict[str, Any]) -> list[dict[str, Any]]:
    """ACTIVE+ topics (incl. AT_RISK) with their state, in curriculum order."""
    out: list[dict[str, Any]] = []
    for topic in program.get("topics", []):
        topic_id = str(topic.get("id"))
        state = scores.get(topic_id)
        if state is None or state.knowledge_state not in _ACTIVE_PLUS:
            continue
        out.append(
            {
                "target_ref": topic_id,
                "knowledge_state": state.knowledge_state,
                "cefr": topic.get("cefr"),
                "evidence_count": state.evidence_count,
            }
        )
    return out


def recent_lexicon(
    store: EventStore, program: dict[str, Any], scores: dict[str, TargetState]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Most-recently practised vocabulary and chunks, split by lexicon ``type``.

    A pure fold over ``EVIDENCE_ADDED``: a lexical unit becomes "recent" once an
    attempt scores against it. Both buckets stay honestly empty until such
    evidence exists -- an empty list, never an invented item.
    """
    units = {str(unit.get("id")): unit for unit in program.get("lexicon", [])}
    last_seen: dict[str, int] = {}
    for index, event in enumerate(store.read()):
        if event.type != EVIDENCE_ADDED_EVENT:
            continue
        ref = str((event.payload.get("primary_target") or {}).get("target_ref") or "")
        if ref in units:
            last_seen[ref] = index
    vocabulary: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for ref in sorted(last_seen, key=lambda r: last_seen[r], reverse=True):
        unit = units[ref]
        state = scores.get(ref)
        entry = {
            "target_ref": ref,
            "title": unit.get("title"),
            "knowledge_state": state.knowledge_state if state is not None else "NEW",
            "evidence_count": state.evidence_count if state is not None else 0,
        }
        if str(unit.get("type", "word")) in _MULTIWORD_TYPES:
            chunks.append(entry)
        else:
            vocabulary.append(entry)
    return vocabulary[:RECENT_LIMIT], chunks[:RECENT_LIMIT]


def recent_encounters(store: EventStore, limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    """Recently added personal-lexicon entries (learner 4), newest first.

    A pure fold over the event log (lessons must not import learner),
    de-duplicated by logical identity. Computed from STATE and never declares
    an entry learned -- a translation request is enrollment, not evidence.
    """
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for event in store.read():
        if event.type != LEARNER_LEXICON_ENTRY_ADDED:
            continue
        key = str(event.payload.get("identity_key"))
        if key in seen:
            continue
        seen.add(key)
        payload = event.payload
        entries.append(
            {
                "entry_id": payload.get("entry_id"),
                "surface": payload.get("surface"),
                "note_ru": payload.get("note_ru"),
                "linked_item_id": payload.get("linked_item_id"),
                "added_at": payload.get("added_at"),
            }
        )
    entries.sort(key=lambda entry: (str(entry["added_at"]), str(entry["entry_id"])), reverse=True)
    return entries[:limit]


def current_preferences(store: EventStore) -> dict[str, Any]:
    """The learner's current ``LearnerPreferences`` snapshot (learner 4a).

    Every ``LEARNER_PREFERENCES_UPDATED`` event carries the FULL resulting
    state, so the newest one wins. The documented defaults at
    ``preferences_version`` 0 before the first ``preferences set``.
    """
    latest: dict[str, Any] | None = None
    for event in store.read():  # canonical sequence order
        if event.type != LEARNER_PREFERENCES_UPDATED:
            continue
        latest = event.payload
    if latest is None:
        return {
            **PREFERENCES_DEFAULTS,
            "preferred_drill_forms": [],
            "preferences_version": 0,
            "updated_at": None,
        }
    return {
        "round_size": latest.get("round_size"),
        "explanation_language": latest.get("explanation_language"),
        "preferred_drill_forms": list(latest.get("preferred_drill_forms") or []),
        "timed_limit_seconds": latest.get("timed_limit_seconds"),
        "feedback_mode": latest.get("feedback_mode"),
        "preferences_version": latest.get("preferences_version"),
        "updated_at": latest.get("updated_at"),
    }


def _last_activity_at(store: EventStore, *, until: datetime | None = None) -> datetime | None:
    """The most recent learner-activity instant (at or before ``until``)."""
    latest: datetime | None = None
    for event in store.read():
        if event.type not in _ACTIVITY_EVENTS:
            continue
        if until is not None and event.occurred_at > until:
            continue
        if latest is None or event.occurred_at > latest:
            latest = event.occurred_at
    return latest


def re_entry(
    store: EventStore, now: datetime, at_risk_targets: list[str], backlog: list[dict[str, Any]]
) -> dict[str, Any]:
    """The break + dropped-Retrievability picture (continuation "re-entry").

    ``now`` is the injected instant; activity after it is ignored, so the view
    is a function of the instant, never of wall-clock. ``lowest_retrievability``
    is ``None`` when nothing is due -- honest no-data, never a fabricated ``0``.
    """
    last_activity = _last_activity_at(store, until=now)
    gap_days = (now - last_activity).days if last_activity is not None else None
    return {
        "last_activity_at": last_activity.isoformat() if last_activity is not None else None,
        "gap_days": gap_days,
        "at_risk_targets": list(at_risk_targets),
        "due_review_count": len(backlog),
        # ``due_backlog`` is sorted by Retrievability ascending, so the head is
        # the most decayed due review.
        "lowest_retrievability": backlog[0]["retrievability"] if backlog else None,
    }


def last_session_summary(store: EventStore, *, exclude_session: str | None = None) -> dict[str, Any] | None:
    """Computed itog of the last FINISHED session -- state only, never notes.

    Honest ``None`` until a session has finished. A pure fold over the
    session's own lifecycle/evidence events; when that session closed by a
    lesson report, the tutor's own summary (``summary.text``/``next_focus``)
    rides along as ``report_summary`` -- it is the report's content, labelled
    as such, not a computed fact.
    """
    events = list(store.read())
    finished = [
        event for event in events if event.type == EVENT_FINISHED and event.correlation_id != exclude_session
    ]
    if not finished:
        return None
    last = finished[-1]
    session_id = last.correlation_id
    attempts = correct = evidence = 0
    outcomes: dict[str, int] = {}
    targets: set[str] = set()
    report_summary: dict[str, Any] | None = None
    for event in events:
        if event.correlation_id != session_id:
            continue
        if event.type == EVENT_ATTEMPT_RECORDED:
            attempts += 1
            if (event.payload.get("assessment") or {}).get("correct"):
                correct += 1
        elif event.type == EVIDENCE_ADDED_EVENT:
            evidence += 1
            ref = str((event.payload.get("primary_target") or {}).get("target_ref") or "")
            if ref:
                targets.add(ref)
        elif event.type == REVIEW_OUTCOME_EVENT:
            outcome = str(event.payload.get("outcome") or "")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        elif event.type == EVENT_LESSON_REPORTED:
            summary = event.payload.get("summary")
            report_summary = dict(summary) if isinstance(summary, dict) else None
    result: dict[str, Any] = {
        "session_id": session_id,
        "finished_at": last.occurred_at.isoformat(),
        "attempts": attempts,
        "correct_attempts": correct,
        "evidence_count": evidence,
        "review_outcomes": dict(sorted(outcomes.items())),
        "targets_practiced": sorted(targets),
    }
    if report_summary is not None:
        result["report_summary"] = report_summary
    return result


def _form_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def recent_errors(store: EventStore, limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    """The learner's recent errors, folded from ``evidence.error_observed``.

    Grouped by ``(target_ref, learner_form)`` (case/space-insensitive; a
    rubric-only observation without a quoted form groups by its finding code),
    each group carrying its occurrence count and its latest correction/cause;
    newest group first. Empty until an error was observed -- never invented.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    order: dict[tuple[str, str], int] = {}
    for index, event in enumerate(store.read()):
        if event.type != EVENT_ERROR_OBSERVED:
            continue
        payload = event.payload
        target_ref = str(payload.get("target_ref") or "")
        form = payload.get("learner_form")
        label = _form_key(str(form)) if isinstance(form, str) and form else f"#{payload.get('finding_code')}"
        key = (target_ref, label)
        previous = groups.get(key)
        groups[key] = {
            "target_ref": payload.get("target_ref"),
            "dimension": payload.get("dimension"),
            "learner_form": form if isinstance(form, str) else None,
            "correction": payload.get("correction"),
            "cause": payload.get("cause"),
            "topic_error_ref": payload.get("topic_error_ref"),
            "finding_code": payload.get("finding_code"),
            "severity": payload.get("severity"),
            "reported_by": payload.get("reported_by"),
            "occurrences": (int(previous["occurrences"]) if previous else 0) + 1,
            "last_session_id": payload.get("session_id") or event.correlation_id,
            "last_observed_at": payload.get("observed_at") or event.occurred_at.isoformat(),
        }
        order[key] = index
    ranked = sorted(groups, key=lambda key: order[key], reverse=True)
    return [groups[key] for key in ranked[:limit]]


def recent_reconstruction_text_ids(store: EventStore, window: int = DEFAULT_TEXT_WINDOW) -> list[str]:
    """Text ids of the last ``window`` reconstructions, newest last.

    Both producers count: a rendered reconstruction snapshot (step protocol)
    and the text a reported lesson's brief carried (``lesson.reported``).
    """
    seen: list[str] = []
    for event in store.read():
        text_id: Any = None
        if event.type == "exercise.rendered" and str(event.payload.get("form") or "") == RECONSTRUCTION:
            text_id = event.payload.get("text_id")
        elif event.type == EVENT_LESSON_REPORTED:
            text_id = (event.payload.get("brief_refs") or {}).get("reconstruction_text_id")
        if text_id is not None:
            seen.append(str(text_id))
    return seen[-window:]


# -- program facts ------------------------------------------------------------


def program_target(program: dict[str, Any], target_ref: str) -> dict[str, Any] | None:
    """A topic or lexical unit of the pinned program by id, or ``None``."""
    for item in [*program.get("topics", []), *program.get("lexicon", [])]:
        if isinstance(item, dict) and str(item.get("id")) == target_ref:
            return item
    return None


def known_program_refs(program: dict[str, Any]) -> frozenset[str]:
    """Every addressable target of the pinned program: topics and lexicon ids."""
    return frozenset(
        str(item.get("id"))
        for item in [*program.get("topics", []), *program.get("lexicon", [])]
        if isinstance(item, dict) and item.get("id") is not None
    )


def _generation_policy(registry: PolicyRegistry, pinned: dict[str, str]) -> dict[str, Any] | None:
    if "generation" not in pinned:
        return None
    return registry.resolve_pinned("generation", pinned["generation"])


def _int_leaf(policy: dict[str, Any] | None, section: str, key: str, fallback: int) -> int:
    value = ((policy or {}).get(section) or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback


def _central_topic(
    program: dict[str, Any],
    arc: dict[str, Any],
    generation: dict[str, Any] | None,
    *,
    with_text: bool,
    recent_text_ids: list[str],
) -> dict[str, Any] | None:
    central = arc.get("central_topic")
    if not isinstance(central, dict) or not central.get("target_ref"):
        return None
    target_ref = str(central["target_ref"])
    item = program_target(program, target_ref) or {}
    is_topic = any(
        isinstance(topic, dict) and str(topic.get("id")) == target_ref for topic in program.get("topics", [])
    )
    facts: dict[str, Any] = {
        "target_ref": target_ref,
        "title": central.get("title"),
        "kind": "topic" if is_topic else "lexical_item",
        "cefr": item.get("cefr"),
        "can_do": central.get("can_do", item.get("can_do")),
        "newness": central.get("newness"),
        "dimensions": list(item.get("dimensions") or []),
        "explanation_language": item.get("explanation_language"),
        "examples": list(item.get("examples") or []),
        "typical_errors": list(item.get("typical_errors") or []),
    }
    for field in _TOPIC_FACT_FIELDS:
        if item.get(field):
            facts[field] = item[field]
    if not is_topic:
        for field in ("type", "meaning_ru", "register", "slot_hint_ru", "contrast", "trap"):
            if item.get(field) is not None:
                facts[field] = item[field]
    frames: list[dict[str, Any]] = []
    key_lexicon: list[dict[str, Any]] = []
    if is_topic:
        limit = _int_leaf(generation, DRILL_BLOCK, "frames_max_primary", DEFAULT_FRAMES_MAX_PRIMARY)
        frames = [
            {**frame, "frame_of": target_ref}
            for frame in frames_for_target(program, target_ref, role="target", limit=limit)
        ]
        frame_refs = {str(frame["frame_ref"]) for frame in frames}
        for ref in item.get("lexicon") or []:
            unit = program_target(program, str(ref))
            if unit is None or str(ref) in frame_refs or unit.get("frame_of"):
                continue
            key_lexicon.append(
                {
                    "target_ref": str(ref),
                    "type": unit.get("type"),
                    "title": unit.get("title"),
                    "meaning_ru": unit.get("meaning_ru"),
                }
            )
    facts["frames"] = frames
    facts["key_lexicon"] = key_lexicon
    text: dict[str, Any] | None = None
    if with_text and is_topic:
        chosen = choose_reconstruction_text(program, target_ref, recent_text_ids=recent_text_ids)
        if chosen is not None:
            text = {
                field: chosen.get(field)
                for field in (
                    "id",
                    "title",
                    "cefr",
                    "carries",
                    "context",
                    "text",
                    "keywords",
                    "target_spans",
                    "summary_ru",
                )
            }
    facts["reconstruction_text"] = text
    return facts


def _review_hint(program: dict[str, Any], target_ref: str) -> dict[str, Any]:
    item = program_target(program, target_ref) or {}
    return {
        "title": item.get("title"),
        "can_do": item.get("can_do"),
        # A RU meaning cue for a lexical target (review is recall by meaning,
        # RU -> EN); topics carry none, so the tutor cues by can-do instead.
        "meaning_ru": item.get("meaning_ru"),
        "examples": list(item.get("examples") or [])[:2],
    }


def session_assignments(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """Every review assignment of the session (any status), by review id."""
    return [
        dict(state)
        for _, state, _ in list_aggregates(store._conn, REVIEW_AGGREGATE)
        if state.get("session_id") == session_id
    ]


def _plan_view(
    plan_state: dict[str, Any],
    program: dict[str, Any],
    generation: dict[str, Any] | None,
    recent_text_ids: list[str],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in sorted(plan_state.get("steps", []), key=lambda s: int(s.get("order_index", 0))):
        view: dict[str, Any] = {
            "step_id": step.get("step_id"),
            "order_index": step.get("order_index"),
            "kind": step.get("kind"),
            "bucket": step.get("bucket"),
            "step_type": step.get("step_type"),
            "target_ref": step.get("target_ref"),
            "dimension": step.get("dimension"),
            "expected_seconds": step.get("expected_seconds"),
            "arc_phase": step.get("arc_phase"),
            "primary_role": step.get("primary_role"),
            "review_assignment_id": step.get("review_assignment_id"),
            "targets": [dict(item) for item in step.get("targets") or []],
            "topic_hint": step.get("topic_hint"),
        }
        for field in ("drill_mode", "rounds", "round_size", "declared_limit_seconds", "text_ref"):
            if step.get(field) is not None:
                view[field] = step[field]
        if str(step.get("step_type") or "") in AUTOMATICITY_STEP_TYPES and program:
            # The authored material the tutor builds the form from: frames of
            # the drilled and contrast targets, or the reconstruction text.
            view["material"] = directive_view(step, program, generation, recent_text_ids=recent_text_ids)
        steps.append(view)
    budget = plan_state.get("budget") or {}
    return {
        "advisory": True,
        "total_seconds": plan_state.get("total_seconds"),
        "mode": plan_state.get("mode"),
        "planned_seconds_by_bucket": dict(budget.get("planned") or {}),
        "waivers": list(plan_state.get("waivers") or []),
        "steps": steps,
    }


def _learner_view(
    store: EventStore,
    registry: PolicyRegistry,
    pinned: dict[str, str],
    program: dict[str, Any],
    as_of: datetime,
    permanent_interleave: PermanentInterleave | None,
) -> dict[str, Any]:
    scoring_version = pinned.get("scoring")
    measured: str | None = None
    score: str | None = None
    levels: dict[str, Any] = {}
    provisional: dict[str, Any] = {"level": None, "provisional": False, "skills": {}}
    xp = {"total": 0, "practice_days": 0, "streak": 0}
    topics: list[dict[str, Any]] = []
    vocabulary: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    at_risk: list[str] = []
    backlog: list[dict[str, Any]] = []
    if scoring_version and program:
        scoring_policy = registry.resolve_pinned("scoring", scoring_version)
        scores = fold_scores(store, scoring_policy)
        levels = working_levels(
            scores,
            program,
            scoring_policy,
            placement=placement_levels(store, program, scoring_policy),
            placement_writing=placement_writing_level(store, scoring_policy),
        )
        measured = measured_working_level(levels)
        provisional = provisional_working_estimate(levels, self_reported=self_reported_levels(store))
        score = learning_score(scores, program, scoring_policy, measured)
        ledger = xp_ledger(store, scoring_policy)
        xp = {"total": ledger["total"], "practice_days": ledger["practice_days"], "streak": ledger["streak"]}
        topics = active_topics(scores, program)
        vocabulary, chunks = recent_lexicon(store, program, scores)
        at_risk = sorted(ref for ref, state in scores.items() if state.knowledge_state == AT_RISK)
        if pinned.get("scheduler"):
            backlog = due_backlog(
                store,
                registry.resolve_pinned("scheduler", pinned["scheduler"]),
                scoring_policy,
                program,
                as_of,
                registry=registry,
                permanent_interleave_targets=(
                    permanent_interleave(program) if permanent_interleave is not None else None
                ),
            )
    return {
        "measured_working_level": measured,
        "provisional_working_estimate": provisional,
        "learning_score": score,
        "skills": levels,
        "xp": xp,
        "active_topics": topics,
        "known_language": {
            "topic_refs": [item["target_ref"] for item in topics],
            "vocabulary_refs": [item["target_ref"] for item in vocabulary],
            "chunk_refs": [item["target_ref"] for item in chunks],
            "recent_vocabulary": vocabulary,
            "recent_chunks": chunks,
            "use_as_comprehensibility_boundary": True,
        },
        "personal_lexicon": {"recent_encounters": recent_encounters(store)},
        "recent_errors": recent_errors(store),
        "re_entry": re_entry(store, as_of, at_risk, backlog),
        "due_backlog": [
            {
                "target_ref": item["target_ref"],
                "dimension": item["dimension"],
                "status": item["status"],
                "retrievability": item["retrievability"],
                "knowledge_state": item["knowledge_state"],
            }
            for item in backlog
        ],
        "preferences": current_preferences(store),
    }


def _requirements(
    registry: PolicyRegistry,
    pinned: dict[str, str],
    central: dict[str, Any] | None,
    reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    configured: dict[str, Any] = dict(_DEFAULT_REQUIREMENTS)
    policy_id: str | None = None
    if "lessons" in pinned:
        payload = registry.resolve_pinned("lessons", pinned["lessons"])
        if isinstance(payload.get("requirements"), dict):
            configured.update(payload["requirements"])
            policy_id = str(payload.get("policy_id"))
    items: list[dict[str, Any]] = []
    min_items = int(configured.get("central_topic_min_items") or 0)
    if central is not None and min_items > 0:
        items.append(
            {
                "requirement_id": "central_topic_items",
                "target_ref": central["target_ref"],
                "min_items": min_items,
                "description": "Report at least this many answered items on the central topic.",
            }
        )
    pending = [str(item["review_id"]) for item in reviews if item.get("status") == "pending"]
    if configured.get("reviews_must_be_addressed") and pending:
        items.append(
            {
                "requirement_id": "reviews_addressed",
                "review_ids": pending,
                "description": (
                    "Address every due review: an item with its review_id, or a reviews_skipped "
                    "entry with a reason. An unaddressed review closes INSUFFICIENT_EVIDENCE(not_attempted)."
                ),
            }
        )
    return {
        "policy": policy_id,
        # Advisory only [PD-2026-09-23]: an unmet requirement is a warning in
        # check-report, never a reason to refuse the report.
        "severity": str(configured.get("severity") or "warning"),
        "items": items,
    }


def _report_contract(registry: PolicyRegistry, pinned: dict[str, str], session_id: str) -> dict[str, Any]:
    leaves: dict[str, Any] | None = None
    try:
        leaves = verdict_policy(registry, pinned)
    except EvidencePolicyInvalid:
        leaves = None
    contract: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "session_id": session_id,
        # A session that pinned no evidence@2 has no verdict scale: it closes
        # through the legacy protocol (or abandon), never by a report.
        "accepts_reports": leaves is not None,
        "evidence_policy": pinned.get(EVIDENCE_KIND),
        "verdicts": list(VERDICTS),
        "verdict_scale": dict(leaves["verdict_scale"]) if leaves else None,
        "review_outcome_by_verdict": dict(leaves["review_outcome_by_verdict"]) if leaves else None,
        "report_limits": dict(leaves["report_limits"]) if leaves else None,
        "item_kinds": list(ITEM_KINDS),
        "dimensions": list(DIMENSIONS),
        "block_modes": list(BLOCK_MODES),
        "review_skip_reasons": list(REVIEW_SKIP_REASONS),
        "rejection_codes": list(REJECTION_CODES),
        "report_error_codes": list(REPORT_ERROR_CODES),
        "notes": [
            "Each item's verdict is the tutor's; the engine stores it with the prompt and the answer.",
            "errors[].learner_form must be quoted verbatim from raw_answer; never send offsets.",
            "A repeated answer span earns no second credit (contributing=false), shown by check-report.",
            "partial closes a review as CONFIRMED; incorrect as REGRESSION.",
            "An empty report is accepted with a warning and closes a talk-only lesson.",
        ],
    }
    return contract


# -- the brief ----------------------------------------------------------------


def brief_hash_of(brief: dict[str, Any]) -> str:
    """The payload hash of ``brief`` without ``report_contract.brief_hash``."""
    contract = dict(brief.get("report_contract") or {})
    contract.pop("brief_hash", None)
    return payload_hash({**brief, "report_contract": contract})


def build_brief(
    store: EventStore,
    registry: PolicyRegistry,
    session_id: str,
    *,
    permanent_interleave: PermanentInterleave | None = None,
) -> dict[str, Any]:
    """The ``lesson_brief@1`` of ``session_id`` (see the module docstring).

    Deterministic: built from the pinned policies, the session's own plan and
    review assignments, and the event log, with every clock-dependent fold
    evaluated at the session's ``started_at``. Works for any session -- one
    that pinned no evidence@2 gets ``report_contract.accepts_reports: false``.
    """
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, _ = found
    manifest = dict(state.get("manifest") or {})
    pinned = {str(key): str(value) for key, value in dict(manifest.get("pinned_versions") or {}).items()}
    as_of = datetime.fromisoformat(str(manifest.get("started_at")))
    clock = FixedClock(as_of)
    program: dict[str, Any] = (
        registry.resolve_pinned("curriculum", pinned["curriculum"]) if "curriculum" in pinned else {}
    )
    generation = _generation_policy(registry, pinned)
    try:
        _, plan_state, _ = get_plan(store, session_id)
    except KernelError:
        plan_state = {}
    arc = dict(plan_state.get("lesson_arc") or manifest.get("lesson_arc") or {})
    window = _int_leaf(generation, RECONSTRUCTION, "text_selection_window_presentations", DEFAULT_TEXT_WINDOW)
    text_ids = recent_reconstruction_text_ids(store, window)
    step_types = {str(step.get("step_type") or "") for step in plan_state.get("steps", [])}
    profile = manifest.get("lesson_profile") or arc.get("profile")
    central = _central_topic(
        program,
        arc,
        generation,
        with_text=profile == "drill" or RECONSTRUCTION in step_types,
        recent_text_ids=text_ids,
    )

    order = {
        str(step.get("step_id")): int(step.get("order_index", 0)) for step in plan_state.get("steps", [])
    }
    assignments = sorted(
        session_assignments(store, session_id),
        key=lambda item: (order.get(str(item.get("step_id")), 1 << 30), str(item.get("review_id"))),
    )
    reviews = [
        {
            "review_id": item.get("review_id"),
            "target_ref": item.get("target_ref"),
            "dimension": item.get("dimension"),
            "urgency": item.get("urgency_class"),
            "status": item.get("status"),
            "hint": _review_hint(program, str(item.get("target_ref"))),
        }
        for item in assignments
    ]

    total_seconds = plan_state.get("total_seconds")
    lesson = {
        "session_id": session_id,
        "provider": manifest.get("provider"),
        "mode": manifest.get("mode"),
        "profile": profile,
        "title": arc.get("title"),
        "reason": arc.get("reason"),
        "reason_kind": arc.get("reason_kind"),
        "theme": arc.get("theme"),
        "duration_minutes": int(total_seconds) // 60 if isinstance(total_seconds, int) else None,
        "duration_class": arc.get("duration_class"),
        "agenda": [dict(item) for item in arc.get("agenda") or []],
        "language_envelope": dict(arc.get("language_envelope") or {}),
        "started_at": manifest.get("started_at"),
        "pinned_versions": dict(sorted(pinned.items())),
    }
    brief: dict[str, Any] = {
        "schema": BRIEF_SCHEMA,
        "lesson": lesson,
        "central_topic": central,
        "reviews_due": reviews,
        "plan": _plan_view(plan_state, program, generation, text_ids),
        "learner": _learner_view(store, registry, pinned, program, clock.now(), permanent_interleave),
        "last_session_summary": last_session_summary(store, exclude_session=session_id),
        "requirements": _requirements(registry, pinned, central, reviews),
        "report_contract": _report_contract(registry, pinned, session_id),
    }
    brief["report_contract"]["brief_hash"] = brief_hash_of(brief)
    return brief


def brief_refs(brief: dict[str, Any]) -> dict[str, Any]:
    """The brief facts a committed report records for later folds."""
    central = brief.get("central_topic") or {}
    text = central.get("reconstruction_text") if isinstance(central, dict) else None
    return {
        "central_target_ref": central.get("target_ref") if isinstance(central, dict) else None,
        "reconstruction_text_id": text.get("id") if isinstance(text, dict) else None,
    }
