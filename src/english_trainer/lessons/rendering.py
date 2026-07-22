"""Recording the rendered exercise before the learner sees it (lessons 3b;
generation@1 ``exercise_rendered_event``; P.3 PD-1 A; roadmap 2.2).

The tutor renders the exercise text from the step's generation directive and
MUST commit it as an immutable ``EXERCISE_RENDERED`` snapshot **before**
presenting the prompt to the learner. The event is the storage: historical
attempts and replay read the stored snapshot, never a re-render (a later
re-render under a changed safety policy would silently rewrite history).

Validation before commit:

- the step must have a ``STEP_PRESENTED`` fact in this active session -- a
  rendered exercise for an unpresented step would invert the delivery order;
- the exercise text is *authored for this project* (``provenance.origin ==
  "authored"``): third-party excerpts are forbidden forever (generation@1
  ``own_text_rule``; the agent is the trusted reporter of this fact, PD-2026-07-19);
- exactly one of ``answer_key`` / ``rubric_ref`` -- an exercise that cannot be
  checked cannot produce admissible evidence;
- live safety: production step types re-check ``production_eligible`` against
  the ACTIVE curriculum at render time (safety is never pinned, OPEN-14).

The engine issues ``exercise_instance_id`` and computes ``content_hash`` over
the canonical exercise content; the client supplies content, never identity.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import production_eligible
from english_trainer.lessons.sessions import (
    EVENT_STEP_PRESENTED,
    IN_PROGRESS,
    STARTED,
    SessionPrecondition,
    get_session,
)

EVENT_EXERCISE_RENDERED = "exercise.rendered"

EXERCISE_SCHEMA_VERSION = 1


def find_presented_step(store: EventStore, session_id: str, step_id: str) -> dict[str, Any] | None:
    """The ``STEP_PRESENTED`` payload for (session, step), or ``None``.

    Fact-based on purpose: a step stays referenceable after any number of
    replans because the delivery *event* is the anchor, not the current
    composition revision (evidence 4.5 [RR2-3]).
    """
    found: dict[str, Any] | None = None
    for event in store.read():
        if (
            event.type == EVENT_STEP_PRESENTED
            and event.correlation_id == session_id
            and str(event.payload.get("step_id")) == step_id
        ):
            found = dict(event.payload)  # keep the last: latest re-claim wins
    return found


def _validate_exercise(exercise: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    prompt = exercise.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        problems.append("prompt: required non-empty string")
    has_key = bool(exercise.get("answer_key"))
    has_rubric = bool(exercise.get("rubric_ref"))
    if has_key == has_rubric:
        problems.append("exactly one of answer_key / rubric_ref is required")
    provenance = exercise.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("origin") != "authored":
        problems.append(
            'provenance.origin must be "authored": all exercise text is written for this '
            "project; third-party excerpts are forbidden (generation@1 own_text_rule)"
        )
    return problems


def record_rendered_exercise(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    step_id: str,
    exercise: dict[str, Any],
    provider: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Persist the rendered-exercise snapshot; returns instance id and hash."""
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, _ = found
    if state.get("status") not in (STARTED, IN_PROGRESS):
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; exercises render only in an active session"
        )
    manifest = dict(state.get("manifest") or {})

    step = find_presented_step(store, session_id, step_id)
    if step is None:
        raise SessionPrecondition(
            f"step {step_id} has no STEP_PRESENTED in session {session_id}: "
            "render follows delivery (`trainer session next` first)"
        )

    problems = _validate_exercise(exercise)
    if problems:
        raise SessionPrecondition("invalid exercise: " + "; ".join(problems))

    lexicon_refs = [str(ref) for ref in (exercise.get("lexicon_refs") or [])]
    pinned = dict((state.get("manifest") or {}).get("pinned_versions") or {})
    rubric_ref = exercise.get("rubric_ref")
    machine_checks = list(exercise.get("machine_checks") or [])
    if rubric_ref is not None or machine_checks:
        # Rubric resolution happens at render, against the SESSION-PINNED
        # version, never active (P.5 PD-5 A): a dangling ref must fail before
        # the learner sees the prompt, not at assessment.
        if "rubric" not in pinned:
            raise SessionPrecondition("the session pins no rubric policy; cannot render a rubric exercise")
        rubric_payload = registry.resolve_pinned("rubric", pinned["rubric"])
        profiles = rubric_payload.get("rubric_profiles") or {}
        if rubric_ref is not None:
            profile = profiles.get(str(rubric_ref).removeprefix("rubric:"))
            if profile is None:
                raise SessionPrecondition(f"rubric ref {rubric_ref!r} does not resolve (no fallback)")
            if step["step_type"] not in (profile.get("allowed_step_types") or []):
                raise SessionPrecondition(
                    f"rubric ref {rubric_ref!r} is incompatible with step type {step['step_type']}"
                )
        operations = rubric_payload.get("machine_operations") or {}
        for check in machine_checks:
            if str(check.get("operation")) not in operations:
                raise SessionPrecondition(
                    f"machine check operation {check.get('operation')!r} is outside the closed set"
                )
    active_safety_version, active_program = registry.resolve_active("curriculum")
    eligible, reason = production_eligible(
        {"step_type": step["step_type"], "generation_directive": {"lexicon_refs": lexicon_refs}},
        active_program,
    )
    if not eligible:
        raise SessionPrecondition(f"safety_changed: {reason}; replan and render a different exercise")

    # Content identity covers exactly what the learner will face; the engine
    # computes it so a client cannot claim two texts are "the same" snapshot.
    content = {
        "prompt": exercise["prompt"],
        "answer_key": exercise.get("answer_key"),
        "rubric_ref": exercise.get("rubric_ref"),
        "distractor_error_refs": [str(ref) for ref in (exercise.get("distractor_error_refs") or [])],
        "lexicon_refs": lexicon_refs,
        # The rubric inputs are part of content identity: a changed check set
        # is a different exercise (P.5, immutable rubric-input snapshot).
        "machine_checks": machine_checks,
    }
    content_hash = payload_hash(content)
    exercise_instance_id = new_ulid(clock, random_source)

    payload: dict[str, Any] = {
        "session_id": session_id,
        "step_id": step_id,
        "exercise_instance_id": exercise_instance_id,
        "content_hash": content_hash,
        "target_refs": [t["target_ref"] for t in step.get("targets", [])],
        "dimensions": sorted(
            {str(t.get("dimension")) for t in step.get("targets", []) if t.get("dimension")}
        ),
        "context_id": step.get("context_id"),
        "lexicon_refs": lexicon_refs,
        "exercise_schema_version": EXERCISE_SCHEMA_VERSION,
        "prompt": exercise["prompt"],
        "answer_key": exercise.get("answer_key"),
        "rubric_ref": exercise.get("rubric_ref"),
        "distractor_error_refs": content["distractor_error_refs"],
        "machine_checks": machine_checks,
        "generation_policy_version": pinned.get("generation"),
        "pinned_curriculum_version": pinned.get("curriculum"),
        "pinned_rubric_version": pinned.get("rubric"),
        "active_safety_version": active_safety_version,
        "provider": provider or manifest.get("provider"),
        "rendered_at": clock.now().isoformat(),
        "provenance": exercise["provenance"],
    }
    with UnitOfWork(store, clock) as uow:
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_EXERCISE_RENDERED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=payload["provider"],
                    correlation_id=session_id,
                    payload=payload,
                    pinned_versions=pinned,
                )
            ]
        )
    return {
        "exercise_instance_id": exercise_instance_id,
        "content_hash": content_hash,
        "step_id": step_id,
        "event_id": event.id,
    }


def find_rendered_exercise(
    store: EventStore, session_id: str, exercise_instance_id: str
) -> dict[str, Any] | None:
    """The stored ``EXERCISE_RENDERED`` payload by instance id, or ``None``."""
    for event in store.read():
        if (
            event.type == EVENT_EXERCISE_RENDERED
            and event.correlation_id == session_id
            and str(event.payload.get("exercise_instance_id")) == exercise_instance_id
        ):
            return dict(event.payload)
    return None
