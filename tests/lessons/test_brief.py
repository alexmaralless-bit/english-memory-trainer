"""The lesson brief (lesson_brief@1) [PD-2026-09-23].

Under test: `session start` returns the brief with the pinned program's facts
(frames with frame_of/carries, examples, typical errors, the reconstruction
text of a drill), the session's review assignments, the advisory plan, the
learner block, lessons@2's advisory requirements and the report contract; the
brief is deterministic (resume rebuilds the same brief and hash, two fresh
stores build identical briefs); a brief/report session pins evidence@2,
lessons@2 and obligations@4 and does not pin rubric.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.lessons.brief import BRIEF_SCHEMA, REPORT_SCHEMA, brief_hash_of, build_brief
from english_trainer.lessons.report import commit_report
from english_trainer.lessons.resume import resume_session
from english_trainer.lessons.sessions import start_session
from tests.lessons.report_support import (
    BE,
    CP,
    EPOCH,
    POSS,
    item,
    lexicon_ports,
    report,
    report_registry,
)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[EventStore, PolicyRegistry, FixedClock, SeededRandomSource]]:
    conn = connect(tmp_path / "brief.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    try:
        yield EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(20260923)
    finally:
        conn.close()


def _start(env: Any, **kwargs: Any) -> dict[str, Any]:
    store, registry, clock, rnd = env
    options: dict[str, Any] = {"lesson_profile": "program_lesson", "target_ref": BE, "duration_minutes": 30}
    options.update(kwargs)
    return start_session(store, registry, clock, rnd, provider="claude-code", **options)


def test_start_returns_the_brief_and_pins_the_report_policy_set(env: Any) -> None:
    started = _start(env)
    pinned = started["pinned_versions"]
    assert pinned["evidence"] == "evidence@2"
    assert pinned["lessons"] == "lessons@2"
    assert pinned["obligations"] == "obligations@4"
    # rubric@1 is active but a brief/report session is not rubric-assessed.
    assert "rubric" not in pinned
    assert started["session_id"] and started["session_revision"] == 1
    # The new flow carries no step-protocol briefing (no delivery dependency).
    assert "briefing" not in started

    brief = started["brief"]
    assert brief["schema"] == BRIEF_SCHEMA
    assert brief["lesson"]["profile"] == "program_lesson"
    assert brief["lesson"]["duration_minutes"] == 30
    assert brief["lesson"]["agenda"]
    assert brief["lesson"]["language_envelope"]["correction_rhythm"] == "explain_then_retry"
    assert "rubric" not in brief["lesson"]["pinned_versions"]


def test_central_topic_carries_the_pinned_program_facts(env: Any) -> None:
    central = _start(env)["brief"]["central_topic"]
    assert central["target_ref"] == BE
    assert central["kind"] == "topic"
    assert central["can_do"].startswith("State identity")
    assert central["examples"] == ["I am a data analyst.", "Our company is small."]
    assert central["typical_errors"] == ["Omitting be in a statement (I engineer)."]
    frames = {frame["frame_ref"]: frame for frame in central["frames"]}
    # topic.lexicon ∩ chunks whose frame_of points back at the topic.
    assert set(frames) == {"chunk.be.i-am-a", "chunk.be.she-is", "chunk.be.they-are"}
    assert frames["chunk.be.i-am-a"]["frame_of"] == BE
    assert frames["chunk.be.i-am-a"]["carries"] == ["tense:present-simple"]
    assert frames["chunk.be.i-am-a"]["meaning_ru"] == "я (работаю)..."
    # Non-frame topic lexicon travels separately.
    assert [unit["target_ref"] for unit in central["key_lexicon"]] == ["word.company"]
    # A program lesson has no reconstruction step: no text is offered.
    assert central["reconstruction_text"] is None


def test_a_drill_brief_offers_the_reconstruction_text_and_the_block_material(env: Any) -> None:
    brief = _start(env, lesson_profile="drill")["brief"]
    text = brief["central_topic"]["reconstruction_text"]
    assert text["id"] == "text.recon.be.team-intro"
    assert text["target_spans"] == ["I am a data engineer", "Our team is"]
    blocks = [step for step in brief["plan"]["steps"] if step["step_type"] == "drill_block"]
    assert blocks, "the drill profile composes drill blocks"
    for step in blocks:
        assert step["drill_mode"] in ("blocked", "interleaved")
        assert step["round_size"] >= 1 and step["rounds"] >= 1
        material = step["material"]
        assert material["form"] == "drill_block"
        assert {frame["frame_ref"] for frame in material["frames"] if frame["role"] == "target"} >= {
            "chunk.be.i-am-a"
        }
    assert brief["plan"]["advisory"] is True


def test_requirements_and_report_contract(env: Any) -> None:
    brief = _start(env)["brief"]
    requirements = brief["requirements"]
    assert requirements["policy"] == "lessons@2"
    assert requirements["severity"] == "warning"
    assert requirements["items"] == [
        {
            "requirement_id": "central_topic_items",
            "target_ref": BE,
            "min_items": 1,
            "description": "Report at least this many answered items on the central topic.",
        }
    ]
    contract = brief["report_contract"]
    assert contract["schema"] == REPORT_SCHEMA
    assert contract["accepts_reports"] is True
    assert contract["verdict_scale"] == {"correct": 1_000_000, "partial": 500_000, "incorrect": 0}
    assert contract["review_outcome_by_verdict"]["partial"] == "CONFIRMED"
    assert contract["report_limits"] == {
        "max_items": 200,
        "max_answer_chars": 4000,
        "max_errors_per_item": 10,
    }
    assert contract["brief_hash"] == brief_hash_of(brief)


def test_resume_rebuilds_the_same_brief_even_days_later(env: Any) -> None:
    store, registry, clock, rnd = env
    started = _start(env)
    clock.advance(seconds=3 * 86400)
    resumed = resume_session(store, registry, clock, rnd, started["session_id"], provider="codex")
    assert canonical_json(resumed["brief"]) == canonical_json(started["brief"])
    assert build_brief(store, registry, started["session_id"]) == started["brief"]


def test_two_fresh_stores_build_identical_briefs(tmp_path: Path) -> None:
    briefs = []
    for name in ("a", "b"):
        conn = connect(tmp_path / f"{name}.db")
        migrate(conn)
        clock = FixedClock(EPOCH)
        try:
            env = (EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(7))
            briefs.append(canonical_json(_start(env)["brief"]))
        finally:
            conn.close()
    assert briefs[0] == briefs[1]


def test_reviews_errors_and_summary_reach_the_next_brief(env: Any) -> None:
    store, registry, clock, rnd = env
    first = _start(env)
    sid = first["session_id"]
    body = report(
        sid,
        first["brief"],
        [
            item("i1", "I am a software engineer."),
            item(
                "i2",
                "She are a manager.",
                verdict="incorrect",
                errors=[{"learner_form": "She are", "correction": "She is", "cause": "agreement"}],
            ),
            item("i3", "My team is small.", target_ref=POSS),
        ],
    )
    commit_report(store, registry, clock, rnd, sid, body, provider="claude-code", idempotency_key="k1")

    clock.advance(seconds=3 * 86400)
    brief = _start(env)["brief"]
    assert brief["reviews_due"], "evidence three days ago makes a review due"
    review = brief["reviews_due"][0]
    assert review["target_ref"] in (BE, POSS) and review["dimension"] == CP
    assert review["review_id"] and review["status"] == "pending" and review["urgency"]
    assert review["hint"]["can_do"]
    assert any(
        req["requirement_id"] == "reviews_addressed" and review["review_id"] in req["review_ids"]
        for req in brief["requirements"]["items"]
    )
    errors = brief["learner"]["recent_errors"]
    assert errors[0]["learner_form"] == "She are"
    assert errors[0]["correction"] == "She is"
    assert errors[0]["reported_by"] == "tutor"
    assert errors[0]["occurrences"] == 1
    summary = brief["last_session_summary"]
    assert summary["session_id"] == sid
    assert summary["report_summary"] == {"text": "Практиковали be.", "next_focus": "possessives"}
    assert brief["learner"]["re_entry"]["gap_days"] == 3


def test_a_session_without_the_report_policies_gets_no_report_contract(
    store: EventStore, registry: PolicyRegistry, clock, random_source
) -> None:
    """Without lessons@2/evidence@2 pinned the brief says reports are not
    accepted -- such a session can only be abandoned; the legacy step briefing
    went away with the step protocol [PD-2026-09-23]."""
    started = start_session(store, registry, clock, random_source, provider="codex")
    assert "briefing" not in started
    assert started["brief"]["report_contract"]["accepts_reports"] is False
    assert started["brief"]["central_topic"] is None


def test_lexicon_ports_are_the_learner_functions() -> None:
    ports = lexicon_ports()
    assert ports["encounter_builder"].__name__ == "build_encounter_events"
    assert ports["encounter_lookup"].__name__ == "find_encounter_entry"
