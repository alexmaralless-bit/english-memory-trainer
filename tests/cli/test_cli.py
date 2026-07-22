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


def test_session_lifecycle_through_the_cli(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    curriculum_dir = str(Path(__file__).resolve().parents[2] / "curriculum")
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "k1"])
    run(
        [
            "curriculum",
            "activate",
            "--version",
            "v1",
            "--curriculum",
            curriculum_dir,
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "a1",
        ]
    )
    capsys.readouterr()

    # Start requires the key in json mode.
    code = run(["session", "start", "--provider", "claude-code", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"

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
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    session_id = env["data"]["session_id"]
    assert env["data"]["pinned_versions"]["curriculum"] == "v1"

    # A second start is a precondition failure, not a silent abandon.
    code = run(
        [
            "session",
            "start",
            "--provider",
            "codex",
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "s2",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.PRECONDITION_FAILED
    assert env["error"]["error_code"] == "SESSION_PRECONDITION"

    # Status shows the active session; finish from STARTED is refused; abandon works.
    code = run(["session", "status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["active"] == session_id

    code = run(["session", "finish", "--format", "json", "--root", root, "--idempotency-key", "f1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.PRECONDITION_FAILED  # nothing recorded -> abandon instead

    # -- step delivery: peek -> next (CAS) -> cached replay -> conflict -> replan
    code = run(["session", "peek", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["plan_version"] == 1
    assert env["data"]["step"] is not None and env["data"]["steps_remaining"] > 0

    code = run(["session", "next", "--expected-plan-version", "1", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    next_args = ["session", "next", "--expected-plan-version", "1", "--format", "json", "--root", root]
    code = run([*next_args, "--idempotency-key", "n1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["plan_version"] == 2
    first_step_id = env["data"]["step"]["step_id"]

    # Same key replays the same step from the cache -- no second STEP_PRESENTED.
    code = run([*next_args, "--idempotency-key", "n1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["cached"] is True
    assert env["data"]["step"]["step_id"] == first_step_id

    # A fresh key with the stale version is a CONFLICT naming the current one.
    code = run([*next_args, "--idempotency-key", "n2"])
    env = _json_stdout(capsys)
    assert code == ExitCode.CONFLICT and env["error"]["error_code"] == "PLAN_VERSION_CONFLICT"
    assert "version 2" in env["error"]["message"]

    code = run(
        [
            "session",
            "replan",
            "--expected-plan-version",
            "2",
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "r1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["composition_revision"] == 2 and env["data"]["plan_version"] == 3

    # -- evidence: EXERCISE_RENDERED before the learner sees it, then the attempt
    exercise_file = tmp_path / "exercise.json"
    exercise_file.write_text(
        json.dumps(
            {
                "prompt": "Complete: I ___ an engineer.",
                "answer_key": ["am"],
                "provenance": {"origin": "authored"},
            }
        ),
        encoding="utf-8",
    )
    code = run(
        [
            "exercise",
            "rendered",
            "--step",
            first_step_id,
            "--input",
            str(exercise_file),
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "x1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    instance_id = env["data"]["exercise_instance_id"]

    attempt_file = tmp_path / "attempt.json"
    attempt_file.write_text(json.dumps({"raw_answer": "am", "hints": 0}), encoding="utf-8")
    code = run(
        [
            "attempt",
            "record",
            "--step",
            first_step_id,
            "--exercise-instance",
            instance_id,
            "--input",
            str(attempt_file),
            "--note",
            "confident answer",
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "at1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["status"] == "assessed"
    assert env["data"]["assessment"]["correct"] is True

    # The untrusted note surfaces in status as its own block.
    code = run(["session", "status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert env["data"]["notes"][0]["text"] == "confident answer"

    # The assessed attempt became evidence; the scoring fold sees it and
    # replays byte-identically (2.3 increment 1).
    code = run(["scoring", "replay", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["consistent"] is True
    assert env["data"]["targets"] == 1  # grammar.be.identity earned mastery
    code = run(["status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    target = env["data"]["targets"]["grammar.be.identity"]
    assert target["knowledge_state"] == "NEW"  # states move only on review outcomes
    assert target["mastery"]["recognition"] == "4.800"  # 8 * 0.6 * 1.00, Decimal exact
    assert env["data"]["measured_working_level"] is None  # no-data, never zero

    # -- increment 4: the pending-set gate and the bank
    # An open (rubric-less) attempt stays `recorded` and blocks finish [P0-2].
    open_file = tmp_path / "open_attempt.json"
    open_file.write_text(json.dumps({"raw_answer": "I am an engineer, so I am."}), encoding="utf-8")
    code = run(
        [
            "attempt",
            "record",
            "--step",
            first_step_id,
            "--input",
            str(open_file),
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "at2",
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["status"] == "recorded"

    code = run(["session", "finish", "--format", "json", "--root", root, "--idempotency-key", "f2"])
    env = _json_stdout(capsys)
    assert code == ExitCode.PRECONDITION_FAILED
    assert "pending" in env["error"]["message"]

    # The assessed attempt earned this exercise its bank admission (PD-2 A).
    code = run(
        [
            "exercise",
            "accept",
            "--instance",
            instance_id,
            "--format",
            "json",
            "--root",
            root,
            "--idempotency-key",
            "ba1",
        ]
    )
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["status"] == "accepted"

    code = run(["exercise", "bank", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["count"] == 1
    assert env["data"]["items"][0]["admission_basis"] == "assessed_attempt"

    code = run(["session", "abandon", "--format", "json", "--root", root, "--idempotency-key", "ab1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["session_id"] == session_id

    # Replay of the same abandon returns the cached result, not an error.
    code = run(["session", "abandon", "--format", "json", "--root", root, "--idempotency-key", "ab1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.NOT_FOUND or env["data"].get("cached") is True

    code = run(["session", "status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert env["data"]["active"] is None


def test_registry_matches_published_surface() -> None:
    from english_trainer.cli.registry import command_registry

    registry = {descriptor.name: descriptor for descriptor in command_registry()}
    assert set(registry) == {
        "doctor",
        "init",
        "database.check",
        "snapshot.create",
        "curriculum.validate",
        "curriculum.show",
        "curriculum.lexicon",
        "curriculum.activate",
        "session.start",
        "session.finish",
        "session.abandon",
        "session.status",
        "session.peek",
        "session.next",
        "session.replan",
        "exercise.rendered",
        "attempt.record",
        "exercise.accept",
        "exercise.reject",
        "exercise.retire",
        "exercise.bank",
        "scoring.replay",
        "status",
        "review.due",
        "review.close",
        "attempt.finalize",
        "memory.render",
        "memory.rebuild",
        "memory.check",
        "skills.sync",
        "skills.validate",
        "adapters.compare",
        "session.resume",
        "placement.start",
        "placement.answer",
        "placement.resume",
        "placement.submit",
        "placement.abandon",
        "placement.decline",
    }
    assert registry["memory.render"].mutating and registry["memory.render"].requires_idempotency_key
    assert not registry["memory.check"].mutating  # drift check repairs nothing
    assert registry["attempt.finalize"].mutating and registry["attempt.finalize"].requires_idempotency_key
    assert registry["review.close"].mutating and registry["review.close"].requires_idempotency_key
    assert not registry["review.due"].mutating  # the backlog recommends, never blocks
    assert not registry["scoring.replay"].mutating  # scores ARE the fold
    assert not registry["status"].mutating
    assert registry["exercise.accept"].mutating and registry["exercise.accept"].requires_idempotency_key
    assert not registry["exercise.bank"].mutating
    assert registry["exercise.rendered"].mutating and registry["exercise.rendered"].requires_idempotency_key
    assert registry["attempt.record"].mutating and registry["attempt.record"].requires_idempotency_key
    assert registry["session.next"].mutating and registry["session.next"].requires_idempotency_key
    assert registry["session.replan"].mutating and registry["session.replan"].requires_idempotency_key
    assert not registry["session.peek"].mutating
    assert registry["init"].mutating and registry["init"].requires_idempotency_key
    assert registry["snapshot.create"].mutating and registry["snapshot.create"].requires_idempotency_key
    assert registry["curriculum.activate"].mutating
    assert registry["curriculum.activate"].requires_idempotency_key
    assert not registry["doctor"].mutating
    assert not registry["database.check"].mutating
    assert not registry["curriculum.validate"].mutating
    assert registry["skills.sync"].mutating and registry["skills.sync"].requires_idempotency_key
    assert not registry["skills.validate"].mutating
    assert not registry["adapters.compare"].mutating
    assert registry["session.resume"].mutating and registry["session.resume"].requires_idempotency_key


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
