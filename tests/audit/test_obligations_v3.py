"""obligations@3 observes the invariant, not the call count [PD-2026-09-22].

The lean tutor protocol produces exactly the facts the old registry was
looking for -- a rendered snapshot before the answer, an assessed attempt, a
closed review -- with fewer commands. obligations@3 therefore asks for those
facts. obligations@2 keeps asking for `attempt.finalize` + `review.close` and
stays resolvable for the sessions that pinned it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.audit import obligations
from english_trainer.audit.policy import require_valid
from english_trainer.audit.views import ObligationPolicyInvalid
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]
STEP_ID = "step-1"


def _policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class _Session:
    """A synthetic, fully observed terminal session in event order."""

    def __init__(self, tmp_path: Path, version: str) -> None:
        conn = connect(tmp_path / "audit.db")
        migrate(conn)
        self.store = EventStore(conn)
        self.clock = FixedClock(datetime(2026, 9, 22, 14, 0, tzinfo=UTC))
        self.rnd = SeededRandomSource(922)
        self.registry = PolicyRegistry(conn, self.clock)
        for file_name, policy_version in (
            ("obligations-v2.yaml", "obligations@2"),
            ("obligations-v3.yaml", "obligations@3"),
        ):
            payload = require_valid(_policy(file_name))
            self.registry.register("obligations", policy_version, payload)
        self.registry.activate("obligations", version)
        self.session_id = new_ulid(self.clock, self.rnd)
        self.events: list[Any] = [
            self._event(
                "session.started",
                {"manifest": {"pinned_versions": {"obligations": version}}},
                actor="engine",
            )
        ]

    def _event(self, type_: str, payload: dict[str, Any], *, actor: str = "agent") -> Any:
        return make_event(
            id=new_ulid(self.clock, self.rnd),
            type=type_,
            occurred_at=self.clock.now(),
            actor=actor,
            correlation_id=self.session_id,
            payload=payload,
        )

    def add(self, type_: str, payload: dict[str, Any], *, actor: str = "agent") -> _Session:
        self.events.append(self._event(type_, payload, actor=actor))
        return self

    def cli(self, command: str) -> _Session:
        self.events.append(
            make_event(
                id=new_ulid(self.clock, self.rnd),
                type="cli.command_terminated",
                occurred_at=self.clock.now(),
                actor="cli-transport",
                correlation_id=f"call-{command}",
                payload={
                    "command": command,
                    "outcome": "success",
                    "exit_code": 0,
                    "session_id": self.session_id,
                },
            )
        )
        return self

    def terminate(self) -> _Session:
        self.cli("session.finish")
        self.events.append(self._event("session.finished", {"session_id": self.session_id}, actor="engine"))
        with UnitOfWork(self.store, self.clock) as uow:
            uow.append(self.events)
        return self

    def report(self) -> dict[str, Any]:
        return obligations(self.store, self.registry, self.session_id)


def _by_id(report: dict[str, Any], obligation_id: str) -> dict[str, Any]:
    matches = [item for item in report["observations"] if item["obligation_id"] == obligation_id]
    assert matches, obligation_id
    return matches[0]


def _delivered(session: _Session) -> _Session:
    return session.add(
        "session.step_presented",
        {"session_id": session.session_id, "step_id": STEP_ID, "step_type": "recognition_check"},
        actor="engine",
    )


def test_the_lean_path_satisfies_delivery_and_correction(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@3")
    _delivered(session)
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    session.add("evidence.error_observed", {"session_id": session.session_id})
    # ONE call: record + assess + close, so no attempt.finalize / review.close
    # telemetry exists anywhere in this session.
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "recorded"},
    )
    session.add(
        "attempt.state_changed",
        {"session_id": session.session_id, "to_status": "assessed"},
    )
    session.add("review.outcome", {"session_id": session.session_id, "outcome": "CONFIRMED"})
    report = session.terminate().report()

    assert report["policy_id"] == "obligations@3"
    assert _by_id(report, "delivery_protocol")["satisfied"] is True
    correction = _by_id(report, "correction_protocol")
    assert correction["applicable"] is True and correction["satisfied"] is True
    assert [event["type"] for event in correction["observed_effects"]] == [
        "attempt.state_changed",
        "review.outcome",
    ]


def test_the_long_path_still_satisfies_the_same_obligations(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@3")
    _delivered(session)
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    session.add("evidence.error_observed", {"session_id": session.session_id})
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "recorded"},
    )
    session.cli("attempt.finalize")
    session.add("attempt.state_changed", {"session_id": session.session_id, "to_status": "assessed"})
    session.cli("review.close")
    session.add("review.outcome", {"session_id": session.session_id, "outcome": "CONFIRMED"})
    report = session.terminate().report()

    assert _by_id(report, "delivery_protocol")["satisfied"] is True
    assert _by_id(report, "correction_protocol")["satisfied"] is True


def test_a_block_attempt_counts_as_an_assessed_attempt(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@3")
    _delivered(session)
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    session.add("evidence.error_observed", {"session_id": session.session_id})
    # A drill block is recorded already-assessed: there is no state change.
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "assessed"},
    )
    session.add("review.outcome", {"session_id": session.session_id, "outcome": "CONFIRMED"})
    report = session.terminate().report()

    correction = _by_id(report, "correction_protocol")
    assert correction["satisfied"] is True
    assert correction["observed_effects"][0]["type"] == "attempt.recorded"


def test_an_engine_closure_on_abandon_does_not_satisfy_the_correction_protocol(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@3")
    _delivered(session)
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    session.add("evidence.error_observed", {"session_id": session.session_id})
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "assessed"},
    )
    # What `abandon` writes: the engine closing what the tutor left open.
    session.add(
        "review.outcome",
        {"session_id": session.session_id, "outcome": "INSUFFICIENT_EVIDENCE", "reason": "abandoned"},
        actor="engine",
    )
    report = session.terminate().report()

    assert _by_id(report, "correction_protocol")["satisfied"] is False


def test_a_snapshot_rendered_after_the_attempt_violates_delivery(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@3")
    _delivered(session)
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "assessed"},
    )
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    report = session.terminate().report()

    delivery = _by_id(report, "delivery_protocol")
    assert delivery["satisfied"] is False
    assert delivery["finding"] == "exercise_snapshot_missing_or_out_of_order"


def test_obligations_v2_stays_resolvable_and_keeps_its_own_reading(tmp_path: Path) -> None:
    session = _Session(tmp_path, "obligations@2")
    _delivered(session)
    session.add("exercise.rendered", {"session_id": session.session_id, "step_id": STEP_ID})
    session.add("evidence.error_observed", {"session_id": session.session_id})
    session.add(
        "attempt.recorded",
        {"session_id": session.session_id, "step_id": STEP_ID, "status": "recorded"},
    )
    session.add("attempt.state_changed", {"session_id": session.session_id, "to_status": "assessed"})
    session.add("review.outcome", {"session_id": session.session_id, "outcome": "CONFIRMED"})
    report = session.terminate().report()

    assert report["policy_id"] == "obligations@2"
    # v2 asked for the two commands by name; the lean session never made them.
    assert _by_id(report, "correction_protocol")["satisfied"] is False
    # ... while its delivery reading (snapshot after the step) still holds.
    assert _by_id(report, "delivery_protocol")["satisfied"] is True


def test_an_unknown_registry_version_is_refused() -> None:
    # obligations@4 [PD-2026-09-23] is now a known version (test_obligations_v4.py);
    # probe one that still isn't.
    with pytest.raises(ObligationPolicyInvalid, match="policy_id"):
        require_valid({**_policy("obligations-v3.yaml"), "policy_id": "obligations@5"})
