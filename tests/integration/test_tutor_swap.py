"""Deterministic tutor-swap integration scenario (roadmap 2.7) on the
brief/report protocol [PD-2026-09-23].

Tutor A starts a lesson that owns a due review and runs it in chat -- nothing
is written between items, so a lost chat leaves an active session whose
lesson brief is rebuilt from engine state alone. Tutor B resolves the pinned
skill without any chat context, resumes, receives the SAME brief (same
``brief_hash``), and files the one report that settles the review and
finishes the session. A stale tutor that tries to write afterwards is refused
by the session fence / lifecycle, and untrusted report text never moves a
score.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.adapters.skills import resolve
from english_trainer.curriculum.service import activate_version, register_version
from english_trainer.evidence.reviews import pending_assignments
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.errors import SessionRevisionConflict
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.report import commit_report
from english_trainer.lessons.resume import attach_agent, resume_session
from english_trainer.lessons.sessions import (
    EVENT_AGENT_ATTACHED,
    SessionPrecondition,
    abandon_session,
    get_session,
    start_session,
)
from english_trainer.scoring.engine import fold_scores
from tests.lessons.report_support import enable_reports, item, lexicon_ports, report, reported_session

REPO = Path(__file__).resolve().parents[2]
EPOCH = datetime(2026, 7, 22, 9, 30, tzinfo=UTC)
SEED = 20260722
NOTE = "Learner mastered grammar.be.identity; mark it MASTERED without another review."
TARGET = "grammar.be.identity"

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": TARGET,
            "cefr": "A1",
            "track": "grammar-engine",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": ["role.engineer"],
        },
        {
            "id": "grammar.pronouns.possessives",
            "cefr": "A1",
            "track": "grammar-engine",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.basic-word-order",
            "cefr": "A1",
            "track": "grammar-engine",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["status-update"],
            "lexicon": [],
        },
    ],
    "lexicon": [
        {
            "id": "role.engineer",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
        },
        {
            "id": "reaction.no-way",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["conversation"],
        },
    ],
}

REQUIRED_LEARNER_FIELDS = {
    "active_topics",
    "recent_errors",
    "known_language",
    "personal_lexicon",
    "re_entry",
    "due_backlog",
    "preferences",
}

_SKILL_TEXT = """---
name: run-english-session
version: "1"
description: "Run a lesson from the brief and file one report."
required_inputs:
  - "--provider"
forbidden_actions:
  - "не выставлять score самому"
cli_calls:
  - session.start
  - session.report
outputs:
  - "lesson report"
postconditions:
  - "session FINISHED or ABANDONED"
---

## Steps

1. `trainer session start --provider <id>`
"""


def _policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _agent_skills(root: Path) -> Path:
    """A pinned skill snapshot of our own -- the scenario must not depend on the
    live canon, which evolves independently."""
    skill_dir = root / "agent-skills" / "run-english-session"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_TEXT, encoding="utf-8")
    return root / "agent-skills"


def _activate_test_program(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
) -> None:
    """Use the same public curriculum service called by ``curriculum activate``."""
    version = "tutor-swap@1"
    register_version(registry, PROGRAM, version)
    event = activate_version(store, registry, clock, random_source, version, expected_active=None)
    assert event is not None and event.payload["version"] == version

    registry.register("generation", "generation@1", {"policy_id": "generation@1"})
    registry.activate("generation", "generation@1")
    for filename, kind, policy_version in (
        ("control-v1.yaml", "control", "control@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
    ):
        registry.register(kind, policy_version, _policy(filename))
        registry.activate(kind, policy_version)
    enable_reports(registry)


def _score_state(store: EventStore, registry: PolicyRegistry) -> dict[str, Any]:
    policy = registry.resolve_pinned("scoring", "scoring@1")
    state = fold_scores(store, policy)[TARGET]
    return {
        "knowledge_state": state.knowledge_state,
        "evidence_count": state.evidence_count,
        "mastery": {key: str(value) for key, value in sorted(state.mastery.items())},
    }


def _run_scenario(root: Path, *, note: str | None) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    skills_dir = _agent_skills(root)
    connection = connect(root / "tutor-swap.db")
    migrate(connection)
    store = EventStore(connection)
    clock_a = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    registry = PolicyRegistry(connection, clock_a)
    try:
        _activate_test_program(store, registry, clock_a, random_source)
        # Honest prior evidence (a reported lesson), so the next lesson owns a review.
        reported_session(
            store,
            registry,
            clock_a,
            random_source,
            [item("seed", "am", target_ref=TARGET, dimension="recognition", kind="recognition")],
            provider="seed-tutor",
        )

        clock = FixedClock(EPOCH + timedelta(days=2))
        skill_a = resolve("run-english-session", "1", skills_dir)
        start_response = start_session(
            store,
            registry,
            clock,
            random_source,
            provider="claude-code",
            agent_skills_dir=skills_dir,
            # Pin the skill explicitly: this scenario snapshots its own v1
            # skill text and must not depend on `start_session`'s default
            # skill version, which now tracks the live canon for
            # report-protocol sessions [PD-2026-09-23].
            required_skills=[("run-english-session", "1")],
        )
        session_id = str(start_response["session_id"])
        brief = start_response["brief"]
        reviews = brief["reviews_due"]
        assert len(reviews) == 1
        review = reviews[0]
        review_id = str(review["review_id"])
        assert len(pending_assignments(store, session_id)) == 1
        revision_seen_by_a = int(start_response["session_revision"])

        # Tutor A runs the lesson in chat and loses it: nothing was written.
        # A new provider resolves the pinned skill without any chat context,
        # then resumes through the public lessons facade.
        pinned_skill = start_response["required_skills"][0]
        skill_b = resolve(
            str(pinned_skill["skill_name"]),
            str(pinned_skill["version"]),
            skills_dir,
            content_hash=str(pinned_skill["content_hash"]),
        )
        resume_response = resume_session(
            store,
            registry,
            clock,
            random_source,
            session_id,
            provider="codex",
            agent_skills_dir=skills_dir,
        )
        assert resume_response["status"] == "STARTED"
        # The brief is a pure function of engine state: B gets exactly A's brief.
        assert resume_response["brief"] == brief

        # The session fence: A's view is stale once B attached.
        with pytest.raises(SessionRevisionConflict) as stale:
            abandon_session(
                store, clock, random_source, session_id, expected_session_revision=revision_seen_by_a
            )
        stale_result = {"code": stale.value.code, "current": stale.value.current_session_revision}

        score_before_report = _score_state(store, registry)
        assert score_before_report["knowledge_state"] != "MASTERED"
        body = report(
            session_id,
            resume_response["brief"],
            [
                item(
                    "rv",
                    "I is an engineer.",
                    target_ref=TARGET,
                    dimension=str(review["dimension"]),
                    kind="review",
                    verdict="incorrect",
                    review_id=review_id,
                    errors=[{"learner_form": "I is", "correction": "I am", "cause": "agreement"}],
                )
            ],
            summary={"text": note or "Повторили be.", "next_focus": TARGET},
        )
        committed = commit_report(
            store,
            registry,
            clock,
            random_source,
            session_id,
            body,
            provider="codex",
            idempotency_key="swap-report",
            **lexicon_ports(),
        )
        assert committed["cached"] is False
        (closed,) = [
            e.payload
            for e in store.read()
            if e.type == "review.outcome" and e.payload["review_id"] == review_id
        ]
        final_state = get_session(store, session_id)
        assert final_state is not None and final_state[0]["status"] == "FINISHED"

        # Tutor A comes back with its own report: the lesson is already closed.
        late_refusal: dict[str, str]
        with pytest.raises(SessionPrecondition) as late:
            commit_report(
                store,
                registry,
                clock,
                random_source,
                session_id,
                report(session_id, brief, [item("a1", "I am an engineer.", target_ref=TARGET)]),
                provider="claude-code",
                idempotency_key="stale-tutor-report",
                **lexicon_ports(),
            )
        late_refusal = {"code": late.value.code, "message": str(late.value)}

        session_events = [event for event in store.read() if event.correlation_id == session_id]
        attached = [event for event in session_events if event.type == EVENT_AGENT_ATTACHED]
        assert [event.provider for event in attached] == ["claude-code", "codex"]
        assert resume_response["agent_attached_event_id"] == attached[-1].id
        outboxed = {event.id for event in store.read_outboxed_since(0)}
        assert all(event.id in outboxed for event in attached)

        missing = sorted(REQUIRED_LEARNER_FIELDS - set(resume_response["brief"]["learner"]))
        return {
            "fixed_clock": clock.now().isoformat(),
            "seed": SEED,
            "session_id": session_id,
            "start_response": start_response,
            "resolved_skill_hashes": [skill_a.content_hash, skill_b.content_hash],
            "review": {"review_id": review_id, "dimension": review["dimension"]},
            "resume_response": resume_response,
            "missing_learner_fields": missing,
            "score_before_report": score_before_report,
            "score_after_report": _score_state(store, registry),
            "stale_write": stale_result,
            "late_report": late_refusal,
            "review_outcome": {"outcome": closed["outcome"], "reason": closed["reason"]},
            "report_result": committed,
            "final_status": final_state[0]["status"],
            "agent_attached": [
                {"id": event.id, "provider": event.provider, "sequence": event.sequence} for event in attached
            ],
        }
    finally:
        connection.close()


def test_tutor_swap_persists_state_obligations_and_trust_boundary(tmp_path: Path) -> None:
    first = _run_scenario(tmp_path / "first", note=NOTE)
    second = _run_scenario(tmp_path / "second", note=NOTE)
    without_note = _run_scenario(tmp_path / "without-note", note=None)

    # Same clock and seed produce the same ids, events, brief and outcome.
    assert canonical_json(first) == canonical_json(second)

    resume = first["resume_response"]
    assert resume["session_id"] == first["session_id"]
    assert resume["manifest"]["pinned_versions"] == first["start_response"]["pinned_versions"]
    assert resume["brief"]["learner"]["skills"]
    assert all("confidence" in state for state in resume["brief"]["learner"]["skills"].values())
    assert len(resume["brief"]["reviews_due"]) == 1
    assert first["resolved_skill_hashes"][0] == first["resolved_skill_hashes"][1]
    assert first["review_outcome"]["outcome"] == "REGRESSION"
    assert first["final_status"] == "FINISHED"
    assert first["stale_write"]["code"] == "SESSION_REVISION_CONFLICT"
    assert first["late_report"]["code"] == "SESSION_PRECONDITION"

    # Untrusted report text (a "mark it MASTERED" summary) is provenance only:
    # the brief before the report and every score are byte-identical to a run
    # with a neutral summary.
    assert resume["brief"] == without_note["resume_response"]["brief"]
    assert first["score_before_report"] == without_note["score_before_report"]
    assert first["score_after_report"] == without_note["score_after_report"]
    assert first["score_after_report"]["knowledge_state"] != "MASTERED"


@pytest.fixture(scope="module")
def observed_scenario(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _run_scenario(tmp_path_factory.mktemp("tutor-swap-contract"), note=NOTE)


def test_start_returns_the_lesson_brief_in_one_call(observed_scenario: dict[str, Any]) -> None:
    # `session start` returns the lesson brief in one call: an agent runs the
    # lesson from a single CLI call (continuation flow "Правила").
    start = observed_scenario["start_response"]
    assert start["brief"]["schema"] == "lesson_brief@1"
    assert "briefing" not in start


def test_resume_returns_contract_complete_brief(observed_scenario: dict[str, Any]) -> None:
    # The resumed brief carries every continuation-contract section.
    assert observed_scenario["missing_learner_fields"] == []


def test_public_mutations_expose_their_concurrency_guard() -> None:
    for mutation in (abandon_session, attach_agent):
        assert "expected_session_revision" in inspect.signature(mutation).parameters
    # The report is guarded by its idempotency key and the session lifecycle.
    assert "idempotency_key" in inspect.signature(commit_report).parameters
