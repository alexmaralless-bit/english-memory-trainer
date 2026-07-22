"""CLI wiring for the placement surface: total JSON envelope, idempotency-key
enforcement, and the self-assessment scalar refusal (cli 4; assessments 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import ExitCode


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def test_placement_start_answer_submit_via_cli(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    start_code = run(["placement", "start", "--format", "json", "--root", root, "--idempotency-key", "s1"])
    start_env = _json_stdout(capsys)
    assert start_code == ExitCode.OK
    assert start_env["ok"] is True
    assert start_env["data"]["form_version"] == "placement-en-core@1"

    answers = tmp_path / "answers.json"
    answers.write_text(
        json.dumps({"section": "grammar", "answers": {"g-be-1": "am", "g-be-2": "is", "g-be-3": "are"}}),
        encoding="utf-8",
    )
    answer_code = run(
        [
            "placement",
            "answer",
            "--format",
            "json",
            "--root",
            root,
            "--input",
            str(answers),
            "--idempotency-key",
            "a1",
        ]
    )
    answer_env = _json_stdout(capsys)
    assert answer_code == ExitCode.OK
    assert answer_env["data"]["status"] == "IN_PROGRESS"

    submit_code = run(["placement", "submit", "--format", "json", "--root", root, "--idempotency-key", "u1"])
    submit_env = _json_stdout(capsys)
    assert submit_code == ExitCode.OK
    assert submit_env["data"]["status"] == "SCORED"
    assert submit_env["data"]["evidence_count"] == 3


def test_placement_start_requires_idempotency_key_in_json(tmp_path: Path, capsys) -> None:
    code = run(["placement", "start", "--format", "json", "--root", str(tmp_path)])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"


def test_placement_decline_scalar_is_rejected_via_cli(tmp_path: Path, capsys) -> None:
    code = run(
        [
            "placement",
            "decline",
            "--format",
            "json",
            "--root",
            str(tmp_path),
            "--self-assessment",
            '"A2"',
            "--idempotency-key",
            "d1",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.INVALID_INPUT
    assert env["error"]["error_code"] == "SELF_ASSESSMENT_INVALID"


def test_placement_decline_object_via_cli(tmp_path: Path, capsys) -> None:
    code = run(
        [
            "placement",
            "decline",
            "--format",
            "json",
            "--root",
            str(tmp_path),
            "--self-assessment",
            '{"schema_version":1,"levels":{"grammar":"A2"}}',
            "--idempotency-key",
            "d2",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert env["data"]["self_reported_levels"] == {"grammar": "A2"}
