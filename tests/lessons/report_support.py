"""Shared set-up for the brief/report tests [PD-2026-09-23].

A miniature program (two topics with authored frames, one reconstruction text,
a few lexical items) and a registry that activates the brief/report policy set
(control@3, generation@3, scheduler@2, scoring@2, automaticity@1, evidence@2,
lessons@2, obligations@4, rubric@1 -- the last one active but NOT pinned by a
report session).
"""

from __future__ import annotations

import copy
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.learner import build_encounter_events, find_encounter_entry

REPO = Path(__file__).resolve().parents[2]
POLICIES = REPO / "curriculum" / "policies"
EPOCH = datetime(2026, 9, 23, 9, 0, 0, tzinfo=UTC)

BE = "grammar.be.identity"
POSS = "grammar.pronouns.possessives"
ORDER = "grammar.basic-word-order"
CP = "controlled_production"

_FRAME = {
    "type": "chunk",
    "curriculum_priority_band": "CORE",
    "usage_policy": "safe_to_use",
    "currency": "current",
    "domains": ["work"],
    "cefr": "A1",
    "carries": ["tense:present-simple"],
}

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": BE,
            "title": "Identity with be",
            "cefr": "A1",
            "can_do": "State identity, role, and company with forms of be.",
            "dimensions": ["recognition", "controlled_production", "spontaneous_production", "transfer"],
            "contexts": ["team-introduction"],
            "lexicon": ["chunk.be.i-am-a", "chunk.be.she-is", "chunk.be.they-are", "word.company"],
            "examples": ["I am a data analyst.", "Our company is small."],
            "typical_errors": ["Omitting be in a statement (I engineer)."],
            "explanation_language": "ru-allowed",
        },
        {
            "id": POSS,
            "cefr": "A1",
            "can_do": "Refer to people and ownership with possessives.",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": ["chunk.poss.my-team"],
            "examples": ["Their team has a demo today."],
            "typical_errors": ["he name instead of his name"],
        },
        {
            "id": ORDER,
            "cefr": "A1",
            "can_do": "Write simple statements in English word order.",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["status-update"],
            "lexicon": [],
            "examples": ["We test the model today."],
            "typical_errors": ["Dropping the subject."],
        },
    ],
    "lexicon": [
        {
            **_FRAME,
            "id": "chunk.be.i-am-a",
            "title": "I am a ___",
            "frame_of": BE,
            "meaning_ru": "я (работаю)...",
            "examples": ["I am a quality engineer."],
        },
        {**_FRAME, "id": "chunk.be.she-is", "title": "She is ___", "frame_of": BE, "meaning_ru": "она..."},
        {
            **_FRAME,
            "id": "chunk.be.they-are",
            "title": "They are ___",
            "frame_of": BE,
            "meaning_ru": "они...",
        },
        {
            **_FRAME,
            "id": "chunk.poss.my-team",
            "title": "my team",
            "frame_of": POSS,
            "meaning_ru": "моя команда",
        },
        {
            "id": "word.company",
            "type": "word",
            "title": "company",
            "meaning_ru": "компания",
            "curriculum_priority_band": "CORE",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
        },
        {
            "id": "word.deadline",
            "type": "word",
            "title": "deadline",
            "meaning_ru": "срок",
            "curriculum_priority_band": "HIGH",
            "usage_policy": "safe_to_use",
            "currency": "current",
            "domains": ["work"],
        },
    ],
    "texts": [
        {
            "id": "text.recon.be.team-intro",
            "title": "Team introduction",
            "cefr": "A1",
            "topic": BE,
            "carries": ["tense:present-simple"],
            "context": "team-introduction",
            "text": "I am a data engineer. Our team is small.",
            "keywords": ["I am a data engineer", "Our team is small"],
            "target_spans": ["I am a data engineer", "Our team is"],
            "summary_ru": "Представление в команде.",
        }
    ],
}

_POLICY_SET = (
    ("control", "control-v3.yaml", "control@3"),
    ("generation", "generation-v3.yaml", "generation@3"),
    ("scheduler", "scheduler-v2.yaml", "scheduler@2"),
    ("scoring", "scoring-v2.yaml", "scoring@2"),
    ("automaticity", "automaticity-v1.yaml", "automaticity@1"),
    ("evidence", "evidence-v2.yaml", "evidence@2"),
    ("lessons", "lessons-v2.yaml", "lessons@2"),
    ("obligations", "obligations-v4.yaml", "obligations@4"),
    ("rubric", "rubric-v1.yaml", "rubric@1"),
)


def policy(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((POLICIES / name).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def report_registry(conn: sqlite3.Connection, clock: FixedClock) -> PolicyRegistry:
    registry = PolicyRegistry(conn, clock)
    registry.register("curriculum", "v-report", copy.deepcopy(PROGRAM))
    registry.activate("curriculum", "v-report")
    for kind, filename, version in _POLICY_SET:
        registry.register(kind, version, policy(filename))
        registry.activate(kind, version)
    return registry


def lexicon_ports() -> dict[str, Any]:
    """The learner lexicon functions, injected into lessons.report."""
    return {"encounter_builder": build_encounter_events, "encounter_lookup": find_encounter_entry}


def item(
    item_id: str,
    raw_answer: str,
    *,
    target_ref: str = BE,
    dimension: str = CP,
    verdict: str = "correct",
    kind: str = "production",
    prompt: str = "Скажи по-английски.",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "target_ref": target_ref,
        "dimension": dimension,
        "kind": kind,
        "prompt": prompt,
        "raw_answer": raw_answer,
        "verdict": verdict,
        "hints": 0,
        "secondary_targets": [],
        "review_id": None,
        "block_id": None,
        "errors": [],
        **extra,
    }


def report(
    session_id: str, brief: dict[str, Any], items: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "schema": "lesson_report@1",
        "session_id": session_id,
        "brief_hash": brief["report_contract"]["brief_hash"],
        "items": items,
        "blocks": [],
        "reviews_skipped": [],
        "teaching": [],
        "lexicon": [],
        "summary": {"text": "Практиковали be.", "next_focus": "possessives"},
        **extra,
    }


def start(store: Any, registry: PolicyRegistry, clock: FixedClock, rnd: Any, **kwargs: Any) -> dict[str, Any]:
    from english_trainer.lessons.sessions import start_session

    options: dict[str, Any] = {"lesson_profile": "program_lesson", "target_ref": BE, "duration_minutes": 30}
    options.update(kwargs)
    return start_session(store, registry, clock, rnd, provider="claude-code", **options)


def start_with_review(
    store: Any, registry: PolicyRegistry, clock: FixedClock, rnd: Any, **kwargs: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lesson 1 reports correct answers; three days later lesson 2 starts with
    at least one due review. Returns ``(started lesson 2, its first review)``."""
    from english_trainer.lessons.report import commit_report

    first = start(store, registry, clock, rnd)
    body = report(
        first["session_id"],
        first["brief"],
        [item("warm-1", "I am a software engineer."), item("warm-2", "My team is small.", target_ref=POSS)],
    )
    commit_report(
        store,
        registry,
        clock,
        rnd,
        first["session_id"],
        body,
        provider="claude-code",
        idempotency_key="lesson-1",
    )
    clock.advance(seconds=3 * 86400)
    second = start(store, registry, clock, rnd, **kwargs)
    reviews = second["brief"]["reviews_due"]
    assert reviews, "a due review is composed into lesson 2"
    return second, reviews[0]


def enable_reports(registry: PolicyRegistry) -> PolicyRegistry:
    """Activate evidence@2 + lessons@2 on top of an existing (older) policy set.

    The per-step protocol is gone [PD-2026-09-23], so a test that needs
    evidence on a legacy control/scheduler/scoring set files it through a
    lesson report; everything else in the registry keeps its versions.
    """
    for kind, filename, version in (
        ("evidence", "evidence-v2.yaml", "evidence@2"),
        ("lessons", "lessons-v2.yaml", "lessons@2"),
    ):
        registry.register(kind, version, policy(filename))
        registry.activate(kind, version)
    return registry


def reported_session(
    store: Any,
    registry: PolicyRegistry,
    clock: FixedClock,
    rnd: Any,
    items: list[dict[str, Any]],
    *,
    provider: str = "claude-code",
    key: str | None = None,
    **start_options: Any,
) -> str:
    """Start a session, file ``items`` as its lesson report, return its id.

    ``registry`` must have evidence@2 + lessons@2 active (:func:`enable_reports`
    or :func:`report_registry`).
    """
    from english_trainer.lessons.report import commit_report
    from english_trainer.lessons.sessions import start_session

    started = start_session(store, registry, clock, rnd, provider=provider, **start_options)
    session_id = str(started["session_id"])
    body = report(session_id, started["brief"], items)
    commit_report(
        store,
        registry,
        clock,
        rnd,
        session_id,
        body,
        provider=provider,
        idempotency_key=key or f"report-{session_id}",
        **lexicon_ports(),
    )
    return session_id
