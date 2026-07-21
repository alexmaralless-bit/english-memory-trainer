"""Envelope validation: UTC instants, matching payload_hash, closed schema
(foundation 3.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from english_trainer.kernel.envelopes import DomainEvent, make_command, make_event

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def test_make_event_computes_matching_hash() -> None:
    ev = make_event(
        id="01",
        type="demo.happened",
        occurred_at=NOW,
        actor="engine",
        correlation_id="corr-1",
        payload={"a": 1},
    )
    assert ev.sequence is None
    assert (
        ev.payload_hash
        == make_event(
            id="02",
            type="demo.happened",
            occurred_at=NOW,
            actor="engine",
            correlation_id="corr-1",
            payload={"a": 1},
        ).payload_hash
    )


def test_make_command_roundtrips() -> None:
    cmd = make_command(
        id="c1",
        type="do.thing",
        occurred_at=NOW,
        actor="tutor",
        correlation_id="corr-1",
        idempotency_key="k1",
        payload={"x": "y"},
    )
    assert cmd.idempotency_key == "k1"
    assert cmd.payload == {"x": "y"}


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        DomainEvent(
            id="1",
            type="t",
            occurred_at=datetime(2026, 7, 21, 12, 0, 0),
            actor="e",
            correlation_id="c",
            payload={},
            payload_hash="x",
        )


def test_payload_hash_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        DomainEvent(
            id="1",
            type="t",
            occurred_at=NOW,
            actor="e",
            correlation_id="c",
            payload={"a": 1},
            payload_hash="deadbeef",
        )


def test_extra_field_rejected() -> None:
    valid_hash = make_event(id="1", type="t", occurred_at=NOW, actor="e", correlation_id="c").payload_hash
    with pytest.raises(ValidationError):
        DomainEvent(
            id="1",
            type="t",
            occurred_at=NOW,
            actor="e",
            correlation_id="c",
            payload={},
            payload_hash=valid_hash,
            surprise="nope",  # type: ignore[call-arg]
        )


def test_event_is_frozen() -> None:
    ev = make_event(id="1", type="t", occurred_at=NOW, actor="e", correlation_id="c")
    with pytest.raises(ValidationError):
        ev.type = "other"  # type: ignore[misc]
