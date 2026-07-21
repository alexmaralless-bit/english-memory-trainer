"""CLI contract tests (cli 4): total envelope, clean stdout in json mode,
closed exit codes, mandatory next_action on refusal, idempotency of init."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from english_trainer.cli.app import run
from english_trainer.cli.envelope import SCHEMA_VERSION, ExitCode
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect, migrate
from english_trainer.kernel.uow import UnitOfWork


def _json_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Parse stdout as exactly one JSON document -- the purity MUST of cli 4.1."""
    out = capsys.readouterr().out
    parsed: dict[str, Any] = json.loads(out)  # raises if anything but one document
    return parsed


def _envelope_shape_ok(env: dict[str, Any]) -> None:
    assert env["schema_version"] == SCHEMA_VERSION
    assert isinstance(env["ok"], bool)
    assert isinstance(env["command"], str)
    assert isinstance(env["correlation_id"], str) and env["correlation_id"]
    if env["ok"]:
        assert "data" in env and "error" not in env
    else:
        assert "error" in env and "data" not in env
        assert env["error"]["next_action"]  # refusal without an exit is a defect


def test_doctor_json_is_one_document_exit_zero(tmp_path: Path, capsys) -> None:
    code = run(["doctor", "--format", "json", "--db", str(tmp_path / "t.db")])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    assert env["ok"] is True
    names = {check["name"] for check in env["data"]["checks"]}
    assert "python" in names and "database" in names  # db missing -> warn entry


def test_doctor_human_default_is_not_a_json_contract(tmp_path: Path, capsys) -> None:
    code = run(["doctor", "--db", str(tmp_path / "t.db")])
    out = capsys.readouterr().out
    assert code == ExitCode.OK
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)  # human format deliberately is not machine-parseable


def test_init_requires_idempotency_key_in_json_mode(tmp_path: Path, capsys) -> None:
    code = run(["init", "--format", "json", "--db", str(tmp_path / "t.db")])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"
    assert not (tmp_path / "t.db").exists()  # the refusal left no trace


def test_init_creates_migrates_and_replays_idempotently(tmp_path: Path, capsys) -> None:
    db = tmp_path / "t.db"
    first = run(["init", "--format", "json", "--db", str(db), "--idempotency-key", "k1"])
    env_first = _json_stdout(capsys)
    assert first == ExitCode.OK
    assert env_first["data"]["created"] is True
    assert env_first["data"]["cached"] is False
    assert db.exists()

    # Same key, same request: the cached result comes back, nothing reruns.
    second = run(["init", "--format", "json", "--db", str(db), "--idempotency-key", "k1"])
    env_second = _json_stdout(capsys)
    assert second == ExitCode.OK
    assert env_second["data"]["cached"] is True
    assert env_second["data"]["created"] is True  # the original result, replayed


def test_init_same_key_different_request_is_conflict(tmp_path: Path, capsys) -> None:
    db_a, db_b = tmp_path / "a.db", tmp_path / "b.db"
    run(["init", "--format", "json", "--db", str(db_a), "--idempotency-key", "k1"])
    capsys.readouterr()
    # Reusing the key for a different database is a different request: CONFLICT.
    conn = connect(db_b)
    migrate(conn)
    conn.execute(
        "INSERT INTO idempotency (idempotency_key, payload_hash, result, created_at) VALUES (?,?,?,?);",
        ("k1", "different-request-hash", "{}", "t"),
    )
    conn.close()
    code = run(["init", "--format", "json", "--db", str(db_b), "--idempotency-key", "k1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.CONFLICT
    assert env["error"]["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_database_check_missing_db_is_not_found(tmp_path: Path, capsys) -> None:
    code = run(["database", "check", "--format", "json", "--db", str(tmp_path / "nope.db")])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.NOT_FOUND
    assert env["error"]["error_code"] == "DATABASE_NOT_FOUND"
    assert env["error"]["next_action"] == "init"


def test_database_check_ok_with_pending_export(tmp_path: Path, capsys) -> None:
    db, export = tmp_path / "t.db", tmp_path / "e.jsonl"
    run(["init", "--format", "json", "--db", str(db), "--idempotency-key", "k1"])
    capsys.readouterr()
    # Append one event through the kernel: export lag must be pending, not error.
    conn = connect(db)
    clock = FixedClock(datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC))
    rnd = SeededRandomSource(1)
    store = EventStore(conn)
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type="demo",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="c",
                    payload={"i": 1},
                )
            ]
        )
    conn.close()

    code = run(["database", "check", "--format", "json", "--db", str(db), "--export", str(export)])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["pending"]["unexported_events"] == 1


def test_database_check_integrity_error_is_precondition_failed(tmp_path: Path, capsys) -> None:
    db = tmp_path / "t.db"
    run(["init", "--format", "json", "--db", str(db), "--idempotency-key", "k1"])
    capsys.readouterr()
    conn = connect(db)
    conn.execute("DROP TABLE outbox;")
    conn.close()

    code = run(["database", "check", "--format", "json", "--db", str(db)])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.PRECONDITION_FAILED
    assert env["error"]["error_code"] == "DATABASE_INTEGRITY_ERROR"
    assert "missing tables" in env["error"]["message"]


def test_usage_error_in_json_mode_is_still_an_envelope(capsys) -> None:
    code = run(["no-such-command", "--format", "json"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "USAGE"


def test_usage_error_in_human_mode_goes_to_stderr(capsys) -> None:
    code = run(["no-such-command"])
    captured = capsys.readouterr()
    assert code == ExitCode.USAGE
    assert captured.out == ""  # nothing agent-parseable pretends to exist
    assert "error" in captured.err


def test_internal_error_is_wrapped_not_raised(tmp_path: Path, capsys) -> None:
    # Pointing --db at a directory makes sqlite fail unexpectedly: the agent
    # must still receive a valid ok:false envelope, never a traceback (cli 4.1).
    code = run(["database", "check", "--format", "json", "--db", str(tmp_path)])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.INTERNAL
    assert env["error"]["error_code"] == "INTERNAL"


def test_registry_matches_published_surface() -> None:
    from english_trainer.cli.registry import command_registry

    registry = {descriptor.name: descriptor for descriptor in command_registry()}
    assert set(registry) == {"doctor", "init", "database.check", "snapshot.create"}
    assert registry["init"].mutating and registry["init"].requires_idempotency_key
    assert registry["snapshot.create"].mutating and registry["snapshot.create"].requires_idempotency_key
    assert not registry["doctor"].mutating
    assert not registry["database.check"].mutating


def test_root_option_drives_default_paths(tmp_path: Path, capsys) -> None:
    # The layout is the single path authority: --root without --db/--export
    # resolves to <root>/trainer.db and <root>/trainer.events.jsonl (1.3).
    code = run(["init", "--format", "json", "--root", str(tmp_path), "--idempotency-key", "k1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert (tmp_path / "trainer.db").exists()
    assert env["data"]["db"] == str(tmp_path / "trainer.db")


def test_snapshot_create_requires_key_in_json_mode(tmp_path: Path, capsys) -> None:
    code = run(["snapshot", "create", "--format", "json", "--root", str(tmp_path)])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.USAGE
    assert env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"


def test_snapshot_create_missing_db_is_not_found(tmp_path: Path, capsys) -> None:
    code = run(["snapshot", "create", "--format", "json", "--root", str(tmp_path), "--idempotency-key", "s1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.NOT_FOUND
    assert env["error"]["next_action"] == "init"


def test_snapshot_create_and_cached_replay(tmp_path: Path, capsys) -> None:
    run(["init", "--format", "json", "--root", str(tmp_path), "--idempotency-key", "k1"])
    capsys.readouterr()

    first = run(
        ["snapshot", "create", "--format", "json", "--root", str(tmp_path), "--idempotency-key", "s1"]
    )
    env_first = _json_stdout(capsys)
    _envelope_shape_ok(env_first)
    assert first == ExitCode.OK
    assert env_first["data"]["cached"] is False
    directory = tmp_path / "snapshots" / env_first["data"]["directory"]
    assert (directory / "trainer.db").exists()
    assert (directory / "manifest.json").exists()

    # Same key: the cached manifest replays; no second snapshot directory.
    second = run(
        ["snapshot", "create", "--format", "json", "--root", str(tmp_path), "--idempotency-key", "s1"]
    )
    env_second = _json_stdout(capsys)
    assert second == ExitCode.OK
    assert env_second["data"]["cached"] is True
    assert env_second["data"]["directory"] == env_first["data"]["directory"]
    snapshot_dirs = [p for p in (tmp_path / "snapshots").iterdir() if p.is_dir()]
    assert len(snapshot_dirs) == 1
