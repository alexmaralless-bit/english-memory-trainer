"""CLI contract tests (cli 4): total envelope, clean stdout in json mode,
closed exit codes, mandatory next_action on refusal, idempotency of init, and
the brief/report session surface [PD-2026-09-23]."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.cli.app import run
from english_trainer.cli.envelope import SCHEMA_VERSION, ExitCode
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
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
    # Two init telemetry facts + the demo + this read command's invocation.
    assert env["data"]["pending"]["unexported_events"] == 4


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


def _activated_root(tmp_path: Path, capsys) -> str:
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
    return root


def _event_count(root: str) -> int:
    """Domain facts only: the CLI transport records every invocation
    (``cli.*`` telemetry), read-only commands included."""
    conn = connect(Path(root) / "trainer.db")
    try:
        return sum(1 for event in EventStore(conn).read() if not event.type.startswith("cli."))
    finally:
        conn.close()


def _first_target(brief: dict[str, Any]) -> tuple[str, str]:
    """A (target, dimension) the brief's advisory plan actually drills."""
    for step in brief["plan"]["steps"]:
        if step.get("target_ref") and step.get("dimension"):
            return str(step["target_ref"]), str(step["dimension"])
    raise AssertionError("the composed plan names no target")


def _report_doc(session_id: str, brief: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "lesson_report@1",
        "session_id": session_id,
        "brief_hash": brief["report_contract"]["brief_hash"],
        "items": items,
        "blocks": [],
        "reviews_skipped": [],
        "teaching": [],
        "lexicon": [],
        "summary": {"text": "Разобрали тему урока.", "next_focus": "повторение"},
    }


def _item(item_id: str, target: str, dimension: str, answer: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "target_ref": target,
        "dimension": dimension,
        "kind": "production",
        "prompt": "Скажи по-английски.",
        "raw_answer": answer,
        "verdict": "correct",
        "hints": 0,
        "secondary_targets": [],
        "review_id": None,
        "block_id": None,
        "errors": [],
    }


def test_session_lifecycle_through_the_cli(tmp_path: Path, capsys) -> None:
    """propose -> start (brief) -> check-report -> report -> status, over the
    brief/report protocol [PD-2026-09-23], with the contract's exit codes."""
    root = _activated_root(tmp_path, capsys)

    code = run(["session", "propose", "--root", root, "--format", "json"])
    proposal = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert proposal["data"]["profile"] == "program_lesson"
    assert proposal["data"]["title"]
    assert proposal["data"]["agenda"]
    assert proposal["data"]["requires_confirmation"] is True

    # Start requires the key in json mode.
    start_args = ["session", "start", "--provider", "claude-code", "--format", "json", "--root", root]
    code = run(start_args)
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    # The proposal-hash option is gone: explicit arguments are the consent.
    code = run([*start_args, "--expected-proposal-hash", "sha256:x", "--idempotency-key", "s0"])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "USAGE"

    code = run([*start_args, "--idempotency-key", "s1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    session_id = env["data"]["session_id"]
    assert env["data"]["pinned_versions"]["curriculum"] == "v1"
    assert "rubric" not in env["data"]["pinned_versions"]  # the verdict is the tutor's
    brief = env["data"]["brief"]
    assert brief["schema"] == "lesson_brief@1"
    assert brief["report_contract"]["accepts_reports"] is True
    assert "briefing" not in env["data"]

    # The same key replays the cached start (the same brief), not a new session.
    code = run([*start_args, "--idempotency-key", "s1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["cached"] is True
    assert env["data"]["session_id"] == session_id

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

    code = run(["session", "status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["active"] == session_id
    assert env["data"]["status"] == "STARTED"

    target, dimension = _first_target(brief)
    bad = _report_doc(session_id, brief, [_item("i1", "grammar.no-such-topic", dimension, "I am here.")])
    good = _report_doc(session_id, brief, [_item("i1", target, dimension, "I am a data engineer.")])
    bad_file, good_file = tmp_path / "bad.json", tmp_path / "good.json"
    bad_file.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    good_file.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")

    # check-report is read-only: an inadmissible report is a SUCCESSFUL check
    # (exit 0) saying `valid: false`, and nothing is written.
    before = _event_count(root)
    code = run(["session", "check-report", "--file", str(bad_file), "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["command"] == "session.check-report"
    assert env["data"]["valid"] is False
    (row,) = env["data"]["items"]
    assert row["status"] == "rejected" and "unknown_target" in [r["code"] for r in row["reasons"]]
    code = run(["session", "check-report", "--file", str(good_file), "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["valid"] is True
    assert env["data"]["items"][0]["status"] == "accepted"
    assert _event_count(root) == before

    # report mutates: the key is mandatory in json mode.
    report_args = ["session", "report", "--provider", "claude-code", "--format", "json", "--root", root]
    code = run([*report_args, "--file", str(good_file)])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    # A report with any rejected item is refused whole: exit 6, the full check
    # rides the error, and nothing is written.
    code = run([*report_args, "--file", str(bad_file), "--idempotency-key", "rep-bad"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.PRECONDITION_FAILED
    assert env["error"]["error_code"] == "REPORT_REJECTED"
    assert env["error"]["check"]["valid"] is False
    assert env["error"]["check"]["items"][0]["status"] == "rejected"
    assert _event_count(root) == before

    # An unreadable file is INVALID_INPUT, never a traceback.
    missing = tmp_path / "missing.json"
    code = run([*report_args, "--file", str(missing), "--idempotency-key", "rep-missing"])
    env = _json_stdout(capsys)
    assert code == ExitCode.INVALID_INPUT and env["error"]["error_code"] == "INVALID_INPUT"

    code = run([*report_args, "--file", str(good_file), "--idempotency-key", "rep-1"])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["command"] == "session.report"
    assert env["data"]["cached"] is False
    assert env["data"]["session_id"] == session_id

    # The session is finished and the slot is free.
    code = run(["session", "status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["active"] is None

    # A retried report (same key, same document) is the cached result -- even
    # without --session, now that no session is active.
    code = run([*report_args, "--file", str(good_file), "--idempotency-key", "rep-1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["cached"] is True
    # The same key with a different document is a CONFLICT.
    code = run([*report_args, "--file", str(bad_file), "--idempotency-key", "rep-1"])
    env = _json_stdout(capsys)
    assert code == ExitCode.CONFLICT and env["error"]["error_code"] == "IDEMPOTENCY_CONFLICT"
    # A fresh key on the finished session is a precondition failure.
    code = run([*report_args, "--file", str(good_file), "--idempotency-key", "rep-2"])
    env = _json_stdout(capsys)
    assert code == ExitCode.PRECONDITION_FAILED

    # The reported answer became evidence; the scoring fold sees it and
    # replays byte-identically.
    code = run(["scoring", "replay", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["consistent"] is True
    assert env["data"]["targets"] == 1
    code = run(["status", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert env["data"]["targets"][target]["evidence_count"] == 1
    assert env["data"]["measured_working_level"] is None  # no-data, never zero

    # No active session and no session in the document: nothing to check.
    orphan = tmp_path / "orphan.json"
    orphan.write_text(json.dumps({"schema": "lesson_report@1"}), encoding="utf-8")
    code = run(["session", "check-report", "--file", str(orphan), "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.NOT_FOUND and env["error"]["error_code"] == "SESSION_NOT_FOUND"


def test_abandon_through_the_cli_is_idempotent(tmp_path: Path, capsys) -> None:
    root = _activated_root(tmp_path, capsys)
    run(
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
    started = _json_stdout(capsys)["data"]
    abandon_args = [
        "session",
        "abandon",
        "--expected-session-revision",
        str(started["session_revision"]),
        "--format",
        "json",
        "--root",
        root,
        "--idempotency-key",
        "ab1",
    ]
    code = run(abandon_args)
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK and env["data"]["session_id"] == started["session_id"]
    assert env["data"]["status_event"] == "session.abandoned"
    # Replay of the same abandon returns the cached result, not an error.
    code = run(abandon_args)
    env = _json_stdout(capsys)
    assert code == ExitCode.NOT_FOUND or env["data"].get("cached") is True
    code = run(["session", "status", "--format", "json", "--root", root])
    assert _json_stdout(capsys)["data"]["active"] is None


@pytest.mark.parametrize(
    "argv",
    [
        ["session", "next"],
        ["session", "peek"],
        ["session", "replan"],
        ["session", "finish"],
        ["teaching", "rendered"],
        ["exercise", "rendered"],
        ["exercise", "prepare"],
        ["exercise", "bank"],
        ["attempt", "record"],
        ["attempt", "record-block"],
        ["attempt", "finalize"],
        ["observed", "record"],
        ["review", "close"],
        ["turn", "submit"],
        ["signal"],
    ],
)
def test_the_per_step_protocol_commands_are_gone(argv: list[str], capsys) -> None:
    code = run([*argv, "--format", "json"])
    env = _json_stdout(capsys)
    assert code == ExitCode.USAGE and env["error"]["error_code"] == "USAGE"


def test_availability_set_and_show_through_cli(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "init"])
    capsys.readouterr()
    conn = connect(tmp_path / "trainer.db")
    clock = FixedClock(datetime(2026, 7, 22, 12, tzinfo=UTC))
    registry = PolicyRegistry(conn, clock)
    loaded = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "curriculum" / "policies" / "control-v1.yaml").read_text(
            "utf-8"
        )
    )
    assert isinstance(loaded, dict)
    registry.register("control", "control@1", loaded)
    registry.activate("control", "control@1")
    conn.close()

    code = run(
        [
            "availability",
            "set",
            "--sessions-per-week-milli",
            "2000",
            "--typical-minutes",
            "30",
            "--root",
            root,
            "--format",
            "json",
            "--idempotency-key",
            "availability-1",
        ]
    )
    set_result = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert set_result["data"]["updated"] is True

    code = run(["availability", "show", "--root", root, "--format", "json"])
    shown = _json_stdout(capsys)
    assert code == ExitCode.OK
    assert shown["data"]["declared"] == {
        "sessions_per_week_milli": 2000,
        "typical_minutes": 30,
    }
    assert shown["data"]["observed"]["sessions_per_week_milli"] == "no-data"


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
        "curriculum.texts",
        "curriculum.activate",
        "session.propose",
        "session.start",
        "session.check-report",
        "session.report",
        "session.abandon",
        "session.status",
        "session.resume",
        "availability.show",
        "availability.set",
        "why",
        "metrics",
        "tunables.list",
        "calibration.list",
        "calibration.propose",
        "calibration.confirm",
        "scoring.replay",
        "scoring.transitions.backfill",
        "status",
        "lexicon.add",
        "lexicon.encounter",
        "lexicon.list",
        "review.due",
        "memory.render",
        "memory.rebuild",
        "memory.check",
        "skills.sync",
        "skills.validate",
        "skills.report",
        "adapters.compare",
        "adapters.capture-turn",
        "audit.session",
        "audit.correlation",
        "audit.target",
        "placement.start",
        "placement.answer",
        "placement.resume",
        "placement.submit",
        "placement.abandon",
        "placement.decline",
        "learner.preferences.show",
        "learner.preferences.set",
    }
    assert registry["memory.render"].mutating and registry["memory.render"].requires_idempotency_key
    assert not registry["memory.check"].mutating  # drift check repairs nothing
    assert not registry["review.due"].mutating  # the backlog recommends, never blocks
    assert not registry["scoring.replay"].mutating  # scores ARE the fold
    assert not registry["status"].mutating
    assert registry["lexicon.add"].mutating and registry["lexicon.add"].requires_idempotency_key
    assert registry["lexicon.encounter"].mutating and registry["lexicon.encounter"].requires_idempotency_key
    assert not registry["lexicon.list"].mutating  # a read-only fold
    # The brief/report protocol: check writes nothing, report commits atomically.
    assert not registry["session.check-report"].mutating
    assert not registry["session.check-report"].requires_idempotency_key
    assert registry["session.report"].mutating and registry["session.report"].requires_idempotency_key
    assert registry["session.report"].owner_module == "lessons"
    assert registry["session.start"].mutating and registry["session.start"].requires_idempotency_key
    assert registry["session.abandon"].mutating and registry["session.abandon"].requires_idempotency_key
    assert not registry["session.propose"].mutating
    assert not registry["session.status"].mutating
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
    assert not registry["availability.show"].mutating
    assert registry["availability.set"].mutating
    assert registry["availability.set"].requires_idempotency_key
    assert not registry["why"].mutating
    assert not registry["metrics"].mutating


def _published_commands() -> set[str]:
    """Every dotted command name the typer app actually serves."""
    import typer.main

    from english_trainer.cli.app import app

    def walk(group: Any, prefix: str) -> set[str]:
        names: set[str] = set()
        for name, command in getattr(group, "commands", {}).items():
            dotted = f"{prefix}.{name}" if prefix else name
            if getattr(command, "commands", None):
                names |= walk(command, dotted)
            else:
                names.add(dotted)
        return names

    return walk(typer.main.get_command(app), "")


def test_every_served_command_is_registered_and_vice_versa() -> None:
    from english_trainer.cli.registry import command_registry

    registered = {descriptor.name for descriptor in command_registry()}
    assert _published_commands() == registered


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


# -- automaticity layer: drill blocks and reconstruction texts (evidence 4.6)


def test_curriculum_texts_serves_the_active_version(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "k1"])
    capsys.readouterr()

    program = {
        "schema_version": 1,
        "topics": [{"id": "grammar.present-perfect.result"}],
        "lexicon": [],
        "texts": [
            {
                "id": "text.recon.ppr.status-update",
                "title": "Status update",
                "topic": "grammar.present-perfect.result",
                "domain": "work",
                "cefr": "A2",
                "text": "I've already sent the report.",
            },
            {
                "id": "text.recon.ppr.weekend",
                "title": "Weekend",
                "topic": "grammar.present-perfect.result",
                "domain": "everyday",
                "cefr": "A2",
                "text": "We've just come back.",
            },
            {
                "id": "text.recon.other.paper",
                "title": "Paper",
                "topic": "grammar.passive.basic-process",
                "domain": "academic",
                "cefr": "B1",
                "text": "The data was collected.",
            },
        ],
    }
    conn = connect(tmp_path / "trainer.db")
    registry = PolicyRegistry(conn, FixedClock(datetime(2026, 9, 22, 9, tzinfo=UTC)))
    registry.register("curriculum", "v-texts", program)
    registry.activate("curriculum", "v-texts")
    conn.close()

    code = run(
        [
            "curriculum",
            "texts",
            "--topic",
            "grammar.present-perfect.result",
            "--format",
            "json",
            "--root",
            root,
        ]
    )
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.OK
    assert env["data"]["version"] == "v-texts"
    assert [text["id"] for text in env["data"]["texts"]] == [
        "text.recon.ppr.status-update",
        "text.recon.ppr.weekend",
    ]

    code = run(
        [
            "curriculum",
            "texts",
            "--topic",
            "grammar.present-perfect.result",
            "--domain",
            "work",
            "--format",
            "json",
            "--root",
            root,
        ]
    )
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["count"] == 1
    assert env["data"]["texts"][0]["id"] == "text.recon.ppr.status-update"

    # A topic with no authored texts is an empty list, not a refusal.
    code = run(["curriculum", "texts", "--topic", "grammar.nowhere", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    assert code == ExitCode.OK and env["data"]["texts"] == []


def test_curriculum_texts_without_an_active_version_refuses(tmp_path: Path, capsys) -> None:
    root = str(tmp_path)
    run(["init", "--format", "json", "--root", root, "--idempotency-key", "k1"])
    capsys.readouterr()
    code = run(["curriculum", "texts", "--topic", "grammar.be.identity", "--format", "json", "--root", root])
    env = _json_stdout(capsys)
    _envelope_shape_ok(env)
    assert code == ExitCode.PRECONDITION_FAILED
    assert env["error"]["next_action"] == "curriculum activate"
