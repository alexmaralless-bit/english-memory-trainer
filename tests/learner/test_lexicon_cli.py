"""CLI contract for the personal-lexicon commands (cli 4): total envelope,
clean JSON stdout, stable error codes, read-only list, and the session fence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import SCHEMA_VERSION, ExitCode
from english_trainer.kernel.clock import FixedClock
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore, connect
from english_trainer.learner.lexicon import EVENT_LEXICON_ENTRY_ADDED
from tests.learner.conftest import PROGRAM, make_session

CLOCK = FixedClock(datetime(2026, 7, 22, 12, tzinfo=UTC))


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


def _seed_curriculum(root: Path) -> None:
    conn = connect(root / "trainer.db")
    registry = PolicyRegistry(conn, CLOCK)
    registry.register("curriculum", "v-test", PROGRAM)
    registry.activate("curriculum", "v-test")
    conn.close()


def _seed_session(root: Path, session_id: str = "SESSION-1") -> None:
    conn = connect(root / "trainer.db")
    make_session(EventStore(conn), CLOCK, session_id)
    conn.close()


def _event_count(root: Path) -> int:
    conn = connect(root / "trainer.db")
    n = sum(1 for e in EventStore(conn).read() if e.type == EVENT_LEXICON_ENTRY_ADDED)
    conn.close()
    return n


# -- basics ------------------------------------------------------------------


def test_add_and_list_round_trip(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(
        [
            "lexicon",
            "add",
            "--surface",
            "serendipity",
            "--note-ru",
            "случайность",
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
    assert env["data"]["source"] == "learner"
    assert env["data"]["linked_item_id"] is None

    code = run(["lexicon", "list", "--root", root, "--format", "json"])
    listed = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert listed["data"]["count"] == 1
    assert listed["data"]["summary"] == {"total": 1, "linked": 0, "unlinked": 1}


def test_add_requires_idempotency_key_in_json(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(["lexicon", "add", "--surface", "x", "--root", root, "--format", "json"])
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"
    assert _event_count(tmp_path) == 0  # the refusal left no trace


def test_list_is_read_only(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    run(["lexicon", "add", "--surface", "one", "--root", root, "--format", "json", "--idempotency-key", "k"])
    capsys.readouterr()
    before = _event_count(tmp_path)
    run(["lexicon", "list", "--root", root, "--format", "json"])
    capsys.readouterr()
    assert _event_count(tmp_path) == before  # list never mutates


# -- linked item resolution --------------------------------------------------


def test_linked_add_succeeds(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    _seed_curriculum(tmp_path)
    code = run(
        [
            "lexicon",
            "add",
            "--surface",
            "feasible",
            "--linked-item",
            "word.feasible",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert env["data"]["linked_item_id"] == "word.feasible"


def test_dangling_linked_item_is_not_found(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    _seed_curriculum(tmp_path)
    code = run(
        [
            "lexicon",
            "add",
            "--surface",
            "ghost",
            "--linked-item",
            "word.nope",
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
    assert code == ExitCode.NOT_FOUND
    assert env["error"]["error_code"] == "LINKED_ITEM_NOT_FOUND"
    assert _event_count(tmp_path) == 0


def test_linked_add_without_active_curriculum_is_precondition(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    code = run(
        [
            "lexicon",
            "add",
            "--surface",
            "feasible",
            "--linked-item",
            "word.feasible",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k1",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.PRECONDITION_FAILED
    assert env["error"]["error_code"] == "NO_ACTIVE_CURRICULUM"


# -- idempotency -------------------------------------------------------------


def test_same_key_same_payload_is_cached(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    args = [
        "lexicon",
        "add",
        "--surface",
        "cached",
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
    assert second["data"]["entry_id"] == first["data"]["entry_id"]
    assert _event_count(tmp_path) == 1


def test_same_key_different_payload_conflicts(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    run(["lexicon", "add", "--surface", "a", "--root", root, "--format", "json", "--idempotency-key", "dup"])
    capsys.readouterr()
    code = run(
        ["lexicon", "add", "--surface", "b", "--root", root, "--format", "json", "--idempotency-key", "dup"]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.CONFLICT
    assert env["error"]["error_code"] == "IDEMPOTENCY_CONFLICT"


# -- session fence -----------------------------------------------------------


def test_encounter_advances_the_session_fence(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    _seed_session(tmp_path)
    code = run(
        [
            "lexicon",
            "encounter",
            "--surface",
            "feasible",
            "--session",
            "SESSION-1",
            "--provider",
            "codex",
            "--expected-session-revision",
            "1",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "e1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["source"] == "encountered"
    assert env["data"]["session_revision"] == 2


def test_stale_session_revision_is_rejected_without_effect(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    _seed_session(tmp_path)
    run(
        [
            "lexicon",
            "encounter",
            "--surface",
            "feasible",
            "--session",
            "SESSION-1",
            "--provider",
            "codex",
            "--expected-session-revision",
            "1",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "e1",
        ]
    )
    capsys.readouterr()
    before = _event_count(tmp_path)
    code = run(
        [
            "lexicon",
            "encounter",
            "--surface",
            "different",
            "--session",
            "SESSION-1",
            "--provider",
            "codex",
            "--expected-session-revision",
            "1",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "e2",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.CONFLICT
    assert env["error"]["error_code"] == "SESSION_REVISION_CONFLICT"
    assert _event_count(tmp_path) == before  # stale write left no event


# -- status lexicon_progress -------------------------------------------------


def _seed_full(root: Path) -> None:
    import yaml

    repo = Path(__file__).resolve().parents[2]
    conn = connect(root / "trainer.db")
    registry = PolicyRegistry(conn, CLOCK)
    registry.register("curriculum", "v-test", PROGRAM)
    registry.activate("curriculum", "v-test")
    for name, kind, version in (
        ("scoring-v1.yaml", "scoring", "scoring@1"),
        ("scheduler-v1.yaml", "scheduler", "scheduler@1"),
    ):
        payload = yaml.safe_load((repo / "curriculum" / "policies" / name).read_text("utf-8"))
        registry.register(kind, version, payload)
        registry.activate(kind, version)
    conn.close()


def test_status_reports_lexicon_progress(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    _init(root, capsys)
    _seed_full(tmp_path)
    run(
        [
            "lexicon",
            "add",
            "--surface",
            "feasible",
            "--linked-item",
            "word.feasible",
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
            "lexicon",
            "add",
            "--surface",
            "blorptastic",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "k2",
        ]
    )
    capsys.readouterr()
    code = run(["status", "--root", root, "--format", "json"])
    env = _json_stdout(capsys)
    _envelope_ok(env)
    assert code == ExitCode.OK
    progress = env["data"]["lexicon_progress"]
    # Two curriculum lexical items, both NEW (no evidence yet); ACTIVE and
    # MASTERED are separate keys -- no ambiguous single "learned_words".
    assert progress["curriculum"] == {"new": 2, "learning": 0, "active": 0, "mastered": 0, "at_risk": 0}
    assert progress["personal"] == {"total": 2, "linked": 1, "unlinked": 1}
