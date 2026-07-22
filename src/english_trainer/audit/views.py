"""Deterministic read models over the authoritative event table."""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.envelopes import DomainEvent
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore

_SELF_REPORTS = {"skill.started", "skill.completed", "skill.failed"}
_TERMINAL_SESSIONS = {"session.finished", "session.abandoned", "session.stale_abandoned"}
_CLI_TERMINAL = "cli.command_terminated"


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
            if event.payload.get("command") in {"session.finish", "session.abandon"}
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
        elif obligation_id == "correction_protocol":
            applicable = any(event.type == "evidence.error_observed" for event in session_events)
            needed = ("attempt.finalize", "review.close")
            effects: list[DomainEvent] = []
            if applicable:
                for command in needed:
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
            observations.append(
                {
                    "obligation_id": obligation_id,
                    "instance": session_id,
                    "applicable": applicable,
                    "satisfied": applicable and len(effects) == len(needed),
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

    return {
        "session_id": session_id,
        "status": "complete",
        "policy_id": policy.get("policy_id"),
        "observations": observations,
    }
