"""The outer CLI transport records safe invocation and terminal facts."""

from __future__ import annotations

import json
from pathlib import Path

from english_trainer.cli.app import run
from english_trainer.cli.envelope import ExitCode
from english_trainer.kernel.store import EventStore, connect


def _read_json(capsys) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_read_and_refused_commands_are_observable_without_raw_argument_values(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    curriculum = str(Path(__file__).resolve().parents[2] / "curriculum")
    assert run(["init", "--root", root, "--format", "json", "--idempotency-key", "init-1"]) == 0
    _read_json(capsys)
    assert (
        run(
            [
                "curriculum",
                "activate",
                "--version",
                "v1",
                "--curriculum",
                curriculum,
                "--root",
                root,
                "--format",
                "json",
                "--idempotency-key",
                "activate-1",
            ]
        )
        == 0
    )
    _read_json(capsys)
    assert (
        run(
            [
                "session",
                "start",
                "--provider",
                "codex",
                "--root",
                root,
                "--format",
                "json",
                "--idempotency-key",
                "start-1",
            ]
        )
        == 0
    )
    started = _read_json(capsys)
    session_id = str(dict(started["data"])["session_id"])

    code = run(
        [
            "session",
            "next",
            "--expected-plan-version",
            "1",
            "--expected-session-revision",
            "1",
            "--root",
            root,
            "--format",
            "json",
        ]
    )
    refused = _read_json(capsys)
    assert code == ExitCode.USAGE
    assert dict(refused["error"])["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    conn = connect(tmp_path / "trainer.db")
    events = list(EventStore(conn).read())
    terminal = next(
        event
        for event in reversed(events)
        if event.type == "cli.command_terminated" and event.payload.get("command") == "session.next"
    )
    invocation = next(event for event in events if event.id == terminal.causation_id)
    assert terminal.payload["session_id"] == session_id
    assert terminal.payload["outcome"] == "refused"
    assert terminal.payload["error_code"] == "MISSING_IDEMPOTENCY_KEY"
    assert invocation.payload["session_id"] == session_id
    assert set(invocation.payload) == {"command", "request_shape_hash", "session_id", "trust"}
    assert curriculum not in str(invocation.payload)
    conn.close()
