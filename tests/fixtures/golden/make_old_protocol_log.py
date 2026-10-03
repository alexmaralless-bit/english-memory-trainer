"""Generator for the golden fixture ``old_protocol_events.jsonl`` (W1-B).

This script is NOT a test and is never collected by pytest -- it is a one-shot
tool, run once by hand, whose OUTPUT is committed. It drives the per-step
protocol modules that W3 of the brief/report phase deleted, so it runs only on
a checkout that still has them (commit 37541a5 or earlier); it is kept as the
provenance of the frozen fixture, which is what the tests read:
``tests/fixtures/golden/old_protocol_events.jsonl`` (the exported event log)
and ``tests/fixtures/golden/expected.json`` (the scoring/automaticity replay
snapshot hashes computed from it).

Why this exists: the lesson-brief/report concept [PD-2026-09-23] deletes the
old per-step protocol commands (``session next``, ``exercise rendered``,
``attempt record``/``finalize``, ``review close``, ...) in a later wave. Before
that happens, this script drives a full, deterministic session through the
CURRENT public Python APIs -- the same ones ``tests/integration/
test_lean_protocol_flow.py`` and ``tests/integration/test_drill_block_flow.py``
exercise -- and captures the resulting event log. ``tests/scoring/
test_golden_replay.py`` then proves that ``scoring replay`` folds this fixed
log to the same snapshot hash forever, independent of which protocol produced
the events (the scoring fold is a pure function of the event log, never of the
producer).

Coverage driven through the OLD protocol, in one continuous event log:
  1. a placement decline with a self-assessment;
  2. a ``program_lesson`` session (control@2/generation@2) with a recorded
     teaching segment;
  3. a plain session (control@1/generation@1) with an OBJECTIVE attempt
     (``answer_key``), finished;
  4. two days later, the same target comes due for review: an OPEN,
     rubric-assessed attempt (``record`` -> ``finalize`` -> ``review close``,
     the long path -- the very path the lean protocol shortens) with a
     lexicon encounter recorded mid-session;
  5. a ``drill`` session (control@3/generation@3/evidence@1) with one drill
     block attempt.

Determinism: one ``FixedClock`` instant per step (never the wall clock) and
one ``SeededRandomSource`` shared across the whole run, exactly like the
integration tests this mirrors.
"""

from __future__ import annotations

# The deleted protocol modules no longer resolve as first-party, which would
# make the import sorter reorder this historical block; keep it as it ran.
# ruff: noqa: I001

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from english_trainer.assessments.placement import decline_placement
from english_trainer.evidence.assessment import finalize_attempt, span_hash
from english_trainer.evidence.attempts import record_attempt, record_block_attempt
from english_trainer.evidence.reviews import close_review, pending_assignments
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.export import JsonlExporter, export_pending
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.learner.lexicon import lexicon_encounter
from english_trainer.lessons.delivery import next_step, peek_step
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import finish_session, start_session
from english_trainer.lessons.teaching import record_teaching_segment
from english_trainer.scoring.replay import replay_scores

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
EPOCH = datetime(2026, 9, 23, 9, 0, tzinfo=UTC)
SEED = 20260923

# -- program v1 (grammar.be.identity growth/review/teaching sessions) --------

GRAMMAR_TARGET = "grammar.be.identity"
LEXICON_ITEM = "role.engineer"

PROGRAM_V1: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        {
            "id": GRAMMAR_TARGET,
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [LEXICON_ITEM],
        },
        {
            "id": "grammar.pronouns.possessives",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["team-introduction"],
            "lexicon": [],
        },
        {
            "id": "grammar.basic-word-order",
            "dimensions": ["recognition", "controlled_production"],
            "contexts": ["status-update"],
            "lexicon": [],
        },
    ],
    "lexicon": [
        {
            "id": LEXICON_ITEM,
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

OBJECTIVE = {
    "prompt": "Choose the form of be: I ___ an engineer.",
    "answer_key": ["am"],
    "provenance": {"origin": "authored"},
}
OPEN_REVIEW = {
    "prompt": "Explain in your own words when you use `am` and say what it does here.",
    "rubric_ref": "rubric:recognition.open",
    "provenance": {"origin": "authored"},
}
OPEN_ANSWER = (
    "I use am only with I, so `I am an engineer` states who I am right now, "
    "and it is the same verb that links me to the role."
)

TEACHING_SEGMENT = {
    "phase_id": "explanation",
    "title": "Be for identity",
    "explanation": "English keeps an explicit subject and a form of be.",
    "examples": ["I am an engineer.", "Maya is on the data team."],
    "common_errors": [
        {
            "learner_form": "I engineer.",
            "correction": "I am an engineer.",
            "explanation": "English identity clauses need be.",
        }
    ],
    "memory_insight": {
        "kind": "memory",
        "origin": "authored_explanation",
        "text": "Think of be as the bridge between a person and an identity.",
    },
    "sources": [],
    "provenance": {"origin": "authored", "provider": "codex"},
}

# -- program v3 (drill session: grammar.present-perfect.result) --------------

DRILL_TARGET = "grammar.present-perfect.result"
DRILL_CONTRAST = "grammar.past-simple.finished-time"


def _frame(topic: str, slug: str, title: str) -> dict[str, Any]:
    return {
        "id": f"chunk.{slug}",
        "type": "chunk",
        "title": title,
        "cefr": "A2",
        "curriculum_priority_band": "CORE",
        "register": "neutral",
        "transparency": "transparent",
        "domains": ["work"],
        "meaning_ru": f"смысл {slug}",
        "frame_of": topic,
        "carries": ["tense:present-perfect"],
        "examples": [title.replace("___", "sent the report")],
        "usage_policy": "safe_to_use",
        "currency": "current",
        "transformations": ["authored"],
    }


DRILL_FRAMES = [
    _frame(DRILL_TARGET, "pp.already-sent", "I've already ___"),
    _frame(DRILL_TARGET, "pp.just-finished", "I've just ___"),
    _frame(DRILL_CONTRAST, "ps.sent-yesterday", "I ___ yesterday"),
    _frame("grammar.articles.second-mention", "art.the-report", "the ___ I mentioned"),
]


def _drill_topic(topic_id: str) -> dict[str, Any]:
    return {
        "id": topic_id,
        "track": "Grammar Engine",
        "cefr": "A2",
        "frequency_tier": "big-five",
        "dimensions": ["recognition", "controlled_production"],
        "contexts": ["status-update"],
        "lexicon": [frame["id"] for frame in DRILL_FRAMES if frame["frame_of"] == topic_id],
    }


PROGRAM_V3: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        _drill_topic(DRILL_TARGET),
        _drill_topic(DRILL_CONTRAST),
        _drill_topic("grammar.articles.second-mention"),
    ],
    "lexicon": DRILL_FRAMES,
}

DRILL_PROMPTS: list[tuple[str, list[str]]] = [
    ("Я уже отправил отчёт.", ["I've already sent the report.", "I have already sent the report."]),
    ("Она только что закончила.", ["She's just finished.", "She has just finished."]),
    ("Мы это починили.", ["We've fixed it."]),
    ("Они перенесли дедлайн.", ["They've moved the deadline."]),
    ("Я ещё не закрыл тикет.", ["I haven't closed the ticket yet."]),
    ("Ты уже проверил логи?", ["Have you checked the logs yet?"]),
    ("Я выложил сборку.", ["I've deployed the build."]),
    ("Мы обновили документацию.", ["We've updated the docs."]),
    ("Он исправил тест.", ["He's fixed the test."]),
    ("Они ответили клиенту.", ["They've replied to the customer."]),
    ("Я перезапустил сервис.", ["I've restarted the service."]),
    ("Мы закрыли инцидент.", ["We've closed the incident."]),
]


def _policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _observations(answer: str, rubric_ref: str, pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    end = len(answer.encode("utf-8"))
    ref = f"{rubric_ref}#criterion:"
    return [
        {
            "rubric_criterion_ref": f"{ref}{criterion}",
            "finding_code": finding,
            "span_ref": {"start_utf8": 0, "end_utf8": end, "span_hash": span_hash(answer, 0, end)},
        }
        for criterion, finding in pairs
    ]


def _claim_until(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    rnd: SeededRandomSource,
    session_id: str,
    step_type: str,
) -> dict[str, Any]:
    claimed: dict[str, Any] | None = None
    while claimed is None or claimed["step"]["step_type"] != step_type:
        peeked = peek_step(store, session_id, registry)
        assert peeked["step"] is not None, f"plan exhausted before a {step_type} step"
        claimed = next_step(
            store,
            registry,
            clock,
            rnd,
            session_id,
            expected_session_revision=peeked["session_revision"],
            expected_plan_version=peeked["plan_version"],
        )
    return claimed


def _finish(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, session_id: str) -> None:
    """Close any still-pending review assignments, then finish the session.

    A session composed under one profile can still surface an ambient due
    review from an earlier session's schedule (spaced review is orthogonal to
    the lesson profile) -- closing whatever is pending, rather than assuming
    none exists, keeps the generator robust to that.
    """
    for assignment in pending_assignments(store, session_id):
        close_review(
            store,
            clock,
            rnd,
            session_id,
            str(assignment["review_id"]),
            expected_session_revision=current_session_revision(store, session_id),
        )
    finish_session(
        store, clock, rnd, session_id, expected_session_revision=current_session_revision(store, session_id)
    )


def build_log(db_path: Path) -> tuple[EventStore, PolicyRegistry]:
    conn = connect(db_path)
    migrate(conn)
    store = EventStore(conn)
    rnd = SeededRandomSource(SEED)
    registry = PolicyRegistry(conn, FixedClock(EPOCH))

    # -- policies active from the start: every session below pins whatever is
    # active at its own start_session call, so registering/activating
    # automaticity@1 FIRST means every session's evidence is eligible for the
    # AUTOMATICITY_UPDATED producer, giving a clean (non-"unrecorded") axis.
    registry.register("automaticity", "automaticity@1", _policy("automaticity-v1.yaml"))
    registry.activate("automaticity", "automaticity@1")

    registry.register("curriculum", "v-test", PROGRAM_V1)
    registry.activate("curriculum", "v-test")
    registry.register("generation", "generation@1", {"policy_id": "generation@1"})
    registry.activate("generation", "generation@1")
    registry.register("control", "control@1", _policy("control-v1.yaml"))
    registry.activate("control", "control@1")
    for filename, kind, version in (
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
        ("scoring-v1.yaml", "scoring", "scoring@1"),
        ("rubric-v1.yaml", "rubric", "rubric@1"),
    ):
        registry.register(kind, version, _policy(filename))
        registry.activate(kind, version)

    # -- 1. placement declined, with a per-skill self-assessment -------------
    decline_placement(
        store,
        registry,
        FixedClock(EPOCH),
        rnd,
        self_assessment={
            "schema_version": 1,
            "levels": {"grammar": "A2", "vocabulary": "A1", "reading": "A2", "writing": "A1"},
        },
        actor="learner",
    )

    # -- 2. day 0: a plain session, one OBJECTIVE attempt, finished ----------
    day0 = FixedClock(EPOCH)
    manifest = start_session(store, registry, day0, rnd, provider="claude-code")
    first = str(manifest["session_id"])
    claimed = next_step(
        store,
        registry,
        day0,
        rnd,
        first,
        expected_session_revision=current_session_revision(store, first),
        expected_plan_version=1,
    )
    step_id = str(claimed["step"]["step_id"])
    rendered = record_rendered_exercise(
        store,
        registry,
        day0,
        rnd,
        first,
        expected_session_revision=current_session_revision(store, first),
        step_id=step_id,
        exercise=dict(OBJECTIVE),
    )
    record_attempt(
        store,
        day0,
        rnd,
        first,
        expected_session_revision=current_session_revision(store, first),
        step_id=step_id,
        raw_answer="am",
        exercise_instance_id=str(rendered["exercise_instance_id"]),
        registry=registry,
    )
    _finish(store, day0, rnd, first)

    # -- 3. day 2: the review comes due; the long path (record -> finalize ->
    # review close) plus a mid-session lexicon encounter -----------------
    day2 = FixedClock(EPOCH + timedelta(days=2))
    second = str(start_session(store, registry, day2, rnd, provider="claude-code")["session_id"])
    version = 1
    while True:
        claimed = next_step(
            store,
            registry,
            day2,
            rnd,
            second,
            expected_session_revision=current_session_revision(store, second),
            expected_plan_version=version,
        )
        version = int(claimed["plan_version"])
        if claimed["step"]["kind"] == "review":
            break
    review_step = claimed["step"]
    review_id = str(review_step["review_assignment_id"])

    rendered = record_rendered_exercise(
        store,
        registry,
        day2,
        rnd,
        second,
        expected_session_revision=current_session_revision(store, second),
        step_id=str(review_step["step_id"]),
        exercise=dict(OPEN_REVIEW),
    )

    lexicon_encounter(
        store,
        day2,
        rnd,
        second,
        surface="engineer",
        note_ru="инженер",
        linked_item_id=LEXICON_ITEM,
        program=PROGRAM_V1,
        provider="claude-code",
        expected_session_revision=current_session_revision(store, second),
    )

    result = record_attempt(
        store,
        day2,
        rnd,
        second,
        expected_session_revision=current_session_revision(store, second),
        step_id=str(review_step["step_id"]),
        raw_answer=OPEN_ANSWER,
        exercise_instance_id=str(rendered["exercise_instance_id"]),
        registry=registry,
    )
    assert result["status"] == "recorded"
    finalize_attempt(
        store,
        registry,
        day2,
        rnd,
        second,
        str(result["attempt_id"]),
        expected_session_revision=current_session_revision(store, second),
        extra_observations=_observations(
            OPEN_ANSWER,
            "rubric:recognition.open",
            [
                ("meaning-accuracy", "required_meaning_stated"),
                ("task-fulfilment", "required_action_completed"),
            ],
        ),
    )
    closed = close_review(
        store,
        day2,
        rnd,
        second,
        review_id,
        expected_session_revision=current_session_revision(store, second),
    )
    assert closed["outcome"] == "CONFIRMED"
    _finish(store, day2, rnd, second)

    # -- 4. a program_lesson session (control@2/generation@2) with a recorded
    # teaching segment ---------------------------------------------------
    registry.register("control", "control@2", _policy("control-v2.yaml"))
    registry.activate("control", "control@2")
    registry.register("generation", "generation@2", _policy("generation-v2.yaml"))
    registry.activate("generation", "generation@2")

    teach_clock = FixedClock(EPOCH + timedelta(days=5))
    manifest = start_session(
        store,
        registry,
        teach_clock,
        rnd,
        provider="codex",
        lesson_profile="program_lesson",
        target_ref=GRAMMAR_TARGET,
    )
    third = str(manifest["session_id"])
    next_step(
        store,
        registry,
        teach_clock,
        rnd,
        third,
        expected_session_revision=current_session_revision(store, third),
        expected_plan_version=1,
    )
    record_teaching_segment(
        store,
        teach_clock,
        rnd,
        third,
        expected_session_revision=current_session_revision(store, third),
        segment=dict(TEACHING_SEGMENT),
    )
    _finish(store, teach_clock, rnd, third)

    # -- 5. a drill session (control@3/generation@3/evidence@1) with one drill
    # block attempt --------------------------------------------------------
    registry.register("curriculum", "v-drill", PROGRAM_V3)
    registry.activate("curriculum", "v-drill")
    registry.register("control", "control@3", _policy("control-v3.yaml"))
    registry.activate("control", "control@3")
    registry.register("generation", "generation@3", _policy("generation-v3.yaml"))
    registry.activate("generation", "generation@3")
    registry.register("evidence", "evidence@1", _policy("evidence-v1.yaml"))
    registry.activate("evidence", "evidence@1")

    drill_clock = FixedClock(EPOCH + timedelta(days=6))
    manifest = start_session(
        store,
        registry,
        drill_clock,
        rnd,
        provider="claude-code",
        lesson_profile="drill",
        target_ref=DRILL_TARGET,
    )
    fourth = str(manifest["session_id"])
    claimed = _claim_until(store, registry, drill_clock, rnd, fourth, "drill_block")
    step = claimed["step"]
    directive = step["generation_directive"]
    round_size = int(directive["round_size"])
    total = round_size * 2
    items = [
        {
            "index": index,
            "prompt": DRILL_PROMPTS[index][0],
            "answer_key": list(DRILL_PROMPTS[index][1]),
            "target_ref": DRILL_TARGET,
            "contrast": False,
            "form": "ru_to_en_sentence",
        }
        for index in range(total)
    ]
    rounds = [
        {"index": 0, "mode": "blocked", "item_indexes": list(range(round_size))},
        {"index": 1, "mode": "blocked", "item_indexes": list(range(round_size, total))},
    ]
    rendered = record_rendered_exercise(
        store,
        registry,
        drill_clock,
        rnd,
        fourth,
        expected_session_revision=claimed["session_revision"],
        step_id=step["step_id"],
        exercise={
            "form": "drill_block",
            "prompt": "Переведите каждую реплику одним предложением.",
            "items": items,
            "rounds": rounds,
            "lexicon_refs": [],
            "provenance": {"origin": "authored"},
        },
    )
    answers = [
        {"index": 0, "raw_answer": "I've already sent the report.", "latency_ms": 4200},
        {"index": 1, "raw_answer": "She has just finished.", "latency_ms": 5100},
        {"index": 2, "raw_answer": "We fixed it.", "latency_ms": 6000, "self_repaired": True},
        *[
            {"index": index, "raw_answer": DRILL_PROMPTS[index][1][0], "latency_ms": 3900}
            for index in range(3, total - 1)
        ],
    ]
    record_block_attempt(
        store,
        drill_clock,
        rnd,
        fourth,
        expected_session_revision=current_session_revision(store, fourth),
        step_id=step["step_id"],
        exercise_instance_id=rendered["exercise_instance_id"],
        items=answers,
        registry=registry,
        idempotency_key="golden-block-1",
    )
    _finish(store, drill_clock, rnd, fourth)

    return store, registry


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "golden.db"
        store, registry = build_log(db_path)

        jsonl_path = OUT_DIR / "old_protocol_events.jsonl"
        exporter = JsonlExporter(jsonl_path)
        export_pending(store, exporter, FixedClock(EPOCH))

        result = replay_scores(store, registry)
        expected = {
            "event_count": store.count(),
            "scoring_policy_version": result["policy_version"],
            "scoring_snapshot_hash": result["snapshot_hash"],
            "scoring_targets": result["targets"],
            "scoring_consistent": result["consistent"],
            "automaticity_policy_version": result["automaticity"]["policy_version"],
            "automaticity_snapshot_hash": result["automaticity"]["snapshot_hash"],
            "automaticity_targets": result["automaticity"]["target_count"],
            "automaticity_consistent": result["automaticity"]["consistent"],
        }
        (OUT_DIR / "expected.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
        print(json.dumps(expected, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
