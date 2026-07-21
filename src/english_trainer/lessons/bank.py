"""The exercise bank: ``generated → accepted | rejected``, ``accepted →
retired`` (generation@1 ``bank_lifecycle``; P.3 PD-2 A; roadmap 2.2).

A rendered exercise is born ``generated`` and is NOT reusable. Admission to
the bank requires an **assessed attempt** against that exact instance -- an
exercise that never survived contact with the learner has not earned reuse --
or an explicit maintainer fast-path whose reason attests that schema, safety,
answer key and authorship were reviewed by a human. Acceptance re-validates
against the ACTIVE curriculum (safety is never pinned): targets and lexicon
refs must resolve, required production must still be allowed, and the
canonical dedup key (normalized prompt skeleton + targets + dimensions + step
type + context family + answer-key hash + sorted lexicon refs) must not
collide with an already-accepted item -- near-duplicates are rejected (the
distinct-transfer-context override arrives when transfer contexts exist as
data).

``rejected`` and ``retired`` are terminal; retiring is only possible from
``accepted``. Reasons come from the closed enums of generation@1 -- free-text
reasons would make the audit stream unqueryable. Bank *reuse* (planned steps
carrying ``bank_item_id`` with re-validation at claim) arrives with the
scheduler's review steps: today's bank only admits, lists and retires.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.delivery import production_eligible
from english_trainer.lessons.rendering import EVENT_EXERCISE_RENDERED

EVENT_EXERCISE_ACCEPTED = "exercise.accepted"
EVENT_EXERCISE_REJECTED = "exercise.rejected"
EVENT_EXERCISE_RETIRED = "exercise.retired"

BANK_AGGREGATE = "bank_item"

ACCEPTED = "accepted"
REJECTED = "rejected"
RETIRED = "retired"

# Closed reason enums (generation@1 bank_lifecycle). Extending them is a
# policy change, not a call-site convenience.
REJECTION_REASONS = frozenset(
    {
        "ambiguous_answer_key",
        "dangling_refs",
        "unsafe_production_requirement",
        "borrowed_text_or_excerpt",
        "wrong_dimension_fit",
        "prompt_fault",
    }
)
RETIREMENT_REASONS = frozenset(
    {
        "active_safety_forbids_reuse",
        "target_retired",
        "lexical_item_retired_or_obsolete",
        "schema_incompatible",
        "better_duplicate_replacement",
        "prompt_fault_threshold",
        "maintainer_rejection",
    }
)


class BankPrecondition(KernelError):
    """The bank operation is not admissible as stated (stable refusal)."""

    code = "BANK_PRECONDITION"


def _find_rendered(store: EventStore, exercise_instance_id: str) -> dict[str, Any]:
    """The EXERCISE_RENDERED payload for an instance, across all sessions --
    admission usually happens near or after session end, so no active-session
    requirement here."""
    for event in store.read():
        if (
            event.type == EVENT_EXERCISE_RENDERED
            and str(event.payload.get("exercise_instance_id")) == exercise_instance_id
        ):
            return dict(event.payload)
    raise BankPrecondition(f"exercise instance {exercise_instance_id} has no EXERCISE_RENDERED")


def _step_type_of(store: EventStore, session_id: str, step_id: str) -> str:
    for event in store.read():
        if (
            event.type == "session.step_presented"
            and event.correlation_id == session_id
            and str(event.payload.get("step_id")) == step_id
        ):
            return str(event.payload.get("step_type"))
    raise BankPrecondition(f"step {step_id} of session {session_id} has no STEP_PRESENTED")


def _has_assessed_attempt(store: EventStore, exercise_instance_id: str) -> bool:
    for event in store.read():
        if (
            event.type == "attempt.recorded"
            and str(event.payload.get("exercise_instance_id") or "") == exercise_instance_id
            and event.payload.get("status") == "assessed"
        ):
            return True
    return False


def dedup_key(rendered: dict[str, Any], step_type: str) -> str:
    """The canonical near-duplicate identity (generation@1 canonical_dedup_key):
    field order fixed, NFC, incidental whitespace stripped, refs sorted."""
    skeleton = " ".join(unicodedata.normalize("NFC", str(rendered.get("prompt") or "")).split()).casefold()
    material = {
        "target_refs": sorted(str(ref) for ref in rendered.get("target_refs") or []),
        "dimensions": sorted(str(d) for d in rendered.get("dimensions") or []),
        "step_type": step_type,
        "context_family": str(rendered.get("context_id") or "").split("|")[0],
        "normalized_prompt_skeleton": skeleton,
        "answer_key_hash": payload_hash(
            {"answer_key": rendered.get("answer_key"), "rubric_ref": rendered.get("rubric_ref")}
        ),
        "sorted_lexicon_refs": sorted(str(ref) for ref in rendered.get("lexicon_refs") or []),
    }
    return payload_hash(material)


def _acceptance_problems(
    rendered: dict[str, Any], step_type: str, active_program: dict[str, Any]
) -> list[str]:
    problems: list[str] = []
    known_targets = {str(t.get("id")) for t in active_program.get("topics", [])} | {
        str(u.get("id")) for u in active_program.get("lexicon", [])
    }
    for ref in rendered.get("target_refs") or []:
        if str(ref) not in known_targets:
            problems.append(f"dangling target ref {ref}")
    known_units = {str(u.get("id")) for u in active_program.get("lexicon", [])}
    for ref in rendered.get("lexicon_refs") or []:
        if str(ref) not in known_units:
            problems.append(f"dangling lexicon ref {ref}")
    eligible, reason = production_eligible(
        {
            "step_type": step_type,
            "generation_directive": {"lexicon_refs": list(rendered.get("lexicon_refs") or [])},
        },
        active_program,
    )
    if not eligible:
        problems.append(f"active safety forbids required production: {reason}")
    provenance = rendered.get("provenance") or {}
    if provenance.get("origin") != "authored":
        problems.append("provenance is not authored")
    if not rendered.get("answer_key") and not rendered.get("rubric_ref"):
        problems.append("neither answer_key nor rubric_ref")
    return problems


def _emit(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    *,
    event_type: str,
    correlation_id: str,
    payload: dict[str, Any],
    actor: str,
    state: dict[str, Any],
    expected_revision: int,
) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            BANK_AGGREGATE,
            str(payload["exercise_instance_id"]),
            state,
            expected_revision=expected_revision,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=correlation_id,
                    payload=payload,
                )
            ]
        )


def accept_exercise(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    exercise_instance_id: str,
    *,
    maintainer_reason: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Admit a rendered exercise into the bank (PD-2 A)."""
    existing = read_aggregate(store._conn, BANK_AGGREGATE, exercise_instance_id)
    if existing is not None:
        status = existing[0].get("status")
        if status == ACCEPTED:
            return {"exercise_instance_id": exercise_instance_id, "status": ACCEPTED, "already": True}
        raise BankPrecondition(
            f"exercise {exercise_instance_id} is {status}; {status} is terminal, it cannot be accepted"
        )

    rendered = _find_rendered(store, exercise_instance_id)
    session_id = str(rendered["session_id"])
    step_type = _step_type_of(store, session_id, str(rendered["step_id"]))

    if not _has_assessed_attempt(store, exercise_instance_id) and not (
        maintainer_reason and maintainer_reason.strip()
    ):
        raise BankPrecondition(
            "bank admission requires an assessed attempt against this exact instance, or the "
            "explicit maintainer fast-path with a reason attesting the review "
            "(generation@1: accept_only_after_assessed_attempt_or_explicit_maintainer_fast_path)"
        )

    _, active_program = registry.resolve_active("curriculum")
    problems = _acceptance_problems(rendered, step_type, active_program)
    if problems:
        raise BankPrecondition("acceptance checks failed: " + "; ".join(problems))

    key = dedup_key(rendered, step_type)
    for item_id, state, _ in list_aggregates(store._conn, BANK_AGGREGATE):
        if state.get("status") == ACCEPTED and state.get("dedup_key") == key:
            raise BankPrecondition(
                f"near-duplicate of accepted bank item {item_id}: same canonical dedup key "
                "(same targets, dimensions, step type, context family, prompt skeleton, answer key)"
            )

    state = {
        "exercise_instance_id": exercise_instance_id,
        "status": ACCEPTED,
        "dedup_key": key,
        "content_hash": rendered["content_hash"],
        "step_type": step_type,
        "target_refs": list(rendered.get("target_refs") or []),
        "dimensions": list(rendered.get("dimensions") or []),
        "context_id": rendered.get("context_id"),
        "lexicon_refs": list(rendered.get("lexicon_refs") or []),
        "source_session_id": session_id,
        "admission_basis": "maintainer_fast_path" if maintainer_reason else "assessed_attempt",
        "admission_reason": (maintainer_reason or "").strip() or None,
        "accepted_at": clock.now().isoformat(),
    }
    payload = {
        "exercise_instance_id": exercise_instance_id,
        "session_id": session_id,
        "step_id": rendered["step_id"],
        "content_hash": rendered["content_hash"],
        "dedup_key": key,
        "admission_basis": state["admission_basis"],
        "admission_reason": state["admission_reason"],
    }
    _emit(
        store,
        clock,
        random_source,
        event_type=EVENT_EXERCISE_ACCEPTED,
        correlation_id=session_id,
        payload=payload,
        actor=actor,
        state=state,
        expected_revision=0,
    )
    return {"exercise_instance_id": exercise_instance_id, "status": ACCEPTED, "dedup_key": key}


def reject_exercise(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    exercise_instance_id: str,
    *,
    reason: str,
    actor: str = "agent",
) -> dict[str, Any]:
    """``generated -> rejected`` (terminal): the instance never becomes reusable."""
    if reason not in REJECTION_REASONS:
        raise BankPrecondition(
            f"unknown rejection reason {reason!r}; allowed: {', '.join(sorted(REJECTION_REASONS))}"
        )
    existing = read_aggregate(store._conn, BANK_AGGREGATE, exercise_instance_id)
    if existing is not None:
        raise BankPrecondition(
            f"exercise {exercise_instance_id} is already {existing[0].get('status')}; "
            "only a generated (unbanked) instance can be rejected"
        )
    rendered = _find_rendered(store, exercise_instance_id)
    session_id = str(rendered["session_id"])
    state = {
        "exercise_instance_id": exercise_instance_id,
        "status": REJECTED,
        "reason": reason,
        "content_hash": rendered["content_hash"],
        "source_session_id": session_id,
        "rejected_at": clock.now().isoformat(),
    }
    payload = {
        "exercise_instance_id": exercise_instance_id,
        "session_id": session_id,
        "reason": reason,
    }
    _emit(
        store,
        clock,
        random_source,
        event_type=EVENT_EXERCISE_REJECTED,
        correlation_id=session_id,
        payload=payload,
        actor=actor,
        state=state,
        expected_revision=0,
    )
    return {"exercise_instance_id": exercise_instance_id, "status": REJECTED, "reason": reason}


def retire_exercise(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    exercise_instance_id: str,
    *,
    reason: str,
    actor: str = "agent",
) -> dict[str, Any]:
    """``accepted -> retired`` (terminal): future reuse stops, history stands."""
    if reason not in RETIREMENT_REASONS:
        raise BankPrecondition(
            f"unknown retirement reason {reason!r}; allowed: {', '.join(sorted(RETIREMENT_REASONS))}"
        )
    existing = read_aggregate(store._conn, BANK_AGGREGATE, exercise_instance_id)
    if existing is None or existing[0].get("status") != ACCEPTED:
        current = existing[0].get("status") if existing else "not in the bank"
        raise BankPrecondition(
            f"exercise {exercise_instance_id} is {current}; only an accepted item can be retired"
        )
    state, revision = existing
    session_id = str(state.get("source_session_id"))
    new_state = {
        **state,
        "status": RETIRED,
        "retirement_reason": reason,
        "retired_at": clock.now().isoformat(),
    }
    payload = {
        "exercise_instance_id": exercise_instance_id,
        "session_id": session_id,
        "reason": reason,
    }
    _emit(
        store,
        clock,
        random_source,
        event_type=EVENT_EXERCISE_RETIRED,
        correlation_id=session_id,
        payload=payload,
        actor=actor,
        state=new_state,
        expected_revision=revision,
    )
    return {"exercise_instance_id": exercise_instance_id, "status": RETIRED, "reason": reason}


def bank_items(store: EventStore, *, status: str | None = None) -> list[dict[str, Any]]:
    """Bank contents in deterministic id order, optionally filtered by status."""
    out: list[dict[str, Any]] = []
    for _, state, _ in list_aggregates(store._conn, BANK_AGGREGATE):
        if status is None or state.get("status") == status:
            out.append(dict(state))
    return out
