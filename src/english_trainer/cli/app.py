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

import json
import platform
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from english_trainer.cli.envelope import (
    ErrorPayload,
    ExitCode,
    failure_envelope,
    print_human,
    print_json_envelope,
    success_envelope,
)
from english_trainer.control.errors import (
    BudgetTooSmall,
    ControlPolicyInvalid,
    NoCandidates,
    PlanVersionConflict,
)
from english_trainer.control.policy import CONTROL_KIND, require_valid
from english_trainer.curriculum.loader import load_policies, load_program
from english_trainer.curriculum.service import (
    activate_version,
    get_topic,
    lexicon_query,
    register_version,
)
from english_trainer.curriculum.validate import validate_program
from english_trainer.evidence.attempts import EvidencePrecondition, list_notes, record_attempt
from english_trainer.kernel.check import database_check
from english_trainer.kernel.clock import SystemClock, SystemRandom
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import IdempotencyConflict, KernelError, StaleRevision
from english_trainer.kernel.export import JsonlExporter
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import SCHEMA_VERSION, EventStore, connect, migrate
from english_trainer.kernel.uow import CachedResult, UnitOfWork
from english_trainer.lessons.delivery import next_step, peek_step, replan_session
from english_trainer.lessons.rendering import record_rendered_exercise
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    active_session_id,
    finish_session,
    get_session,
    start_session,
)
from english_trainer.storage.layout import StorageLayout, open_storage, resolve_layout
from english_trainer.storage.snapshot import create_snapshot

app = typer.Typer(add_completion=False, help="English Memory Trainer engine CLI.")
database_app = typer.Typer(add_completion=False, help="Storage integrity commands.")
app.add_typer(database_app, name="database")
snapshot_app = typer.Typer(add_completion=False, help="Point-in-time snapshots of the local state.")
app.add_typer(snapshot_app, name="snapshot")
curriculum_app = typer.Typer(add_completion=False, help="The authored program: validate, inspect, activate.")
app.add_typer(curriculum_app, name="curriculum")
session_app = typer.Typer(add_completion=False, help="Learning sessions: start, finish, abandon, status.")
app.add_typer(session_app, name="session")
exercise_app = typer.Typer(add_completion=False, help="Rendered-exercise snapshots (EXERCISE_RENDERED).")
app.add_typer(exercise_app, name="exercise")
attempt_app = typer.Typer(add_completion=False, help="Learner attempts against delivered steps.")
app.add_typer(attempt_app, name="attempt")

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


def _emit(envelope: dict[str, Any], human: list[str], fmt: str, code: ExitCode) -> NoReturn:
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


_CurriculumOpt = Annotated[Path, typer.Option("--curriculum", help="Path to the authored program directory.")]


@curriculum_app.command("validate")
def curriculum_validate(
    fmt: _FormatOpt = "text",
    curriculum: _CurriculumOpt = Path("curriculum"),
    correlation_id: _CorrOpt = None,
) -> None:
    """Validate the authored program (or a candidate). Read-only; repairs nothing."""
    corr = _correlation(correlation_id)
    program = load_program(curriculum)
    report = validate_program(program)
    if report.ok:
        data = {
            "errors": [],
            "warnings": report.warnings,
            "topics": len(program["topics"]),
            "lexicon": len(program["lexicon"]),
        }
        human = [
            f"curriculum valid: {len(program['topics'])} topics, {len(program['lexicon'])} lexical items",
            *[f"  warn: {line}" for line in report.warnings],
        ]
        _emit(success_envelope("curriculum.validate", corr, data), human, fmt, ExitCode.OK)
    error = ErrorPayload(
        error_code="CURRICULUM_INVALID",
        message=f"{len(report.errors)} validation errors; first: " + " | ".join(report.errors[:5]),
        allowed_actions=["curriculum validate"],
        next_action="fix the listed errors, then curriculum validate",
    )
    human = [f"curriculum INVALID: {len(report.errors)} errors"] + [f"  - {e}" for e in report.errors]
    _emit(failure_envelope("curriculum.validate", corr, error), human, fmt, ExitCode.INVALID_INPUT)


@curriculum_app.command("show")
def curriculum_show(
    topic: Annotated[str, typer.Option("--topic", help="Topic id to show.")],
    fmt: _FormatOpt = "text",
    curriculum: _CurriculumOpt = Path("curriculum"),
    correlation_id: _CorrOpt = None,
) -> None:
    """Show one topic with its full body."""
    corr = _correlation(correlation_id)
    found = get_topic(load_program(curriculum), topic)
    if found is None:
        error = ErrorPayload(
            error_code="TOPIC_NOT_FOUND",
            message=f"topic {topic!r} does not exist in {curriculum}.",
            allowed_actions=["curriculum validate", "curriculum show --topic <id>"],
            next_action="curriculum validate",
        )
        _emit(
            failure_envelope("curriculum.show", corr, error),
            [f"error: no topic {topic}"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    human = [f"{found['id']} [{found.get('cefr')}] {found.get('track')}", f"  can_do: {found.get('can_do')}"]
    _emit(success_envelope("curriculum.show", corr, {"topic": found}), human, fmt, ExitCode.OK)


@curriculum_app.command("lexicon")
def curriculum_lexicon(
    fmt: _FormatOpt = "text",
    curriculum: _CurriculumOpt = Path("curriculum"),
    item_type: Annotated[str | None, typer.Option("--type", help="Filter by item type.")] = None,
    cefr: Annotated[str | None, typer.Option("--cefr", help="Filter by CEFR level.")] = None,
    band: Annotated[str | None, typer.Option("--band", help="Filter by curriculum_priority_band.")] = None,
    register: Annotated[str | None, typer.Option("--register", help="Filter by register.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum items returned.")] = 20,
    correlation_id: _CorrOpt = None,
) -> None:
    """Query the lexicon with simple filters. Deterministic order by id."""
    corr = _correlation(correlation_id)
    items = lexicon_query(
        load_program(curriculum),
        item_type=item_type,
        cefr=cefr,
        priority_band=band,
        register=register,
        limit=limit,
    )
    data = {"count": len(items), "items": items}
    human = [f"{len(items)} lexical items"] + [
        f"  {item.get('id')} [{item.get('cefr')}/{item.get('curriculum_priority_band')}]" for item in items
    ]
    _emit(success_envelope("curriculum.lexicon", corr, data), human, fmt, ExitCode.OK)


@curriculum_app.command("activate")
def curriculum_activate(
    version: Annotated[str, typer.Option("--version", help="Version id to register and activate.")],
    fmt: _FormatOpt = "text",
    curriculum: _CurriculumOpt = Path("curriculum"),
    root: _RootOpt = Path(),
    expected_active: Annotated[
        str | None,
        typer.Option("--expected-active", help="The version the caller believes is active (CAS)."),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Required with --format json (cli 4.3)."),
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Validate, register and CAS-activate the program as one version.

    Activation and its ``curriculum.version_activated`` event commit atomically.
    """
    corr = _correlation(correlation_id)
    if fmt == "json" and not idempotency_key:
        error = ErrorPayload(
            error_code="MISSING_IDEMPOTENCY_KEY",
            message="`trainer curriculum activate` mutates state: --idempotency-key is required with json.",
            allowed_actions=["curriculum activate --idempotency-key <key>"],
            next_action="curriculum activate --idempotency-key <key>",
        )
        _emit(failure_envelope("curriculum.activate", corr, error), [], fmt, ExitCode.USAGE)

    program = load_program(curriculum)
    report = validate_program(program)
    if not report.ok:
        error = ErrorPayload(
            error_code="CURRICULUM_INVALID",
            message=f"{len(report.errors)} validation errors; first: " + " | ".join(report.errors[:5]),
            allowed_actions=["curriculum validate"],
            next_action="curriculum validate",
        )
        _emit(
            failure_envelope("curriculum.activate", corr, error),
            [f"error: invalid program ({len(report.errors)} errors)"],
            fmt,
            ExitCode.INVALID_INPUT,
        )

    layout = resolve_layout(root)
    request_hash = payload_hash(
        {"command": "curriculum.activate", "version": version, "expected": expected_active}
    )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    data = {**dict(prior.value), "cached": True}
                    _emit(
                        success_envelope("curriculum.activate", corr, data),
                        [f"curriculum {data.get('version')} active (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            register_version(registry, program, version)
            # Engine policies ship with the curriculum (curriculum/policies/):
            # register and activate them alongside the program so a fresh
            # install can start a session. Registration is idempotent for
            # identical content; control@1 is validated before it may register.
            policies = load_policies(curriculum)
            for kind, policy_version, payload in policies:
                if kind == CONTROL_KIND:
                    require_valid(payload)
                registry.register(kind, policy_version, payload)
                registry.activate(kind, policy_version)
            event = activate_version(
                storage.store, registry, SystemClock(), SystemRandom(), version, expected_active
            )
            result: dict[str, Any] = {
                "version": version,
                "previous": expected_active,
                "activated": event is not None,
                "event_id": event.id if event is not None else None,
                "policies": [policy_version for _, policy_version, _ in policies],
            }
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        data = {**result, "cached": False}
        human = [f"curriculum {version} " + ("activated" if data["activated"] else "already active (no-op)")]
        _emit(success_envelope("curriculum.activate", corr, data), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["curriculum activate --idempotency-key <fresh-key>"],
            next_action="curriculum activate --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("curriculum.activate", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except ControlPolicyInvalid as exc:
        error = ErrorPayload(
            error_code="CONTROL_POLICY_INVALID",
            message=str(exc),
            allowed_actions=["curriculum validate"],
            next_action="fix curriculum/policies/control-v1.yaml, then curriculum activate",
        )
        _emit(
            failure_envelope("curriculum.activate", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.INVALID_INPUT,
        )
    except StaleRevision as exc:
        error = ErrorPayload(
            error_code="STALE_ACTIVE_VERSION",
            message=str(exc),
            allowed_actions=["curriculum activate --expected-active <current>"],
            next_action="re-read the active version, then curriculum activate",
        )
        _emit(failure_envelope("curriculum.activate", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except KernelError as exc:
        error = ErrorPayload(
            error_code="CURRICULUM_VERSION_CONFLICT",
            message=str(exc),
            allowed_actions=["curriculum activate --version <new-id>"],
            next_action="curriculum activate --version <new-id>",
        )
        _emit(failure_envelope("curriculum.activate", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)


def _require_key(command: str, corr: str, fmt: str, idempotency_key: str | None) -> None:
    if fmt == "json" and not idempotency_key:
        spoken = command.replace(".", " ")
        error = ErrorPayload(
            error_code="MISSING_IDEMPOTENCY_KEY",
            message=f"`trainer {spoken}` mutates state: --idempotency-key is required with json.",
            allowed_actions=[f"{spoken} --idempotency-key <key>"],
            next_action=f"{spoken} --idempotency-key <key>",
        )
        _emit(failure_envelope(command, corr, error), [], fmt, ExitCode.USAGE)


@session_app.command("start")
def session_start(
    provider: Annotated[str, typer.Option("--provider", help="Tutor provider attaching to the session.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    mode: Annotated[str, typer.Option("--mode", help="Session mode.")] = "balanced",
    duration_minutes: Annotated[
        int | None,
        typer.Option("--duration-minutes", help="Session budget; defaults to the control policy."),
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Open a session: pins active policies into the manifest and composes the plan."""
    corr = _correlation(correlation_id)
    _require_key("session.start", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    request_hash = payload_hash(
        {
            "command": "session.start",
            "provider": provider,
            "mode": mode,
            "duration_minutes": duration_minutes,
            "root": str(layout.root),
        }
    )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope("session.start", corr, {**dict(prior.value), "cached": True}),
                        ["session (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            manifest = start_session(
                storage.store,
                registry,
                SystemClock(),
                SystemRandom(),
                provider=provider,
                mode=mode,
                duration_minutes=duration_minutes,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, manifest)
        data = {**manifest, "cached": False}
        human = [
            f"session {manifest['session_id']} started ({mode}, provider {provider})",
            f"  pinned: {manifest['pinned_versions']}",
        ]
        _emit(success_envelope("session.start", corr, data), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["session start --idempotency-key <fresh-key>"],
            next_action="session start --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("session.start", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (SessionPrecondition, BudgetTooSmall, NoCandidates) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session abandon", "curriculum activate", "session status"],
            next_action="session status",
        )
        _emit(
            failure_envelope("session.start", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


def _close_command(
    command: str,
    closer: Any,
    fmt: str,
    root: Path,
    session: str | None,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> None:
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            session_id = session if session is not None else active_session_id(storage.store)
            if session_id is None or get_session(storage.store, session_id) is None:
                error = ErrorPayload(
                    error_code="SESSION_NOT_FOUND",
                    message="no such session (and no active session to default to).",
                    allowed_actions=["session status", "session start"],
                    next_action="session status",
                )
                _emit(failure_envelope(command, corr, error), ["error: no session"], fmt, ExitCode.NOT_FOUND)
            request_hash = payload_hash({"command": command, "session": session_id, "root": str(layout.root)})
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope(command, corr, {**dict(prior.value), "cached": True}),
                        [f"{command} (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            event = closer(storage.store, SystemClock(), SystemRandom(), session_id)
            result = {"session_id": session_id, "event_id": event.id, "status_event": event.type}
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope(command, corr, {**result, "cached": False}),
            [f"session {session_id}: {event.type}"],
            fmt,
            ExitCode.OK,
        )
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=[f"{command.replace('.', ' ')} --idempotency-key <fresh-key>"],
            next_action=f"{command.replace('.', ' ')} --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except SessionPrecondition as exc:
        error = ErrorPayload(
            error_code="SESSION_PRECONDITION",
            message=str(exc),
            allowed_actions=["session status", "session abandon"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@session_app.command("finish")
def session_finish(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: Annotated[
        str | None, typer.Option("--session", help="Session id; defaults to the active session.")
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Finish the session (the only way to complete one). Requires IN_PROGRESS."""
    _close_command("session.finish", finish_session, fmt, root, session, idempotency_key, correlation_id)


@session_app.command("abandon")
def session_abandon(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: Annotated[
        str | None, typer.Option("--session", help="Session id; defaults to the active session.")
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Explicitly abandon the session; everything already recorded is kept."""
    _close_command("session.abandon", abandon_session, fmt, root, session, idempotency_key, correlation_id)


@session_app.command("status")
def session_status(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Show the active session, if any. Read-only."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(
            failure_envelope("session.status", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    with open_storage(layout) as storage:
        session_id = active_session_id(storage.store)
        if session_id is None:
            data: dict[str, Any] = {"active": None}
            human = ["no active session"]
        else:
            found = get_session(storage.store, session_id)
            state = found[0] if found else {}
            notes = list_notes(storage.store, session_id)
            data = {
                "active": session_id,
                "status": state.get("status"),
                "manifest": state.get("manifest"),
                # Untrusted agent notes ride along as their own block, never
                # mixed into state (evidence 3 [R-3], P0-5).
                "notes": notes,
            }
            human = [f"active session: {session_id} [{state.get('status')}]"] + [
                f"  note ({entry.get('author_provider')}): {entry.get('text')}" for entry in notes
            ]
    _emit(success_envelope("session.status", corr, data), human, fmt, ExitCode.OK)


_SessionOpt = Annotated[
    str | None, typer.Option("--session", help="Session id; defaults to the active session.")
]
_PlanVersionOpt = Annotated[
    int, typer.Option("--expected-plan-version", help="CAS token from peek/start (control 4.2).")
]


def _resolve_session(command: str, corr: str, fmt: str, storage: Any, session: str | None) -> str:
    session_id = session if session is not None else active_session_id(storage.store)
    if session_id is None or get_session(storage.store, session_id) is None:
        error = ErrorPayload(
            error_code="SESSION_NOT_FOUND",
            message="no such session (and no active session to default to).",
            allowed_actions=["session status", "session start"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), ["error: no session"], fmt, ExitCode.NOT_FOUND)
    return session_id


@session_app.command("peek")
def session_peek(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Show the next step and the current plan_version. Read-only: nothing is
    marked presented, nothing is published (control 4.2)."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session("session.peek", corr, fmt, storage, session)
            data = peek_step(storage.store, session_id)
        step = data.get("step")
        human = [
            f"session {session_id}: plan v{data['plan_version']} "
            f"(revision {data['composition_revision']}), {data['steps_remaining']} steps remaining"
        ]
        if step is not None:
            human.append(
                f"  next: {step['step_id']} [{step['bucket']}/{step['step_type']}] "
                f"{step.get('target_ref') or 'free conversation'}"
            )
        _emit(success_envelope("session.peek", corr, data), human, fmt, ExitCode.OK)
    except SessionPrecondition as exc:
        error = ErrorPayload(
            error_code="SESSION_PRECONDITION",
            message=str(exc),
            allowed_actions=["session status", "session start"],
            next_action="session status",
        )
        _emit(
            failure_envelope("session.peek", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


def _plan_mutation(
    command: str,
    runner: Any,
    fmt: str,
    root: Path,
    session: str | None,
    expected_plan_version: int,
    idempotency_key: str | None,
    correlation_id: str | None,
    describe: Any,
) -> None:
    """Shared shape of ``session next`` / ``session replan``: idempotent replay
    is answered before the CAS check (control 4.2), a CAS miss is a CONFLICT
    carrying the current version, an exhausted plan is a precondition."""
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    spoken = command.replace(".", " ")
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session(command, corr, fmt, storage, session)
            request_hash = payload_hash(
                {
                    "command": command,
                    "session": session_id,
                    "expected_plan_version": expected_plan_version,
                    "root": str(layout.root),
                }
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope(command, corr, {**dict(prior.value), "cached": True}),
                        [f"{spoken} (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = runner(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                SystemClock(),
                SystemRandom(),
                session_id,
                expected_plan_version=expected_plan_version,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope(command, corr, {**result, "cached": False}),
            describe(result),
            fmt,
            ExitCode.OK,
        )
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=[f"{spoken} --idempotency-key <fresh-key>"],
            next_action=f"{spoken} --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except PlanVersionConflict as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session peek", f"{spoken} --expected-plan-version <current>"],
            next_action="session peek",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (SessionPrecondition, NoCandidates, BudgetTooSmall) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session replan", "session finish", "session status"],
            next_action="session replan" if command == "session.next" else "session finish",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@session_app.command("next")
def session_next(
    expected_plan_version: _PlanVersionOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Claim the next step (mutating, CAS): marks it presented, moves its cost
    planned -> presented, bumps plan_version and publishes STEP_PRESENTED."""

    def describe(result: dict[str, Any]) -> list[str]:
        step = result["step"]
        return [
            f"step {step['step_id']} [{step['bucket']}/{step['step_type']}] "
            f"{step.get('target_ref') or 'free conversation'}",
            f"  plan version now {result['plan_version']}",
        ]

    _plan_mutation(
        "session.next",
        next_step,
        fmt,
        root,
        session,
        expected_plan_version,
        idempotency_key,
        correlation_id,
        describe,
    )


@session_app.command("replan")
def session_replan(
    expected_plan_version: _PlanVersionOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Recompose the unpresented remainder (mutating, CAS): a new composition
    revision over the remaining budget; presented steps are kept."""

    def describe(result: dict[str, Any]) -> list[str]:
        return [
            f"replanned: revision {result['composition_revision']}, "
            f"plan version {result['plan_version']}, {result['steps_planned']} steps ahead"
        ]

    _plan_mutation(
        "session.replan",
        replan_session,
        fmt,
        root,
        session,
        expected_plan_version,
        idempotency_key,
        correlation_id,
        describe,
    )


def _read_input_json(command: str, corr: str, fmt: str, path: Path) -> dict[str, Any]:
    """Parse the ``--input FILE`` JSON document or refuse with INVALID_INPUT."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("top-level value must be a JSON object")
        return loaded
    except (OSError, ValueError) as exc:
        error = ErrorPayload(
            error_code="INVALID_INPUT",
            message=f"cannot read {path}: {exc}",
            allowed_actions=[f"{command.replace('.', ' ')} --input <json-file>"],
            next_action="fix the input file and retry",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.INVALID_INPUT)


_InputOpt = Annotated[Path, typer.Option("--input", help="JSON file with the payload.")]
_StepOpt = Annotated[str, typer.Option("--step", help="Step id from `session next`.")]


@exercise_app.command("rendered")
def exercise_rendered(
    step: _StepOpt,
    input_file: _InputOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Persist the rendered-exercise snapshot BEFORE the learner sees it
    (P.3 PD-1 A). Returns the engine-issued exercise_instance_id."""
    corr = _correlation(correlation_id)
    _require_key("exercise.rendered", corr, fmt, idempotency_key)
    exercise = _read_input_json("exercise.rendered", corr, fmt, input_file)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session("exercise.rendered", corr, fmt, storage, session)
            request_hash = payload_hash(
                {"command": "exercise.rendered", "session": session_id, "step": step, "exercise": exercise}
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope("exercise.rendered", corr, {**dict(prior.value), "cached": True}),
                        ["exercise rendered (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = record_rendered_exercise(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                SystemClock(),
                SystemRandom(),
                session_id,
                step_id=step,
                exercise=exercise,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope("exercise.rendered", corr, {**result, "cached": False}),
            [
                f"exercise {result['exercise_instance_id']} rendered for step {step}",
                f"  content hash: {result['content_hash']}",
            ],
            fmt,
            ExitCode.OK,
        )
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["exercise rendered --idempotency-key <fresh-key>"],
            next_action="exercise rendered --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("exercise.rendered", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except SessionPrecondition as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session peek", "session next", "session status"],
            next_action="session peek",
        )
        _emit(
            failure_envelope("exercise.rendered", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


@attempt_app.command("record")
def attempt_record(
    step: _StepOpt,
    input_file: _InputOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    exercise_instance: Annotated[
        str | None,
        typer.Option("--exercise-instance", help="EXERCISE_RENDERED instance id (structured tasks)."),
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="Untrusted agent note; never evidence.")] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Record a learner attempt against a delivered step. The input file
    carries {raw_answer, observations?, hints?}; target/dimension/mode/origin
    are derived by the engine from the step, never taken from the client."""
    corr = _correlation(correlation_id)
    _require_key("attempt.record", corr, fmt, idempotency_key)
    payload = _read_input_json("attempt.record", corr, fmt, input_file)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session("attempt.record", corr, fmt, storage, session)
            request_hash = payload_hash(
                {
                    "command": "attempt.record",
                    "session": session_id,
                    "step": step,
                    "exercise_instance": exercise_instance,
                    "input": payload,
                }
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope("attempt.record", corr, {**dict(prior.value), "cached": True}),
                        ["attempt (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = record_attempt(
                storage.store,
                SystemClock(),
                SystemRandom(),
                session_id,
                step_id=step,
                raw_answer=str(payload.get("raw_answer", "")),
                exercise_instance_id=exercise_instance,
                observations=list(payload.get("observations", [])),
                hints=int(payload.get("hints", 0)),
                note=note,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        assessment = result.get("assessment")
        human = [f"attempt {result['attempt_id']} {result['status']}"]
        if assessment is not None:
            human.append(f"  objective check: {'correct' if assessment['correct'] else 'incorrect'}")
        _emit(success_envelope("attempt.record", corr, {**result, "cached": False}), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["attempt record --idempotency-key <fresh-key>"],
            next_action="attempt record --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("attempt.record", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (EvidencePrecondition, SessionPrecondition) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session peek", "exercise rendered", "session status"],
            next_action="session peek",
        )
        _emit(
            failure_envelope("attempt.record", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


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
