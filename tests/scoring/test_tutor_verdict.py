"""``assessment_basis: tutor_verdict`` in the scoring fold (lesson-brief/report
concept [PD-2026-09-23]; W1-B).

The lesson-brief/report protocol makes the TUTOR the verdict, on the fixed
scale ``correct 1.0 / partial 0.5 / incorrect 0`` -- the engine never
regrades it. ``fold_scores`` folds it exactly like a rubric score
(``quality = score_ppm / 1e6``, session cap applies) with ONE deliberate
difference: ``rubric_cap`` never applies, because that cap is specific to the
engine's own rubric pipeline (P.5), not to a channel the concept leaves
uncapped by design (checked post-hoc by ``audit-english-tutor`` instead).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.engine import fold_scores

CORRECT_PPM = 1_000_000
PARTIAL_PPM = 500_000
INCORRECT_PPM = 0


def _emit(store: EventStore, clock: Any, rnd: Any, event_type: str, payload: dict[str, Any]) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=event_type,
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id=str(payload.get("session_id") or "corr"),
                    payload=payload,
                )
            ]
        )


def _tutor_evidence(
    store: EventStore,
    clock: Any,
    rnd: Any,
    *,
    target: str = "t.tutor",
    dimension: str = "recognition",
    score_ppm: int,
    session_id: str = "s1",
    hints: int = 0,
    **extra: Any,
) -> None:
    payload = {
        "evidence_id": new_ulid(clock, rnd),
        "session_id": session_id,
        "primary_target": {"target_ref": target, "dimension": dimension},
        "origin": extra.pop("origin", "session"),
        "assessment_basis": "tutor_verdict",
        "score_ppm": score_ppm,
        "correct": score_ppm >= CORRECT_PPM,
        "hints": hints,
        **extra,
    }
    _emit(store, clock, rnd, "evidence.added", payload)


def test_correct_verdict_grants_the_full_quality_delta(store, clock, random_source, policy) -> None:
    _tutor_evidence(store, clock, random_source, target="t.correct", score_ppm=CORRECT_PPM)
    scores = fold_scores(store, policy)
    got = scores["t.correct"].mastery["recognition"]
    expected = Decimal("8") * Decimal("0.6") * (Decimal(CORRECT_PPM) / Decimal(1_000_000))
    assert got == expected  # base * mode(recognition) * independence(1) * quality(1.0)


def test_partial_verdict_scales_the_delta_by_half(store, clock, random_source, policy) -> None:
    _tutor_evidence(
        store,
        clock,
        random_source,
        target="t.partial",
        dimension="spontaneous_production",
        score_ppm=PARTIAL_PPM,
    )
    scores = fold_scores(store, policy)
    got = scores["t.partial"].mastery["spontaneous_production"]
    expected = Decimal("8") * Decimal("1.0") * (Decimal(PARTIAL_PPM) / Decimal(1_000_000))
    assert got == expected == Decimal("4.0")


def test_incorrect_verdict_gives_zero_delta_never_a_punishment(store, clock, random_source, policy) -> None:
    _tutor_evidence(store, clock, random_source, target="t.wrong", score_ppm=INCORRECT_PPM)
    scores = fold_scores(store, policy)
    assert scores["t.wrong"].mastery == {}  # zero quality adds nothing
    assert scores["t.wrong"].evidence_count == 1  # the attempt still counts as evidence
    assert scores["t.wrong"].stability_days == Decimal("2.0")  # first evidence still seeds stability


def test_tutor_verdict_is_not_capped_by_rubric_cap(store, clock, random_source, policy) -> None:
    # rubric_cap (scoring-v1.yaml: 40) is ABOVE session_cap (15), so a single
    # session never exercises it -- rubric_gain only accumulates ACROSS
    # sessions. Three sessions each hitting their own session_cap (15) sum to
    # 45 > 40: a rubric-basis run of this exact shape would be capped at 40 by
    # rubric_cap; tutor_verdict must reach the full 45, capped only by each
    # session's own session_cap.
    rubric_cap = Decimal(str(policy["mastery"]["rubric_cap"]))
    session_cap = Decimal(str(policy["mastery"]["session_cap"]))
    assert 3 * session_cap > rubric_cap  # the policy actually exercises the distinction

    for session_id in ("s-a", "s-b", "s-c"):
        for _ in range(6):  # 6 * 4.8 = 28.8 > session_cap 15: each session caps at 15
            _tutor_evidence(
                store, clock, random_source, target="t.uncapped", score_ppm=CORRECT_PPM, session_id=session_id
            )
    scores = fold_scores(store, policy)
    state = scores["t.uncapped"]
    assert state.mastery["recognition"] == 3 * session_cap  # 45: session caps only, rubric_cap never bit
    assert state.rubric_gain == Decimal(0)  # tutor_verdict gain never counts toward rubric_gain
    assert any("session-cap" in line for line in state.audit)
    assert not any("rubric-cap" in line for line in state.audit)


def test_tutor_verdict_still_respects_the_session_cap(store, clock, random_source, policy) -> None:
    session_cap = Decimal(str(policy["mastery"]["session_cap"]))
    for _n in range(6):  # 6 * 4.8 = 28.8 > session cap 15, same shape as the objective_check cap test
        _tutor_evidence(
            store, clock, random_source, target="t.cap", score_ppm=CORRECT_PPM, session_id="s-cap"
        )
    scores = fold_scores(store, policy)
    assert scores["t.cap"].mastery["recognition"] == session_cap
    assert any("session-cap" in line for line in scores["t.cap"].audit)


def test_tutor_verdict_hints_reduce_independence_like_every_other_basis(
    store, clock, random_source, policy
) -> None:
    _tutor_evidence(store, clock, random_source, target="t.plain", score_ppm=CORRECT_PPM, hints=0)
    _tutor_evidence(store, clock, random_source, target="t.hinted", score_ppm=CORRECT_PPM, hints=2)
    scores = fold_scores(store, policy)
    plain = scores["t.plain"].mastery["recognition"]
    hinted = scores["t.hinted"].mastery["recognition"]
    assert hinted < plain
