"""Session resume: required_skills resolution, AGENT_ATTACHED, and the lesson
brief as a block separate from state (lessons 4b/5; roadmap 2.5;
[PD-2026-09-23] -- the brief replaced the step-protocol briefing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from english_trainer.adapters.events import SKILL_REQUIRED
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.resume import EVENT_AGENT_ATTACHED, LEARNER_PREFERENCES_UPDATED, resume_session
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    get_session,
    start_session,
)

# The documented defaults (learner 4a): a brief before the first
# `preferences set` carries these, at preferences_version 0.
_DEFAULT_PREFERENCES = {
    "round_size": 6,
    "explanation_language": "ru",
    "preferred_drill_forms": [],
    "timed_limit_seconds": 240,
    "feedback_mode": "stage_dependent",
    "preferences_version": 0,
    "updated_at": None,
}


def _emit_preferences_updated(
    store: EventStore, clock: FixedClock, random_source: SeededRandomSource, **fields: object
) -> None:
    payload = {
        "round_size": 6,
        "explanation_language": "ru",
        "preferred_drill_forms": [],
        "timed_limit_seconds": 240,
        "feedback_mode": "stage_dependent",
        "preferences_version": 1,
        "updated_at": clock.now().isoformat(),
        **fields,
    }
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=LEARNER_PREFERENCES_UPDATED,
                    occurred_at=clock.now(),
                    actor="learner",
                    correlation_id="learner-preferences",
                    payload=payload,
                )
            ]
        )


# The learner-state sections the continuation flow requires of every brief
# (continuation "Состав tutor briefing", now `brief.learner`).
_REQUIRED_LEARNER_FIELDS = {
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
    required_skill = manifest["required_skills"][0]
    assert required_skill["skill_name"] == "run-english-session"
    assert required_skill["version"] == "1"
    assert required_skill["content_hash"]
    assert "session.start" in required_skill["cli_calls"]
    events = list(store.read())
    required = [event for event in events if event.type == SKILL_REQUIRED]
    assert len(required) == 1
    assert required[0].payload["skill_name"] == "run-english-session"
    assert required[0].payload["version"] == "1"
    assert required[0].payload["content_hash"] == required_skill["content_hash"]
    assert required[0].payload["cli_calls"] == required_skill["cli_calls"]


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


def test_resume_attaches_the_agent_and_rebuilds_the_brief(
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

    result = resume_session(
        store,
        full_registry,
        clock,
        random_source,
        session_id,
        provider="codex",
        agent_skills_dir=agent_skills_dir,
    )

    assert result["session_id"] == session_id
    assert result["status"] == "STARTED"
    assert "briefing" not in result and "notes" not in result  # the step-protocol blocks are gone

    brief = result["brief"]
    # Resume rebuilds the SAME brief (and brief_hash) the start returned.
    assert brief == manifest["brief"]
    learner = brief["learner"]
    assert learner["measured_working_level"] is None  # no evidence yet: honest no-data
    assert learner["learning_score"] is None
    assert brief["reviews_due"] == []
    assert learner["xp"] == {"total": 0, "practice_days": 0, "streak": 0}

    # Every continuation-contract section is present, each an honest no-data
    # value before any evidence exists (never a fabricated zero/error).
    assert set(learner) >= _REQUIRED_LEARNER_FIELDS
    assert learner["active_topics"] == []
    assert learner["recent_errors"] == []  # ERROR_OBSERVED not emitted yet
    assert learner["known_language"]["recent_vocabulary"] == []
    assert learner["known_language"]["recent_chunks"] == []
    assert learner["re_entry"]["gap_days"] is None
    assert learner["re_entry"]["at_risk_targets"] == []
    assert learner["re_entry"]["lowest_retrievability"] is None
    assert learner["due_backlog"] == []
    assert brief["last_session_summary"] is None
    # LearnerPreferences (learner 4a): the documented defaults before the
    # learner ever called `preferences set`, at preferences_version 0.
    assert learner["preferences"] == _DEFAULT_PREFERENCES

    events = list(store.read())
    attached = [event for event in events if event.type == EVENT_AGENT_ATTACHED]
    # start attaches the starting tutor too, so there are two attaches now:
    # the claude-code start, then the codex resume.
    assert [event.provider for event in attached] == ["claude-code", "codex"]
    assert attached[-1].payload["skills"] == manifest["required_skills"]
    assert result["agent_attached_event_id"] == attached[-1].id


def test_resume_refuses_when_the_exact_pinned_skill_snapshot_is_missing(
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
    active_skill = agent_skills_dir / "run-english-session" / "SKILL.md"
    active_skill.write_text(
        _SKILL_TEXT.replace('version: "1"', 'version: "2"'),
        encoding="utf-8",
    )

    with pytest.raises(SessionPrecondition, match="pinned tutor skill snapshot is unavailable"):
        resume_session(
            store,
            full_registry,
            clock,
            random_source,
            str(manifest["session_id"]),
            provider="codex",
            agent_skills_dir=agent_skills_dir,
        )

    attached = [event for event in store.read() if event.type == EVENT_AGENT_ATTACHED]
    assert len(attached) == 1


def test_start_returns_the_same_contract_complete_brief(
    store, full_registry, clock, random_source, agent_skills_dir
) -> None:
    # `session start` returns the lesson brief in one call, using the SAME
    # builder as resume -- every section, honest no-data cold.
    response = start_session(
        store,
        full_registry,
        clock,
        random_source,
        provider="claude-code",
        agent_skills_dir=agent_skills_dir,
    )
    assert "briefing" not in response
    learner = response["brief"]["learner"]
    assert set(learner) >= _REQUIRED_LEARNER_FIELDS
    assert learner["measured_working_level"] is None  # cold start: honest no-data
    assert learner["recent_errors"] == []
    assert response["brief"]["last_session_summary"] is None
    assert learner["preferences"] == _DEFAULT_PREFERENCES

    # Trust boundary: the computed brief rides the response only; the
    # persisted, immutable Session Manifest never carries it (lessons 4b).
    state, _ = get_session(store, str(response["session_id"]))
    assert "brief" not in state["manifest"] and "briefing" not in state["manifest"]


def test_start_brief_reflects_a_recorded_learner_preferences_snapshot(
    store, full_registry, clock, random_source
) -> None:
    _emit_preferences_updated(store, clock, random_source, round_size=8, explanation_language="en")
    response = start_session(store, full_registry, clock, random_source, provider="claude-code")
    preferences = response["brief"]["learner"]["preferences"]
    assert preferences["round_size"] == 8
    assert preferences["explanation_language"] == "en"
    assert preferences["preferences_version"] == 1


def test_resume_brief_reflects_the_latest_learner_preferences_snapshot(
    store, full_registry, clock, random_source
) -> None:
    manifest = start_session(store, full_registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    _emit_preferences_updated(store, clock, random_source, round_size=8, preferences_version=1)
    _emit_preferences_updated(
        store, clock, random_source, round_size=4, feedback_mode="always_explain", preferences_version=2
    )

    result = resume_session(store, full_registry, clock, random_source, session_id, provider="codex")

    preferences = result["brief"]["learner"]["preferences"]
    # The newest full snapshot wins outright -- never a merge of the two
    # (learner 4a versioned full-snapshot contract).
    assert preferences["round_size"] == 4
    assert preferences["feedback_mode"] == "always_explain"
    assert preferences["preferences_version"] == 2


def test_resume_refuses_a_terminal_session(store, full_registry, clock, random_source) -> None:
    manifest = start_session(store, full_registry, clock, random_source, provider="claude-code")
    session_id = str(manifest["session_id"])
    event = abandon_session(
        store,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
    )
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
