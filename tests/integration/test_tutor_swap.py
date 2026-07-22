"""Deterministic tutor-swap integration scenario (roadmap 2.7).

The passing test proves every continuation property exposed by the current
public APIs. Strict xfails at the bottom record the three contract surfaces
that 2.5 does not yet expose; they are findings, not workarounds.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.adapters.skills import resolve
from english_trainer.control.errors import PlanVersionConflict
from english_trainer.curriculum.service import activate_version, register_version
from english_trainer.evidence.attempts import record_attempt
from english_trainer.evidence.reviews import close_review, pending_assignments
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.delivery import next_step, peek_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.resume import resume_session
from english_trainer.lessons.sessions import (
    EVENT_AGENT_ATTACHED,
    SessionPrecondition,
    finish_session,
    get_plan,
    get_session,
    start_session,
)
from english_trainer.scoring.engine import fold_scores

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

EXERCISE = {
    "prompt": "Choose the form of be: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}

REQUIRED_BRIEFING_FIELDS = {
    "active_topics",
    "top_errors",
    "recent_vocabulary",
    "recent_chunks",
    "re_entry",
    "recommendations",
    "last_session_summary",
}


def _policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


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


def _render_and_answer(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
    session_id: str,
    step_id: str,
    answer: str,
    *,
    note: str | None = None,
    provider: str,
) -> dict[str, Any]:
    rendered = record_rendered_exercise(
        store,
        registry,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        exercise=dict(EXERCISE),
    )
    return record_attempt(
        store,
        clock,
        random_source,
        session_id,
        step_id=step_id,
        raw_answer=answer,
        exercise_instance_id=str(rendered["exercise_instance_id"]),
        note=note,
        provider=provider,
    )


def _seed_due_review(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
) -> None:
    """Create honest prior evidence so the tutor-swap session owns a review."""
    manifest = start_session(
        store,
        registry,
        clock,
        random_source,
        provider="seed-tutor",
        agent_skills_dir=REPO / "agent-skills",
    )
    session_id = str(manifest["session_id"])
    claimed = next_step(store, registry, clock, random_source, session_id, expected_plan_version=1)
    attempt = _render_and_answer(
        store,
        registry,
        clock,
        random_source,
        session_id,
        str(claimed["step"]["step_id"]),
        "am",
        provider="seed-tutor",
    )
    assert attempt["assessment"]["correct"] is True
    finish_session(store, clock, random_source, session_id)


def _claim_review_step(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
    session_id: str,
) -> tuple[dict[str, Any], int]:
    version = 1
    presented = 0
    while True:
        claimed = next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_plan_version=version,
        )
        version = int(claimed["plan_version"])
        presented += 1
        if claimed["step"]["kind"] == "review":
            return dict(claimed["step"]), presented


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
    connection = connect(root / "tutor-swap.db")
    migrate(connection)
    store = EventStore(connection)
    clock_a = FixedClock(EPOCH)
    random_source = SeededRandomSource(SEED)
    registry = PolicyRegistry(connection, clock_a)
    try:
        _activate_test_program(store, registry, clock_a, random_source)
        _seed_due_review(store, registry, clock_a, random_source)

        clock = FixedClock(EPOCH + timedelta(days=2))
        skill_a = resolve("run-english-session", "1", REPO / "agent-skills")
        start_response = start_session(
            store,
            registry,
            clock,
            random_source,
            provider="claude-code",
            agent_skills_dir=REPO / "agent-skills",
        )
        session_id = str(start_response["session_id"])
        _, plan, _ = get_plan(store, session_id)
        reviews = [step for step in plan["steps"] if step["kind"] == "review"]
        assert len(reviews) == 1
        review_id = str(reviews[0]["review_assignment_id"])

        review_step, presented_before_swap = _claim_review_step(
            store, registry, clock, random_source, session_id
        )
        attempt = _render_and_answer(
            store,
            registry,
            clock,
            random_source,
            session_id,
            str(review_step["step_id"]),
            "is",
            note=note,
            provider="claude-code",
        )
        assert attempt["status"] == "assessed"
        assert attempt["assessment"] == {
            "basis": "objective_check",
            "correct": False,
            "score_ppm": 0,
            "checked_against_content_hash": attempt["assessment"]["checked_against_content_hash"],
        }
        assert len(pending_assignments(store, session_id)) == 1

        # A new provider resolves the pinned skill without any chat context,
        # then resumes through the public lessons facade.
        pinned_skill = start_response["required_skills"][0]
        skill_b = resolve(
            str(pinned_skill["skill_name"]),
            str(pinned_skill["version"]),
            REPO / "agent-skills",
        )
        resume_response = resume_session(
            store,
            registry,
            clock,
            random_source,
            session_id,
            provider="codex",
        )
        assert resume_response["status"] == "IN_PROGRESS"
        assert resume_response["briefing"]["pending_reviews"] == 1

        finish_refusal: dict[str, str]
        with pytest.raises(SessionPrecondition) as blocked:
            finish_session(store, clock, random_source, session_id)
        finish_refusal = {"code": blocked.value.code, "message": str(blocked.value)}
        state_after_refusal = get_session(store, session_id)
        assert state_after_refusal is not None and state_after_refusal[0]["status"] == "IN_PROGRESS"

        # The currently exposed optimistic token is plan_version. Two tutors
        # read the same value; the second write loses with a stable error.
        shared_view = peek_step(store, session_id)
        assert shared_view["step"] is not None
        winner = next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_plan_version=int(shared_view["plan_version"]),
        )
        with pytest.raises(PlanVersionConflict) as stale:
            next_step(
                store,
                registry,
                clock,
                random_source,
                session_id,
                expected_plan_version=int(shared_view["plan_version"]),
            )
        stale_result = {
            "code": stale.value.code,
            "current_plan_version": stale.value.current_plan_version,
            "message": str(stale.value),
        }
        assert stale_result["current_plan_version"] == winner["plan_version"]

        score_before_close = _score_state(store, registry)
        assert score_before_close["knowledge_state"] != "MASTERED"
        closed = close_review(store, clock, random_source, session_id, review_id)
        assert closed["outcome"] == "REGRESSION"
        finished = finish_session(store, clock, random_source, session_id)
        final_state = get_session(store, session_id)
        assert final_state is not None and final_state[0]["status"] == "FINISHED"

        session_events = [event for event in store.read() if event.correlation_id == session_id]
        attached = [event for event in session_events if event.type == EVENT_AGENT_ATTACHED]
        assert [event.provider for event in attached] == ["claude-code", "codex"]
        assert resume_response["agent_attached_event_id"] == attached[-1].id
        outboxed = {event.id for event in store.read_outboxed_since(0)}
        assert all(event.id in outboxed for event in attached)

        notes = list(resume_response["notes"])
        assert notes == ([] if note is None else [notes[0]])
        if note is not None:
            assert notes[0]["text"] == note
            assert notes[0]["author_provider"] == "claude-code"
            assert note not in canonical_json(resume_response["briefing"]).decode("utf-8")
        assert "notes" not in resume_response["briefing"]

        missing = sorted(REQUIRED_BRIEFING_FIELDS - set(resume_response["briefing"]))
        return {
            "fixed_clock": clock.now().isoformat(),
            "seed": SEED,
            "session_id": session_id,
            "start_response": start_response,
            "start_has_briefing": "briefing" in start_response,
            "resolved_skill_hashes": [skill_a.content_hash, skill_b.content_hash],
            "review": {
                "review_id": review_id,
                "step_id": review_step["step_id"],
                "presented_before_swap": presented_before_swap,
                "incorrect_score_ppm": attempt["assessment"]["score_ppm"],
            },
            "resume_response": resume_response,
            "missing_briefing_fields": missing,
            "score_before_close": score_before_close,
            "finish_refusal": finish_refusal,
            "stale_write": stale_result,
            "review_outcome": closed,
            "finish_event": {"type": finished.type, "payload": finished.payload},
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

    # Same clock and seed produce the same ids, events, briefing and outcome.
    assert canonical_json(first) == canonical_json(second)

    resume = first["resume_response"]
    assert resume["session_id"] == first["session_id"]
    assert resume["status"] == "IN_PROGRESS"
    assert resume["manifest"]["pinned_versions"] == first["start_response"]["pinned_versions"]
    assert resume["briefing"]["skills"]
    assert all("confidence" in state for state in resume["briefing"]["skills"].values())
    assert resume["briefing"]["pending_reviews"] == 1
    assert resume["notes"][0]["text"] == NOTE
    assert first["review_outcome"]["outcome"] == "REGRESSION"
    assert first["final_status"] == "FINISHED"
    assert first["finish_refusal"]["code"] == "SESSION_PRECONDITION"
    assert first["stale_write"]["code"] == "PLAN_VERSION_CONFLICT"

    # A malicious note changes only the physically separate notes block. The
    # computed briefing and score fold are byte-identical to a no-note run.
    assert resume["briefing"] == without_note["resume_response"]["briefing"]
    assert first["score_before_close"] == without_note["score_before_close"]
    assert first["score_before_close"]["knowledge_state"] != "MASTERED"


@pytest.fixture(scope="module")
def observed_scenario(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _run_scenario(tmp_path_factory.mktemp("tutor-swap-contract"), note=NOTE)


@pytest.mark.xfail(
    strict=True,
    reason="2.5 finding: session start returns only the manifest, not the required tutor briefing",
)
def test_start_returns_tutor_briefing_in_one_call(observed_scenario: dict[str, Any]) -> None:
    assert "briefing" in observed_scenario["start_response"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2.5 finding: resume briefing lacks active topics, top errors, recent vocabulary/chunks, "
        "re-entry, recommendations, and last-session summary"
    ),
)
def test_resume_returns_contract_complete_briefing(observed_scenario: dict[str, Any]) -> None:
    briefing = observed_scenario["resume_response"]["briefing"]
    assert set(briefing) >= REQUIRED_BRIEFING_FIELDS


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OPEN-11 finding: public session mutations expose plan_version CAS but no "
        "expected_session_revision token"
    ),
)
def test_public_mutations_expose_optimistic_session_revision() -> None:
    for mutation in (record_attempt, finish_session):
        assert "expected_session_revision" in inspect.signature(mutation).parameters
