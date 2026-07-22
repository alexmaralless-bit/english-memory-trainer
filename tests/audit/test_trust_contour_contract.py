"""Executable findings for the underspecified 2.9 trust contour."""

from __future__ import annotations

import importlib
import inspect

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2.9 finding: adapters have file/skill parity but no provider-message ingress, "
        "so provider_message_id + content hash + UTF-8 span cannot be captured at an adapter boundary"
    ),
)
def test_adapter_boundary_exposes_untrusted_user_turn_capture() -> None:
    adapters = importlib.import_module("english_trainer.adapters")
    capture = adapters.capture_user_turn
    parameters = inspect.signature(capture).parameters
    assert {"provider_message_id", "content"} <= set(parameters)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2.9 finding: audit.obligations is specified, but no versioned obligation payload or "
        "authoritative observable CLI-call stream defines deterministic effect matching"
    ),
)
def test_audit_exposes_obligation_correlation_for_tutor_compliance() -> None:
    audit = importlib.import_module("english_trainer.audit")
    correlate = audit.obligations
    assert "session_id" in inspect.signature(correlate).parameters
