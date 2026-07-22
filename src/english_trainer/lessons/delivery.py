"""Step delivery under CAS: ``session next`` / ``peek`` / ``replan``
(control 4.2-4.3; lessons owns the commands, control defines the behavior).

Claiming a step is a *mutation* [R-1]: in one UnitOfWork it marks the next
unpresented step as presented, moves its ``expected_seconds`` from
``SessionBudget.planned`` to ``DeliveryLedger.presented`` (so ``effective =
presented + planned`` never double-counts), bumps ``plan_version`` and
publishes ``STEP_PRESENTED``. The CAS token is ``expected_plan_version``: a
mismatch is a stable :class:`PlanVersionConflict` carrying the current
version -- the loser peeks and retries with a fresh key. ``peek`` is
read-only and publishes nothing.

``STEP_PRESENTED`` records that the step was handed **to the tutor**, not
shown to the learner [RR2-2] -- the engine cannot observe the chat screen, so
it does not claim to. The exercise text itself still requires an
``EXERCISE_RENDERED`` before the learner sees it (P.3; evidence increment).

Live safety runs before delivery [П.3]: the *active* curriculum decides
``production_eligible`` at claim time (never the pinned one -- a unit that
became recognition-only yesterday must not be produced today). The composed
v1 steps (intro / free conversation) are not production, so today the check
can only pass; the gate exists so the bank increment inherits it rather than
retrofitting it.

``replan`` builds ``composition_revision + 1`` from the *remainder* [RR2-6]:
residual floors are ``max(0, floor(total * bp / 10000) - presented[bucket])``,
presented steps pass through verbatim, surviving candidates keep their step
AND review-assignment ids, and a new ``SESSION_COMPOSED`` rides the same UoW.
An unpresented review step dropped from the new revision is CANCELLED in that
transaction -- terminal for the finish gate, never a learning outcome [RR2-4].
"""

from __future__ import annotations

from typing import Any

from english_trainer.control.compose import compose_plan, step_targets
from english_trainer.control.errors import PlanVersionConflict
from english_trainer.control.policy import CONTROL_KIND, PRODUCTION_STEP_TYPES, require_valid
from english_trainer.evidence.reviews import cancel_assignment
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.sessions import (
    EVENT_COMPOSED,
    EVENT_SAFETY_REJECTED,
    EVENT_STEP_PRESENTED,
    IN_PROGRESS,
    PLAN_AGGREGATE,
    SESSION_AGGREGATE,
    STARTED,
    SessionPrecondition,
    get_plan,
    get_session,
    plan_summary,
    presented_targets,
    review_candidates_for,
    save_new_review_assignments,
)


def _active_session(store: EventStore, session_id: str) -> tuple[dict[str, Any], int, dict[str, Any]]:
    found = get_session(store, session_id)
    if found is None:
        raise SessionPrecondition(f"session {session_id} does not exist")
    state, revision = found
    if state.get("status") not in (STARTED, IN_PROGRESS):
        raise SessionPrecondition(
            f"session {session_id} is {state.get('status')}; steps are delivered only to an active session"
        )
    return state, revision, dict(state.get("manifest") or {})


def _next_unpresented(plan_state: dict[str, Any]) -> dict[str, Any] | None:
    pending = [step for step in plan_state["steps"] if step["presented_at"] is None]
    pending.sort(key=lambda step: int(step["order_index"]))
    return pending[0] if pending else None


def _check_version(plan_state: dict[str, Any], expected_plan_version: int) -> None:
    current = int(plan_state["plan_version"])
    if current != expected_plan_version:
        raise PlanVersionConflict(
            f"plan is at version {current}, caller expected {expected_plan_version}; "
            "peek and retry with the fresh version and a fresh idempotency key",
            current_plan_version=current,
        )


def production_eligible(step: dict[str, Any], active_program: dict[str, Any]) -> tuple[bool, str | None]:
    """The live safety predicate (control 4.2 [П.3], v1 slice).

    Production step types must not target lexical units the *active* program
    marks recognition-only or non-current (generation@1: dated is
    recognition-only by default; expiry suspends production). Non-production
    steps are always eligible -- introducing or recognizing a unit is exactly
    what a safety-restricted unit still allows.
    """
    if step["step_type"] not in PRODUCTION_STEP_TYPES:
        return True, None
    refs = set(step.get("generation_directive", {}).get("lexicon_refs") or [])
    if not refs:
        return True, None
    by_id = {str(unit.get("id")): unit for unit in active_program.get("lexicon", [])}
    for ref in sorted(refs):
        unit = by_id.get(ref)
        if unit is None:
            return False, f"unit {ref} no longer exists in the active curriculum"
        if str(unit.get("usage_policy", "safe_to_use")) == "recognition_only":
            return False, f"unit {ref} is recognition-only under the active safety policy"
        if str(unit.get("currency", "current")) != "current":
            return False, f"unit {ref} is no longer current ({unit.get('currency')})"
    return True, None


def peek_step(store: EventStore, session_id: str) -> dict[str, Any]:
    """Read-only view of the next step and the CAS token (control 4.2):
    nothing is marked, nothing is published."""
    _active_session(store, session_id)
    _, plan_state, _ = get_plan(store, session_id)
    step = _next_unpresented(plan_state)
    return {
        "session_id": session_id,
        "plan_version": int(plan_state["plan_version"]),
        "composition_revision": int(plan_state["composition_revision"]),
        "steps_remaining": sum(1 for s in plan_state["steps"] if s["presented_at"] is None),
        "step": step,
    }


def next_step(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    expected_plan_version: int,
    actor: str = "engine",
) -> dict[str, Any]:
    """Atomically claim the next step; returns it with the new plan version."""
    session_state, session_revision, manifest = _active_session(store, session_id)
    plan_id, plan_state, plan_revision = get_plan(store, session_id)
    _check_version(plan_state, expected_plan_version)

    step = _next_unpresented(plan_state)
    if step is None:
        raise SessionPrecondition(
            f"plan of session {session_id} is exhausted; `trainer session replan` for more "
            "or finish the session"
        )

    # Live safety before delivery: the ACTIVE curriculum decides, and a
    # refusal leaves version and ledger untouched (the rejection event is the
    # only thing written).
    active_safety_version, active_program = registry.resolve_active("curriculum")
    eligible, reason = production_eligible(step, active_program)
    if not eligible:
        with UnitOfWork(store, clock) as uow:
            uow.append(
                [
                    make_event(
                        id=new_ulid(clock, random_source),
                        type=EVENT_SAFETY_REJECTED,
                        occurred_at=clock.now(),
                        actor=actor,
                        provider=manifest.get("provider"),
                        correlation_id=session_id,
                        payload={
                            "session_id": session_id,
                            "step_id": step["step_id"],
                            "reason": reason,
                            "active_safety_version": active_safety_version,
                        },
                        pinned_versions=dict(manifest.get("pinned_versions") or {}),
                    )
                ]
            )
        raise SessionPrecondition(
            f"safety_changed: {reason}; `trainer session replan` recomposes under the active policy"
        )

    presented_at = clock.now().isoformat()
    cost = int(step["expected_seconds"])
    bucket = str(step["bucket"])
    new_version = int(plan_state["plan_version"]) + 1

    new_state = dict(plan_state)
    new_state["steps"] = [
        {**s, "presented_at": presented_at} if s["step_id"] == step["step_id"] else s
        for s in plan_state["steps"]
    ]
    planned = dict(plan_state["budget"]["planned"])
    planned[bucket] = int(planned[bucket]) - cost
    new_state["budget"] = {**plan_state["budget"], "planned": planned}
    presented = dict(plan_state["ledger"]["presented"])
    presented[bucket] = int(presented[bucket]) + cost
    presented_seconds = int(plan_state["ledger"]["presented_seconds"]) + cost
    new_state["ledger"] = {
        "presented": presented,
        "presented_seconds": presented_seconds,
        "remaining_seconds": int(plan_state["total_seconds"]) - presented_seconds,
    }
    new_state["plan_version"] = new_version
    new_state["active_safety_version"] = active_safety_version

    presented_step = {**step, "presented_at": presented_at}
    payload: dict[str, Any] = {
        "step_id": step["step_id"],
        "session_id": session_id,
        "session_plan_id": plan_id,
        "composition_revision": int(plan_state["composition_revision"]),
        "plan_version": new_version,
        "kind": step["kind"],
        "bucket": bucket,
        "step_type": step["step_type"],
        "targets": step_targets(step),
        "context_id": step["context_id"],
        "presented_at": presented_at,
        "active_safety_version": active_safety_version,
    }
    # Exactly one exercise source (control 4.3a): a bank item id once the bank
    # exists, otherwise the hash of the canonical generation directive.
    if step.get("bank_item_id"):
        payload["bank_item_id"] = step["bank_item_id"]
    else:
        payload["generation_directive_hash"] = payload_hash(step["generation_directive"])

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(PLAN_AGGREGATE, plan_id, new_state, expected_revision=plan_revision)
        if session_state.get("status") == STARTED:
            # The first delivered step is the "first real work" edge
            # STARTED -> IN_PROGRESS, in the same transaction as the claim.
            uow.save_aggregate(
                SESSION_AGGREGATE,
                session_id,
                {**session_state, "status": IN_PROGRESS},
                expected_revision=session_revision,
            )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_STEP_PRESENTED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload=payload,
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return {"session_id": session_id, "plan_version": new_version, "step": presented_step}


def replan_session(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    expected_plan_version: int,
    actor: str = "engine",
) -> dict[str, Any]:
    """Recompose the unpresented remainder as ``composition_revision + 1``."""
    _, _, manifest = _active_session(store, session_id)
    plan_id, plan_state, plan_revision = get_plan(store, session_id)
    _check_version(plan_state, expected_plan_version)

    pinned = dict(manifest.get("pinned_versions") or {})
    program = registry.resolve_pinned("curriculum", pinned["curriculum"])
    policy = require_valid(registry.resolve_pinned(CONTROL_KIND, pinned[CONTROL_KIND]))
    active_safety_version, _ = registry.resolve_active("curriculum")

    kept = [step for step in plan_state["steps"] if step["presented_at"] is not None]
    unpresented = [step for step in plan_state["steps"] if step["presented_at"] is None]
    keep_step_ids = {str(step["candidate_id"]): str(step["step_id"]) for step in unpresented}
    keep_review_ids = {
        str(step["candidate_id"]): str(step["review_assignment_id"])
        for step in unpresented
        if step.get("kind") == "review"
    }
    composed = compose_plan(
        program=program,
        policy=policy,
        generation_version=pinned["generation"],
        mode=str(plan_state["mode"]),
        total_seconds=int(plan_state["total_seconds"]),
        presented_targets=presented_targets(store),
        presented_by_bucket={k: int(v) for k, v in plan_state["ledger"]["presented"].items()},
        presented_steps=kept,
        keep_step_ids=keep_step_ids,
        review_candidates=review_candidates_for(store, registry, pinned, program, policy, clock),
        keep_review_ids=keep_review_ids,
        new_id=lambda: new_ulid(clock, random_source),
    )
    new_revision = int(plan_state["composition_revision"]) + 1
    new_version = int(plan_state["plan_version"]) + 1
    new_state: dict[str, Any] = {
        "session_id": session_id,
        "mode": plan_state["mode"],
        "total_seconds": plan_state["total_seconds"],
        "composition_revision": new_revision,
        "plan_version": new_version,
        "active_safety_version": active_safety_version,
        **composed,
    }
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(PLAN_AGGREGATE, plan_id, new_state, expected_revision=plan_revision)
        # Replan leaves no orphans and creates no debt (4.2 [RR2-4]): an
        # unpresented review step dropped from the new revision is CANCELLED
        # in the same UoW -- terminal, but never a learning outcome. Steps
        # newly admitted get their pending assignments here too.
        surviving_review_ids = {
            str(step["review_assignment_id"]) for step in new_state["steps"] if step.get("kind") == "review"
        }
        for step in unpresented:
            if step.get("kind") == "review" and str(step["review_assignment_id"]) not in surviving_review_ids:
                cancel_assignment(
                    store,
                    uow,
                    clock,
                    random_source,
                    str(step["review_assignment_id"]),
                    reason="replanned",
                    actor=actor,
                )
        save_new_review_assignments(uow, new_state, session_id, clock.now().isoformat())
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_COMPOSED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=manifest.get("provider"),
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "session_plan_id": plan_id,
                        "composition_revision": new_revision,
                        "plan_version": new_version,
                        "budget": {"total_seconds": plan_state["total_seconds"], **new_state["budget"]},
                        "steps": plan_summary(new_state),
                        "waivers": new_state["waivers"],
                        "active_safety_version": active_safety_version,
                    },
                    pinned_versions=pinned,
                )
            ]
        )
    return {
        "session_id": session_id,
        "composition_revision": new_revision,
        "plan_version": new_version,
        "steps_planned": sum(1 for s in new_state["steps"] if s["presented_at"] is None),
    }
