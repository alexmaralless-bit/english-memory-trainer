"""``automaticity@1`` end to end: it activates with the shipped curriculum, it
is pinned into the Session Manifest, and ``trainer status`` reports it as its
own block (scoring 3d)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import ExitCode
from english_trainer.kernel.clock import SystemClock, SystemRandom
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.automaticity import AUTOMATICITY_KIND, backfill_automaticity_updates
from english_trainer.storage.layout import resolve_layout

CURRICULUM = Path(__file__).resolve().parents[2] / "curriculum"


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
    env = _json(capsys)
    assert "automaticity@1" in env["data"]["policies"]
    return root


def test_the_policy_activates_with_the_curriculum(tmp_path: Path, capsys) -> None:
    root = _activated(tmp_path, capsys)
    layout = resolve_layout(Path(root))
    conn = connect(layout.db)
    try:
        registry = PolicyRegistry(conn, SystemClock())
        assert registry.active_version(AUTOMATICITY_KIND) == "automaticity@1"
    finally:
        conn.close()


def test_the_manifest_pins_the_axis_beside_scoring(tmp_path: Path, capsys) -> None:
    root = _activated(tmp_path, capsys)
    code = run(
        [
            "session",
            "start",
            "--provider",
            "claude-code",
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "s1",
        ]
    )
    assert code == ExitCode.OK
    pinned = _json(capsys)["data"]["pinned_versions"]
    assert pinned[AUTOMATICITY_KIND] == "automaticity@1"
    # The shipped scoring policy (scoring@2 since the placement-derived level):
    # a separate KIND from the axis, not a replacement for it.
    assert pinned["scoring"] == "scoring@2"


def test_status_reports_automaticity_as_its_own_block(tmp_path: Path, capsys) -> None:
    root = _activated(tmp_path, capsys)
    layout = resolve_layout(Path(root))
    conn = connect(layout.db)
    try:
        store = EventStore(conn)
        registry = PolicyRegistry(conn, SystemClock())
        clock = SystemClock()
        source = make_event(
            id=new_ulid(clock, SystemRandom()),
            type="evidence.added",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id="s1",
            payload={
                "evidence_id": "e1",
                "session_id": "s1",
                "form": "drill_block",
                "mode": "controlled_production",
                "origin": "session",
                "assessment_basis": "objective_check",
                "primary_target": {
                    "target_ref": "grammar.be.identity",
                    "dimension": "controlled_production",
                },
                "correct": True,
                "score_ppm": 1_000_000,
                "hints": 0,
                "items": [
                    {
                        "index": 0,
                        "prompt_ref": "x#item:0",
                        "raw_answer": "a",
                        "presented": True,
                        "objective_correct": True,
                        "latency_ms": 900,
                        "self_repaired": False,
                    }
                ],
            },
            pinned_versions={AUTOMATICITY_KIND: "automaticity@1"},
        )
        with UnitOfWork(store, clock) as uow:
            uow.append([source])
        with UnitOfWork(store, clock) as uow:
            assert backfill_automaticity_updates(store, registry, uow)["created"] == 1
    finally:
        conn.close()

    code = run(["status", "--format", "json", "--root", root])
    assert code == ExitCode.OK
    data = _json(capsys)["data"]
    axis = data["automaticity"]
    assert axis["status"] == "measured"
    assert axis["policy_version"] == "automaticity@1"
    assert axis["targets"]["grammar.be.identity"]["state"] == "deliberate"
    assert axis["targets"]["grammar.be.identity"]["accuracy_ppm"] == 1_000_000
    # Kept strictly apart from Mastery and knowledge state (scoring 3d).
    assert "automaticity" not in data["targets"].get("grammar.be.identity", {})

    code = run(["scoring", "replay", "--format", "json", "--root", root])
    assert code == ExitCode.OK
    report = _json(capsys)["data"]
    assert report["consistent"] is True
    assert report["automaticity"]["mismatches"] == []
