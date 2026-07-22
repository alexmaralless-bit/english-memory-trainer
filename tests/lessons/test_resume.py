"""Session resume: required_skills resolution, AGENT_ATTACHED, and the tutor
briefing as a block separate from state (lessons 4b/5; roadmap 2.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from english_trainer.adapters.events import SKILL_REQUIRED
from english_trainer.lessons.resume import EVENT_AGENT_ATTACHED, resume_session
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    get_session,
    start_session,
)

# The seven state sections the continuation flow requires of every briefing
# (continuation "Состав tutor briefing").
_REQUIRED_BRIEFING_FIELDS = {
    "active_topics",
    "top_errors",
    "recent_vocabulary",
    "recent_chunks",
    "re_entry",
    "recommendations",
    "last_session_summary",
}

_SKILL_TEXT = """---
name: run-english-session
version: "1"
description: "Run a full English session end to end via the CLI."
required_inputs:
  - "--provider"
forbidden_actions:
  - "не выставлять score самому"
cli_calls:
  - session.start
outputs:
  - "session summary"
postconditions:
  - "session FINISHED or ABANDONED"
---

## Steps

1. `trainer session start --provider <id>`
"""


@pytest.fixture
def agent_skills_dir(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "agent-skills" / "run-english-session"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_TEXT, encoding="utf-8")
    return tmp_path / "agent-skills"


def test_start_without_agent_skills_dir_keeps_required_skills_empty(
    store, registry, clock, random_source
) -> None:
    manifest = start_session(store, registry, clock, random_source, provider="claude-code")
    assert manifest["required_skills"] == []
    assert SKILL_REQUIRED not in [event.type for event in store.read()]


def test_start_resolves_the_default_required_skill(
    store, registry, clock, random_source, agent_skills_dir
) -> None:
    manifest = start_session(
        store,
        registry,
        clock,
        random_source,
        provider="claude-code",
        agent_skills_dir=agent_skills_dir,
    )
    assert manifest["required_skills"] == [{"skill_name": "run-english-session", "version": "1"}]
    events = list(store.read())
    required = [event for event in events if event.type == SKILL_REQUIRED]
    assert len(required) == 1
    assert required[0].payload["skill_name"] == "run-english-session"
    assert required[0].payload["version"] == "1"


def test_start_fails_outright_when_a_required_skill_is_unavailable(
    store, registry, clock, random_source, agent_skills_dir
) -> None:
    with pytest.raises(SessionPrecondition, match="unavailable"):
        start_session(
            store,
            registry,
            clock,
            random_source,
            provider="claude-code",
            agent_skills_dir=agent_skills_dir,
            required_skills=[("run-english-session", "999")],
        )
    assert store.count() == 0  # the refused start created nothing


def test_resume_attaches_the_agent_and_builds_a_briefing(
    store, full_registry, clock, random_source, agent_skills_dir
) -> None:
    manifest = start_session(
        store,
        full_registry,
        clock,
        random_source,
        provider="claude-code",
        agent_skills_dir=agent_skills_dir,
    )
    session_id = str(manifest["session_id"])

    result = resume_session(store, full_registry, clock, random_source, session_id, provider="codex")

    assert result["session_id"] == session_id
    assert result["status"] == "STARTED"
    assert result["notes"] == []  # no notes recorded yet -- an honest empty block

    briefing = result["briefing"]
    assert briefing["measured_working_level"] is None  # no evidence yet: honest no-data
    assert briefing["learning_score"] is None
    assert briefing["pending_reviews"] == 0
    assert briefing["xp"] == {"total": 0, "practice_days": 0, "streak": 0}

    # All seven continuation-contract sections are present, each an honest
    # no-data value before any evidence exists (never a fabricated zero/error).
    assert set(briefing) >= _REQUIRED_BRIEFING_FIELDS
    assert briefing["active_topics"] == []
    assert briefing["top_errors"] == []  # ERROR_OBSERVED not emitted yet
    assert briefing["recent_vocabulary"] == []
    assert briefing["recent_chunks"] == []
    assert briefing["re_entry"]["gap_days"] is None
    assert briefing["re_entry"]["at_risk_targets"] == []
    assert briefing["re_entry"]["lowest_retrievability"] is None
    assert briefing["recommendations"]["due_reviews"] == []
    assert briefing["last_session_summary"] is None

    events = list(store.read())
    attached = [event for event in events if event.type == EVENT_AGENT_ATTACHED]
    # start attaches the starting tutor too, so there are two attaches now:
    # the claude-code start, then the codex resume.
    assert [event.provider for event in attached] == ["claude-code", "codex"]
    assert attached[-1].payload["skills"] == manifest["required_skills"]
    assert result["agent_attached_event_id"] == attached[-1].id


def test_start_returns_the_same_contract_complete_briefing(
    store, full_registry, clock, random_source, agent_skills_dir
) -> None:
    # Finding 1: `session start` returns the tutor briefing in one call, using
    # the SAME builder as resume -- all seven sections, honest no-data cold.
    response = start_session(
        store,
        full_registry,
        clock,
        random_source,
        provider="claude-code",
        agent_skills_dir=agent_skills_dir,
    )
    briefing = response["briefing"]
    assert set(briefing) >= _REQUIRED_BRIEFING_FIELDS
    assert briefing["measured_working_level"] is None  # cold start: honest no-data
    assert briefing["top_errors"] == []
    assert briefing["last_session_summary"] is None

    # Trust boundary: the computed briefing rides the response only; the
    # persisted, immutable Session Manifest never carries it (lessons 4b).
    state, _ = get_session(store, str(response["session_id"]))
    assert "briefing" not in state["manifest"]


def test_resume_refuses_a_terminal_session(store, full_registry, clock, random_source) -> None:
    manifest = start_session(store, full_registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    event = abandon_session(store, clock, random_source, session_id)
    assert event.type.endswith("abandoned")

    with pytest.raises(SessionPrecondition):
        resume_session(store, full_registry, clock, random_source, session_id, provider="codex")


def test_resume_on_unknown_session_is_a_precondition(store, full_registry, clock, random_source) -> None:
    with pytest.raises(SessionPrecondition):
        resume_session(store, full_registry, clock, random_source, "no-such-session", provider="codex")


def test_resume_is_idempotent_by_provider_change_not_by_the_call_itself(
    store, full_registry, clock, random_source
) -> None:
    # Resume is not itself idempotent (each call attaches again) -- that
    # discipline belongs to the CLI's idempotency-key wrapper, not to
    # `resume_session` (mirrors every other lessons mutation).
    manifest = start_session(store, full_registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    resume_session(store, full_registry, clock, random_source, session_id, provider="codex")
    resume_session(store, full_registry, clock, random_source, session_id, provider="claude-code")
    attached = [event for event in store.read() if event.type == EVENT_AGENT_ATTACHED]
    # The start attaches the starting provider first, then the two resumes.
    assert [event.provider for event in attached] == ["claude-code", "codex", "claude-code"]
