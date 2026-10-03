"""Deterministic read models over the authoritative event table."""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.aggregates import list_aggregates, read_aggregate
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

_SELF_REPORTS = {"skill.started", "skill.completed", "skill.failed"}
_TERMINAL_SESSIONS = {"session.finished", "session.abandoned", "session.stale_abandoned"}
_CLI_TERMINAL = "cli.command_terminated"

# obligations@4 [PD-2026-09-23]: event/aggregate names local to audit -- the
# module must not import lessons (LAYER_ALLOWLIST, tests/architecture/
# test_boundaries.py), so the brief/report protocol's facts are named here by
# their event-log spelling, not imported as constants from their producer.
_EVENT_SESSION_STARTED = "session.started"
_EVENT_SESSION_FINISHED = "session.finished"
_EVENT_LESSON_REPORTED = "lesson.reported"
_EVENT_REVIEW_OUTCOME = "review.outcome"
_EVENT_REVIEW_ASSIGNMENT_CANCELLED = "review.assignment_cancelled"
# review_assignment is SQLite-authoritative operational state, not
# event-sourced (audit 4 -- foundation 3.5): there is no domain event for
# assignment CREATION, only for its terminal disposition, so enumerating
# "every review assignment of the session" reads the aggregate table. The
# observation this produces is labelled `snapshot_source` rather than folded
# in as an indistinguishable replayed fact.
_REVIEW_ASSIGNMENT_AGGREGATE = "review_assignment"


class ObligationPolicyInvalid(KernelError):
    code = "OBLIGATION_POLICY_INVALID"


def _event_dict(event: DomainEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def _sorted(events: list[DomainEvent]) -> list[DomainEvent]:
    return sorted(events, key=lambda event: int(event.sequence or 0))


def session_view(store: EventStore, session_id: str) -> dict[str, Any]:
    """Return session-correlated facts plus linked CLI transport facts."""
    all_events = list(store.read())
    selected = [
        event
        for event in all_events
        if event.correlation_id == session_id or event.payload.get("session_id") == session_id
    ]
    linked_ids = {str(event.causation_id) for event in selected if event.causation_id}
    selected.extend(event for event in all_events if event.id in linked_ids and event not in selected)
    aggregate = read_aggregate(store._conn, "session", session_id)
    return {
        "key_kind": "session",
        "key": session_id,
        "events": [_event_dict(event) for event in _sorted(selected)],
        "operational_snapshot": (
            {"state": aggregate[0], "revision": aggregate[1]} if aggregate is not None else None
        ),
        "complete": any(event.type in _TERMINAL_SESSIONS for event in selected),
    }


def correlation_view(store: EventStore, correlation_id: str) -> dict[str, Any]:
    events = [event for event in store.read() if event.correlation_id == correlation_id]
    return {
        "key_kind": "correlation",
        "key": correlation_id,
        "events": [_event_dict(event) for event in _sorted(events)],
        "complete": any(event.type == _CLI_TERMINAL for event in events),
    }


def target_history(store: EventStore, target_id: str, dimension: str | None = None) -> dict[str, Any]:
    events = [
        event
        for event in store.read()
        if event.payload.get("target_ref") == target_id
        and (dimension is None or event.payload.get("dimension") == dimension)
    ]
    return {
        "key_kind": "target",
        "key": target_id,
        "dimension": dimension,
        "events": [_event_dict(event) for event in _sorted(events)],
        "complete": True,
    }


def _session_pinned_obligations(events: list[DomainEvent], registry: PolicyRegistry) -> dict[str, Any]:
    started = next((event for event in events if event.type == "session.started"), None)
    if started is None:
        raise ObligationPolicyInvalid("session has no session.started fact")
    manifest = dict(started.payload.get("manifest") or {})
    version = dict(manifest.get("pinned_versions") or {}).get("obligations")
    if version is None:
        raise ObligationPolicyInvalid("session did not pin an obligations policy")
    return registry.resolve_pinned("obligations", str(version))


def _terminal_cli(events: list[DomainEvent], session_id: str) -> list[DomainEvent]:
    return [
        event
        for event in events
        if event.type == _CLI_TERMINAL and event.payload.get("session_id") == session_id
    ]


def obligations(store: EventStore, registry: PolicyRegistry, session_id: str) -> dict[str, Any]:
    """Correlate one fully observed terminal session under its pinned policy."""
    events = list(store.read())
    session_events = [
        event
        for event in events
        if event.correlation_id == session_id or event.payload.get("session_id") == session_id
    ]
    terminal = next((event for event in session_events if event.type in _TERMINAL_SESSIONS), None)
    cli = _terminal_cli(events, session_id)
    terminal_cli = next(
        (
            event
            for event in cli
            # `session.report` commits the lesson report and finishes the
            # session in one transaction (brief/report protocol [PD-2026-09-23]).
            if event.payload.get("command") in {"session.finish", "session.abandon", "session.report"}
            and event.payload.get("outcome") == "success"
        ),
        None,
    )
    if terminal is None or terminal_cli is None:
        return {
            "session_id": session_id,
            "status": "no-data",
            "reason": "session is not a fully observed terminal CLI session",
            "observations": [],
        }
    try:
        policy = _session_pinned_obligations(session_events, registry)
    except KernelError as exc:
        return {
            "session_id": session_id,
            "status": "no-data",
            "reason": str(exc),
            "observations": [],
        }

    definitions = {str(item["obligation_id"]): item for item in policy.get("obligations") or []}
    order = [str(item) for item in policy.get("matching_order") or []]
    if set(order) != set(definitions):
        raise ObligationPolicyInvalid("matching_order must name every obligation exactly once")

    if str(policy.get("policy_id")) == "obligations@4":
        # obligations@4 [PD-2026-09-23] observes the brief/report protocol: a
        # dedicated evaluator, selected by the session's own pinned version,
        # so obligations@1/@2/@3 keep resolving exactly as they always have
        # for sessions that pinned one of them (audit 4).
        observations = _obligations_v4(
            store, session_events, cli, order, definitions, session_id, terminal, terminal_cli
        )
    else:
        observations = _obligations_legacy(
            session_events, cli, order, definitions, session_id, terminal, terminal_cli
        )

    return {
        "session_id": session_id,
        "status": "complete",
        "policy_id": policy.get("policy_id"),
        "observations": observations,
    }


def _obligations_legacy(
    session_events: list[DomainEvent],
    cli: list[DomainEvent],
    order: list[str],
    definitions: dict[str, dict[str, Any]],
    session_id: str,
    terminal: DomainEvent,
    terminal_cli: DomainEvent,
) -> list[dict[str, Any]]:
    """obligations@1/@2/@3, unchanged: the exact matcher those policies were
    accepted against (audit 4, [PD-2026-07-22]/[PD-2026-07-23]/[PD-2026-09-22])."""
    consumed_effects: set[str] = set()
    observations: list[dict[str, Any]] = []

    for obligation_id in order:
        definition = definitions[obligation_id]
        if obligation_id == "required_skill_effect":
            required = [event for event in session_events if event.type == "skill.required"]
            for requirement in required:
                reports = [
                    event
                    for event in session_events
                    if event.type == "skill.completed"
                    and event.payload.get("skill_name") == requirement.payload.get("skill_name")
                    and event.payload.get("version") == requirement.payload.get("version")
                ]
                allowed = set(requirement.payload.get("cli_calls") or [])
                effect = next(
                    (
                        event
                        for event in cli
                        if event.id not in consumed_effects
                        and event.payload.get("outcome") == "success"
                        and event.payload.get("command") in allowed
                    ),
                    None,
                )
                if effect is not None:
                    consumed_effects.add(effect.id)
                observations.append(
                    {
                        "obligation_id": obligation_id,
                        "instance": (
                            f"{requirement.payload.get('skill_name')}@{requirement.payload.get('version')}"
                        ),
                        "applicable": True,
                        "satisfied": effect is not None
                        and (bool(reports) or not definition.get("self_report_required")),
                        "observed_effects": [_event_dict(effect)] if effect is not None else [],
                        "self_report_events": [_event_dict(event) for event in reports],
                        "finding": (
                            "self_report_without_observed_effect"
                            if reports and effect is None
                            else "observed_effect_without_self_report"
                            if effect is not None and not reports
                            else None
                        ),
                    }
                )
        elif obligation_id == "lesson_preflight":
            started = next(
                (event for event in session_events if event.type == "session.started"),
                None,
            )
            manifest = dict((started.payload.get("manifest") or {}) if started else {})
            arc = dict(manifest.get("lesson_arc") or {})
            applicable = bool(arc)
            satisfied = applicable and all(
                arc.get(field)
                for field in (
                    "title",
                    "profile",
                    "reason",
                    "agenda",
                    "language_envelope",
                    "proposal_hash",
                )
            )
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": bool(satisfied),
                    "observed_effects": [_event_dict(started)] if started is not None else [],
                    "self_report_events": [],
                    "finding": None if satisfied else "lesson_preflight_missing",
                }
            )
        elif obligation_id == "teaching_snapshot":
            introductions = [
                event
                for event in session_events
                if event.type == "session.step_presented"
                and event.payload.get("step_type") == "new_material_intro"
            ]
            teaching_events = [event for event in session_events if event.type == "teaching.segment_rendered"]
            applicable = bool(introductions)
            satisfied = applicable and bool(teaching_events)
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": satisfied,
                    "observed_effects": [_event_dict(event) for event in teaching_events],
                    "self_report_events": [],
                    "finding": None if satisfied else "teaching_snapshot_missing",
                }
            )
        elif obligation_id == "delivery_protocol":
            # obligations@3 asks what actually protects the learner: the exact
            # prompt was persisted before the answer. obligations@2 asked only
            # that the snapshot follow STEP_PRESENTED; both readings stay
            # resolvable, chosen by the pinned policy's own required_effect.
            before_attempt = str(definition.get("required_effect")) == "exercise_rendered_before_attempt"
            structured = [
                event
                for event in session_events
                if event.type == "session.step_presented"
                and event.payload.get("step_type") not in ("new_material_intro", "free_conversation")
            ]
            rendered_by_step = {
                str(event.payload.get("step_id")): event
                for event in session_events
                if event.type == "exercise.rendered"
            }
            attempt_by_step: dict[str, DomainEvent] = {}
            for event in _sorted(session_events):
                if event.type == "attempt.recorded":
                    attempt_by_step.setdefault(str(event.payload.get("step_id")), event)
            if not structured:
                observations.append(
                    {
                        "obligation_id": obligation_id,
                        "instance": session_id,
                        "applicable": False,
                        "satisfied": False,
                        "observed_effects": [],
                        "self_report_events": [],
                        "finding": None,
                    }
                )
            for presented in structured:
                step_id = str(presented.payload.get("step_id"))
                exercise_event = rendered_by_step.get(step_id)
                ordered = exercise_event is not None and int(exercise_event.sequence or 0) > int(
                    presented.sequence or 0
                )
                if ordered and before_attempt and exercise_event is not None:
                    attempt_event = attempt_by_step.get(step_id)
                    ordered = attempt_event is None or int(exercise_event.sequence or 0) < int(
                        attempt_event.sequence or 0
                    )
                observations.append(
                    {
                        "obligation_id": obligation_id,
                        "instance": step_id,
                        "applicable": True,
                        "satisfied": ordered,
                        "observed_effects": (
                            [_event_dict(presented), _event_dict(exercise_event)]
                            if exercise_event is not None
                            else [_event_dict(presented)]
                        ),
                        "self_report_events": [],
                        "finding": None if ordered else "exercise_snapshot_missing_or_out_of_order",
                    }
                )
        elif obligation_id == "correction_protocol":
            applicable = any(event.type == "evidence.error_observed" for event in session_events)
            required_effects = [str(item) for item in definition.get("required_effects") or []]
            effects: list[DomainEvent] = []
            if applicable and "attempt_assessed" in required_effects:
                # obligations@3 asks for the OUTCOME, not for two particular
                # commands: an attempt that reached `assessed` (the single-call
                # record with observations, a drill block, or the two-call
                # recovery path) and a review closed by the agent through
                # either trigger. Both are domain facts, so a shorter protocol
                # that produces them is compliant, and a self-report that
                # produces neither still is not.
                assessed = next(
                    (
                        event
                        for event in _sorted(session_events)
                        if (event.type == "attempt.recorded" and event.payload.get("status") == "assessed")
                        or (
                            event.type == "attempt.state_changed"
                            and event.payload.get("to_status") == "assessed"
                        )
                    ),
                    None,
                )
                # Agent-actor only: the INSUFFICIENT_EVIDENCE outcomes that
                # `abandon` writes are the engine closing what the tutor left
                # open, and must never satisfy the correction protocol.
                closed = next(
                    (
                        event
                        for event in _sorted(session_events)
                        if event.type == "review.outcome" and event.actor == "agent"
                    ),
                    None,
                )
                effects = [event for event in (assessed, closed) if event is not None]
                satisfied = assessed is not None and closed is not None
            elif applicable:
                for command in ("attempt.finalize", "review.close"):
                    effect = next(
                        (
                            event
                            for event in cli
                            if event.id not in consumed_effects
                            and event.payload.get("outcome") == "success"
                            and event.payload.get("command") == command
                        ),
                        None,
                    )
                    if effect is not None:
                        consumed_effects.add(effect.id)
                        effects.append(effect)
                satisfied = len(effects) == 2
            else:
                satisfied = False
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": applicable and satisfied,
                    "observed_effects": [_event_dict(event) for event in effects],
                    "self_report_events": [],
                    "finding": None,
                }
            )
        elif obligation_id == "forbidden_action_absence":
            forbidden = set(definition.get("forbidden_error_codes") or [])
            violations = [event for event in cli if event.payload.get("error_code") in forbidden]
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": True,
                    "satisfied": not violations,
                    "observed_effects": [_event_dict(terminal), _event_dict(terminal_cli)],
                    "self_report_events": [],
                    "finding": "forbidden_action_observed" if violations else None,
                }
            )
        else:
            raise ObligationPolicyInvalid(f"unsupported obligation {obligation_id!r}")

    return observations


def _obligations_v4(
    store: EventStore,
    session_events: list[DomainEvent],
    cli: list[DomainEvent],
    order: list[str],
    definitions: dict[str, dict[str, Any]],
    session_id: str,
    terminal: DomainEvent,
    terminal_cli: DomainEvent,
) -> list[dict[str, Any]]:
    """obligations@4 [PD-2026-09-23]: the brief/report protocol replaces
    per-step delivery and engine-graded correction with one committed report,
    so `delivery_protocol`/`correction_protocol` (and the now-meaningless
    `teaching_snapshot`) are gone. Two outcome-shaped obligations take their
    place: the report itself must land before the session closes
    (`report_committed`), and every review the session assigned must reach a
    terminal disposition (`reviews_addressed`). `forbidden_action_absence` is
    unchanged in meaning from @1-@3. `required_skill_effect`'s required
    *effect* is unchanged, but what counts as its self-report widens: the
    lean protocol has no separate `skills report` call, so a `lesson.reported`
    event now also satisfies `self_report_required` [PD-2026-09-23]."""
    consumed_effects: set[str] = set()
    observations: list[dict[str, Any]] = []

    for obligation_id in order:
        definition = definitions[obligation_id]
        if obligation_id == "required_skill_effect":
            required = [event for event in session_events if event.type == "skill.required"]
            # obligations@4 [PD-2026-09-23]: the brief/report protocol has no
            # separate `skills report` self-report call left to make -- the
            # lesson report IS the tutor's self-report (staging/journal/
            # 2026-09-23-lesson-brief-report-concept.md). A `lesson.reported`
            # event filed by the agent, with its provider set, satisfies
            # `self_report_required` for every skill this session pinned via
            # `skill.required`, exactly as a `skill.completed` self-report
            # would; it is recorded in `self_report_events`, never folded into
            # `observed_effects` (audit §4's self-report/observed split).
            lesson_reports = [
                event
                for event in session_events
                if event.type == _EVENT_LESSON_REPORTED and event.actor == "agent" and event.provider
            ]
            for requirement in required:
                reports = [
                    event
                    for event in session_events
                    if event.type == "skill.completed"
                    and event.payload.get("skill_name") == requirement.payload.get("skill_name")
                    and event.payload.get("version") == requirement.payload.get("version")
                ] + lesson_reports
                allowed = set(requirement.payload.get("cli_calls") or [])
                effect = next(
                    (
                        event
                        for event in cli
                        if event.id not in consumed_effects
                        and event.payload.get("outcome") == "success"
                        and event.payload.get("command") in allowed
                    ),
                    None,
                )
                if effect is not None:
                    consumed_effects.add(effect.id)
                observations.append(
                    {
                        "obligation_id": obligation_id,
                        "instance": (
                            f"{requirement.payload.get('skill_name')}@{requirement.payload.get('version')}"
                        ),
                        "applicable": True,
                        "satisfied": effect is not None
                        and (bool(reports) or not definition.get("self_report_required")),
                        "observed_effects": [_event_dict(effect)] if effect is not None else [],
                        "self_report_events": [_event_dict(event) for event in reports],
                        "finding": (
                            "self_report_without_observed_effect"
                            if reports and effect is None
                            else "observed_effect_without_self_report"
                            if effect is not None and not reports
                            else None
                        ),
                    }
                )
        elif obligation_id == "lesson_preflight":
            # The brief/report protocol always starts a session with an
            # explicit `--profile` (interface table, staging concept
            # 2026-09-23): what protects the learner is that the pinned
            # manifest names it, not the richer title/reason/agenda snapshot
            # obligations@2/@3 asked for.
            started = next((event for event in session_events if event.type == _EVENT_SESSION_STARTED), None)
            manifest = dict((started.payload.get("manifest") or {}) if started else {})
            satisfied = bool(manifest.get("lesson_profile"))
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": True,
                    "satisfied": satisfied,
                    "observed_effects": [_event_dict(started)] if started is not None else [],
                    "self_report_events": [],
                    "finding": None if satisfied else "lesson_preflight_missing",
                }
            )
        elif obligation_id == "report_committed":
            reported = next(
                (event for event in _sorted(session_events) if event.type == _EVENT_LESSON_REPORTED), None
            )
            finished = next(
                (event for event in session_events if event.type == _EVENT_SESSION_FINISHED), None
            )
            applicable = finished is not None
            satisfied = bool(
                finished is not None
                and reported is not None
                and int(reported.sequence or 0) < int(finished.sequence or 0)
            )
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": satisfied,
                    "observed_effects": [
                        _event_dict(event) for event in (reported, finished) if event is not None
                    ],
                    "self_report_events": [],
                    "finding": None if (not applicable or satisfied) else "report_missing_or_out_of_order",
                }
            )
        elif obligation_id == "reviews_addressed":
            # review_assignment CREATION is not event-sourced (see
            # `_REVIEW_ASSIGNMENT_AGGREGATE` above): enumerate the session's
            # assignments from the operational snapshot and correlate each
            # against the events that close it.
            assignments = [
                (review_id, state)
                for review_id, state, _ in list_aggregates(store._conn, _REVIEW_ASSIGNMENT_AGGREGATE)
                if state.get("session_id") == session_id
            ]
            outcome_by_review: dict[str, DomainEvent] = {}
            for event in _sorted(session_events):
                if event.type == _EVENT_REVIEW_OUTCOME:
                    outcome_by_review.setdefault(str(event.payload.get("review_id")), event)
            cancelled_by_review = {
                str(event.payload.get("review_id")): event
                for event in session_events
                if event.type == _EVENT_REVIEW_ASSIGNMENT_CANCELLED
            }
            applicable = bool(assignments)
            unaddressed: list[str] = []
            effects: list[DomainEvent] = []
            for review_id, _state in assignments:
                outcome_event = outcome_by_review.get(review_id)
                cancelled_event = cancelled_by_review.get(review_id)
                if outcome_event is not None:
                    reason = outcome_event.payload.get("reason")
                    if outcome_event.payload.get("outcome") == "INSUFFICIENT_EVIDENCE" and not reason:
                        unaddressed.append(review_id)
                    else:
                        effects.append(outcome_event)
                elif cancelled_event is not None:
                    effects.append(cancelled_event)
                else:
                    unaddressed.append(review_id)
            satisfied = bool(applicable and not unaddressed)
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": satisfied,
                    "observed_effects": [_event_dict(event) for event in effects],
                    "self_report_events": [],
                    # A session with no review assignments is not-applicable,
                    # not violating: mirror report_committed's convention
                    # (satisfied stays False, finding stays None) rather than
                    # naming a violation ("reviews_left_unaddressed") that
                    # never happened.
                    "finding": None if (not applicable or satisfied) else "reviews_left_unaddressed",
                    "snapshot_source": _REVIEW_ASSIGNMENT_AGGREGATE,
                }
            )
        elif obligation_id == "forbidden_action_absence":
            forbidden = set(definition.get("forbidden_error_codes") or [])
            violations = [event for event in cli if event.payload.get("error_code") in forbidden]
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": True,
                    "satisfied": not violations,
                    "observed_effects": [_event_dict(terminal), _event_dict(terminal_cli)],
                    "self_report_events": [],
                    "finding": "forbidden_action_observed" if violations else None,
                }
            )
        else:
            raise ObligationPolicyInvalid(f"unsupported obligation {obligation_id!r}")

    return observations
