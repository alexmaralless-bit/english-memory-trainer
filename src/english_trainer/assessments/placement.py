"""Placement lifecycle over kernel CAS aggregates (assessments 2-4; roadmap 2.6).

A placement is a revisioned operational aggregate with the contract lifecycle
``STARTED -> IN_PROGRESS -> SUBMITTED -> SCORED`` plus the terminalizations
``ABANDONED`` / ``DECLINED`` / ``EXPIRED``. At most one placement is active at a
time; the singleton pointer aggregate enforces that under compare-and-set, so
two concurrent starts cannot both win -- the same shape the session lifecycle
uses (lessons/sessions).

Two things make placement a *timed diagnostic* rather than an open-ended quiz:

- **Resume window / expiry** [PD-2026-07-20]. Answers are checkpointed
  incrementally, so a lost chat leaves a resumable placement. But a placement
  left idle past ``resume_window`` (default 48h from ``last_activity_at``) is
  terminalized ``EXPIRED`` by an **append-only, replayable** ``PLACEMENT_EXPIRED``
  event whose ``boundary_at`` is derived deterministically from
  ``last_activity_at`` + the pinned window -- never from the sweep's wall clock,
  exactly like ``OVERDUE_AT_RISK_TRIGGERED``/``SESSION_STALE_ABANDONED``.
- **Exposure**. Every answered item's exposure id is recorded, so on a re-take
  re-seen items are down-weighted (or zeroed) and the applied weight is
  **captured into the evidence event** -- a memorized form cannot be re-sat as
  fresh evidence, and replay reproduces the exact contribution.

On ``submit`` the placement scores itself: correct objective items become
``origin=placement`` evidence and a matching ``review.outcome`` per verified
target. The scoring engine already caps ``origin=placement`` at ``ACTIVE`` (never
``MASTERED``) -- this module only emits the facts; scoring owns the ceiling.

Deliberately deferred to the content phase (П, OPEN-17): the full authored
A1-B1 form content and a second form; the writing rubric hand-off (a placement
has no session/rendered-exercise/rubric context the evidence rubric pipeline
needs, so writing items record a provisional observation and contribute no
measured level); calibration of ``resume_window``/``form_cooldown_days`` and of
the item->outcome mapping.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Any

from english_trainer.assessments.forms import (
    OBJECTIVE,
    WRITING,
    form_sections,
    item_exposure_id,
    section_items,
    select_form,
)
from english_trainer.assessments.policy import (
    ASSESSMENTS_KIND,
    ASSESSMENTS_VERSION,
    CEFR_LEVELS,
    CORE_SKILLS,
    default_policy,
    require_valid,
    resume_window,
)
from english_trainer.assessments.self_assessment import (
    SELF_ASSESSMENT_SCHEMA_VERSION,
    normalize_self_assessment,
)
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError, NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import KNOWN_KINDS, PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.transitions import build_state_transition

PLACEMENT_AGGREGATE = "placement"
POINTER_AGGREGATE = "placement_pointer"
POINTER_ID = "active"

EVENT_STARTED = "placement.started"
EVENT_CHECKPOINT = "placement.checkpoint"
EVENT_RESUMED = "placement.resumed"
EVENT_SUBMITTED = "placement.submitted"
EVENT_SCORED = "placement.scored"
EVENT_DECLINED = "placement.declined"
EVENT_ABANDONED = "placement.abandoned"
EVENT_EXPIRED = "placement.expired"

# Cross-module facts. Events ARE the module boundary (foundation 4): assessments
# emits the same evidence/outcome shapes the scoring and scheduler folds consume,
# with string literals for the consumed shapes. The narrow transition-event
# producer is imported so source outcome + canonical transition stay atomic.
EVIDENCE_ADDED_EVENT = "evidence.added"
REVIEW_OUTCOME_EVENT = "review.outcome"

STARTED = "STARTED"
IN_PROGRESS = "IN_PROGRESS"
SUBMITTED = "SUBMITTED"
SCORED = "SCORED"
ABANDONED = "ABANDONED"
DECLINED = "DECLINED"
EXPIRED = "EXPIRED"

_ACTIVE_STATES = (STARTED, IN_PROGRESS)
_TERMINAL_STATES = (SUBMITTED, SCORED, ABANDONED, DECLINED, EXPIRED)


class PlacementPrecondition(KernelError):
    """The action is not allowed in the current state -- do something else.

    Maps to the CLI's PRECONDITION_FAILED (exit 6): retrying will not help.
    """

    code = "PLACEMENT_PRECONDITION"


# -- reads --------------------------------------------------------------------


def active_placement_id(store: EventStore) -> str | None:
    from english_trainer.kernel.aggregates import read_aggregate

    row = read_aggregate(store._conn, POINTER_AGGREGATE, POINTER_ID)
    if row is None:
        return None
    value = row[0].get("placement_id")
    return str(value) if value else None


def get_placement(store: EventStore, placement_id: str) -> tuple[dict[str, Any], int] | None:
    from english_trainer.kernel.aggregates import read_aggregate

    return read_aggregate(store._conn, PLACEMENT_AGGREGATE, placement_id)


# -- policy / pinning ---------------------------------------------------------


def ensure_policy(registry: PolicyRegistry, clock: Clock) -> str:
    """Register and activate the shipped assessments policy, idempotently.

    Registration is a no-op for identical content (foundation 3.6), and the
    version is only activated when nothing is active yet -- so this never
    disturbs an operator who pinned a different version.
    """
    require_valid(default_policy())
    registry.register(ASSESSMENTS_KIND, ASSESSMENTS_VERSION, default_policy())
    try:
        return registry.active_version(ASSESSMENTS_KIND)
    except NoActivePolicy:
        registry.activate(ASSESSMENTS_KIND, ASSESSMENTS_VERSION)
        return registry.active_version(ASSESSMENTS_KIND)


def _pin_versions(registry: PolicyRegistry, assessments_version: str) -> dict[str, str]:
    """Pin the active version of every known policy kind plus assessments."""
    pinned: dict[str, str] = {ASSESSMENTS_KIND: assessments_version}
    for kind in sorted(KNOWN_KINDS):
        try:
            pinned[kind] = registry.active_version(kind)
        except NoActivePolicy:
            continue
    return pinned


def _assessments_policy(registry: PolicyRegistry, manifest: dict[str, Any]) -> dict[str, Any]:
    """Resolve the placement's pinned assessments policy (never the active one)."""
    version = str(manifest.get("pinned_assessments_policy") or ASSESSMENTS_VERSION)
    return require_valid(registry.resolve_pinned(ASSESSMENTS_KIND, version))


# -- deterministic answer checking --------------------------------------------


def _normalize_answer(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def _objective_check(raw_answer: str, answer_key: Any) -> bool:
    variants = answer_key if isinstance(answer_key, list) else [answer_key]
    normalized = _normalize_answer(raw_answer)
    return any(_normalize_answer(str(variant)) == normalized for variant in variants)


# -- exposure -----------------------------------------------------------------


def prior_exposed_ids(store: EventStore, exclude_placement_id: str) -> set[str]:
    """Every ``item_exposure_id`` shown in a *different* placement (assessments 3).

    Read from the append-only checkpoint facts: an item the learner has already
    been shown is "re-seen" on any later placement, whatever that placement's
    outcome was.
    """
    seen: set[str] = set()
    for event in store.read():
        if event.type != EVENT_CHECKPOINT:
            continue
        if str(event.payload.get("placement_id")) == exclude_placement_id:
            continue
        for exposure_id in event.payload.get("item_exposure_ids", []):
            seen.add(str(exposure_id))
    return seen


def _applied_exposure_weight(exposure_id: str, prior: set[str], policy: dict[str, Any]) -> str:
    """The captured exposure weight: fresh for a first showing, down-weighted
    (or zeroed) for a re-seen item -- so a memorized form is not fresh evidence."""
    if exposure_id in prior:
        return str(policy["reseen_exposure_weight"])
    return str(policy["fresh_exposure_weight"])


# -- next section -------------------------------------------------------------


def next_unanswered_section(form: dict[str, Any], answered_sections: list[str]) -> str | None:
    for section in form_sections(form):
        if section not in answered_sections:
            return section
    return None


# -- start --------------------------------------------------------------------


def start_placement(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    form_selector: str | None = None,
    actor: str = "engine",
) -> dict[str, Any]:
    """Select a fixed form, pin the policies and open the placement.

    Refuses when another placement is still active: the contract keeps "start
    with abandon" as two explicit commands, so the caller abandons/submits the
    active one first.
    """
    assessments_version = ensure_policy(registry, clock)
    current = active_placement_id(store)
    if current is not None:
        raise PlacementPrecondition(
            f"placement {current} is still active; submit, abandon or let it expire first"
        )

    form = select_form(form_selector)
    pinned = _pin_versions(registry, assessments_version)
    placement_id = new_ulid(clock, random_source)
    started_at = clock.now().isoformat()
    manifest: dict[str, Any] = {
        "placement_id": placement_id,
        "form_version": str(form["form_version"]),
        "seed": str(form["seed"]),
        "started_at": started_at,
        "pinned_versions": pinned,
        "pinned_assessments_policy": assessments_version,
        "sections": form_sections(form),
    }
    state: dict[str, Any] = {
        "status": STARTED,
        "manifest": manifest,
        "last_activity_at": started_at,
        "answers": {},
        "answered_sections": [],
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(PLACEMENT_AGGREGATE, placement_id, state, expected_revision=0)
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is None:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"placement_id": placement_id}, expected_revision=0
            )
        else:
            pstate, prevision = pointer
            if pstate.get("placement_id"):
                raise PlacementPrecondition("another placement became active concurrently")
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"placement_id": placement_id}, expected_revision=prevision
            )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_STARTED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=placement_id,
                    payload={"manifest": manifest},
                    pinned_versions=pinned,
                )
            ]
        )

    # The agent presents item prompts verbatim; the answer keys stay engine-side.
    items = [
        {
            "item_id": item["item_id"],
            "section": item["section"],
            "kind": item["kind"],
            "prompt": item["prompt"],
            "target_ref": item["target_ref"],
            "dimension": item["dimension"],
        }
        for item in form["items"]
    ]
    return {
        "placement_id": placement_id,
        "status": STARTED,
        "form_version": manifest["form_version"],
        "seed": manifest["seed"],
        "pinned_versions": pinned,
        "pinned_assessments_policy": assessments_version,
        "sections": manifest["sections"],
        "items": items,
    }


# -- answer (checkpoint) ------------------------------------------------------


def answer_placement(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    placement_id: str,
    *,
    section: str,
    answers: dict[str, str],
    actor: str = "agent",
) -> dict[str, Any]:
    """Incrementally record one section's answers (checkpoint -> IN_PROGRESS)."""
    found = get_placement(store, placement_id)
    if found is None:
        raise PlacementPrecondition(f"placement {placement_id} does not exist")
    state, revision = found
    status = str(state.get("status"))
    if status not in _ACTIVE_STATES:
        raise PlacementPrecondition(
            f"placement {placement_id} is {status}; answers attach only to an active placement"
        )
    manifest = state.get("manifest") or {}
    form = select_form(str(manifest.get("form_version")))
    if section not in form_sections(form):
        raise PlacementPrecondition(f"section {section!r} is not part of form {manifest.get('form_version')}")
    if not isinstance(answers, dict) or not answers:
        raise PlacementPrecondition("answers must be a non-empty object keyed by item id")

    valid_item_ids = {item["item_id"] for item in section_items(form, section)}
    accepted: dict[str, str] = {}
    for item_id, raw in answers.items():
        if item_id not in valid_item_ids:
            raise PlacementPrecondition(f"item {item_id!r} is not in section {section!r}")
        accepted[str(item_id)] = str(raw)

    merged_answers = {**state.get("answers", {})}
    section_answers = {**merged_answers.get(section, {}), **accepted}
    merged_answers[section] = section_answers
    answered_sections = list(state.get("answered_sections", []))
    if section not in answered_sections:
        answered_sections.append(section)

    form_version = str(manifest.get("form_version"))
    exposure_ids = sorted(item_exposure_id(form_version, item_id) for item_id in accepted)
    answered_at = clock.now().isoformat()
    new_state = {
        **state,
        "status": IN_PROGRESS,
        "answers": merged_answers,
        "answered_sections": answered_sections,
        "last_activity_at": answered_at,
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(PLACEMENT_AGGREGATE, placement_id, new_state, expected_revision=revision)
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_CHECKPOINT,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=placement_id,
                    payload={
                        "placement_id": placement_id,
                        "section": section,
                        "item_ids": sorted(accepted),
                        "item_exposure_ids": exposure_ids,
                        "answered_at": answered_at,
                    },
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return {
        "placement_id": placement_id,
        "status": IN_PROGRESS,
        "section": section,
        "answered_items": sorted(accepted),
        "next_section": next_unanswered_section(form, answered_sections),
    }


# -- resume / expiry ----------------------------------------------------------


def expiry_boundary(state: dict[str, Any], policy: dict[str, Any]) -> datetime:
    """The deterministic expiry instant: ``last_activity_at`` + resume window."""
    last = datetime.fromisoformat(str(state["last_activity_at"]))
    return last + resume_window(policy)


def _expire(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    placement_id: str,
    state: dict[str, Any],
    revision: int,
    *,
    boundary: datetime,
    pinned_assessments_policy: str,
    actor: str,
) -> DomainEvent:
    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            PLACEMENT_AGGREGATE,
            placement_id,
            {**state, "status": EXPIRED, "closed_at": boundary.isoformat()},
            expected_revision=revision,
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("placement_id") == placement_id:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"placement_id": None}, expected_revision=pointer[1]
            )
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_EXPIRED,
                    # The deterministic boundary crossing, NOT the sweep's clock
                    # (same rule as OVERDUE_AT_RISK_TRIGGERED): replay reproduces it.
                    occurred_at=boundary,
                    actor=actor,
                    correlation_id=placement_id,
                    payload={
                        "placement_id": placement_id,
                        "boundary_at": boundary.isoformat(),
                        "last_activity_at": str(state.get("last_activity_at")),
                        "pinned_assessments_policy": pinned_assessments_policy,
                    },
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return event


def resume_placement(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    placement_id: str,
    *,
    actor: str = "agent",
) -> dict[str, Any]:
    """Return state + the next section, within the resume window.

    Past the window the placement is terminalized ``EXPIRED`` (append-only,
    replayable) and resume is refused: a diagnostic answered with a week-long
    gap is not one measurement.
    """
    found = get_placement(store, placement_id)
    if found is None:
        raise PlacementPrecondition(f"placement {placement_id} does not exist")
    state, revision = found
    status = str(state.get("status"))
    if status in _TERMINAL_STATES:
        raise PlacementPrecondition(f"placement {placement_id} is {status}; nothing to resume")

    manifest = state.get("manifest") or {}
    policy = _assessments_policy(registry, manifest)
    boundary = expiry_boundary(state, policy)
    version = str(manifest.get("pinned_assessments_policy") or ASSESSMENTS_VERSION)
    if clock.now() >= boundary:
        _expire(
            store,
            clock,
            random_source,
            placement_id,
            state,
            revision,
            boundary=boundary,
            pinned_assessments_policy=version,
            actor="engine",
        )
        raise PlacementPrecondition(
            f"placement {placement_id} expired at {boundary.isoformat()} "
            "(resume window elapsed); start a new placement"
        )

    form = select_form(str(manifest.get("form_version")))
    answered_sections = list(state.get("answered_sections", []))
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_RESUMED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=placement_id,
                    payload={
                        "placement_id": placement_id,
                        "resumed_at": clock.now().isoformat(),
                        "answered_sections": answered_sections,
                    },
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return {
        "placement_id": placement_id,
        "status": status,
        "form_version": manifest.get("form_version"),
        "answered_sections": answered_sections,
        "next_section": next_unanswered_section(form, answered_sections),
        "boundary_at": boundary.isoformat(),
    }


def sweep_expired_placements(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    actor: str = "engine",
) -> list[str]:
    """Terminalize the active placement if its window has elapsed.

    Append-only and deterministic: emits ``PLACEMENT_EXPIRED`` at the derived
    ``boundary_at``. At most one placement is active (singleton pointer), and a
    re-run finds it already ``EXPIRED`` and mints nothing. Returns the expired
    placement ids.
    """
    placement_id = active_placement_id(store)
    if placement_id is None:
        return []
    found = get_placement(store, placement_id)
    if found is None:
        return []
    state, revision = found
    if str(state.get("status")) not in _ACTIVE_STATES:
        return []
    manifest = state.get("manifest") or {}
    policy = _assessments_policy(registry, manifest)
    boundary = expiry_boundary(state, policy)
    if clock.now() < boundary:
        return []
    _expire(
        store,
        clock,
        random_source,
        placement_id,
        state,
        revision,
        boundary=boundary,
        pinned_assessments_policy=str(manifest.get("pinned_assessments_policy") or ASSESSMENTS_VERSION),
        actor=actor,
    )
    return [placement_id]


# -- submit (score) -----------------------------------------------------------


def _score_answers(
    store: EventStore,
    form: dict[str, Any],
    manifest: dict[str, Any],
    answers: dict[str, dict[str, str]],
    policy: dict[str, Any],
    placement_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Grade answered items into (scored_item rows, evidence payloads, outcome
    payloads). Correct objective items with non-zero exposure weight become
    ``origin=placement`` evidence + a CONFIRMED outcome; re-seen (zeroed) items
    and writing items are recorded non-contributing."""
    form_version = str(manifest["form_version"])
    prior = prior_exposed_ids(store, placement_id)
    scored_items: list[dict[str, Any]] = []
    evidence_payloads: list[dict[str, Any]] = []
    outcome_payloads: list[dict[str, Any]] = []

    for section in form_sections(form):
        section_answers = answers.get(section, {})
        for item in section_items(form, section):
            item_id = item["item_id"]
            if item_id not in section_answers:
                continue
            raw = section_answers[item_id]
            exposure_id = item_exposure_id(form_version, item_id)
            weight = _applied_exposure_weight(exposure_id, prior, policy)
            contributing_weight = Decimal(weight) > 0
            target_ref = item["target_ref"]
            dimension = item["dimension"]
            row: dict[str, Any] = {
                "item_id": item_id,
                "section": section,
                "target_ref": target_ref,
                "dimension": dimension,
                "item_exposure_id": exposure_id,
                "applied_exposure_weight": weight,
                "kind": item["kind"],
            }
            if item["kind"] == WRITING:
                # Provisional-only: a placement has no session/rubric context to
                # produce a measured level (deferred, П). Recorded for audit.
                row.update({"basis": "writing_provisional", "correct": None, "contributing": False})
                scored_items.append(row)
                continue
            if item["kind"] != OBJECTIVE:
                row.update({"basis": "unknown_kind", "correct": None, "contributing": False})
                scored_items.append(row)
                continue

            correct = _objective_check(raw, item.get("answer_key"))
            contributing = bool(correct and contributing_weight)
            row.update({"basis": "objective_check", "correct": correct, "contributing": contributing})
            scored_items.append(row)
            if not contributing:
                continue
            span_hash = payload_hash({"raw_answer": raw, "item_exposure_id": exposure_id})
            evidence_payloads.append(
                {
                    "evidence_id": None,  # filled with a fresh id at emit time
                    "placement_id": placement_id,
                    "session_id": placement_id,
                    "item_id": item_id,
                    "item_exposure_id": exposure_id,
                    "applied_exposure_weight": weight,
                    "origin": "placement",
                    "mode": dimension,
                    "primary_target": {"target_ref": target_ref, "dimension": dimension},
                    "selection_basis": "declared_item_target",
                    "assessment_basis": "objective_check",
                    "correct": True,
                    "score_ppm": 1_000_000,
                    "hints": 0,
                    "span_hash": span_hash,
                    "credit_allocations": [
                        {
                            "target_ref": target_ref,
                            "dimension": dimension,
                            "contribution": "1.0",
                            "used": True,
                            "reason": "primary",
                        }
                    ],
                }
            )
            outcome_payloads.append(
                {
                    "target_ref": target_ref,
                    "dimension": dimension,
                    "outcome": "CONFIRMED",
                    "origin": "placement",
                    "placement_id": placement_id,
                    "item_id": item_id,
                    "item_exposure_id": exposure_id,
                    "applied_exposure_weight": weight,
                }
            )
    return scored_items, evidence_payloads, outcome_payloads


def submit_placement(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    placement_id: str,
    *,
    actor: str = "engine",
) -> dict[str, Any]:
    """Terminal, idempotent submit: grade the form and hand off to scoring.

    One submit per form. A repeat returns the stored scored result and mints no
    new events (the placement is already ``SCORED``). ``origin=placement``
    evidence and outcomes carry the ACTIVE ceiling that scoring enforces.
    """
    found = get_placement(store, placement_id)
    if found is None:
        raise PlacementPrecondition(f"placement {placement_id} does not exist")
    state, revision = found
    status = str(state.get("status"))
    if status in (SUBMITTED, SCORED):
        prior_result = dict(state.get("scored_result") or {})
        return {**prior_result, "placement_id": placement_id, "status": SCORED, "already": True}
    if status != IN_PROGRESS:
        raise PlacementPrecondition(
            f"placement {placement_id} is {status}: only an IN_PROGRESS placement can be submitted "
            "(a placement with no answers is abandoned, not submitted)"
        )

    manifest = state.get("manifest") or {}
    pinned = dict(manifest.get("pinned_versions") or {})
    policy = _assessments_policy(registry, manifest)
    form = select_form(str(manifest.get("form_version")))
    answers: dict[str, dict[str, str]] = dict(state.get("answers") or {})

    scored_items, evidence_payloads, outcome_payloads = _score_answers(
        store, form, manifest, answers, policy, placement_id
    )
    submitted_at = clock.now().isoformat()
    scored_result = {
        "form_version": manifest.get("form_version"),
        "scored_items": scored_items,
        "evidence_count": len(evidence_payloads),
        "outcome_count": len(outcome_payloads),
        "scored_at": submitted_at,
    }

    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            PLACEMENT_AGGREGATE,
            placement_id,
            {**state, "status": SCORED, "closed_at": submitted_at, "scored_result": scored_result},
            expected_revision=revision,
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("placement_id") == placement_id:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"placement_id": None}, expected_revision=pointer[1]
            )
        submitted_event = make_event(
            id=new_ulid(clock, random_source),
            type=EVENT_SUBMITTED,
            occurred_at=clock.now(),
            actor=actor,
            correlation_id=placement_id,
            payload={"placement_id": placement_id, "form_version": manifest.get("form_version")},
            pinned_versions=pinned,
        )
        evidence_events = [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVIDENCE_ADDED_EVENT,
                occurred_at=clock.now(),
                actor=actor,
                correlation_id=placement_id,
                payload={
                    **payload,
                    "evidence_id": new_ulid(clock, random_source),
                    "recorded_at": submitted_at,
                },
                pinned_versions=pinned,
            )
            for payload in evidence_payloads
        ]
        outcome_events = [
            make_event(
                id=new_ulid(clock, random_source),
                type=REVIEW_OUTCOME_EVENT,
                occurred_at=clock.now(),
                actor=actor,
                correlation_id=placement_id,
                payload=payload,
                pinned_versions=pinned,
            )
            for payload in outcome_payloads
        ]
        transition_events = []
        state_overrides: dict[str, tuple[str, str | None]] = {}
        for outcome_event in outcome_events:
            target_ref = str(outcome_event.payload["target_ref"])
            transition_event = build_state_transition(
                store,
                registry,
                outcome_event,
                before_override=state_overrides.get(target_ref),
            )
            if transition_event is not None:
                transition_events.append(transition_event)
                state_overrides[target_ref] = (
                    str(transition_event.payload["to_state"]),
                    None,
                )
        scored_event = make_event(
            id=new_ulid(clock, random_source),
            type=EVENT_SCORED,
            occurred_at=clock.now(),
            actor=actor,
            correlation_id=placement_id,
            payload={"placement_id": placement_id, **scored_result},
            pinned_versions=pinned,
        )
        uow.append([submitted_event, *evidence_events, *outcome_events, *transition_events, scored_event])

    return {**scored_result, "placement_id": placement_id, "status": SCORED, "already": False}


# -- abandon ------------------------------------------------------------------


def abandon_placement(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    placement_id: str,
    *,
    actor: str = "engine",
) -> DomainEvent:
    """STARTED | IN_PROGRESS -> ABANDONED. Forbidden after SUBMITTED/SCORED."""
    found = get_placement(store, placement_id)
    if found is None:
        raise PlacementPrecondition(f"placement {placement_id} does not exist")
    state, revision = found
    status = str(state.get("status"))
    if status not in _ACTIVE_STATES:
        raise PlacementPrecondition(
            f"placement {placement_id} is {status}; abandon is allowed only from STARTED/IN_PROGRESS"
        )
    manifest = state.get("manifest") or {}
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            PLACEMENT_AGGREGATE,
            placement_id,
            {**state, "status": ABANDONED, "closed_at": clock.now().isoformat()},
            expected_revision=revision,
        )
        pointer = uow.get_aggregate(POINTER_AGGREGATE, POINTER_ID)
        if pointer is not None and pointer[0].get("placement_id") == placement_id:
            uow.save_aggregate(
                POINTER_AGGREGATE, POINTER_ID, {"placement_id": None}, expected_revision=pointer[1]
            )
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_ABANDONED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=placement_id,
                    payload={"placement_id": placement_id, "from_status": status},
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return event


# -- decline ------------------------------------------------------------------


def decline_placement(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    *,
    self_assessment: Any | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Record a declined placement, optionally with a per-skill self-assessment.

    Declining blocks nothing. ``self_assessment`` MUST be the per-core-skill
    object (a scalar is refused); each reported level is written to that skill's
    ``self_reported_level`` as a provisional estimate, fully overridden by the
    first admissible evidence for that skill (learner model, out of scope here).
    Missing skills stay ``unknown`` -- no default, no broadcast.
    """
    assessments_version = ensure_policy(registry, clock)
    reported: dict[str, str] = {}
    if self_assessment is not None:
        reported = normalize_self_assessment(
            self_assessment, core_skills=CORE_SKILLS, cefr_levels=CEFR_LEVELS
        )
    pinned = _pin_versions(registry, assessments_version)
    placement_id = new_ulid(clock, random_source)
    declined_at = clock.now().isoformat()
    with UnitOfWork(store, clock) as uow:
        uow.save_aggregate(
            PLACEMENT_AGGREGATE,
            placement_id,
            {
                "status": DECLINED,
                "manifest": {
                    "placement_id": placement_id,
                    "pinned_versions": pinned,
                    "pinned_assessments_policy": assessments_version,
                },
                "self_reported_levels": reported,
                "declined_at": declined_at,
            },
            expected_revision=0,
        )
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_DECLINED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=placement_id,
                    payload={
                        "placement_id": placement_id,
                        "schema_version": SELF_ASSESSMENT_SCHEMA_VERSION,
                        # Per-skill self_reported_level for exactly the reported
                        # skills; absent skills are unknown, never defaulted.
                        "self_reported_levels": reported,
                        "declined_at": declined_at,
                        "pinned_assessments_policy": assessments_version,
                    },
                    pinned_versions=pinned,
                )
            ]
        )
    return {
        "placement_id": placement_id,
        "status": DECLINED,
        "self_reported_levels": reported,
    }
