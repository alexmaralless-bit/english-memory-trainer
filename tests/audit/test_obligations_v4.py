"""obligations@4 observes the brief/report protocol [PD-2026-09-22-brief]:
one committed `lesson.reported` event replaces the per-step delivery and
engine-graded correction obligations of obligations@1-@3
(staging/concepts/2026-09-23-lesson-brief-report-concept.md). Two
outcome-shaped obligations take their place -- `report_committed` (a report
landed before the session finished) and `reviews_addressed` (no review
assignment the session picked up was left dangling) -- while
`required_skill_effect`, `lesson_preflight` and `forbidden_action_absence`
carry over unchanged in meaning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from english_trainer.audit import obligations
from english_trainer.audit.policy import require_valid
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork

REPO = Path(__file__).resolve().parents[2]


def _policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class _Session:
    """A synthetic, fully observed terminal session pinned to obligations@4."""

    def __init__(self, tmp_path: Path, *, lesson_profile: str | None = "program_lesson") -> None:
        conn = connect(tmp_path / "audit.db")
        migrate(conn)
        self.store = EventStore(conn)
        self.clock = FixedClock(datetime(2026, 9, 23, 14, 0, tzinfo=UTC))
        self.rnd = SeededRandomSource(923)
        self.registry = PolicyRegistry(conn, self.clock)
        payload = require_valid(_policy("obligations-v4.yaml"))
        self.registry.register("obligations", "obligations@4", payload)
        self.registry.activate("obligations", "obligations@4")
        self.session_id = new_ulid(self.clock, self.rnd)
        manifest: dict[str, Any] = {"pinned_versions": {"obligations": "obligations@4"}}
        if lesson_profile is not None:
            manifest["lesson_profile"] = lesson_profile
        self.events: list[Any] = [self._event("session.started", {"manifest": manifest}, actor="engine")]
        self._pending_aggregates: list[tuple[str, str, dict[str, Any]]] = []

    def _event(
        self, type_: str, payload: dict[str, Any], *, actor: str = "agent", provider: str | None = None
    ) -> Any:
        return make_event(
            id=new_ulid(self.clock, self.rnd),
            type=type_,
            occurred_at=self.clock.now(),
            actor=actor,
            provider=provider,
            correlation_id=self.session_id,
            payload=payload,
        )

    def add(
        self, type_: str, payload: dict[str, Any], *, actor: str = "agent", provider: str | None = None
    ) -> _Session:
        self.events.append(self._event(type_, payload, actor=actor, provider=provider))
        return self

    def cli(self, command: str) -> _Session:
        self.events.append(
            make_event(
                id=new_ulid(self.clock, self.rnd),
                type="cli.command_terminated",
                occurred_at=self.clock.now(),
                actor="cli-transport",
                correlation_id=f"call-{command}-{len(self.events)}",
                payload={
                    "command": command,
                    "outcome": "success",
                    "exit_code": 0,
                    "session_id": self.session_id,
                },
            )
        )
        return self

    def review_assignment(self, review_id: str, *, status: str = "pending", **extra: Any) -> _Session:
        state = {
            "review_id": review_id,
            "session_id": self.session_id,
            "step_id": f"step-{review_id}",
            "target_ref": "grammar.be.identity",
            "dimension": "controlled_production",
            "status": status,
            "created_at": self.clock.now().isoformat(),
            **extra,
        }
        self._pending_aggregates.append(("review_assignment", review_id, state))
        return self

    def terminate(self, *, finished: bool = True) -> _Session:
        self.cli("session.finish" if finished else "session.abandon")
        self.events.append(
            self._event(
                "session.finished" if finished else "session.abandoned",
                {"session_id": self.session_id},
                actor="engine",
            )
        )
        with UnitOfWork(self.store, self.clock) as uow:
            for aggregate_type, aggregate_id, state in self._pending_aggregates:
                uow.save_aggregate(aggregate_type, aggregate_id, state, expected_revision=0)
            uow.append(self.events)
        return self

    def report(self) -> dict[str, Any]:
        return obligations(self.store, self.registry, self.session_id)


def _by_id(report: dict[str, Any], obligation_id: str) -> dict[str, Any]:
    matches = [item for item in report["observations"] if item["obligation_id"] == obligation_id]
    assert matches, obligation_id
    return matches[0]


def test_a_compliant_session_satisfies_every_applicable_obligation(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.add(
        "skill.required",
        {
            "session_id": session.session_id,
            "skill_name": "run-english-session",
            "version": "v10",
            "cli_calls": ["session.report"],
        },
        actor="engine",
    )
    session.add(
        "skill.completed",
        {"session_id": session.session_id, "skill_name": "run-english-session", "version": "v10"},
    )
    session.review_assignment("review-1", status="closed", outcome="CONFIRMED")
    session.add(
        "review.outcome",
        {
            "session_id": session.session_id,
            "review_id": "review-1",
            "outcome": "CONFIRMED",
            "reason": None,
        },
    )
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h1", "items": [], "reviews_skipped": []},
    )
    session.cli("session.report")
    report = session.terminate().report()

    assert report["status"] == "complete"
    assert report["policy_id"] == "obligations@4"
    applicable = [item for item in report["observations"] if item["applicable"]]
    assert applicable
    assert all(item["satisfied"] for item in applicable), applicable
    assert _by_id(report, "report_committed")["satisfied"] is True
    assert _by_id(report, "reviews_addressed")["satisfied"] is True
    assert _by_id(report, "lesson_preflight")["satisfied"] is True
    assert _by_id(report, "required_skill_effect")["satisfied"] is True
    assert _by_id(report, "forbidden_action_absence")["satisfied"] is True


def test_a_lesson_reported_event_alone_satisfies_required_skill_effect(tmp_path: Path) -> None:
    # [PD-2026-09-23]: the brief/report protocol has no `skills report` call
    # left to make, so no `skill.completed` event ever lands -- this mirrors a
    # real reported session (01M393ZY73872DF2FG68GHVQA1) whose only self-report
    # is `lesson.reported`.
    session = _Session(tmp_path)
    session.add(
        "skill.required",
        {
            "session_id": session.session_id,
            "skill_name": "run-english-session",
            "version": "10",
            "cli_calls": ["session.report"],
        },
        actor="engine",
        provider="claude_code",
    )
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h8", "items": [], "reviews_skipped": []},
        actor="agent",
        provider="claude_code",
    )
    session.cli("session.report")
    report = session.terminate().report()

    outcome = _by_id(report, "required_skill_effect")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is True
    assert outcome["finding"] is None
    assert any(event["type"] == "lesson.reported" for event in outcome["self_report_events"])
    assert all(event["type"] != "lesson.reported" for event in outcome["observed_effects"])


def test_an_abandoned_session_without_any_self_report_leaves_required_skill_effect_unsatisfied(
    tmp_path: Path,
) -> None:
    # Unchanged behaviour: a session that never files a report (abandoned) and
    # never self-reports via `skill.completed` either stays unsatisfied, with
    # the same finding obligations@1-@3 would have raised.
    session = _Session(tmp_path)
    session.add(
        "skill.required",
        {
            "session_id": session.session_id,
            "skill_name": "run-english-session",
            "version": "10",
            "cli_calls": ["session.abandon"],
        },
        actor="engine",
        provider="claude_code",
    )
    report = session.terminate(finished=False).report()

    outcome = _by_id(report, "required_skill_effect")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is False
    assert outcome["self_report_events"] == []
    assert outcome["finding"] == "observed_effect_without_self_report"


def test_a_finished_session_without_a_report_violates_report_committed(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    report = session.terminate().report()

    outcome = _by_id(report, "report_committed")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is False
    assert outcome["finding"] == "report_missing_or_out_of_order"


def test_a_report_filed_after_session_finished_violates_report_committed(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.cli("session.finish")
    session.add("session.finished", {"session_id": session.session_id}, actor="engine")
    # Out of order: the report lands AFTER the session already finished.
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h2", "items": [], "reviews_skipped": []},
    )
    with UnitOfWork(session.store, session.clock) as uow:
        uow.append(session.events)
    report = session.report()

    outcome = _by_id(report, "report_committed")
    assert outcome["satisfied"] is False


def test_an_abandoned_session_does_not_require_a_report(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    report = session.terminate(finished=False).report()

    outcome = _by_id(report, "report_committed")
    assert outcome["applicable"] is False
    assert outcome["satisfied"] is False


def test_a_pending_review_assignment_left_unaddressed_is_a_violation(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.review_assignment("review-1")  # never closed
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h3", "items": [], "reviews_skipped": []},
    )
    report = session.terminate().report()

    outcome = _by_id(report, "reviews_addressed")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is False
    assert outcome["finding"] == "reviews_left_unaddressed"
    assert outcome["snapshot_source"] == "review_assignment"


def test_a_skipped_review_with_a_reason_counts_as_addressed(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.review_assignment(
        "review-1", status="closed", outcome="INSUFFICIENT_EVIDENCE", reason="learner_declined"
    )
    session.add(
        "review.outcome",
        {
            "session_id": session.session_id,
            "review_id": "review-1",
            "outcome": "INSUFFICIENT_EVIDENCE",
            "reason": "learner_declined",
        },
    )
    session.add(
        "lesson.reported",
        {
            "session_id": session.session_id,
            "report_hash": "h4",
            "items": [],
            "reviews_skipped": [{"review_id": "review-1", "reason": "learner_declined"}],
        },
    )
    report = session.terminate().report()

    outcome = _by_id(report, "reviews_addressed")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is True


def test_insufficient_evidence_without_a_reason_does_not_count_as_addressed(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.review_assignment("review-1")
    session.add(
        "review.outcome",
        {
            "session_id": session.session_id,
            "review_id": "review-1",
            "outcome": "INSUFFICIENT_EVIDENCE",
            "reason": None,
        },
    )
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h5", "items": [], "reviews_skipped": []},
    )
    report = session.terminate().report()

    assert _by_id(report, "reviews_addressed")["satisfied"] is False


def test_a_cancelled_assignment_counts_as_addressed(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.review_assignment("review-1", status="cancelled", reason="replanned")
    session.add(
        "review.assignment_cancelled",
        {"session_id": session.session_id, "review_id": "review-1", "reason": "replanned"},
        actor="engine",
    )
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h6", "items": [], "reviews_skipped": []},
    )
    report = session.terminate().report()

    assert _by_id(report, "reviews_addressed")["satisfied"] is True


def test_no_review_assignments_makes_reviews_addressed_inapplicable(tmp_path: Path) -> None:
    session = _Session(tmp_path)
    session.add(
        "lesson.reported",
        {"session_id": session.session_id, "report_hash": "h7", "items": [], "reviews_skipped": []},
    )
    report = session.terminate().report()

    outcome = _by_id(report, "reviews_addressed")
    assert outcome["applicable"] is False
    # Not-applicable is not a violation: satisfied stays False (the
    # `report_committed` convention for an inapplicable observation) but no
    # finding is raised -- there was nothing left unaddressed.
    assert outcome["satisfied"] is False
    assert outcome["finding"] is None


def test_a_session_started_without_a_lesson_profile_violates_lesson_preflight(tmp_path: Path) -> None:
    session = _Session(tmp_path, lesson_profile=None)
    report = session.terminate().report()

    outcome = _by_id(report, "lesson_preflight")
    assert outcome["applicable"] is True
    assert outcome["satisfied"] is False
    assert outcome["finding"] == "lesson_preflight_missing"


def test_obligations_v3_stays_resolvable_for_its_own_sessions(tmp_path: Path) -> None:
    # obligations@4 must not disturb how a session pinned to an earlier
    # version resolves: register both, pin the old one, and confirm its own
    # (unmoved) evaluator still runs.
    conn = connect(tmp_path / "audit.db")
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(datetime(2026, 9, 23, 14, 0, tzinfo=UTC))
    rnd = SeededRandomSource(924)
    registry = PolicyRegistry(conn, clock)
    registry.register("obligations", "obligations@3", require_valid(_policy("obligations-v3.yaml")))
    registry.register("obligations", "obligations@4", require_valid(_policy("obligations-v4.yaml")))
    registry.activate("obligations", "obligations@3")
    session_id = new_ulid(clock, rnd)
    events = [
        make_event(
            id=new_ulid(clock, rnd),
            type="session.started",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id=session_id,
            payload={"manifest": {"pinned_versions": {"obligations": "obligations@3"}}},
        ),
        make_event(
            id=new_ulid(clock, rnd),
            type="cli.command_terminated",
            occurred_at=clock.now(),
            actor="cli-transport",
            correlation_id=f"call-{session_id}",
            payload={
                "command": "session.finish",
                "outcome": "success",
                "exit_code": 0,
                "session_id": session_id,
            },
        ),
        make_event(
            id=new_ulid(clock, rnd),
            type="session.finished",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id=session_id,
            payload={"session_id": session_id},
        ),
    ]
    with UnitOfWork(store, clock) as uow:
        uow.append(events)

    report = obligations(store, registry, session_id)
    assert report["policy_id"] == "obligations@3"
    obligation_ids = {item["obligation_id"] for item in report["observations"]}
    assert "delivery_protocol" in obligation_ids
    assert "report_committed" not in obligation_ids
