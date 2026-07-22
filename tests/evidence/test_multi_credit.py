"""One answer span gets deterministic bounded credit across targets."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from english_trainer.evidence.policy import allocate_credit
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.engine import fold_scores

REPO = Path(__file__).resolve().parents[2]


def test_allocation_is_primary_first_canonical_and_capped() -> None:
    targets = [
        {"target_ref": "target.d", "dimension": "recognition"},
        {"target_ref": "target.b", "dimension": "recognition"},
        {"target_ref": "target.c", "dimension": "recognition"},
        {"target_ref": "target.a", "dimension": "recognition"},
    ]
    allocations = allocate_credit(
        targets,
        targets[3],
        {"primary_weight": "1.0", "secondary_weight": "0.5", "total_weight_cap": "2.0"},
    )
    assert [(item["target_ref"], item["contribution"], item["used"]) for item in allocations] == [
        ("target.a", "1.0", True),
        ("target.b", "0.5", True),
        ("target.c", "0.5", True),
        ("target.d", "0", False),
    ]
    assert allocations[-1]["reason"] == "total_cap"


def test_scoring_consumes_secondary_weight_without_hiding_extra_targets(tmp_path: Path) -> None:
    conn = connect(tmp_path / "multi-credit.db")
    migrate(conn)
    store = EventStore(conn)
    clock = FixedClock(datetime(2026, 7, 22, 9, 0, tzinfo=UTC))
    random_source = SeededRandomSource(44)
    allocations = allocate_credit(
        [
            {"target_ref": "target.a", "dimension": "recognition"},
            {"target_ref": "target.b", "dimension": "recognition"},
            {"target_ref": "target.c", "dimension": "recognition"},
            {"target_ref": "target.d", "dimension": "recognition"},
        ],
        {"target_ref": "target.a", "dimension": "recognition"},
        {"primary_weight": "1.0", "secondary_weight": "0.5", "total_weight_cap": "2.0"},
    )
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="evidence.added",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="session-1",
                    payload={
                        "session_id": "session-1",
                        "assessment_basis": "objective_check",
                        "correct": True,
                        "hints": 0,
                        "primary_target": allocations[0],
                        "credit_allocations": allocations,
                    },
                )
            ]
        )
    policy = yaml.safe_load(
        (REPO / "curriculum" / "policies" / "scoring-v1.yaml").read_text(encoding="utf-8")
    )
    scores = fold_scores(store, policy)
    assert Decimal(scores["target.a"].mastery["recognition"]) == Decimal("4.8")
    assert Decimal(scores["target.b"].mastery["recognition"]) == Decimal("2.4")
    assert Decimal(scores["target.c"].mastery["recognition"]) == Decimal("2.4")
    assert "target.d" not in scores
