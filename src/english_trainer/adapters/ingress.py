"""Untrusted provider ingress and skill self-report facts.

These records are audit inputs, never learner evidence.  The adapter boundary
stores the exact local user text so a UTF-8 byte span remains independently
verifiable after the provider chat has disappeared.
"""

from __future__ import annotations

import hashlib
from typing import Any

from english_trainer.adapters.errors import (
    ProviderMessageConflict,
    SkillReportInvalid,
    UserTurnInvalid,
)
from english_trainer.adapters.events import SKILL_COMPLETED, SKILL_FAILED, SKILL_REQUIRED, SKILL_STARTED
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.session_fence import bump_session, load_session_for_update
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

USER_TURN_CAPTURED = "adapter.user_turn_captured"
_REPORT_EVENT = {
    "started": SKILL_STARTED,
    "completed": SKILL_COMPLETED,
    "failed": SKILL_FAILED,
}


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def _validate_span(content: str, byte_start: int, byte_end: int) -> None:
    encoded = content.encode()
    if byte_start < 0 or byte_end < byte_start or byte_end > len(encoded):
        raise UserTurnInvalid(
            f"UTF-8 byte span [{byte_start}, {byte_end}) is outside content length {len(encoded)}"
        )
    try:
        encoded[byte_start:byte_end].decode()
    except UnicodeDecodeError as exc:
        raise UserTurnInvalid("UTF-8 byte span must start and end on code-point boundaries") from exc


def _captured_message(store: EventStore, provider: str, provider_message_id: str) -> DomainEvent | None:
    for event in store.read():
        if (
            event.type == USER_TURN_CAPTURED
            and event.provider == provider
            and event.payload.get("provider_message_id") == provider_message_id
        ):
            return event
    return None


def capture_user_turn(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    provider: str,
    provider_message_id: str,
    content: str,
    expected_session_revision: int,
    byte_start: int = 0,
    byte_end: int | None = None,
    actor: str = "adapter",
) -> dict[str, Any]:
    """Persist one provider-global message identity and an auditable raw span.

    Same-id/same-content replay returns the original fact before consulting the
    now-advanced session fence.  Same id with different bytes or span is a
    stable conflict and can never silently rewrite the original turn.
    """
    if not provider.strip() or not provider_message_id.strip():
        raise UserTurnInvalid("provider and provider_message_id must be non-empty")
    resolved_end = len(content.encode()) if byte_end is None else byte_end
    _validate_span(content, byte_start, resolved_end)
    digest = _content_hash(content)
    prior = _captured_message(store, provider, provider_message_id)
    if prior is not None:
        same = (
            prior.correlation_id == session_id
            and prior.payload.get("content_hash") == digest
            and prior.payload.get("byte_start") == byte_start
            and prior.payload.get("byte_end") == resolved_end
            and prior.payload.get("content") == content
        )
        if not same:
            raise ProviderMessageConflict(
                f"{provider} message {provider_message_id!r} was already captured with different content"
            )
        return {
            "event_id": prior.id,
            "session_id": session_id,
            "content_hash": digest,
            "byte_start": byte_start,
            "byte_end": resolved_end,
            "cached": True,
        }

    state, revision = load_session_for_update(store, session_id, expected_session_revision)
    manifest = dict(state.get("manifest") or {})
    with UnitOfWork(store, clock) as uow:
        new_revision = bump_session(uow, session_id, state, revision, clock.now())
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=USER_TURN_CAPTURED,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=session_id,
                    payload={
                        "session_id": session_id,
                        "provider_message_id": provider_message_id,
                        "content": content,
                        "content_hash": digest,
                        "byte_start": byte_start,
                        "byte_end": resolved_end,
                        "trust": "untrusted_user_input",
                    },
                    pinned_versions=dict(manifest.get("pinned_versions") or {}),
                )
            ]
        )
    return {
        "event_id": event.id,
        "session_id": session_id,
        "content_hash": digest,
        "byte_start": byte_start,
        "byte_end": resolved_end,
        "session_revision": new_revision,
        "cached": False,
    }


def report_skill(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    session_id: str,
    *,
    skill_name: str,
    version: str,
    status: str,
    expected_session_revision: int,
    provider: str,
    actor: str = "agent",
) -> dict[str, Any]:
    """Record an explicitly untrusted report for one session-pinned skill."""
    event_type = _REPORT_EVENT.get(status)
    if event_type is None:
        raise SkillReportInvalid("status must be started, completed, or failed")
    required = next(
        (
            event
            for event in store.read()
            if event.type == SKILL_REQUIRED
            and event.correlation_id == session_id
            and event.payload.get("skill_name") == skill_name
            and str(event.payload.get("version")) == version
        ),
        None,
    )
    if required is None:
        raise SkillReportInvalid(f"skill {skill_name}@{version} is not required by session {session_id}")
    existing = next(
        (
            event
            for event in store.read()
            if event.type == event_type
            and event.correlation_id == session_id
            and event.payload.get("skill_name") == skill_name
            and str(event.payload.get("version")) == version
        ),
        None,
    )
    if existing is not None:
        return {"event_id": existing.id, "session_id": session_id, "cached": True}

    state, revision = load_session_for_update(store, session_id, expected_session_revision)
    with UnitOfWork(store, clock) as uow:
        new_revision = bump_session(uow, session_id, state, revision, clock.now())
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor=actor,
                    provider=provider,
                    correlation_id=session_id,
                    causation_id=required.id,
                    payload={
                        "session_id": session_id,
                        "skill_name": skill_name,
                        "version": version,
                        "content_hash": required.payload.get("content_hash"),
                        "status": status,
                        "trust": "untrusted_agent_self_report",
                    },
                    pinned_versions=dict(required.pinned_versions),
                )
            ]
        )
    return {
        "event_id": event.id,
        "session_id": session_id,
        "session_revision": new_revision,
        "cached": False,
    }
