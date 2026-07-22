"""Versioned tunable catalogue and propose/confirm calibration workflow.

The catalogue contains metadata and ranges only.  Active values continue to
live in their owner policies, so replay has one source of truth.
"""

from __future__ import annotations

from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import Any

from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError, NoActivePolicy
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

TUNABLES_KIND = "tunables"
TUNABLES_VERSION = "tunables@1"
EVENT_CALIBRATION_PROPOSED = "calibration.proposed"
EVENT_POLICY_ACTIVATED = "policy.version_activated"
EVENT_CALIBRATION_APPLIED = "calibration.applied"


class TunableCatalogueInvalid(KernelError):
    code = "TUNABLE_CATALOGUE_INVALID"


class CalibrationPrecondition(KernelError):
    code = "CALIBRATION_PRECONDITION"


def _leaves(value: object, prefix: str) -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    result: set[str] = set()
    for key, item in value.items():
        result.update(_leaves(item, f"{prefix}.{key}"))
    return result


def _value_at(payload: dict[str, Any], parameter_id: str) -> Any:
    parts = parameter_id.split(".")
    current: Any = payload
    for part in parts[1:]:
        if not isinstance(current, dict) or part not in current:
            raise TunableCatalogueInvalid(f"{parameter_id}: owner policy has no such leaf")
        current = current[part]
    return current


def _replace_value(payload: dict[str, Any], parameter_id: str, value: int | str) -> dict[str, Any]:
    copied: dict[str, Any] = {**payload}
    cursor = copied
    parts = parameter_id.split(".")[1:]
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            raise TunableCatalogueInvalid(f"{parameter_id}: owner policy has no such leaf")
        cloned = {**child}
        cursor[part] = cloned
        cursor = cloned
    cursor[parts[-1]] = value
    return copied


def _number(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TunableCatalogueInvalid(f"{path}: must be an integer or decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise TunableCatalogueInvalid(f"{path}: is not numeric") from None
    if not parsed.is_finite():
        raise TunableCatalogueInvalid(f"{path}: must be finite")
    return parsed


def validate_catalogue(catalogue: dict[str, Any], owner_policies: dict[str, dict[str, Any]]) -> list[str]:
    """Validate shape, ranges and complete two-way control-policy coverage."""
    errors: list[str] = []
    rows = catalogue.get("parameters")
    if not isinstance(rows, list):
        return ["tunables.parameters: must be a list"]
    seen: set[str] = set()
    catalogued_control: set[str] = set()
    for index, row in enumerate(rows):
        path = f"tunables.parameters[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{path}: must be an object")
            continue
        parameter_id = row.get("parameter_id")
        if not isinstance(parameter_id, str) or "." not in parameter_id:
            errors.append(f"{path}.parameter_id: invalid")
            continue
        if parameter_id in seen:
            errors.append(f"{path}.parameter_id: duplicate {parameter_id}")
        seen.add(parameter_id)
        if row.get("change_mode") != "propose_confirm":
            errors.append(f"{path}.change_mode: must be propose_confirm")
        allowed = row.get("allowed_range")
        if not isinstance(allowed, list) or len(allowed) != 2:
            errors.append(f"{path}.allowed_range: must contain [minimum, maximum]")
            continue
        try:
            low = _number(allowed[0], f"{path}.allowed_range[0]")
            high = _number(allowed[1], f"{path}.allowed_range[1]")
            if low > high:
                errors.append(f"{path}.allowed_range: minimum exceeds maximum")
        except TunableCatalogueInvalid as exc:
            errors.append(str(exc))
            continue
        kind = parameter_id.split(".", 1)[0]
        owner = owner_policies.get(kind)
        if owner is None:
            errors.append(f"{path}: owner policy {kind!r} is unavailable")
            continue
        try:
            current = _number(_value_at(owner, parameter_id), parameter_id)
        except TunableCatalogueInvalid as exc:
            errors.append(str(exc))
            continue
        if not low <= current <= high:
            errors.append(f"{parameter_id}: active value is outside allowed_range")
        if row.get("owner") == "0.12 control":
            catalogued_control.add(parameter_id)

    control = owner_policies.get("control")
    if control is not None:
        ignored = {
            "control.policy_id",
            "control.schema_version",
            "control.status",
            "control.canonical_encoding",
            "control.numeric_value_rule",
        }
        control_leaves = _leaves(control, "control") - ignored
        missing = sorted(control_leaves - catalogued_control)
        extra = sorted(catalogued_control - control_leaves)
        if missing:
            errors.append(f"control catalogue missing: {', '.join(missing)}")
        if extra:
            errors.append(f"control catalogue stale: {', '.join(extra)}")
    return errors


def _active_owner_policies(registry: PolicyRegistry, catalogue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    kinds = {
        str(row.get("parameter_id", "")).split(".", 1)[0]
        for row in catalogue.get("parameters") or []
        if isinstance(row, dict)
    }
    policies: dict[str, dict[str, Any]] = {}
    for kind in sorted(kinds):
        try:
            _, policies[kind] = registry.resolve_active(kind)
        except NoActivePolicy:
            continue
    return policies


def require_valid_catalogue(registry: PolicyRegistry, catalogue: dict[str, Any]) -> dict[str, Any]:
    errors = validate_catalogue(catalogue, _active_owner_policies(registry, catalogue))
    if errors:
        raise TunableCatalogueInvalid("; ".join(errors))
    return catalogue


def list_tunables(registry: PolicyRegistry, *, owner: str | None = None) -> list[dict[str, Any]]:
    _, catalogue = registry.resolve_active(TUNABLES_KIND)
    require_valid_catalogue(registry, catalogue)
    rows = [dict(row) for row in catalogue["parameters"] if isinstance(row, dict)]
    if owner is not None:
        rows = [row for row in rows if row.get("owner") == owner]
    return sorted(rows, key=lambda row: str(row["parameter_id"]))


def _catalogue_row(registry: PolicyRegistry, parameter_id: str) -> dict[str, Any]:
    for row in list_tunables(registry):
        if row["parameter_id"] == parameter_id:
            return row
    raise CalibrationPrecondition(f"unknown tunable {parameter_id!r}")


def _within(row: dict[str, Any], value: int | str) -> bool:
    low, high = row["allowed_range"]
    return (
        _number(low, "allowed minimum")
        <= _number(value, "proposed value")
        <= _number(high, "allowed maximum")
    )


def _pins(registry: PolicyRegistry) -> dict[str, str]:
    pins: dict[str, str] = {}
    for kind in ("control", "tunables"):
        with suppress(NoActivePolicy):
            pins[kind] = registry.active_version(kind)
    return pins


def propose_calibration(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    parameter_id: str,
    proposed_value: int | str,
    *,
    rationale: str,
    actor: str = "owner",
) -> dict[str, Any]:
    row = _catalogue_row(registry, parameter_id)
    if not _within(row, proposed_value):
        raise CalibrationPrecondition(
            f"{parameter_id} value {proposed_value!r} is outside {row['allowed_range']!r}"
        )
    kind = parameter_id.split(".", 1)[0]
    owner_version, owner_policy = registry.resolve_active(kind)
    proposal_id = new_ulid(clock, random_source)
    payload = {
        "proposal_id": proposal_id,
        "parameter_id": parameter_id,
        "previous_value": _value_at(owner_policy, parameter_id),
        "proposed_value": proposed_value,
        "owner": row["owner"],
        "owner_policy_version": owner_version,
        "catalogue_version": registry.active_version(TUNABLES_KIND),
        "rationale": rationale,
        "status": "pending",
    }
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_CALIBRATION_PROPOSED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=proposal_id,
                    payload=payload,
                    pinned_versions=_pins(registry),
                )
            ]
        )
    return payload


def list_calibrations(store: EventStore) -> list[dict[str, Any]]:
    proposals: dict[str, dict[str, Any]] = {}
    applied: dict[str, dict[str, Any]] = {}
    for event in store.read():
        if event.type == EVENT_CALIBRATION_PROPOSED:
            proposals[str(event.payload["proposal_id"])] = dict(event.payload)
        elif event.type == EVENT_CALIBRATION_APPLIED:
            applied[str(event.payload["proposal_id"])] = dict(event.payload)
    result = []
    for proposal_id, proposal in proposals.items():
        application = (
            {"status": "applied", "application": applied[proposal_id]} if proposal_id in applied else {}
        )
        result.append({**proposal, **application})
    return result


def confirm_calibration(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    proposal_id: str,
    *,
    actor: str = "owner",
) -> dict[str, Any]:
    known = {str(item["proposal_id"]): item for item in list_calibrations(store)}
    proposal = known.get(proposal_id)
    if proposal is None:
        raise CalibrationPrecondition(f"calibration proposal {proposal_id} does not exist")
    if proposal.get("status") == "applied":
        return dict(proposal["application"])

    parameter_id = str(proposal["parameter_id"])
    row = _catalogue_row(registry, parameter_id)
    value = proposal["proposed_value"]
    if not isinstance(value, int | str) or isinstance(value, bool) or not _within(row, value):
        raise CalibrationPrecondition(f"proposal {proposal_id} is outside the active catalogue")
    kind = parameter_id.split(".", 1)[0]
    expected_version = str(proposal["owner_policy_version"])
    if registry.active_version(kind) != expected_version:
        raise CalibrationPrecondition(
            f"owner policy {kind} changed after proposal; create a fresh calibration proposal"
        )
    successor = _replace_value(registry.resolve_pinned(kind, expected_version), parameter_id, value)
    successor_version = f"{kind}@cal-{proposal_id.lower()}"
    successor["policy_id"] = successor_version
    activation_event_id = new_ulid(clock, random_source)
    applied_event_id = new_ulid(clock, random_source)
    activated_payload = {
        "kind": kind,
        "previous_version": expected_version,
        "version": successor_version,
        "content_hash": payload_hash(successor),
        "reason": "confirmed_calibration",
        "proposal_id": proposal_id,
    }
    applied_payload = {
        "proposal_id": proposal_id,
        "parameter_id": parameter_id,
        "value": value,
        "owner_policy_version": successor_version,
        "activation_event_id": activation_event_id,
        "status": "applied",
    }
    with UnitOfWork(store, clock) as uow:
        registry.register(kind, successor_version, successor)
        registry.activate(kind, successor_version)
        uow.append(
            [
                make_event(
                    id=activation_event_id,
                    type=EVENT_POLICY_ACTIVATED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=proposal_id,
                    payload=activated_payload,
                    pinned_versions=_pins(registry),
                ),
                make_event(
                    id=applied_event_id,
                    type=EVENT_CALIBRATION_APPLIED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=proposal_id,
                    causation_id=activation_event_id,
                    payload=applied_payload,
                    pinned_versions=_pins(registry),
                ),
            ]
        )
    return applied_payload
