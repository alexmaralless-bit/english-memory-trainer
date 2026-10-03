"""check_report / commit_report (lesson_report@1) [PD-2026-09-23].

Under test: the check is read-only and returns per-item accepted/rejected with
stable reason codes and the effects a commit would have (score, contributing
incl. the duplicate-span flag, review outcome); a rejected report writes
nothing; the commit is atomic and idempotent by key; reviews close by the
evidence@2 verdict table (correct/partial -> CONFIRMED, incorrect ->
REGRESSION), unaddressed ones INSUFFICIENT_EVIDENCE(not_attempted), skipped
ones INSUFFICIENT_EVIDENCE(<reason>); an empty report finishes a talk-only
lesson; lexicon entries are enrolled through the injected learner writer.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from english_trainer.evidence.reviews import REVIEW_AGGREGATE
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.errors import IdempotencyConflict
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.learner import find_encounter_entry, lexicon_entries
from english_trainer.lessons.report import ReportRejected, check_report, commit_report
from english_trainer.lessons.sessions import (
    FINISHED,
    SessionPrecondition,
    active_session_id,
    get_session,
    start_session,
)
from tests.lessons.report_support import (
    BE,
    CP,
    EPOCH,
    POSS,
    item,
    lexicon_ports,
    report,
    report_registry,
    start,
    start_with_review,
)

Env = tuple[EventStore, PolicyRegistry, FixedClock, SeededRandomSource]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    conn = connect(tmp_path / "report.db")
    migrate(conn)
    clock = FixedClock(EPOCH)
    try:
        yield EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(20260923)
    finally:
        conn.close()


def _check(env: Env, session_id: str, body: Any) -> dict[str, Any]:
    store, registry, _, _ = env
    return check_report(store, registry, session_id, body, encounter_lookup=find_encounter_entry)


def _commit(env: Env, session_id: str, body: Any, key: str = "key-1") -> dict[str, Any]:
    store, registry, clock, rnd = env
    return commit_report(
        store,
        registry,
        clock,
        rnd,
        session_id,
        body,
        provider="claude-code",
        idempotency_key=key,
        **lexicon_ports(),
    )


def _row(check: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(row for row in check["items"] if row["item_id"] == item_id)


def _codes(row: dict[str, Any]) -> list[str]:
    return [reason["code"] for reason in row["reasons"]]


# -- check ------------------------------------------------------------------------


def test_check_accepts_a_good_report_shows_effects_and_writes_nothing(env: Env) -> None:
    store = env[0]
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [
            item("i1", "I am a software engineer.", secondary_targets=[{"target_ref": "word.company"}]),
            item("i2", "I am a tester.", verdict="partial"),
            item("i3", "I am a software engineer."),  # the same span again
            item("i4", "company", target_ref="word.deadline", dimension="recognition", verdict="incorrect"),
        ],
    )
    before = store.count()
    check = _check(env, sid, body)
    assert store.count() == before
    assert check["valid"] is True and check["errors"] == []
    assert check["brief_hash"]["matches"] is True
    first = _row(check, "i1")
    assert first["status"] == "accepted"
    assert first["effects"]["score_ppm"] == 1_000_000
    assert first["effects"]["contributing"] is True
    assert first["effects"]["credit_targets"] == [
        {"target_ref": BE, "dimension": CP},
        {"target_ref": "word.company", "dimension": CP},
    ]
    assert _row(check, "i2")["effects"]["score_ppm"] == 500_000
    duplicate = _row(check, "i3")
    assert duplicate["status"] == "accepted"
    assert duplicate["effects"]["duplicate_span"] is True
    assert duplicate["effects"]["contributing"] is False
    assert any(w["code"] == "duplicate_span" and w["item_id"] == "i3" for w in check["warnings"])
    # A lexical item is an addressable target too.
    assert _row(check, "i4")["effects"]["step_type"] == "recognition_check"
    assert check["summary"]["duplicate_spans"] == 1
    assert check["requirements"][0]["met"] is True


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"target_ref": "grammar.nope"}, "unknown_target"),
        ({"secondary_targets": [{"target_ref": "word.nope"}]}, "unknown_target"),
        ({"dimension": "listening"}, "bad_dimension"),
        ({"raw_answer": "   "}, "empty_answer"),
        ({"raw_answer": "x" * 4001}, "answer_too_long"),
        ({"verdict": "almost"}, "bad_verdict"),
        ({"hints": -1}, "bad_hints"),
        ({"review_id": "no-such-review"}, "review_mismatch"),
        ({"block_id": "b-missing"}, "block_unknown"),
        (
            {"errors": [{"learner_form": "He are", "correction": "He is", "cause": "agreement"}]},
            "learner_form_not_in_answer",
        ),
        ({"errors": [{"learner_form": "I"}] * 11}, "too_many_errors"),
    ],
)
def test_check_rejects_an_inadmissible_item(env: Env, mutation: dict[str, Any], code: str) -> None:
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid, started["brief"], [item("ok", "I am a pilot."), {**item("bad", "I am a cook."), **mutation}]
    )
    check = _check(env, sid, body)
    assert check["valid"] is False
    assert _row(check, "ok")["status"] == "accepted"
    bad = _row(check, "bad")
    assert bad["status"] == "rejected" and bad["effects"] is None
    assert code in _codes(bad)


def test_check_rejects_a_duplicate_item_id(env: Env) -> None:
    started = start(*env)
    sid = started["session_id"]
    body = report(sid, started["brief"], [item("x", "I am a pilot."), item("x", "I am a cook.")])
    check = _check(env, sid, body)
    assert check["valid"] is False
    assert _codes(check["items"][1]) == ["duplicate_item_id"]


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"schema": "lesson_report@0"}, "bad_schema"),
        ({"session_id": "someone-else"}, "session_mismatch"),
        ({"items": {"not": "a list"}}, "bad_schema"),
        ({"summary": {"score": 0.5}}, "bad_schema"),  # binary floats are not canonical
    ],
)
def test_report_level_errors(env: Env, patch: dict[str, Any], code: str) -> None:
    started = start(*env)
    sid = started["session_id"]
    body = {**report(sid, started["brief"], [item("i1", "I am a pilot.")]), **patch}
    check = _check(env, sid, body)
    assert check["valid"] is False
    assert [error["code"] for error in check["errors"]] == [code]


def test_too_many_items_is_a_report_level_error(env: Env) -> None:
    started = start(*env)
    sid = started["session_id"]
    items = [item(f"i{n}", f"I am engineer number {n}.") for n in range(201)]
    check = _check(env, sid, report(sid, started["brief"], items))
    assert [error["code"] for error in check["errors"]] == ["too_many_items"]


def test_a_changed_or_missing_brief_hash_is_a_warning_only(env: Env) -> None:
    started = start(*env)
    sid = started["session_id"]
    body = report(sid, started["brief"], [item("i1", "I am a pilot.")])
    changed = _check(env, sid, {**body, "brief_hash": "0" * 64})
    assert changed["valid"] is True
    assert changed["brief_hash"]["matches"] is False
    assert "brief_changed" in [w["code"] for w in changed["warnings"]]
    missing = _check(env, sid, {**body, "brief_hash": None})
    assert missing["valid"] is True
    assert "brief_hash_missing" in [w["code"] for w in missing["warnings"]]


def test_unmet_requirements_are_warnings(env: Env) -> None:
    started = start(*env)
    sid = started["session_id"]
    check = _check(env, sid, report(sid, started["brief"], [item("i1", "My team is big.", target_ref=POSS)]))
    assert check["valid"] is True
    central = next(r for r in check["requirements"] if r["requirement_id"] == "central_topic_items")
    assert central["met"] is False and central["observed_items"] == 0
    assert "requirement_unmet" in [w["code"] for w in check["warnings"]]


def test_check_needs_an_active_evidence_v2_session(
    env: Env,
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
) -> None:
    legacy = start_session(store, registry, clock, random_source, provider="codex")
    with pytest.raises(SessionPrecondition, match="evidence"):
        check_report(store, registry, legacy["session_id"], {})
    with pytest.raises(SessionPrecondition, match="does not exist"):
        _check(env, "no-such-session", {})


# -- commit -----------------------------------------------------------------------


def test_a_rejected_report_writes_nothing(env: Env) -> None:
    store = env[0]
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid, started["brief"], [item("ok", "I am a pilot."), item("bad", "I am a cook.", verdict="meh")]
    )
    before = store.count()
    with pytest.raises(ReportRejected) as caught:
        _commit(env, sid, body)
    assert store.count() == before
    assert caught.value.code == "REPORT_REJECTED"
    assert _codes(_row(caught.value.check, "bad")) == ["bad_verdict"]
    state, _ = get_session(store, sid) or ({}, 0)
    assert state["status"] == "STARTED"
    assert active_session_id(store) == sid


def test_commit_finishes_the_session_and_is_idempotent_by_key(env: Env) -> None:
    store = env[0]
    started = start(*env)
    sid = started["session_id"]
    body = report(sid, started["brief"], [item("i1", "I am a pilot."), item("i2", "I am a pilot.")])
    result = _commit(env, sid, body)
    assert result["cached"] is False
    assert result["status"] == FINISHED
    assert [row["contributing"] for row in result["items"]] == [True, False]
    state, revision = get_session(store, sid) or ({}, 0)
    assert state["status"] == FINISHED and revision == result["session_revision"] == 3
    assert active_session_id(store) is None
    finished = [e for e in store.read() if e.type == "session.finished"]
    assert finished[-1].payload["from_status"] == "IN_PROGRESS"
    assert finished[-1].payload["reported_from_status"] == "STARTED"
    assert finished[-1].payload["closed_by"] == "lesson_report"

    count = store.count()
    again = _commit(env, sid, body)
    assert again["cached"] is True
    assert {k: v for k, v in again.items() if k != "cached"} == {
        k: v for k, v in result.items() if k != "cached"
    }
    assert store.count() == count
    with pytest.raises(IdempotencyConflict):
        _commit(env, sid, {**body, "summary": {"text": "другое"}})
    # A new key for a finished session is a precondition failure, not a second write.
    with pytest.raises(SessionPrecondition):
        _commit(env, sid, body, key="key-2")
    assert store.count() == count


def test_commit_event_order(env: Env) -> None:
    store = env[0]
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [
            item(
                "i1",
                "She are a manager.",
                verdict="incorrect",
                errors=[{"learner_form": "She are", "correction": "She is", "cause": "agreement"}],
            )
        ],
        lexicon=[{"surface": "pull an all-nighter", "linked_item_id": None, "note_ru": "не спать всю ночь"}],
    )
    count = store.count()
    _commit(env, sid, body)
    types = [e.type for e in store.read()][count:]
    assert types[0] == "lesson.reported"
    assert types[1] == "session.step_presented"
    assert types[2:4] == ["attempt.recorded", "evidence.added"]
    assert "evidence.error_observed" in types
    assert types[-2:] == ["learner.lexicon_entry_added", "session.finished"]
    reported = next(e for e in store.read() if e.type == "lesson.reported")
    assert reported.payload["report_hash"] and reported.payload["items"][0]["item_id"] == "i1"
    assert reported.payload["reviews_skipped"] == []
    presented = next(
        e for e in store.read() if e.type == "session.step_presented" and e.correlation_id == sid
    )
    assert presented.payload["source"] == "lesson_report"
    assert presented.payload["targets"] == [{"target_ref": BE, "dimension": CP, "role": "target"}]
    error = next(e for e in store.read() if e.type == "evidence.error_observed")
    assert error.payload["span_ref"]["start_utf8"] == 0 and error.payload["span_ref"]["end_utf8"] == 7
    assert error.payload["reported_by"] == "tutor"


def test_an_empty_report_finishes_a_talk_only_lesson(env: Env) -> None:
    store = env[0]
    started, review = start_with_review(*env)
    sid = started["session_id"]
    body = report(sid, started["brief"], [])
    check = _check(env, sid, body)
    assert check["valid"] is True
    assert "empty_report" in [w["code"] for w in check["warnings"]]
    assert check["reviews_unaddressed"] == [review["review_id"]]
    result = _commit(env, sid, body)
    assert result["status"] == FINISHED
    assert result["reviews"] == [
        {"review_id": review["review_id"], "outcome": "INSUFFICIENT_EVIDENCE", "reason": "not_attempted"}
    ]
    assert not [e for e in store.read() if e.type == "attempt.recorded" and e.correlation_id == sid]


@pytest.mark.parametrize(
    ("verdict", "outcome"),
    [("correct", "CONFIRMED"), ("partial", "CONFIRMED"), ("incorrect", "REGRESSION")],
)
def test_a_review_item_closes_by_the_verdict_table(env: Env, verdict: str, outcome: str) -> None:
    store = env[0]
    started, review = start_with_review(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [
            item(
                "r1",
                "Their project is late.",
                target_ref=review["target_ref"],
                dimension=review["dimension"],
                kind="review",
                verdict=verdict,
                review_id=review["review_id"],
            )
        ],
    )
    check = _check(env, sid, body)
    assert _row(check, "r1")["effects"]["review_outcome"] == {
        "review_id": review["review_id"],
        "outcome": outcome,
        "reason": None,
    }
    result = _commit(env, sid, body)
    assert result["reviews"] == [{"review_id": review["review_id"], "outcome": outcome, "reason": None}]
    state, _ = read_aggregate(store._conn, REVIEW_AGGREGATE, review["review_id"]) or ({}, 0)
    assert state["status"] == "closed" and state["outcome"] == outcome
    presented = [
        e
        for e in store.read()
        if e.type == "session.step_presented" and e.payload.get("review_assignment_id") == review["review_id"]
    ]
    assert len(presented) == 1 and presented[0].payload["kind"] == "review"


def test_a_review_item_with_a_repeated_span_closes_insufficient(env: Env) -> None:
    started, review = start_with_review(*env)
    sid = started["session_id"]
    # "My team is small." already earned credit for POSS in lesson 1.
    body = report(
        sid,
        started["brief"],
        [
            item(
                "r1",
                "My team is small.",
                target_ref=review["target_ref"],
                dimension=review["dimension"],
                review_id=review["review_id"],
            )
        ],
    )
    check = _check(env, sid, body)
    effects = _row(check, "r1")["effects"]
    assert effects["duplicate_span"] is True
    assert effects["review_outcome"]["outcome"] == "INSUFFICIENT_EVIDENCE"
    result = _commit(env, sid, body)
    assert result["reviews"][0]["outcome"] == "INSUFFICIENT_EVIDENCE"


def test_review_mismatch_on_target_and_a_second_claim(env: Env) -> None:
    started, review = start_with_review(*env)
    sid = started["session_id"]
    other_target = BE if review["target_ref"] != BE else POSS
    body = report(
        sid,
        started["brief"],
        [
            item("wrong", "I am a pilot.", target_ref=other_target, review_id=review["review_id"]),
            item(
                "right", "Their plan works.", target_ref=review["target_ref"], review_id=review["review_id"]
            ),
            item(
                "again", "Their plan fails.", target_ref=review["target_ref"], review_id=review["review_id"]
            ),
        ],
    )
    check = _check(env, sid, body)
    assert _codes(_row(check, "wrong")) == ["review_mismatch"]
    assert _row(check, "right")["status"] == "accepted"
    assert _codes(_row(check, "again")) == ["review_mismatch"]


def test_a_skipped_review_closes_insufficient_with_its_reason(env: Env) -> None:
    started, review = start_with_review(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [item("i1", "I am a pilot.")],
        reviews_skipped=[{"review_id": review["review_id"], "reason": "learner_declined"}],
    )
    check = _check(env, sid, body)
    assert check["reviews"]["skipped"] == [
        {"review_id": review["review_id"], "reason": "learner_declined", "outcome": "INSUFFICIENT_EVIDENCE"}
    ]
    assert check["reviews_unaddressed"] == []
    result = _commit(env, sid, body)
    assert result["reviews"] == [
        {"review_id": review["review_id"], "outcome": "INSUFFICIENT_EVIDENCE", "reason": "learner_declined"}
    ]


def test_a_skip_of_an_unknown_review_is_refused(env: Env) -> None:
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [item("i1", "I am a pilot.")],
        reviews_skipped=[{"review_id": "nope", "reason": "no_time"}],
    )
    check = _check(env, sid, body)
    assert check["valid"] is False
    assert check["skip_problems"][0]["reasons"][0]["code"] == "review_mismatch"


def test_lexicon_entries_new_already_enrolled_and_rejected(env: Env) -> None:
    store = env[0]
    started = start(*env)
    sid = started["session_id"]
    body = report(
        sid,
        started["brief"],
        [item("i1", "I am a pilot.")],
        lexicon=[
            {"surface": "pull an all-nighter", "linked_item_id": None, "note_ru": "не спать всю ночь"},
            {"surface": "deadline", "linked_item_id": "word.deadline", "note_ru": "срок"},
            {"surface": "Pull an  all-nighter", "linked_item_id": None},
        ],
    )
    check = _check(env, sid, body)
    assert [row["status"] for row in check["lexicon"]] == ["new", "new", "duplicate_in_report"]
    result = _commit(env, sid, body)
    assert [row["status"] for row in result["lexicon"]] == ["enrolled", "enrolled", "already_enrolled"]
    surfaces = sorted(str(entry["surface"]) for entry in lexicon_entries(store))
    assert surfaces == ["deadline", "pull an all-nighter"]

    started = start(*env)
    sid = started["session_id"]
    again = report(
        sid,
        started["brief"],
        [],
        lexicon=[
            {"surface": "pull an all-nighter", "linked_item_id": None},
            {"surface": "x", "linked_item_id": "grammar.be.identity"},  # a topic is not a lexical item
            {"surface": "  ", "linked_item_id": None},
        ],
    )
    check = _check(env, sid, again)
    assert [row["status"] for row in check["lexicon"]] == ["already_enrolled", "rejected", "rejected"]
    assert check["lexicon"][1]["reasons"][0]["code"] == "unknown_target"
    assert check["lexicon"][2]["reasons"][0]["code"] == "empty_surface"
    assert check["valid"] is False


def test_lexicon_needs_the_injected_writer(env: Env) -> None:
    store, registry, clock, rnd = env
    started = start(*env)
    sid = started["session_id"]
    body = report(sid, started["brief"], [], lexicon=[{"surface": "on it", "linked_item_id": None}])
    check = check_report(store, registry, sid, body)
    assert check["lexicon"][0]["status"] == "unchecked"
    assert "lexicon_unchecked" in [w["code"] for w in check["warnings"]]
    count = store.count()
    with pytest.raises(SessionPrecondition, match="lexicon writer"):
        commit_report(store, registry, clock, rnd, sid, body, provider="claude-code", idempotency_key="k")
    assert store.count() == count
