"""start -> brief -> check -> report -> status, end to end [PD-2026-09-23].

The brief/report protocol keeps the event contract and changes only its
producer, so every consumer reads reported lessons unchanged: control's
presented-target, saturation and deferral folds see the reported items; the
automaticity axis folds a reported drill block; obligations@4 finds a
reported session compliant; `scoring replay` is consistent; and the whole
flow is deterministic -- two fresh stores fed the same inputs write the same
(type, payload hash) sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from english_trainer.audit.views import obligations
from english_trainer.control.deferral import reduce_deferrals
from english_trainer.control.saturation import reduce_saturation, target_pairs
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.learner import find_encounter_entry, lexicon_entries
from english_trainer.lessons.report import check_report, commit_report
from english_trainer.lessons.sessions import get_session, presented_targets
from english_trainer.scheduler.engine import fold_schedules
from english_trainer.scoring.automaticity import EVENT_AUTOMATICITY_UPDATED
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.replay import replay_scores
from tests.lessons.report_support import (
    BE,
    CP,
    EPOCH,
    ORDER,
    POLICIES,
    POSS,
    item,
    lexicon_ports,
    report,
    report_registry,
    start,
)


def _open(db: Path) -> tuple[EventStore, PolicyRegistry, FixedClock, SeededRandomSource]:
    conn = connect(db)
    migrate(conn)
    clock = FixedClock(EPOCH)
    return EventStore(conn), report_registry(conn, clock), clock, SeededRandomSource(20260923)


def _cli_terminated(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, session_id: str) -> None:
    """What the CLI transport writes after `trainer session report` succeeds."""
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type="cli.command_terminated",
                    occurred_at=clock.now(),
                    actor="cli-transport",
                    correlation_id=f"call-{session_id}",
                    payload={
                        "command": "session.report",
                        "outcome": "success",
                        "exit_code": 0,
                        "session_id": session_id,
                    },
                )
            ]
        )


def _lesson_one(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, rnd: SeededRandomSource
) -> str:
    started = start(store, registry, clock, rnd)
    sid = str(started["session_id"])
    body = report(
        sid,
        started["brief"],
        [
            item("i1", "I am a software engineer.", secondary_targets=[{"target_ref": "word.company"}]),
            item(
                "i2",
                "She are a manager.",
                verdict="incorrect",
                errors=[{"learner_form": "She are", "correction": "She is", "cause": "agreement"}],
            ),
            item("i3", "I am a software engineer."),  # repeated span
            item("i4", "My team is small.", target_ref=POSS, verdict="partial"),
            item("i5", "We test the model today.", target_ref=ORDER, dimension="transfer"),
        ],
        teaching=[{"target_ref": BE, "summary": "am/is/are по лицам"}],
        lexicon=[{"surface": "pull an all-nighter", "linked_item_id": None, "note_ru": "не спать всю ночь"}],
    )
    check = check_report(store, registry, sid, body, encounter_lookup=find_encounter_entry)
    assert check["valid"] is True
    assert [row["effects"]["duplicate_span"] for row in check["items"]] == [False, False, True, False, False]
    clock.advance(seconds=45 * 60)
    commit_report(
        store,
        registry,
        clock,
        rnd,
        sid,
        body,
        provider="claude-code",
        idempotency_key="lesson-1",
        **lexicon_ports(),
    )
    _cli_terminated(store, clock, rnd, sid)
    return sid


def _lesson_two_drill(
    store: EventStore, registry: PolicyRegistry, clock: FixedClock, rnd: SeededRandomSource
) -> tuple[str, dict[str, Any]]:
    clock.advance(seconds=3 * 86400)
    started = start(store, registry, clock, rnd, lesson_profile="drill")
    sid = str(started["session_id"])
    brief = started["brief"]
    review = brief["reviews_due"][0]
    answers = [
        ("d1", "I am a pilot.", "correct", BE),
        ("d2", "She is a doctor.", "correct", BE),
        ("d3", "They is late.", "incorrect", BE),
        ("d4", "We are ready.", "correct", BE),
        ("d5", "I am a pilot.", "correct", BE),  # repeated inside the block
        ("d6", "Her team is big.", "correct", POSS),  # a contrast item
    ]
    items = [
        item(
            item_id,
            answer,
            target_ref=target,
            kind="drill_item",
            verdict=verdict,
            block_id="b1",
            errors=(
                [{"learner_form": "They is", "correction": "They are", "cause": "agreement"}]
                if verdict == "incorrect"
                else []
            ),
        )
        for item_id, answer, verdict, target in answers
    ]
    items.insert(
        0,
        item(
            "rv",
            "Whose laptop is this?",
            target_ref=review["target_ref"],
            dimension=review["dimension"],
            kind="review",
            review_id=review["review_id"],
        ),
    )
    body = report(sid, brief, items, blocks=[{"block_id": "b1", "target_ref": BE, "mode": "interleaved"}])
    check = check_report(store, registry, sid, body, encounter_lookup=find_encounter_entry)
    assert check["valid"] is True, check
    block = check["blocks"][0]["effects"]
    assert block["credited_items"] == 5 and block["duplicates"] == 1
    assert block["accuracy_ppm"] == 800_000 and block["verdict"] == "correct"
    clock.advance(seconds=30 * 60)
    result = commit_report(
        store,
        registry,
        clock,
        rnd,
        sid,
        body,
        provider="claude-code",
        idempotency_key="lesson-2",
        **lexicon_ports(),
    )
    _cli_terminated(store, clock, rnd, sid)
    return sid, result


def _run(db: Path) -> tuple[EventStore, PolicyRegistry, list[str]]:
    store, registry, clock, rnd = _open(db)
    first = _lesson_one(store, registry, clock, rnd)
    second, _ = _lesson_two_drill(store, registry, clock, rnd)
    return store, registry, [first, second]


def test_the_full_flow(tmp_path: Path) -> None:
    store, registry, (first, second) = _run(tmp_path / "flow.db")
    for sid in (first, second):
        state, _ = get_session(store, sid) or ({}, 0)
        assert state["status"] == "FINISHED"

    # -- scores, schedules, automaticity -------------------------------------
    scoring = yaml.safe_load((POLICIES / "scoring-v2.yaml").read_text("utf-8"))
    scores = fold_scores(store, scoring)
    assert scores[BE].evidence_count > 0 and scores[POSS].evidence_count > 0
    assert fold_schedules(store, registry.resolve_pinned("scheduler", "scheduler@2"), registry=registry)
    replay = replay_scores(store, registry)
    assert replay["consistent"] is True
    assert any(e.type == EVENT_AUTOMATICITY_UPDATED for e in store.read())
    block = next(
        e for e in store.read() if e.type == "evidence.added" and e.payload.get("form") == "drill_block"
    )
    assert block.payload["assessment_basis"] == "tutor_verdict"
    assert [i["item_id"] for i in block.payload["items"]] == ["d1", "d2", "d3", "d4", "d6"]
    contrast = next(i for i in block.payload["items"] if i["item_id"] == "d6")
    assert contrast["contrast"] is True

    # -- the review closed by the verdict ---------------------------------------
    outcomes = [e.payload for e in store.read() if e.type == "review.outcome" and e.correlation_id == second]
    # The addressed review confirms; every other due review closes
    # INSUFFICIENT_EVIDENCE(not_attempted) in the same transaction.
    assert outcomes[0]["outcome"] == "CONFIRMED" and outcomes[0]["attempt_id"]
    assert [(o["outcome"], o["reason"]) for o in outcomes[1:]] == [
        ("INSUFFICIENT_EVIDENCE", "not_attempted")
    ] * (len(outcomes) - 1)

    # -- control folds see the reported items --------------------------------------
    assert {BE, POSS, ORDER, "word.company"} <= presented_targets(store)
    reported = [
        e
        for e in store.read()
        if e.type == "session.step_presented" and e.payload.get("source") == "lesson_report"
    ]
    block_step = next(e for e in reported if e.payload["step_type"] == "drill_block")
    assert target_pairs(block_step.payload) == [(BE, CP), (POSS, CP)]
    control = yaml.safe_load((POLICIES / "control-v3.yaml").read_text("utf-8"))
    events = list(store.read())
    saturation = reduce_saturation(events, control)
    assert saturation[(BE, CP)].exposures_in_window >= 2
    assert saturation[(ORDER, "transfer")].last_transfer_check_at is not None
    # The review target was presented in its session: no deferral is counted.
    review_key = (str(outcomes[0]["target_ref"]), str(outcomes[0]["dimension"]))
    assert review_key not in reduce_deferrals(events, control)

    # -- errors, lexicon, next brief -------------------------------------------
    errors = [e.payload for e in store.read() if e.type == "evidence.error_observed"]
    assert [(p["learner_form"], p["item_id"]) for p in errors] == [("She are", "i2"), ("They is", "d3")]
    assert [str(entry["surface"]) for entry in lexicon_entries(store)] == ["pull an all-nighter"]

    # -- obligations@4 -------------------------------------------------------------
    for sid in (first, second):
        observed = obligations(store, registry, sid)
        assert observed["status"] == "complete" and observed["policy_id"] == "obligations@4"
        by_id = {o["obligation_id"]: o for o in observed["observations"]}
        assert by_id["report_committed"]["satisfied"] is True
        assert by_id["lesson_preflight"]["satisfied"] is True
    second_obligations = {o["obligation_id"]: o for o in obligations(store, registry, second)["observations"]}
    assert second_obligations["reviews_addressed"]["satisfied"] is True


def test_the_flow_is_deterministic_across_fresh_stores(tmp_path: Path) -> None:
    sequences = []
    hashes = []
    for name in ("a", "b"):
        store, registry, _ = _run(tmp_path / f"{name}.db")
        sequences.append([(e.type, e.payload_hash) for e in store.read()])
        hashes.append(replay_scores(store, registry)["snapshot_hash"])
    assert sequences[0] == sequences[1]
    assert hashes[0] == hashes[1]
