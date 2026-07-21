"""The ``trainer`` CLI entry point (cli 1, 4, 5; foundation 6).

This increment publishes the kernel-facing surface: ``trainer doctor`` (first
step when diagnosing a broken setup), ``trainer init`` (bootstrap the local
state -- the one mutating command, so it requires an idempotency key in json
mode) and ``trainer database check`` (integrity of the store and its JSONL
export). ``trainer scoring replay`` arrives with the scoring module -- there
are no scores to replay yet, and pretending otherwise would violate the honest
boundary.

Contract highlights this module enforces (cli 4):

- with ``--format json`` stdout is exactly one JSON envelope -- success,
  domain refusal, usage error and internal error alike;
- exit codes come from the closed set in
  :class:`~english_trainer.cli.envelope.ExitCode`;
- every refusal names ``next_action``;
- read-only commands never mutate, not even to repair what they find.

The default database and export paths are provisional conveniences until the
storage module (roadmap 1.3) fixes the layout; agents should pass ``--db`` /
``--export`` explicitly.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from english_trainer.cli.envelope import (
    ErrorPayload,
    ExitCode,
    failure_envelope,
    print_human,
    print_json_envelope,
    success_envelope,
)
from english_trainer.kernel.check import database_check
from english_trainer.kernel.clock import SystemClock, SystemRandom
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import IdempotencyConflict, KernelError
from english_trainer.kernel.export import JsonlExporter
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import SCHEMA_VERSION, EventStore, connect, migrate
from english_trainer.kernel.uow import CachedResult, UnitOfWork
from english_trainer.storage.layout import StorageLayout, open_storage, resolve_layout
from english_trainer.storage.snapshot import create_snapshot

app = typer.Typer(add_completion=False, help="English Memory Trainer engine CLI.")
database_app = typer.Typer(add_completion=False, help="Storage integrity commands.")
app.add_typer(database_app, name="database")
snapshot_app = typer.Typer(add_completion=False, help="Point-in-time snapshots of the local state.")
app.add_typer(snapshot_app, name="snapshot")

_FormatOpt = Annotated[str, typer.Option("--format", help="Output format: text (human) or json (contract).")]
_RootOpt = Annotated[Path, typer.Option("--root", help="Trainer home directory (storage layout root).")]
_DbOpt = Annotated[
    Path | None, typer.Option("--db", help="SQLite database path; defaults to <root>/trainer.db.")
]
_ExportOpt = Annotated[
    Path | None,
    typer.Option("--export", help="JSONL export path; defaults to <root>/trainer.events.jsonl."),
]
_CorrOpt = Annotated[
    str | None, typer.Option("--correlation-id", help="Correlation id; generated when absent.")
]


def _paths(root: Path, db: Path | None, export: Path | None) -> tuple[StorageLayout, Path, Path]:
    """Resolve effective paths: explicit options win, the layout fills the rest."""
    layout = resolve_layout(root)
    return layout, db if db is not None else layout.db, export if export is not None else layout.export


def _correlation(provided: str | None) -> str:
    # The CLI edge is the one layer allowed to touch the system clock/random
    # (foundation 8): the id must exist before any engine call it correlates.
    return provided if provided else new_ulid(SystemClock(), SystemRandom())


def _emit(envelope: dict[str, Any], human: list[str], fmt: str, code: ExitCode) -> None:
    if fmt == "json":
        print_json_envelope(envelope)
    else:
        print_human(human)
    raise typer.Exit(int(code))


@app.command()
def doctor(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    db: _DbOpt = None,
    export: _ExportOpt = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Diagnose the environment and local state. Read-only; run this first."""
    corr = _correlation(correlation_id)
    _, db, export = _paths(root, db, export)
    checks: list[dict[str, Any]] = [
        {"name": "python", "status": "ok", "detail": platform.python_version()},
        {"name": "platform", "status": "ok", "detail": platform.platform()},
    ]
    if db.exists():
        conn = connect(db)
        try:
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            applied = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY 1;")]
            schema_ok = bool(applied) and applied[-1] == SCHEMA_VERSION
            checks.append(
                {
                    "name": "sqlite_integrity",
                    "status": "ok" if integrity == "ok" else "error",
                    "detail": str(integrity),
                }
            )
            checks.append(
                {
                    "name": "journal_mode",
                    "status": "ok" if str(journal).lower() == "wal" else "warn",
                    "detail": str(journal),
                }
            )
            checks.append(
                {
                    "name": "schema_version",
                    "status": "ok" if schema_ok else "warn",
                    "detail": f"applied={applied} expected={SCHEMA_VERSION}",
                }
            )
        finally:
            conn.close()
    else:
        checks.append(
            {"name": "database", "status": "warn", "detail": f"{db} does not exist; run `trainer init`"}
        )
    checks.append(
        {
            "name": "export",
            "status": "ok" if export.exists() else "warn",
            "detail": str(export) if export.exists() else f"{export} does not exist yet",
        }
    )
    data = {"db": str(db), "export": str(export), "checks": checks}
    human = [f"trainer doctor — {db}"] + [f"  [{c['status']:>5}] {c['name']}: {c['detail']}" for c in checks]
    _emit(success_envelope("doctor", corr, data), human, fmt, ExitCode.OK)


@app.command()
def init(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    db: _DbOpt = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Required with --format json (cli 4.3)."),
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Initialize the local state: create the database and apply migrations."""
    corr = _correlation(correlation_id)
    _, db, _export = _paths(root, db, None)
    if fmt == "json" and not idempotency_key:
        # Mutating commands must carry the key in json mode: the process can die
        # after commit and before the response is printed, and without the key
        # the agent cannot safely retry (cli 4.3).
        error = ErrorPayload(
            error_code="MISSING_IDEMPOTENCY_KEY",
            message="`trainer init` is mutating: --idempotency-key is required with --format json.",
            allowed_actions=["init --idempotency-key <key>", "doctor"],
            next_action="init --idempotency-key <key>",
        )
        _emit(failure_envelope("init", corr, error), [], fmt, ExitCode.USAGE)

    existed = db.exists()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db)
    try:
        migrate(conn)  # forward-only and idempotent by construction
        store = EventStore(conn)
        result: dict[str, Any] = {
            "db": str(db),
            "created": not existed,
            "schema_version": SCHEMA_VERSION,
        }
        cached = False
        if idempotency_key:
            request_hash = payload_hash({"command": "init", "db": str(db)})
            with UnitOfWork(store, SystemClock()) as uow:
                prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    result = dict(prior.value)
                    cached = True
                else:
                    uow.record_result(idempotency_key, request_hash, result)
        data = {**result, "cached": cached}
        human = [
            f"initialized {db}" if data.get("created") else f"{db} already initialized",
            f"schema version: {data.get('schema_version')}",
        ]
        _emit(success_envelope("init", corr, data), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["init --idempotency-key <fresh-key>"],
            next_action="init --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("init", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    finally:
        conn.close()


@database_app.command("check")
def database_check_cmd(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    db: _DbOpt = None,
    export: _ExportOpt = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Check store integrity and the export up to the acknowledged offset.

    Export lag is reported as pending work, not an error (foundation 2.1);
    divergence after catch-up fails the check. Read-only: nothing is repaired.
    """
    corr = _correlation(correlation_id)
    _, db, export = _paths(root, db, export)
    if not db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{db} does not exist.",
            allowed_actions=["init", "doctor"],
            next_action="init",
        )
        _emit(
            failure_envelope("database.check", corr, error),
            [f"error: {db} not found"],
            fmt,
            ExitCode.NOT_FOUND,
        )

    conn = connect(db)
    try:
        report = database_check(EventStore(conn), JsonlExporter(export))
    finally:
        conn.close()

    if report.ok:
        data = {"errors": [], "pending": dict(report.pending)}
        human = ["database check: ok", f"  pending: {dict(report.pending)}"]
        _emit(success_envelope("database.check", corr, data), human, fmt, ExitCode.OK)
    error = ErrorPayload(
        error_code="DATABASE_INTEGRITY_ERROR",
        message="; ".join(report.errors),
        allowed_actions=["doctor", "init"],
        next_action="doctor",
    )
    human = ["database check: FAILED"] + [f"  - {line}" for line in report.errors]
    _emit(failure_envelope("database.check", corr, error), human, fmt, ExitCode.PRECONDITION_FAILED)


@snapshot_app.command("create")
def snapshot_create(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Required with --format json (cli 4.3)."),
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Create a point-in-time snapshot after a WAL checkpoint (foundation 3.9)."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    if fmt == "json" and not idempotency_key:
        error = ErrorPayload(
            error_code="MISSING_IDEMPOTENCY_KEY",
            message="`trainer snapshot create` mutates state: --idempotency-key is required with json.",
            allowed_actions=["snapshot create --idempotency-key <key>", "doctor"],
            next_action="snapshot create --idempotency-key <key>",
        )
        _emit(failure_envelope("snapshot.create", corr, error), [], fmt, ExitCode.USAGE)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init", "doctor"],
            next_action="init",
        )
        _emit(
            failure_envelope("snapshot.create", corr, error),
            [f"error: {layout.db} not found"],
            fmt,
            ExitCode.NOT_FOUND,
        )

    request_hash = payload_hash({"command": "snapshot.create", "root": str(layout.root)})
    try:
        if idempotency_key:
            # The replay check runs on its own short-lived connection and is
            # closed BEFORE the snapshot: the checkpoint must not compete with
            # another live connection of ours (foundation 3.9).
            with open_storage(layout) as storage, UnitOfWork(storage.store, SystemClock()) as uow:
                prior = uow.check_idempotency(idempotency_key, request_hash)
            if isinstance(prior, CachedResult):
                data = {**dict(prior.value), "cached": True}
                _emit(
                    success_envelope("snapshot.create", corr, data),
                    [f"snapshot {data.get('directory')} (cached result)"],
                    fmt,
                    ExitCode.OK,
                )
        manifest = create_snapshot(layout, SystemClock())
        if idempotency_key:
            with open_storage(layout) as storage, UnitOfWork(storage.store, SystemClock()) as uow:
                uow.record_result(idempotency_key, request_hash, manifest)
        data = {**manifest, "cached": False}
        human = [f"snapshot created: {manifest['directory']}"] + [
            f"  {name}: {digest}" for name, digest in manifest["files"].items()
        ]
        _emit(success_envelope("snapshot.create", corr, data), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["snapshot create --idempotency-key <fresh-key>"],
            next_action="snapshot create --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("snapshot.create", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except KernelError as exc:
        error = ErrorPayload(
            error_code="SNAPSHOT_CONFLICT",
            message=str(exc),
            allowed_actions=["snapshot create (retry later)", "doctor"],
            next_action="doctor",
        )
        _emit(failure_envelope("snapshot.create", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)


def _wants_json(argv: list[str]) -> bool:
    if "--format=json" in argv:
        return True
    return any(arg == "--format" and argv[i + 1 : i + 2] == ["json"] for i, arg in enumerate(argv))


def run(argv: list[str]) -> int:
    """Invoke the app; guarantee an envelope and a closed exit code (cli 4.1/4.2).

    An exception escaping unwrapped would hand the agent unparseable garbage;
    even internal errors must come back as a valid ``ok: false`` envelope.
    Usage errors are recognized by the ``format_message`` protocol rather than
    by class: typer vendors its argument-parsing library, so the concrete
    exception type is not part of any public surface we could import.
    """
    try:
        # In non-standalone mode the framework *returns* the exit code carried
        # by a raised Exit instead of re-raising it; both paths are honored.
        result = app(args=argv, standalone_mode=False)
        if isinstance(result, int):
            return result
    except typer.Exit as exc:
        return int(exc.exit_code)
    except Exception as exc:  # the contract demands a valid envelope, never a traceback
        format_message = getattr(exc, "format_message", None)
        if callable(format_message):  # argument-parsing refusal (UsageError protocol)
            message = str(format_message())
            if _wants_json(argv):
                error = ErrorPayload(
                    error_code="USAGE",
                    message=message,
                    allowed_actions=["--help"],
                    next_action="--help",
                )
                print_json_envelope(failure_envelope("usage", _correlation(None), error))
            else:
                sys.stderr.write(f"error: {message}\n")
            return int(ExitCode.USAGE)
        if _wants_json(argv):
            error = ErrorPayload(
                error_code="INTERNAL",
                message=f"{type(exc).__name__}: {exc}",
                allowed_actions=["doctor"],
                next_action="doctor",
            )
            print_json_envelope(failure_envelope("internal", _correlation(None), error))
        else:
            sys.stderr.write(f"internal error: {type(exc).__name__}: {exc}\n")
        return int(ExitCode.INTERNAL)
    return int(ExitCode.OK)


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))
