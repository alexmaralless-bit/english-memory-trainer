"""``trainer review due`` feeds the scheduler both of its injected inputs.

The scheduler layer is pure: it never reads curriculum content and never
resolves a policy version of its own (wiki/modules/scheduler.md 3a). Both
facts therefore have to arrive from the call site --

- ``permanent_interleave_targets``: the article-tier frames of the ACTIVE
  curriculum snapshot, classified by ``curriculum.permanent_interleave_targets``
  (the one place that knows the ``frame_of``-under-``grammar.articles.`` rule);
- ``registry``: per-event pinned scheduler-policy resolution, so a log spanning
  a ``scheduler@1`` -> ``scheduler@2`` activation folds every event under the
  table it was actually assigned under, never today's active one.

Both are asserted end to end, through the published CLI surface.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import ExitCode
from english_trainer.kernel.clock import SystemClock, SystemRandom
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.storage.layout import resolve_layout

CURRICULUM = Path(__file__).resolve().parents[2] / "curriculum"

# A real article-tier frame of the shipped lexicon: `frame_of` names a
# `grammar.articles.*` topic, so it belongs to the permanent interleaved tier.
ARTICLE_FRAME = "chunk.articles-identity.im-a"
# A target that is not a frame at all: the flag must stay False for it.
PLAIN_TARGET = "grammar.present-perfect.result"


def _json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(capsys.readouterr().out)
    return parsed


def _activated(tmp_path: Path, capsys) -> str:
    root = str(tmp_path)
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "k1"])
    capsys.readouterr()
    code = run(
        [
            "curriculum",
            "activate",
            "--version",
            "v1",
            "--curriculum",
            str(CURRICULUM),
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "a1",
        ]
    )
    assert code == ExitCode.OK
    capsys.readouterr()
    return root


def _seed(root: str, entries: list[tuple[str, str]]) -> None:
    """One evidence + one CONFIRMED outcome per (target, scheduler version).

    Both facts are placed far in the past so the resulting schedule is due
    whatever the wall clock of the run is.
    """
    layout = resolve_layout(Path(root))
    conn = connect(layout.db)
    try:
        store = EventStore(conn)
        clock = SystemClock()
        rnd = SystemRandom()
        opened = datetime.now(UTC) - timedelta(days=400)
        confirmed = datetime.now(UTC) - timedelta(days=300)
        events = []
        for target_ref, scheduler_version in entries:
            correlation = new_ulid(clock, rnd)
            events.append(
                make_event(
                    id=new_ulid(clock, rnd),
                    type="evidence.added",
                    occurred_at=opened,
                    actor="engine",
                    correlation_id=correlation,
                    payload={
                        "evidence_id": new_ulid(clock, rnd),
                        "primary_target": {"target_ref": target_ref, "dimension": "recognition"},
                        "correct": True,
                        "score_ppm": 1_000_000,
                    },
                    pinned_versions={"scheduler": scheduler_version},
                )
            )
            events.append(
                make_event(
                    id=new_ulid(clock, rnd),
                    type="review.outcome",
                    occurred_at=confirmed,
                    actor="engine",
                    correlation_id=correlation,
                    payload={
                        "review_id": new_ulid(clock, rnd),
                        "target_ref": target_ref,
                        "dimension": "recognition",
                        "outcome": "CONFIRMED",
                        "origin": "session",
                    },
                    pinned_versions={"scheduler": scheduler_version},
                )
            )
        with UnitOfWork(store, clock) as uow:
            uow.append(events)
    finally:
        conn.close()


def _due(root: str, capsys) -> dict[str, dict[str, Any]]:
    assert run(["review", "due", "--format", "json", "--root", root]) == ExitCode.OK
    return {str(c["target_ref"]): c for c in _json(capsys)["data"]["due"]}


def test_review_due_marks_the_article_tier_frame(tmp_path: Path, capsys) -> None:
    root = _activated(tmp_path, capsys)
    _seed(root, [(ARTICLE_FRAME, "scheduler@2"), (PLAIN_TARGET, "scheduler@2")])
    due = _due(root, capsys)
    assert due[ARTICLE_FRAME]["permanent_interleave"] is True
    # The rule is about article frames, not about "everything due".
    assert due[PLAIN_TARGET]["permanent_interleave"] is False


def test_review_due_folds_each_event_under_its_own_pinned_scheduler(tmp_path: Path, capsys) -> None:
    """scheduler@1 steps 1 -> 3 days; scheduler@2's ladder steps 1 -> 2 days.

    Both targets take exactly one CONFIRMED, so the only thing that can make
    their intervals differ is per-event pinned resolution.
    """
    root = _activated(tmp_path, capsys)
    _seed(root, [(ARTICLE_FRAME, "scheduler@2"), (PLAIN_TARGET, "scheduler@1")])
    due = _due(root, capsys)
    assert due[ARTICLE_FRAME]["interval_days"] == 2  # relearning ladder [1, 2, 4]
    assert due[PLAIN_TARGET]["interval_days"] == 3  # base table [1, 3, 7, ...]
