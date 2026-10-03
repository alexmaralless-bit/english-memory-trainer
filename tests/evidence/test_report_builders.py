"""Tutor-verdict report builders (evidence@2, [PD-2026-09-23]).

The lesson report changes the producer of the evidence facts, not their
contract. Under test: the evidence@2 policy validates beside evidence@1; the
verdict maps to ``score_ppm`` through the pinned scale; spans are derived from
the quoted learner form (UTF-8 byte offsets, the rubric span contract); the
builders are pure; and a whole report appended item by item inside ONE
UnitOfWork yields the automaticity, state-transition, schedule, XP and
recurring-error facts the existing consumers already read.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.control.saturation import recurring_error_keys
from english_trainer.evidence.assessment import span_hash
from english_trainer.evidence.attempts import ATTEMPT_AGGREGATE, EVENT_ATTEMPT_RECORDED, EVENT_EVIDENCE_ADDED
from english_trainer.evidence.observed import EVENT_ERROR_OBSERVED
from english_trainer.evidence.policy import (
    EvidencePolicyInvalid,
    multi_credit_policy,
    require_valid,
    require_valid_verdict_leaves,
    verdict_policy,
)
from english_trainer.evidence.report import (
    ReportInputInvalid,
    answer_span_hash,
    automaticity_updates,
    build_attempt_payload,
    build_block_attempt_payload,
    build_error_payload,
    build_evidence_payload,
    derive_span,
    item_events,
    span_already_credited,
    verdict_assessment,
    verdict_score,
)
from english_trainer.evidence.reviews import (
    REVIEW_AGGREGATE,
    _outcome_from_assessment,
    close_insufficient,
    closure_from_verdict,
)
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scheduler.engine import fold_schedules
from english_trainer.scoring.aggregates import xp_ledger
from english_trainer.scoring.automaticity import DELIBERATE, EVENT_AUTOMATICITY_UPDATED, NOT_MEASURED
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.transitions import EVENT_STATE_TRANSITION

EPOCH = datetime(2026, 7, 22, 9, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]
POLICIES = REPO / "curriculum" / "policies"

BE = "grammar.be.identity"
POSS = "grammar.pronouns.possessives"
DIM = "controlled_production"


def _yaml(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((POLICIES / name).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


V2 = _yaml("evidence-v2.yaml")
VERDICTS = require_valid_verdict_leaves(V2)


# -- policy -------------------------------------------------------------------


def _validated_span(raw_answer: str, span: dict[str, Any]) -> dict[str, Any]:
    """The rubric span contract, verbatim (the removed ``observed record``
    validator): in-bounds UTF-8 byte offsets on character boundaries with the
    matching ``span_hash``."""
    start, end = int(span["start_utf8"]), int(span["end_utf8"])
    data = raw_answer.encode("utf-8")
    assert 0 <= start < end <= len(data)
    data[:start].decode("utf-8")
    data[:end].decode("utf-8")
    expected = span_hash(raw_answer, start, end)
    assert span["span_hash"] == expected
    return {"start_utf8": start, "end_utf8": end, "span_hash": expected}


def test_both_evidence_versions_validate() -> None:
    assert require_valid(_yaml("evidence-v1.yaml"))["policy_id"] == "evidence@1"
    assert require_valid(V2)["policy_id"] == "evidence@2"
    # evidence@2 keeps evidence@1's allocation decisions byte-for-byte.
    assert V2["multi_credit"] == _yaml("evidence-v1.yaml")["multi_credit"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(policy_id="evidence@3"),
        lambda p: p.update(schema_version=1),
        lambda p: p["verdict_scale"].update(partial=1_000_001),
        lambda p: p["verdict_scale"].update(partial=True),
        lambda p: p["verdict_scale"].update(incorrect=600_000),
        lambda p: p["verdict_scale"].update(correct=900_000),
        lambda p: p["verdict_scale"].pop("partial"),
        lambda p: p["review_outcome_by_verdict"].update(partial="RECOVERED"),
        lambda p: p["report_limits"].update(max_items=0),
        lambda p: p["tutor_errors"].update(default_severity="fatal"),
        lambda p: p.pop("verdict_scale"),
    ],
)
def test_a_broken_evidence_v2_is_refused(mutate: Any) -> None:
    broken = copy.deepcopy(V2)
    mutate(broken)
    with pytest.raises(EvidencePolicyInvalid):
        require_valid(broken)


def test_verdict_policy_needs_a_pinned_v2(store: EventStore, registry: PolicyRegistry) -> None:
    registry.register("evidence", "evidence@1", _yaml("evidence-v1.yaml"))
    registry.register("evidence", "evidence@2", V2)
    assert verdict_policy(registry, {"evidence": "evidence@2"}) == VERDICTS
    with pytest.raises(EvidencePolicyInvalid):
        verdict_policy(registry, {"evidence": "evidence@1"})
    with pytest.raises(EvidencePolicyInvalid):
        verdict_policy(registry, {})


# -- verdict ------------------------------------------------------------------


def test_verdicts_map_through_the_pinned_scale() -> None:
    assert verdict_score("correct", VERDICTS) == 1_000_000
    assert verdict_score("partial", VERDICTS) == 500_000
    assert verdict_score("incorrect", VERDICTS) == 0
    assert verdict_assessment("partial", VERDICTS) == {
        "basis": "tutor_verdict",
        "verdict": "partial",
        "correct": False,
        "score_ppm": 500_000,
        "contributing": True,
    }


@pytest.mark.parametrize("verdict", ["Correct", "right", "", "PARTIAL"])
def test_an_unknown_verdict_is_refused(verdict: str) -> None:
    with pytest.raises(ReportInputInvalid) as caught:
        verdict_score(verdict, VERDICTS)
    assert caught.value.reason == "bad_verdict"


def test_the_review_map_is_the_policys() -> None:
    table = VERDICTS["review_outcome_by_verdict"]
    for verdict, outcome in [("correct", "CONFIRMED"), ("partial", "CONFIRMED"), ("incorrect", "REGRESSION")]:
        assert _outcome_from_assessment(verdict_assessment(verdict, VERDICTS), table) == (outcome, None)
    # The default table is the evidence@2 one; a repeated span never moves.
    assert _outcome_from_assessment(verdict_assessment("partial", VERDICTS)) == ("CONFIRMED", None)
    repeated = verdict_assessment("correct", VERDICTS, contributing=False)
    assert _outcome_from_assessment(repeated, table) == ("INSUFFICIENT_EVIDENCE", "no_credited_span")
    unknown = {"basis": "tutor_verdict", "verdict": "maybe"}
    assert _outcome_from_assessment(unknown, table) == ("INSUFFICIENT_EVIDENCE", "unknown_verdict")


# -- spans --------------------------------------------------------------------


def test_span_is_derived_in_utf8_bytes() -> None:
    raw = "I am a teacher and an editor."
    span = derive_span(raw, "an editor")
    assert span is not None
    assert raw.encode("utf-8")[span["start_utf8"] : span["end_utf8"]] == b"an editor"
    assert span["span_hash"] == span_hash(raw, span["start_utf8"], span["end_utf8"])
    assert span["span_hash"].startswith("sha256:")
    # The derived span satisfies the rubric span contract verbatim.
    assert _validated_span(raw, span) == span


def test_span_offsets_count_bytes_not_characters_in_cyrillic_text() -> None:
    raw = "Я думаю, he go to work every day — да."
    span = derive_span(raw, "he go")
    assert span is not None
    prefix = "Я думаю, "
    assert span["start_utf8"] == len(prefix.encode("utf-8")) != len(prefix)
    assert span["end_utf8"] - span["start_utf8"] == len(b"he go")
    cyrillic = derive_span(raw, "да")
    assert cyrillic is not None
    assert raw.encode("utf-8")[cyrillic["start_utf8"] : cyrillic["end_utf8"]].decode("utf-8") == "да"
    assert _validated_span(raw, cyrillic) == cyrillic


def test_the_first_occurrence_wins_and_absence_is_none() -> None:
    raw = "a cat and a cat"
    span = derive_span(raw, "a cat")
    assert span is not None and span["start_utf8"] == 0
    assert derive_span(raw, "the cat") is None
    assert derive_span(raw, "") is None
    assert derive_span(raw, "A CAT") is None  # exact form, never a guess


def test_an_error_whose_form_is_not_in_the_answer_is_refused() -> None:
    with pytest.raises(ReportInputInvalid) as caught:
        build_error_payload(
            observed_error_id="E1",
            attempt_id="A1",
            session_id="S1",
            item_id="i1",
            target_ref=BE,
            dimension=DIM,
            raw_answer="She is engineer.",
            error={"learner_form": "is a engineer", "correction": "is an engineer", "cause": "article"},
            severity="major",
            observed_at="2026-07-22T09:00:00+00:00",
        )
    assert caught.value.reason == "learner_form_not_in_answer"


# -- purity -------------------------------------------------------------------


def _attempt(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "attempt_id": "A1",
        "session_id": "S1",
        "step_id": "P1",
        "item_id": "i1",
        "step_type": "controlled_production",
        "kind": "production",
        "target_ref": BE,
        "dimension": DIM,
        "prompt": "Она инженер.",
        "raw_answer": "She is engineer.",
        "verdict": "partial",
        "policy": VERDICTS,
        "recorded_at": "2026-07-22T09:00:00+00:00",
        "secondary_targets": [{"target_ref": POSS}],
        "hints": 1,
    }
    base.update(overrides)
    return build_attempt_payload(**base)


def test_builders_are_pure_and_deterministic() -> None:
    first, second = _attempt(), _attempt()
    assert first == second
    assert first["status"] == "assessed"
    assert first["assessment"] == {
        "basis": "tutor_verdict",
        "verdict": "partial",
        "correct": False,
        "score_ppm": 500_000,
        "contributing": True,
    }
    assert first["targets"] == [{"target_ref": BE, "dimension": DIM}, {"target_ref": POSS, "dimension": DIM}]
    assert first["response_latency_ms"] is None
    policy = {"primary_weight": "1.0", "secondary_weight": "0.5", "total_weight_cap": "2.0"}
    evidence = build_evidence_payload(first, evidence_id="EV1", multi_credit=policy)
    assert evidence == build_evidence_payload(second, evidence_id="EV1", multi_credit=policy)
    assert evidence is not None
    assert evidence["assessment_basis"] == "tutor_verdict"
    assert evidence["score_ppm"] == 500_000 and evidence["correct"] is False
    assert evidence["prompt"] == "Она инженер."
    assert [(a["target_ref"], a["contribution"], a["used"]) for a in evidence["credit_allocations"]] == [
        (BE, "1.0", True),
        (POSS, "0.5", True),
    ]
    # A repeated span records but mints no evidence.
    repeated = _attempt(contributing=False)
    assert repeated["non_contributing"] is True
    assert build_evidence_payload(repeated, evidence_id="EV1", multi_credit=policy) is None


def test_an_empty_answer_is_refused() -> None:
    with pytest.raises(ReportInputInvalid) as caught:
        _attempt(raw_answer="   ")
    assert caught.value.reason == "empty_answer"


# -- a whole report in one UnitOfWork -------------------------------------------


@pytest.fixture
def pinned(registry: PolicyRegistry) -> dict[str, str]:
    for kind, name, version in [
        ("evidence", "evidence-v2.yaml", "evidence@2"),
        ("scoring", "scoring-v2.yaml", "scoring@2"),
        ("scheduler", "scheduler-v2.yaml", "scheduler@2"),
        ("automaticity", "automaticity-v1.yaml", "automaticity@1"),
    ]:
        registry.register(kind, version, _yaml(name))
        registry.activate(kind, version)
    return {
        "curriculum": "v-test",
        "evidence": "evidence@2",
        "scoring": "scoring@2",
        "scheduler": "scheduler@2",
        "automaticity": "automaticity@1",
    }


def _start(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, pinned: dict[str, str]) -> str:
    """A started session plus three pending review assignments, straight into the log."""
    session_id = new_ulid(clock, rnd)
    manifest = {"provider": "claude-code", "pinned_versions": pinned}
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type="session.started",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=session_id,
                    payload={"session_id": session_id, "manifest": manifest},
                )
            ]
        )
        for review_id, target in [("R-BE-1", BE), ("R-BE-2", BE), ("R-POSS", POSS), ("R-SKIP", POSS)]:
            uow.save_aggregate(
                REVIEW_AGGREGATE,
                review_id,
                {
                    "review_id": review_id,
                    "session_id": session_id,
                    "step_id": f"planned-{review_id}",
                    "target_ref": target,
                    "dimension": DIM,
                    "status": "pending",
                    "schedule_epoch": 1,
                },
                expected_revision=0,
            )
    return session_id


REPORT_ITEMS: list[dict[str, Any]] = [
    {"item_id": "b1-1", "block_id": "b1", "raw_answer": "She's an engineer.", "verdict": "correct"},
    {"item_id": "b1-2", "block_id": "b1", "raw_answer": "We're a team.", "verdict": "correct"},
    {"item_id": "b1-3", "block_id": "b1", "raw_answer": "I are ready.", "verdict": "incorrect"},
    {"item_id": "b1-4", "block_id": "b1", "raw_answer": "They're developers.", "verdict": "correct"},
    {"item_id": "b2-1", "block_id": "b2", "raw_answer": "He's a designer.", "verdict": "correct"},
    {"item_id": "b2-2", "block_id": "b2", "raw_answer": "You're late.", "verdict": "correct"},
    {"item_id": "b2-3", "block_id": "b2", "raw_answer": "It's mine.", "verdict": "correct"},
    {"item_id": "b2-4", "block_id": "b2", "raw_answer": "I'm tired.", "verdict": "correct"},
    {
        "item_id": "r1",
        "review_id": "R-BE-1",
        "target_ref": BE,
        "raw_answer": "I am a developer.",
        "verdict": "correct",
    },
    {
        "item_id": "r2",
        "review_id": "R-BE-2",
        "target_ref": BE,
        "raw_answer": "She is a QA.",
        "verdict": "partial",
    },
    {
        "item_id": "p1",
        "review_id": "R-POSS",
        "target_ref": POSS,
        "raw_answer": "It is my laptop and it is him phone.",
        "verdict": "incorrect",
        "errors": [{"learner_form": "him phone", "correction": "his phone", "cause": "object vs possessive"}],
    },
    {
        "item_id": "p2",
        "target_ref": POSS,
        "raw_answer": "Это her book, not him book.",
        "verdict": "incorrect",
        "errors": [{"learner_form": "him book", "correction": "his book", "cause": "object vs possessive"}],
    },
    # A repeated span for the same (target, dimension): recorded, not credited.
    {"item_id": "dup", "target_ref": BE, "raw_answer": "I am a developer.", "verdict": "correct"},
]


def _commit(
    store: EventStore,
    clock: FixedClock,
    rnd: SeededRandomSource,
    registry: PolicyRegistry,
    session_id: str,
    pinned: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Commit the report the way ``lessons.report.commit_report`` will: one
    UnitOfWork, facts appended item by item, derived facts built after the
    earlier items are in the log."""
    policy = verdict_policy(registry, pinned)
    multi_credit = multi_credit_policy(registry, pinned)
    severity = policy["tutor_errors"]["default_severity"]
    table = policy["review_outcome_by_verdict"]
    closures: dict[str, dict[str, Any]] = {}
    with UnitOfWork(store, clock) as uow:
        blocks = ["b1", "b2"]
        for block_id in blocks:
            members = [item for item in REPORT_ITEMS if item.get("block_id") == block_id]
            attempt = build_block_attempt_payload(
                store,
                attempt_id=new_ulid(clock, rnd),
                session_id=session_id,
                step_id=f"step-{block_id}",
                block_id=block_id,
                step_type="drill_block",
                target_ref=BE,
                dimension=DIM,
                items=members,
                policy=policy,
                recorded_at=clock.now().isoformat(),
                mode="blocked",
            )
            uow.save_aggregate(ATTEMPT_AGGREGATE, attempt["attempt_id"], attempt, expected_revision=0)
            batch = item_events(
                clock, rnd, attempt=attempt, multi_credit=multi_credit, severity=severity, pinned=pinned
            )
            uow.append([*batch, *automaticity_updates(store, clock, registry, batch)])
        for item in REPORT_ITEMS:
            if item.get("block_id"):
                continue
            primary = {"target_ref": item["target_ref"], "dimension": DIM}
            duplicate = span_already_credited(store, answer_span_hash(item["raw_answer"]), primary)
            attempt = build_attempt_payload(
                attempt_id=new_ulid(clock, rnd),
                session_id=session_id,
                step_id=f"step-{item['item_id']}",
                item_id=item["item_id"],
                step_type="controlled_production",
                kind="review" if item.get("review_id") else "production",
                target_ref=item["target_ref"],
                dimension=DIM,
                prompt="Скажи по-английски.",
                raw_answer=item["raw_answer"],
                verdict=item["verdict"],
                policy=policy,
                recorded_at=clock.now().isoformat(),
                contributing=not duplicate,
                review_id=item.get("review_id"),
            )
            uow.save_aggregate(ATTEMPT_AGGREGATE, attempt["attempt_id"], attempt, expected_revision=0)
            batch = item_events(
                clock,
                rnd,
                attempt=attempt,
                multi_credit=multi_credit,
                errors=item.get("errors", []),
                severity=severity,
                pinned=pinned,
            )
            uow.append([*batch, *automaticity_updates(store, clock, registry, batch)])
            if item.get("review_id"):
                closures[item["review_id"]] = closure_from_verdict(
                    store,
                    uow,
                    clock,
                    rnd,
                    session_id,
                    item["review_id"],
                    attempt=attempt,
                    outcome_by_verdict=table,
                    pinned=pinned,
                    provider="claude-code",
                )
        closures["R-SKIP"] = close_insufficient(
            store, uow, clock, rnd, session_id, "R-SKIP", reason="no_time", pinned=pinned
        )
    return closures


def test_a_report_batch_in_one_unit_of_work(
    store: EventStore,
    clock: FixedClock,
    random_source: SeededRandomSource,
    registry: PolicyRegistry,
    pinned: Any,
) -> None:
    session_id = _start(store, clock, random_source, pinned)
    closures = _commit(store, clock, random_source, registry, session_id, pinned)
    events = list(store.read())

    # -- attempts and evidence -----------------------------------------------
    recorded = [e for e in events if e.type == EVENT_ATTEMPT_RECORDED]
    evidence = [e for e in events if e.type == EVENT_EVIDENCE_ADDED]
    assert len(recorded) == 2 + 5  # two blocks + five single items
    assert all(e.payload["status"] == "assessed" for e in recorded)
    assert all(e.payload["assessment"]["basis"] == "tutor_verdict" for e in recorded)
    assert len(evidence) == 2 + 4  # the repeated span mints no evidence
    dup = next(e for e in recorded if e.payload.get("item_id") == "dup")
    assert dup.payload["non_contributing"] is True
    b1 = next(e for e in evidence if e.payload.get("block_id") == "b1")
    assert b1.payload["form"] == "drill_block"
    assert [item["objective_correct"] for item in b1.payload["items"]] == [True, True, False, True]
    assert [item["verdict"] for item in b1.payload["items"]] == ["correct", "correct", "incorrect", "correct"]
    assert all("latency_ms" not in item for item in b1.payload["items"])
    assert b1.payload["block_score_ppm"] == 750_000 and b1.payload["correct"] is True
    # Every aggregate was saved and is settled.
    for event in recorded:
        found = read_aggregate(store._conn, ATTEMPT_AGGREGATE, event.payload["attempt_id"])
        assert found is not None and found[0]["status"] == "assessed"

    # -- automaticity: the second block saw the first -------------------------------
    axis = [e for e in events if e.type == EVENT_AUTOMATICITY_UPDATED]
    assert [e.causation_id for e in axis] == [
        e.id for e in evidence if e.payload.get("form") == "drill_block"
    ]
    assert axis[0].payload["from_state"] == NOT_MEASURED and axis[0].payload["to_state"] == DELIBERATE
    # 3/4 then 4/4 correct: the window accuracy over BOTH blocks (7/8) proves
    # the second fold saw the first block, appended earlier in the same UoW.
    assert axis[0].payload["accuracy_ppm"] == 750_000
    assert axis[1].payload["accuracy_ppm"] == 875_000

    # -- reviews: mapped by the pinned table, transitions threaded ------------------
    assert {k: v["outcome"] for k, v in closures.items()} == {
        "R-BE-1": "CONFIRMED",
        "R-BE-2": "CONFIRMED",  # partial confirms (PD-2026-09-23)
        "R-POSS": "REGRESSION",
        "R-SKIP": "INSUFFICIENT_EVIDENCE",
    }
    assert closures["R-SKIP"]["reason"] == "no_time"
    outcomes = [e for e in events if e.type == "review.outcome"]
    transitions = {e.causation_id: e.payload for e in events if e.type == EVENT_STATE_TRANSITION}
    assert len(transitions) == len(outcomes) == 4
    by_review = {e.payload["review_id"]: transitions[e.id] for e in outcomes}
    # The second BE closure sees the first one's transition inside the same UoW.
    assert (by_review["R-BE-1"]["from_state"], by_review["R-BE-1"]["to_state"]) == ("NEW", "LEARNING")
    assert (by_review["R-BE-2"]["from_state"], by_review["R-BE-2"]["to_state"]) == ("LEARNING", "ACTIVE")
    assert by_review["R-POSS"]["to_state"] == "NEW"
    for review_id in closures:
        found = read_aggregate(store._conn, REVIEW_AGGREGATE, review_id)
        assert found is not None and found[0]["status"] == "closed"
    # Idempotent re-close: no second outcome.
    with UnitOfWork(store, clock) as uow:
        again = close_insufficient(
            store, uow, clock, random_source, session_id, "R-BE-1", reason="not_attempted", pinned=pinned
        )
    assert again["already"] is True and again["outcome"] == "CONFIRMED"
    assert sum(1 for e in store.read() if e.type == "review.outcome") == 4

    # -- errors -----------------------------------------------------------------
    observed = [e for e in events if e.type == EVENT_ERROR_OBSERVED]
    assert [e.payload["learner_form"] for e in observed] == ["him phone", "him book"]
    for event in observed:
        payload = event.payload
        assert payload["reported_by"] == "tutor" and payload["severity"] == "major"
        assert (payload["target_ref"], payload["dimension"]) == (POSS, DIM)
        attempt = next(e for e in recorded if e.payload["attempt_id"] == payload["attempt_id"])
        assert _validated_span(attempt.payload["raw_answer"], payload["span_ref"]) == payload["span_ref"]
    control = _yaml("control-v1.yaml")
    assert recurring_error_keys(events, control) == frozenset({(POSS, DIM)})

    # -- scheduler and XP read the facts unchanged -------------------------------
    # fold_scores accepts the facts; knowledge state follows the review outcomes
    # alone, independent of how the scoring branch weighs a tutor verdict.
    scores = fold_scores(store, _yaml("scoring-v2.yaml"))
    assert scores[BE].knowledge_state == "ACTIVE"
    assert scores[POSS].knowledge_state == "NEW"
    schedules = fold_schedules(store, _yaml("scheduler-v2.yaml"), registry=registry)
    assert set(schedules) == {(BE, DIM), (POSS, DIM)}
    ledger = xp_ledger(store, _yaml("scoring-v2.yaml"))
    kinds = [award["award_kind"] for award in ledger["awards"]]
    assert kinds.count("attempt_finalized") == 7 and kinds.count("review_closed") == 4


def test_the_same_report_is_byte_identical_on_a_fresh_store(
    tmp_path: Path, registry: PolicyRegistry, pinned: Any, store: EventStore
) -> None:
    """Determinism: same seed, same clock, same report -> same facts."""

    def run(path: Path) -> list[tuple[str, str]]:
        conn = connect(path)
        migrate(conn)
        try:
            local = EventStore(conn)
            clock = FixedClock(EPOCH)
            rnd = SeededRandomSource(7)
            reg = PolicyRegistry(conn, clock)
            reg.register("curriculum", "v-test", {"schema_version": 1, "topics": [], "lexicon": []})
            for kind, name, version in [
                ("evidence", "evidence-v2.yaml", "evidence@2"),
                ("scoring", "scoring-v2.yaml", "scoring@2"),
                ("scheduler", "scheduler-v2.yaml", "scheduler@2"),
                ("automaticity", "automaticity-v1.yaml", "automaticity@1"),
            ]:
                reg.register(kind, version, _yaml(name))
            session_id = _start(local, clock, rnd, pinned)
            _commit(local, clock, rnd, reg, session_id, pinned)
            return [(e.type, e.payload_hash) for e in local.read()]
        finally:
            conn.close()

    assert run(tmp_path / "a.db") == run(tmp_path / "b.db")
