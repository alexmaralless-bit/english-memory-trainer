"""CLI wiring for the placement surface: total JSON envelope, idempotency-key
enforcement, and the self-assessment scalar refusal (cli 4; assessments 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import ExitCode
from tests.assessments.fixtures import (
    FULL_FORM_CORRECT,
    FULL_FORM_VERSION,
    WRITING_ANSWER,
    activate_fixture_curriculum,
    strong_writing_observations,
)


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def test_placement_start_answer_submit_via_cli(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    assert run(["init", "--format", "json", "--root", root, "--idempotency-key", "i1"]) == ExitCode.OK
    capsys.readouterr()
    activate_fixture_curriculum(tmp_path)

    start_code = run(["placement", "start", "--format", "json", "--root", root, "--idempotency-key", "s1"])
    start_env = _json_stdout(capsys)
    assert start_code == ExitCode.OK
    assert start_env["ok"] is True
    data = start_env["data"]
    assert data["form_version"] == FULL_FORM_VERSION
    assert data["form_selection"]["basis"] == "unseen"
    assert data["passages"][0]["passage_id"] == "p-a2-1"
    items = {item["item_id"]: item for item in data["items"]}
    # The presented item carries everything needed to show it -- and no key.
    assert items["g-a1-01"]["kind"] == "choice"
    assert items["g-a1-01"]["options"] == ["writes", "write", "writing", "wrote"]
    assert items["r-a2-01"]["passage_id"] == "p-a2-1"
    assert items["w-a2-01"]["min_words"] == 60 and items["w-a2-01"]["max_words"] == 120
    assert all("answer_key" not in item for item in data["items"])

    for index, (section, answers) in enumerate(FULL_FORM_CORRECT.items()):
        payload = tmp_path / f"answers-{section}.json"
        payload.write_text(json.dumps({"section": section, "answers": answers}), encoding="utf-8")
        code = run(
            [
                "placement",
                "answer",
                "--format",
                "json",
                "--root",
                root,
                "--input",
                str(payload),
                "--idempotency-key",
                f"a{index}",
            ]
        )
        env = _json_stdout(capsys)
        assert code == ExitCode.OK
        assert env["data"]["status"] == "IN_PROGRESS"

    writing = tmp_path / "answers-writing.json"
    writing.write_text(
        json.dumps(
            {
                "section": "writing",
                "answers": {"w-a2-01": WRITING_ANSWER},
                "observations": {"w-a2-01": strong_writing_observations()},
            }
        ),
        encoding="utf-8",
    )
    code = run(
        [
            "placement",
            "answer",
            "--format",
            "json",
            "--root",
            root,
            "--input",
            str(writing),
            "--idempotency-key",
            "aw",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert env["data"]["observed_items"] == ["w-a2-01"]

    submit_code = run(["placement", "submit", "--format", "json", "--root", root, "--idempotency-key", "u1"])
    submit_env = _json_stdout(capsys)
    assert submit_code == ExitCode.OK
    assert submit_env["data"]["status"] == "SCORED"
    # 20 objective items + the rubric-settled writing fragment.
    assert submit_env["data"]["evidence_count"] == 21
    skills = submit_env["data"]["skills"]
    assert skills["grammar"] == {"level": "A2", "confidence": "low", "basis": "placement"}
    assert skills["reading"]["level"] == "A2"
    assert skills["vocabulary"]["level"] == "A2"
    # One fragment can never reach the coverage floor: writing stays unknown.
    assert "writing" not in skills

    status_code = run(["status", "--format", "json", "--root", root])
    status_env = _json_stdout(capsys)
    assert status_code == ExitCode.OK
    assert status_env["data"]["skills"]["grammar"] == {
        "level": "A2",
        "confidence": "low",
        "basis": "placement",
        # An objective band is a measurement, not a provisional claim.
        "provisional": False,
        # One item per topic -> LEARNING, not ACTIVE: the placement level comes
        # from the diagnostic, not from evidence coverage.
        "active_topics": 0,
    }
    # The strong writing fragment gives a PROVISIONAL writing band and nothing
    # more (learning-model 6): flagged, very-low confidence, basis placement.
    assert status_env["data"]["skills"]["writing"] == {
        "level": "A2",
        "confidence": "very_low",
        "basis": "placement",
        "provisional": True,
        "active_topics": 0,
    }
    # ...so the MEASURED level stays unknown -- a provisional row is not evidence.
    assert status_env["data"]["measured_working_level"] is None
    # The provisional estimate is what a learner who has just sat the placement
    # gets to start from: every skill claimed, the weakest one leading.
    estimate = status_env["data"]["provisional_working_estimate"]
    assert estimate["level"] == "A2"
    assert estimate["provisional"] is True
    assert estimate["skills"]["writing"] == {
        "level": "A2",
        "confidence": "very_low",
        "basis": "placement",
        "provisional": True,
    }
    assert estimate["skills"]["reading"]["provisional"] is False


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
