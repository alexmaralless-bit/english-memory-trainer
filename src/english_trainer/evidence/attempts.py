"""Recording attempts against delivered steps (evidence contract 0.4; 2.2).

Evidence is the only door through which knowledge reaches scoring, and the
door checks papers: an attempt must reference a step with a recorded
``STEP_PRESENTED`` in its active session, and a structured attempt must
reference a stored ``EXERCISE_RENDERED`` snapshot that matches the step. From
those facts the engine derives target, dimension, mode and ``origin`` itself
-- the client cannot claim a probe was a review or re-aim an answer at a
different topic [RR2-3].

This module deliberately reads **only published events and its own
aggregates** (evidence depends on kernel + curriculum, never on lessons):
session status is folded from the session lifecycle events, the step comes
from ``STEP_PRESENTED``, the exercise from ``EXERCISE_RENDERED``. The event
log is the module boundary.

What is honestly computable today:

- **objective check**: an attempt against a stored exercise with an
  ``answer_key`` is scored by deterministic normalization (NFC, casefold,
  whitespace collapse) against the key's variants -- status ``assessed``.
- **open answers** stay ``recorded``: rubric-based AttemptAssessment needs the
  scoring policy (roadmap 2.3) and is never invented by the client (0.4:
  client-side ready-made classification is forbidden).
- **semantic identity**: ``span_hash`` over the raw answer; the same span
  resubmitted for the same primary target is refused -- new keys or a new
  session do not mint new evidence.

``ATTEMPT_RECORDED`` captures everything scoring will need (capture-into-event
4.5): raw answer, span hash, targets, origin, exercise reference, pinned
versions. ``EVIDENCE_ADDED`` -- the scored fact -- arrives with scoring (2.3).

Session notes (``--note``) are stored as untrusted text with author and
timestamp; they are not evidence and never touch scoring [P0-5].
"""

from __future__ import annotations

import unicodedata
from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

# Consumed event contracts (published by lessons). String literals on purpose:
# events are the cross-module interface; importing lessons here would invert
# the dependency rule (evidence depends on kernel + curriculum only).
SESSION_STARTED_EVENT = "session.started"
SESSION_CLOSED_EVENTS = ("session.finished", "session.abandoned")
STEP_PRESENTED_EVENT = "session.step_presented"
EXERCISE_RENDERED_EVENT = "exercise.rendered"
EXERCISE_USED_EVENT = "exercise.used"

EVENT_ATTEMPT_RECORDED = "attempt.recorded"
EVENT_ATTEMPT_STATE_CHANGED = "attempt.state_changed"
EVENT_EVIDENCE_ADDED = "evidence.added"

ATTEMPT_AGGREGATE = "attempt"
NOTES_AGGREGATE = "session_notes"

# Closed / structured step types whose evidence is an objective check: an
# attempt without a stored exercise snapshot cannot be checked and is refused.
# Open production and conversation record now and get rubric assessment in 2.3.
REQUIRES_EXERCISE_INSTANCE = frozenset({"recognition_check", "controlled_production", "gate_item"})

RECORDED = "recorded"
ASSESSED = "assessed"
# Terminal, non-contributing: the session was abandoned before assessment.
# Never an input to scoring -- the learner is not punished for a lost chat.
CLOSED_UNASSESSED = "closed_unassessed"


class EvidencePrecondition(KernelError):
    """The attempt is not admissible as stated -- fix the reference, not retry."""

    code = "EVIDENCE_PRECONDITION"


def _session_manifest(store: EventStore, session_id: str) -> dict[str, Any]:
    """Fold the session's lifecycle events: manifest if the session is active."""
    manifest: dict[str, Any] | None = None
    closed = False
    for event in store.read():
        if event.correlation_id != session_id:
            continue
        if event.type == SESSION_STARTED_EVENT:
            manifest = dict(event.payload.get("manifest") or {})
        elif event.type in SESSION_CLOSED_EVENTS:
            closed = True
    if manifest is None:
        raise EvidencePrecondition(f"session {session_id} does not exist")
    if closed:
        raise EvidencePrecondition(
            f"session {session_id} is closed; attempts attach only to an active session"
        )
    return manifest


def _presented_step(store: EventStore, session_id: str, step_id: str) -> dict[str, Any]:
    found: dict[str, Any] | None = None
    for event in store.read():
        if (
            event.type == STEP_PRESENTED_EVENT
            and event.correlation_id == session_id
            and str(event.payload.get("step_id")) == step_id
        ):
            found = dict(event.payload)
    if found is None:
        raise EvidencePrecondition(
            f"step {step_id} has no STEP_PRESENTED in session {session_id}: "
            "an attempt without a delivered step is not admissible [RR2-3]"
        )
    return found


def _rendered_exercise(store: EventStore, session_id: str, instance_id: str) -> dict[str, Any]:
    for event in store.read():
        if (
            event.type == EXERCISE_RENDERED_EVENT
            and event.correlation_id == session_id
            and str(event.payload.get("exercise_instance_id")) == instance_id
        ):
            return dict(event.payload)
    use: dict[str, Any] | None = None
    for event in store.read():
        if (
            event.type == EXERCISE_USED_EVENT
            and event.correlation_id == session_id
            and str(event.payload.get("exercise_instance_id")) == instance_id
        ):
            use = dict(event.payload)
            break
    if use is not None:
        for event in store.read():
            if (
                event.type == EXERCISE_RENDERED_EVENT
                and str(event.payload.get("exercise_instance_id")) == instance_id
                and event.payload.get("content_hash") == use.get("content_hash")
            ):
                return {
                    **dict(event.payload),
                    "session_id": session_id,
                    "step_id": use["step_id"],
                    "reused_from_session_id": event.payload.get("session_id"),
                }
    raise EvidencePrecondition(
        f"exercise instance {instance_id} has no EXERCISE_RENDERED in session {session_id}"
    )


def _normalize_answer(text: str) -> str:
    collapsed = " ".join(unicodedata.normalize("NFC", text).split())
    return collapsed.casefold()


def _objective_check(raw_answer: str, answer_key: Any) -> bool:
    variants = answer_key if isinstance(answer_key, list) else [answer_key]
    normalized = _normalize_answer(raw_answer)
    return any(_normalize_answer(str(variant)) == normalized for variant in variants)


def _duplicate_span_exists(store: EventStore, span_hash: str, primary_target: dict[str, Any] | None) -> bool:
    """One source span counts at most once per (target, dimension) -- across
    sessions and idempotency keys alike (semantic identity, 0.4 4.1)."""
    for event in store.read():
        if event.type != EVENT_ATTEMPT_RECORDED:
            continue
        if event.payload.get("span_hash") != span_hash:
            continue
        if event.payload.get("primary_target") == primary_target:
            return True
    return False


def record_attempt(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    step_id: str,
    raw_answer: str,
    exercise_instance_id: str | None = None,
    observations: list[dict[str, Any]] | None = None,
    hints: int = 0,
    note: str | None = None,
    provider: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Record one learner attempt against a delivered step."""
    if not raw_answer or not raw_answer.strip():
        raise EvidencePrecondition("raw_answer is empty: an explanation is not evidence (0.4 4.2)")

    manifest = _session_manifest(store, session_id)
    step = _presented_step(store, session_id, step_id)
    step_type = str(step.get("step_type"))

    exercise: dict[str, Any] | None = None
    if exercise_instance_id is not None:
        exercise = _rendered_exercise(store, session_id, exercise_instance_id)
        if str(exercise.get("step_id")) != step_id:
            raise EvidencePrecondition(
                f"exercise instance {exercise_instance_id} was rendered for step "
                f"{exercise.get('step_id')}, not {step_id}"
            )
    elif step_type in REQUIRES_EXERCISE_INSTANCE:
        raise EvidencePrecondition(
            f"step type {step_type} is a structured check: record the EXERCISE_RENDERED "
            "snapshot first (`trainer exercise rendered`) and pass --exercise-instance"
        )

    # The engine derives the classification facts; the client never sends them.
    targets = [dict(t) for t in step.get("targets", [])]
    primary_target = None
    selection_basis = "no_target"  # target-less choice steps record without a target
    if exercise is not None and exercise.get("target_refs"):
        refs = list(exercise["target_refs"])
        dims = list(exercise.get("dimensions") or [])
        primary_target = {"target_ref": str(refs[0]), "dimension": str(dims[0]) if dims else None}
        selection_basis = "declared_item_target"
    elif targets:
        primary_target = dict(targets[0])  # targets[] is already in canonical order
        selection_basis = "canonical_order"
    origin = "control_probe" if step.get("kind") == "probe" else "session"

    span_hash = payload_hash({"raw_answer": raw_answer})
    if _duplicate_span_exists(store, span_hash, primary_target):
        raise EvidencePrecondition(
            "this answer span was already recorded for the same target: one source span "
            "counts at most once per (target, dimension) -- semantic identity (0.4 4.1)"
        )

    assessment: dict[str, Any] | None = None
    status = RECORDED
    if exercise is not None and exercise.get("answer_key") is not None:
        correct = _objective_check(raw_answer, exercise["answer_key"])
        assessment = {
            "basis": "objective_check",
            "correct": correct,
            "score_ppm": 1_000_000 if correct else 0,
            "checked_against_content_hash": exercise["content_hash"],
        }
        status = ASSESSED

    attempt_id = new_ulid(clock, random_source)
    pinned = dict(manifest.get("pinned_versions") or {})
    recorded_at = clock.now().isoformat()
    payload: dict[str, Any] = {
        "attempt_id": attempt_id,
        "session_id": session_id,
        "step_id": step_id,
        "exercise_instance_id": exercise_instance_id,
        "step_type": step_type,
        "mode": step_type,
        "origin": origin,
        "targets": targets,
        "primary_target": primary_target,
        "selection_basis": selection_basis,
        "raw_answer": raw_answer,
        "span_hash": span_hash,
        "observations": list(observations or []),
        "hints": hints,
        "status": status,
        "assessment": assessment,
        "recorded_at": recorded_at,
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(ATTEMPT_AGGREGATE, attempt_id, payload, expected_revision=0)
        if note is not None and note.strip():
            entry = {
                "author_provider": provider or manifest.get("provider"),
                "created_at": recorded_at,
                "text": note.strip(),
                "attempt_id": attempt_id,
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
        batch = [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_ATTEMPT_RECORDED,
                occurred_at=clock.now(),
                actor=actor,
                provider=provider or manifest.get("provider"),
                correlation_id=session_id,
                payload=payload,
                pinned_versions=pinned,
            )
        ]
        if assessment is not None:
            # The assessed attempt IS admissible evidence: EVIDENCE_ADDED rides
            # the same transaction (capture-into-event, 0.4 4.5) with the full
            # CreditAllocation. v1 allocation: the single primary pair at full
            # weight -- multi-credit spans arrive with integration steps.
            batch.append(
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_EVIDENCE_ADDED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider or manifest.get("provider"),
                    correlation_id=session_id,
                    causation_id=batch[0].id,
                    payload={
                        "evidence_id": new_ulid(clock, random_source),
                        "attempt_id": attempt_id,
                        "session_id": session_id,
                        "step_id": step_id,
                        "exercise_instance_id": exercise_instance_id,
                        "origin": origin,
                        "mode": step_type,
                        "primary_target": primary_target,
                        "selection_basis": selection_basis,
                        "credit_allocations": [
                            {
                                "target_ref": primary_target["target_ref"],
                                "dimension": primary_target.get("dimension"),
                                "contribution": "1.0",
                                "used": True,
                                "reason": "primary",
                            }
                        ]
                        if primary_target
                        else [],
                        "span_hash": span_hash,
                        "assessment_basis": assessment["basis"],
                        "correct": assessment["correct"],
                        "score_ppm": assessment["score_ppm"],
                        "hints": hints,
                        "recorded_at": recorded_at,
                    },
                    pinned_versions=pinned,
                )
            )
        uow.append(batch)
    return {
        "attempt_id": attempt_id,
        "status": status,
        "assessment": assessment,
        "primary_target": primary_target,
        "selection_basis": selection_basis,
        "origin": origin,
    }


def list_notes(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """The session's untrusted notes in chronological order [R-3]."""
    from english_trainer.kernel.aggregates import read_aggregate

    found = read_aggregate(store._conn, NOTES_AGGREGATE, session_id)
    if found is None:
        return []
    notes = found[0].get("notes", [])
    return [dict(entry) for entry in notes]


def session_attempts(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """Recorded attempts of a session, in event order (the finish increment
    checks their statuses; scoring folds them in 2.3)."""
    out: list[dict[str, Any]] = []
    for event in store.read():
        if event.type == EVENT_ATTEMPT_RECORDED and event.correlation_id == session_id:
            out.append(dict(event.payload))
    return out


def pending_attempts(store: EventStore, session_id: str) -> list[dict[str, Any]]:
    """Attempts of the session whose disposition is still open (lessons 0.5).

    The pending set is read from the attempt *aggregates* (the operational
    truth for lifecycle status), located via the session's ``ATTEMPT_RECORDED``
    events. ``recorded`` attempts are pending; ``assessed`` and
    ``closed_unassessed`` are settled. Review assignments join this set once
    the scheduler exists.
    """
    from english_trainer.kernel.aggregates import read_aggregate

    pending: list[dict[str, Any]] = []
    for recorded in session_attempts(store, session_id):
        attempt_id = str(recorded["attempt_id"])
        found = read_aggregate(store._conn, ATTEMPT_AGGREGATE, attempt_id)
        state = found[0] if found is not None else recorded
        if state.get("status") not in (ASSESSED, CLOSED_UNASSESSED):
            pending.append(dict(state))
    return pending


def close_pending_attempts(
    store: EventStore,
    uow: UnitOfWork,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    reason: str,
    actor: str = "engine",
) -> list[str]:
    """Close every pending attempt of the session without scoring contribution.

    Runs INSIDE the caller's UnitOfWork (lessons owns the abandon trigger,
    evidence executes the closure -- 0.4 4.3): aggregate updates and the
    ``ATTEMPT_STATE_CHANGED`` events commit atomically with the session
    terminalization or not at all. Returns the closed attempt ids.
    """
    closed: list[str] = []
    for state in pending_attempts(store, session_id):
        attempt_id = str(state["attempt_id"])
        found = uow.get_aggregate(ATTEMPT_AGGREGATE, attempt_id)
        if found is None:
            continue
        current, revision = found
        previous = str(current.get("status"))
        uow.save_aggregate(
            ATTEMPT_AGGREGATE,
            attempt_id,
            {
                **current,
                "status": CLOSED_UNASSESSED,
                "non_contributing": True,
                "close_reason": reason,
                "closed_at": clock.now().isoformat(),
            },
            expected_revision=revision,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_ATTEMPT_STATE_CHANGED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=current.get("provider"),
                    correlation_id=session_id,
                    payload={
                        "attempt_id": attempt_id,
                        "session_id": session_id,
                        "from_status": previous,
                        "to_status": CLOSED_UNASSESSED,
                        "reason": reason,
                        "non_contributing": True,
                    },
                )
            ]
        )
        closed.append(attempt_id)
    return closed
