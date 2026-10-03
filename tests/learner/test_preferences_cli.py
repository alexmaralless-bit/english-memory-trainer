"""CLI contract for the LearnerPreferences commands (learner 4a; cli 4): total
envelope, clean JSON stdout, stable error codes, read-only show, merge
semantics, and idempotency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import SCHEMA_VERSION, ExitCode
from english_trainer.kernel.store import connect
from english_trainer.learner.preferences import EVENT_PREFERENCES_UPDATED

_DEFAULT_SNAPSHOT = {
    "round_size": 6,
    "explanation_language": "ru",
    "preferred_drill_forms": [],
    "timed_limit_seconds": 240,
    "feedback_mode": "stage_dependent",
    "preferences_version": 0,
    "updated_at": None,
}


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def _envelope_ok(env: dict[str, Any]) -> None:
    assert env["schema_version"] == SCHEMA_VERSION
    assert isinstance(env["ok"], bool)
    assert isinstance(env["correlation_id"], str) and env["correlation_id"]
    if env["ok"]:
        assert "data" in env and "error" not in env
    else:
        assert "error" in env and "data" not in env
        assert env["error"]["next_action"]


def _init(root: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "init"])
    capsys.readouterr()


def _event_count(root: Path) -> int:
    conn = connect(root / "trainer.db")
    from english_trainer.kernel.store import EventStore

    n = sum(1 for e in EventStore(conn).read() if e.type == EVENT_PREFERENCES_UPDATED)
    conn.close()
    return n


# -- show ---------------------------------------------------------------------


def test_show_returns_documented_defaults_before_any_set(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(["learner", "preferences", "show", "--root", root, "--format", "json"])
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.OK
    assert env["data"] == _DEFAULT_SNAPSHOT


def test_show_is_read_only(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "8",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    capsys.readouterr()
    before = _event_count(tmp_path)
    run(["learner", "preferences", "show", "--root", root, "--format", "json"])
    capsys.readouterr()
    assert _event_count(tmp_path) == before  # show never mutates


# -- set: basics and merge semantics -------------------------------------


def test_set_requires_idempotency_key_in_json(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(["learner", "preferences", "set", "--round-size", "8", "--root", root, "--format", "json"])
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"
    assert _event_count(tmp_path) == 0  # the refusal left no trace


def test_set_and_show_round_trip(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "8",
            "--explanation-language",
            "en",
            "--timed-limit-seconds",
            "300",
            "--feedback-mode",
            "always_explain",
            "--preferred-drill-forms",
            "minimal_pair,frame_recall",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["round_size"] == 8
    assert env["data"]["explanation_language"] == "en"
    assert env["data"]["timed_limit_seconds"] == 300
    assert env["data"]["feedback_mode"] == "always_explain"
    assert env["data"]["preferred_drill_forms"] == ["minimal_pair", "frame_recall"]
    assert env["data"]["preferences_version"] == 1

    code = run(["learner", "preferences", "show", "--root", root, "--format", "json"])
    shown = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert shown["data"]["round_size"] == 8
    assert shown["data"]["preferences_version"] == 1


def test_set_merges_over_current_leaving_other_fields_untouched(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "9",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    capsys.readouterr()
    run(
        [
            "learner",
            "preferences",
            "set",
            "--explanation-language",
            "en",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k2",
        ]
    )
    env = _json_stdout(capsys)
    assert env["data"]["round_size"] == 9  # carried over from the first `set`
    assert env["data"]["explanation_language"] == "en"
    assert env["data"]["preferences_version"] == 2


def test_invalid_round_size_is_rejected(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "2",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.INVALID_INPUT
    assert env["error"]["error_code"] == "PREFERENCES_INVALID"
    assert _event_count(tmp_path) == 0


def test_invalid_explanation_language_is_rejected(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(
        [
            "learner",
            "preferences",
            "set",
            "--explanation-language",
            "fr",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.INVALID_INPUT
    assert env["error"]["error_code"] == "PREFERENCES_INVALID"


# -- idempotency -------------------------------------------------------------


def test_same_key_same_payload_is_cached(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    args = [
        "learner",
        "preferences",
        "set",
        "--round-size",
        "8",
        "--root",
        root,
        "--format",
        "json",
        "--idempotency-key",
        "same",
    ]
    run(args)
    first = _json_stdout(capsys)
    run(args)
    second = _json_stdout(capsys)
    assert second["data"]["cached"] is True
    assert second["data"]["preferences_version"] == first["data"]["preferences_version"]
    assert _event_count(tmp_path) == 1


def test_same_key_different_payload_conflicts(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "8",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "dup",
        ]
    )
    capsys.readouterr()
    code = run(
        [
            "learner",
            "preferences",
            "set",
            "--round-size",
            "4",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "dup",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.CONFLICT
    assert env["error"]["error_code"] == "IDEMPOTENCY_CONFLICT"
