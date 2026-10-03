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

import hashlib
import json
import platform
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from english_trainer.adapters.compare import DEFAULT_FIXTURES
from english_trainer.adapters.compare import compare as adapters_compare
from english_trainer.adapters.errors import AdapterError
from english_trainer.adapters.ingress import capture_user_turn, report_skill
from english_trainer.adapters.skills import sync as adapters_sync
from english_trainer.adapters.skills import validate as adapters_validate
from english_trainer.assessments.forms import UnknownForm
from english_trainer.assessments.placement import (
    PlacementPrecondition,
    abandon_placement,
    active_placement_id,
    answer_placement,
    decline_placement,
    get_placement,
    resume_placement,
    start_placement,
    submit_placement,
)
from english_trainer.assessments.policy import ASSESSMENTS_KIND
from english_trainer.assessments.policy import require_valid as require_valid_assessments
from english_trainer.assessments.self_assessment import SelfAssessmentInvalid
from english_trainer.audit import correlation_view, obligations, session_view, target_history
from english_trainer.audit.policy import OBLIGATIONS_KIND
from english_trainer.audit.policy import require_valid as require_valid_obligations
from english_trainer.cli.envelope import (
    ErrorPayload,
    ExitCode,
    failure_envelope,
    print_human,
    print_json_envelope,
    success_envelope,
)
from english_trainer.cli.registry import command_registry
from english_trainer.cli.telemetry import (
    command_name as telemetry_command_name,
)
from english_trainer.cli.telemetry import (
    database_path as telemetry_database_path,
)
from english_trainer.cli.telemetry import (
    record_invocation,
    record_terminal,
)
from english_trainer.cli.telemetry import (
    session_hint as telemetry_session_hint,
)
from english_trainer.control.availability import availability_get, availability_set
from english_trainer.control.errors import (
    AvailabilityInvalid,
    BudgetTooSmall,
    ControlPolicyInvalid,
    NoCandidates,
)
from english_trainer.control.metrics import metrics as policy_metrics
from english_trainer.control.policy import CONTROL_KIND, require_valid
from english_trainer.control.trace import DecisionTraceUnavailable, explain
from english_trainer.control.tunables import (
    CalibrationPrecondition,
    TunableCatalogueInvalid,
    confirm_calibration,
    list_calibrations,
    list_tunables,
    propose_calibration,
)
from english_trainer.curriculum.loader import load_policies, load_program, rubric_profile_refs
from english_trainer.curriculum.service import (
    activate_version,
    get_topic,
    lexicon_query,
    permanent_interleave_targets,
    register_version,
    texts_for_topic,
)
from english_trainer.curriculum.validate import validate_program
from english_trainer.evidence.attempts import EvidencePrecondition
from english_trainer.evidence.policy import EVIDENCE_KIND
from english_trainer.evidence.policy import require_valid as require_valid_evidence
from english_trainer.evidence.rubric import RUBRIC_KIND, RubricPolicyInvalid
from english_trainer.evidence.rubric import require_valid as require_valid_rubric
from english_trainer.kernel.check import database_check
from english_trainer.kernel.clock import SystemClock, SystemRandom
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import (
    IdempotencyConflict,
    KernelError,
    NoActivePolicy,
    SessionRevisionConflict,
    StaleRevision,
)
from english_trainer.kernel.export import JsonlExporter
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import SCHEMA_VERSION, EventStore, connect, migrate
from english_trainer.kernel.uow import CachedResult, UnitOfWork
from english_trainer.learner.errors import LexiconEntryInvalid, LinkedItemNotFound, PreferencesInvalid
from english_trainer.learner.lexicon import (
    build_encounter_events,
    find_encounter_entry,
    lexicon_add,
    lexicon_encounter,
    lexicon_list,
    personal_lexicon_summary,
)
from english_trainer.learner.preferences import preferences_get, preferences_set
from english_trainer.lessons.policy import LESSONS_KIND
from english_trainer.lessons.policy import require_valid as require_valid_lessons
from english_trainer.lessons.report import ReportRejected, check_report, commit_report
from english_trainer.lessons.resume import resume_session
from english_trainer.lessons.sessions import (
    SessionPrecondition,
    abandon_session,
    active_session_id,
    get_plan,
    get_session,
    propose_session,
    start_session,
)
from english_trainer.memory.engine import check as memory_check
from english_trainer.memory.engine import emit_projection_updated, rebuild, render
from english_trainer.scheduler.engine import due_backlog
from english_trainer.scheduler.policy import SCHEDULER_KIND, SchedulerPolicyInvalid
from english_trainer.scheduler.policy import require_valid as require_valid_scheduler
from english_trainer.scoring.aggregates import (
    learning_score,
    measured_working_level,
    placement_levels,
    placement_writing_level,
    provisional_working_estimate,
    self_reported_levels,
    working_levels,
    xp_ledger,
)
from english_trainer.scoring.automaticity import (
    AUTOMATICITY_KIND,
    AutomaticityPolicyInvalid,
    require_valid_automaticity,
)
from english_trainer.scoring.compliance import tutor_compliance
from english_trainer.scoring.engine import fold_scores
from english_trainer.scoring.policy import SCORING_KIND, ScoringPolicyInvalid
from english_trainer.scoring.policy import require_valid as require_valid_scoring
from english_trainer.scoring.replay import replay_scores
from english_trainer.scoring.transitions import backfill_state_transitions, transition_coverage
from english_trainer.storage.layout import StorageLayout, open_storage, resolve_layout
from english_trainer.storage.snapshot import create_snapshot

app = typer.Typer(add_completion=False, help="English Memory Trainer engine CLI.")
database_app = typer.Typer(add_completion=False, help="Storage integrity commands.")
app.add_typer(database_app, name="database")
snapshot_app = typer.Typer(add_completion=False, help="Point-in-time snapshots of the local state.")
app.add_typer(snapshot_app, name="snapshot")
curriculum_app = typer.Typer(add_completion=False, help="The authored program: validate, inspect, activate.")
app.add_typer(curriculum_app, name="curriculum")
session_app = typer.Typer(
    add_completion=False, help="Learning sessions: propose, start, resume, check-report, report, abandon."
)
app.add_typer(session_app, name="session")
scoring_app = typer.Typer(add_completion=False, help="Deterministic scores from the event log.")
app.add_typer(scoring_app, name="scoring")
scoring_transitions_app = typer.Typer(add_completion=False, help="Canonical score-state facts.")
scoring_app.add_typer(scoring_transitions_app, name="transitions")
review_app = typer.Typer(add_completion=False, help="Review scheduling: what is due, and when.")
app.add_typer(review_app, name="review")
memory_app = typer.Typer(add_completion=False, help="The Obsidian projection (generated zone).")
app.add_typer(memory_app, name="memory")
skills_app = typer.Typer(add_completion=False, help="Agent Skills: sync canon, validate structure/drift.")
app.add_typer(skills_app, name="skills")
adapters_app = typer.Typer(add_completion=False, help="Adapter parity: observable-effect comparison.")
app.add_typer(adapters_app, name="adapters")
placement_app = typer.Typer(
    add_completion=False, help="Placement diagnostics: start, answer, resume, submit."
)
app.add_typer(placement_app, name="placement")
availability_app = typer.Typer(add_completion=False, help="Declared and observed learning rhythm.")
app.add_typer(availability_app, name="availability")
tunables_app = typer.Typer(add_completion=False, help="Versioned calibration catalogue.")
app.add_typer(tunables_app, name="tunables")
calibration_app = typer.Typer(add_completion=False, help="Propose and confirm policy calibration.")
app.add_typer(calibration_app, name="calibration")
audit_app = typer.Typer(add_completion=False, help="Read-only views over authoritative facts.")
app.add_typer(audit_app, name="audit")
lexicon_app = typer.Typer(add_completion=False, help="The learner's personal lexicon (layer 3).")
app.add_typer(lexicon_app, name="lexicon")
learner_app = typer.Typer(add_completion=False, help="What belongs to the learner, not their knowledge.")
app.add_typer(learner_app, name="learner")
learner_preferences_app = typer.Typer(add_completion=False, help="The form a session takes (learner 4a).")
learner_app.add_typer(learner_preferences_app, name="preferences")

_RUN_CORRELATION: ContextVar[str | None] = ContextVar("cli_run_correlation", default=None)
_LAST_ENVELOPE: ContextVar[dict[str, Any] | None] = ContextVar("cli_last_envelope", default=None)

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
_AgentSkillsOpt = Annotated[
    Path, typer.Option("--agent-skills", help="Canonical Agent Skills directory (adapters).")
]


def _paths(root: Path, db: Path | None, export: Path | None) -> tuple[StorageLayout, Path, Path]:
    """Resolve effective paths: explicit options win, the layout fills the rest."""
    layout = resolve_layout(root)
    return layout, db if db is not None else layout.db, export if export is not None else layout.export


def _correlation(provided: str | None) -> str:
    # The CLI edge is the one layer allowed to touch the system clock/random
    # (foundation 8): the id must exist before any engine call it correlates.
    return provided if provided else _RUN_CORRELATION.get() or new_ulid(SystemClock(), SystemRandom())


def _emit(envelope: dict[str, Any], human: list[str], fmt: str, code: ExitCode) -> NoReturn:
    _LAST_ENVELOPE.set(envelope)
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
    report = validate_program(program, rubric_refs=rubric_profile_refs(curriculum))
    forms = [str(form.get("form_version")) for form in program.get("placement_forms") or []]
    if report.ok:
        data = {
            "errors": [],
            "warnings": report.warnings,
            "topics": len(program["topics"]),
            "lexicon": len(program["lexicon"]),
            "placement_forms": forms,
        }
        human = [
            f"curriculum valid: {len(program['topics'])} topics, {len(program['lexicon'])} lexical items"
            + (f", {len(forms)} placement form(s)" if forms else ""),
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


@curriculum_app.command("texts")
def curriculum_texts(
    topic: Annotated[str, typer.Option("--topic", help="Topic id that owns the texts.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    domain: Annotated[
        str | None, typer.Option("--domain", help="Filter by domain: work | everyday | academic.")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Reconstruction texts of the ACTIVE curriculum version for a topic.

    Read-only, and deliberately served from the active snapshot rather than the
    authored directory: what the tutor reconstructs must be the same text the
    engine can resolve later from a pinned version (curriculum 2d).
    """
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
            failure_envelope("curriculum.texts", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            version, program = registry.resolve_active("curriculum")
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("curriculum.texts", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )
    texts = texts_for_topic(program, topic)
    if domain is not None:
        texts = [text for text in texts if str(text.get("domain")) == domain]
    data = {"version": version, "topic": topic, "domain": domain, "count": len(texts), "texts": texts}
    human = [f"{len(texts)} reconstruction text(s) for {topic} [{version}]"] + [
        f"  {text.get('id')} [{text.get('cefr')}/{text.get('domain')}] {text.get('title')}" for text in texts
    ]
    _emit(success_envelope("curriculum.texts", corr, data), human, fmt, ExitCode.OK)


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
    report = validate_program(program, rubric_refs=rubric_profile_refs(curriculum))
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
                elif kind == SCORING_KIND:
                    require_valid_scoring(payload)
                elif kind == AUTOMATICITY_KIND:
                    # The automaticity axis is its own policy kind (scoring 3d):
                    # registered and pinned beside scoring@1, overriding nothing
                    # in it and overridden by nothing in it.
                    require_valid_automaticity(payload)
                elif kind == SCHEDULER_KIND:
                    require_valid_scheduler(payload)
                elif kind == RUBRIC_KIND:
                    require_valid_rubric(payload)
                elif kind == ASSESSMENTS_KIND:
                    require_valid_assessments(payload)
                elif kind == EVIDENCE_KIND:
                    require_valid_evidence(payload)
                elif kind == LESSONS_KIND:
                    require_valid_lessons(payload)
                elif kind == OBLIGATIONS_KIND:
                    require_valid_obligations(payload)
                registry.register(kind, policy_version, payload)
                registry.activate(kind, policy_version)
            if any(kind == "tunables" for kind, _, _ in policies):
                # Validate only after every owner policy has been activated;
                # completeness and current-value-in-range are bidirectional.
                list_tunables(registry)
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
    except (
        ControlPolicyInvalid,
        ScoringPolicyInvalid,
        AutomaticityPolicyInvalid,
        SchedulerPolicyInvalid,
        RubricPolicyInvalid,
    ) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum validate"],
            next_action="fix the policy file under curriculum/policies/, then curriculum activate",
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
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Learner-facing lesson profile; separate from internal --mode."),
    ] = None,
    topic: Annotated[
        str | None, typer.Option("--topic", help="Learner-selected central curriculum target.")
    ] = None,
    theme: Annotated[
        str | None, typer.Option("--theme", help="Learner-selected communicative theme.")
    ] = None,
    agent_skills: _AgentSkillsOpt = Path("agent-skills"),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Open a session: pin the active policies, compose the plan, return the brief.

    The explicit ``--profile``/``--topic``/``--duration-minutes``/``--theme``
    are the learner's consent [PD-2026-09-23]; the response carries the
    ``lesson_brief@1`` the tutor runs the whole lesson from."""
    corr = _correlation(correlation_id)
    _require_key("session.start", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    request_hash = payload_hash(
        {
            "command": "session.start",
            "provider": provider,
            "mode": mode,
            "duration_minutes": duration_minutes,
            "profile": profile,
            "topic": topic,
            "theme": theme,
            "agent_skills": str(agent_skills),
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
                lesson_profile=profile,
                target_ref=topic,
                theme=theme,
                agent_skills_dir=agent_skills,
                # The edge owns the curriculum layer, so it hands lessons the
                # classifier for the permanent interleaved tier (scheduler 3a);
                # lessons applies it to the snapshot it pinned.
                permanent_interleave=permanent_interleave_targets,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, manifest)
        data = {**manifest, "cached": False}
        human = [
            f"session {manifest['session_id']} started ({mode}, provider {provider})",
            f"  pinned: {manifest['pinned_versions']}",
        ]
        if manifest.get("lesson_arc"):
            arc = manifest["lesson_arc"]
            human.insert(1, f"  lesson: {arc['title']} [{arc['profile']}]")
        _emit(success_envelope("session.start", corr, data), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["session start --idempotency-key <fresh-key>"],
            next_action="session start --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("session.start", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (SessionPrecondition, BudgetTooSmall, NoCandidates, ValueError) as exc:
        error = ErrorPayload(
            error_code=getattr(exc, "code", "INVALID_LESSON_PROPOSAL"),
            message=str(exc),
            allowed_actions=["session abandon", "curriculum activate", "session propose"],
            next_action="session propose",
        )
        _emit(
            failure_envelope("session.start", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


@session_app.command("propose")
def session_propose(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    duration_minutes: Annotated[
        int | None,
        typer.Option("--duration-minutes", help="Requested duration; defaults to availability policy."),
    ] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Learner-facing lesson profile.")] = None,
    topic: Annotated[str | None, typer.Option("--topic", help="Requested central curriculum target.")] = None,
    theme: Annotated[str | None, typer.Option("--theme", help="Requested communicative theme.")] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Preview the lesson title, reason, agenda, and language envelope.

    Read-only: it does not open a session or reserve learner state.
    """
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
            failure_envelope("session.propose", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    try:
        with open_storage(layout) as storage:
            proposal = propose_session(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                SystemClock(),
                duration_minutes=duration_minutes,
                lesson_profile=profile,
                target_ref=topic,
                theme=theme,
            )
        central = proposal.get("central_topic") or {}
        human = [
            f"{proposal['title']} ({proposal['duration_minutes']} min, {proposal['duration_class']})",
            f"  why: {proposal['reason']}",
        ]
        if central:
            human.append(f"  central topic: {central.get('title')} [{central.get('newness')}]")
        human.append("  agenda: " + " → ".join(item["name"] for item in proposal["agenda"]))
        if proposal["requires_confirmation"]:
            human.append("  confirm this system recommendation before starting")
        _emit(success_envelope("session.propose", corr, proposal), human, fmt, ExitCode.OK)
    except (SessionPrecondition, BudgetTooSmall, ValueError) as exc:
        error = ErrorPayload(
            error_code=getattr(exc, "code", "INVALID_LESSON_PROPOSAL"),
            message=str(exc),
            allowed_actions=["curriculum activate", "session propose --profile <profile>"],
            next_action="session propose",
        )
        _emit(
            failure_envelope("session.propose", corr, error),
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
    expected_session_revision: int,
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
            request_hash = payload_hash(
                {
                    "command": command,
                    "session": session_id,
                    "expected_session_revision": expected_session_revision,
                    "root": str(layout.root),
                }
            )
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
            event = closer(
                storage.store,
                SystemClock(),
                SystemRandom(),
                session_id,
                expected_session_revision=expected_session_revision,
            )
            result = {
                "session_id": session_id,
                "event_id": event.id,
                "status_event": event.type,
                "session_revision": event.payload["session_revision"],
            }
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
    except SessionRevisionConflict as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status"],
            next_action="session status",
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


@session_app.command("abandon")
def session_abandon(
    expected_session_revision: Annotated[
        int, typer.Option("--expected-session-revision", help="CAS token from status/resume.")
    ],
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
    _close_command(
        "session.abandon",
        abandon_session,
        fmt,
        root,
        session,
        expected_session_revision,
        idempotency_key,
        correlation_id,
    )


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
            revision = found[1] if found else None
            _, plan_state, _ = get_plan(storage.store, session_id)
            data = {
                "active": session_id,
                "status": state.get("status"),
                "session_revision": revision,
                "manifest": state.get("manifest"),
                "lesson_arc": plan_state.get("lesson_arc") or (state.get("manifest") or {}).get("lesson_arc"),
            }
            human = [f"active session: {session_id} [{state.get('status')}]"]
    _emit(success_envelope("session.status", corr, data), human, fmt, ExitCode.OK)


_SessionOpt = Annotated[
    str | None, typer.Option("--session", help="Session id; defaults to the active session.")
]
_SessionRevisionOpt = Annotated[
    int, typer.Option("--expected-session-revision", help="CAS token from status/resume.")
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


@session_app.command("resume")
def session_resume(
    provider: Annotated[str, typer.Option("--provider", help="Tutor provider attaching to the session.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    agent_skills: _AgentSkillsOpt = Path("agent-skills"),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Resume a session: its state + the rebuilt lesson brief, attaching
    ``provider`` (AGENT_ATTACHED, lessons 4b/5). There is no separate
    ``session attach``: changing tutor mid-stream is a cold resume."""
    corr = _correlation(correlation_id)
    _require_key("session.resume", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session("session.resume", corr, fmt, storage, session)
            request_hash = payload_hash(
                {
                    "command": "session.resume",
                    "session": session_id,
                    "provider": provider,
                    "agent_skills": str(agent_skills),
                    "root": str(layout.root),
                }
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope("session.resume", corr, {**dict(prior.value), "cached": True}),
                        ["session resume (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = resume_session(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                SystemClock(),
                SystemRandom(),
                session_id,
                provider=provider,
                agent_skills_dir=agent_skills,
                permanent_interleave=permanent_interleave_targets,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        brief = result["brief"]
        human = [
            f"session {session_id} resumed by {provider} [{result['status']}]",
            f"  lesson: {(brief.get('lesson') or {}).get('title')} · "
            f"reviews due: {len(brief.get('reviews_due') or [])}",
        ]
        _emit(success_envelope("session.resume", corr, {**result, "cached": False}), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["session resume --idempotency-key <fresh-key>"],
            next_action="session resume --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("session.resume", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except SessionPrecondition as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session start"],
            next_action="session status",
        )
        _emit(
            failure_envelope("session.resume", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


_ReportFileOpt = Annotated[Path, typer.Option("--file", help="The lesson_report@1 JSON document.")]


def _read_report(command: str, corr: str, fmt: str, path: Path) -> Any:
    """Parse the report file; any JSON value is passed on, the check validates it."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error = ErrorPayload(
            error_code="INVALID_INPUT",
            message=f"cannot read {path}: {exc}",
            allowed_actions=[f"{command.replace('.', ' ')} --file <report.json>"],
            next_action="fix the report file and retry",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.INVALID_INPUT)


def _report_session(command: str, corr: str, fmt: str, storage: Any, session: str | None, report: Any) -> str:
    """``--session``, else the active session, else the session the report names.

    The last fallback serves a retried ``session report`` after a commit that
    already finished the session (no active pointer any more): the same key
    and document then return the cached result instead of SESSION_NOT_FOUND.
    """
    if session is None and active_session_id(storage.store) is None and isinstance(report, dict):
        named = report.get("session_id")
        if isinstance(named, str) and get_session(storage.store, named) is not None:
            return named
    return _resolve_session(command, corr, fmt, storage, session)


def _check_lines(check: dict[str, Any]) -> list[str]:
    summary = check.get("summary") or {}
    lines = [f"report {'valid' if check.get('valid') else 'NOT valid'}: {summary}"]
    lines += [f"  error {error['code']}: {error['message']}" for error in check.get("errors") or []]
    for row in check.get("items") or []:
        if row.get("status") == "rejected":
            codes = ", ".join(reason["code"] for reason in row.get("reasons") or [])
            lines.append(f"  item {row.get('item_id')}: rejected ({codes})")
    lines += [f"  warning {warning.get('code')}" for warning in check.get("warnings") or []]
    return lines


@session_app.command("check-report")
def session_check_report(
    report_file: _ReportFileOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Validate a lesson report WITHOUT writing anything (read-only).

    Per item: accepted/rejected with stable reason codes and the effects a
    commit would have (score, contributing, review outcome); plus the reviews
    left unaddressed, the advisory requirements and the warnings. An invalid
    report is a successful check (exit 0) with ``valid: false``."""
    command = "session.check-report"
    corr = _correlation(correlation_id)
    report = _read_report(command, corr, fmt, report_file)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope(command, corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    try:
        with open_storage(layout) as storage:
            session_id = _report_session(command, corr, fmt, storage, session, report)
            check = check_report(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                session_id,
                report,
                encounter_lookup=find_encounter_entry,
                permanent_interleave=permanent_interleave_targets,
            )
        _emit(success_envelope(command, corr, check), _check_lines(check), fmt, ExitCode.OK)
    except SessionPrecondition as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session start"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@session_app.command("report")
def session_report(
    report_file: _ReportFileOpt,
    provider: Annotated[str, typer.Option("--provider", help="Tutor provider filing the report.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Commit the lesson report and finish the session in ONE transaction.

    Any rejected item refuses the whole report and writes nothing
    (REPORT_REJECTED, exit 6, the full check in ``error.check``). The same key
    with the same report returns the cached result; with a different report it
    is an IDEMPOTENCY_CONFLICT. No session-revision token is asked for."""
    command = "session.report"
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    report = _read_report(command, corr, fmt, report_file)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope(command, corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    # Text mode may omit the key (cli 4.3); the commit is still idempotent, by
    # a key derived from the document itself.
    key = (
        idempotency_key
        or "session.report:"
        + hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    )
    try:
        with open_storage(layout) as storage:
            session_id = _report_session(command, corr, fmt, storage, session, report)
            result = commit_report(
                storage.store,
                PolicyRegistry(storage._conn, SystemClock()),
                SystemClock(),
                SystemRandom(),
                session_id,
                report,
                provider=provider,
                idempotency_key=key,
                encounter_builder=build_encounter_events,
                encounter_lookup=find_encounter_entry,
                permanent_interleave=permanent_interleave_targets,
            )
        human = [
            f"session {session_id}: report committed{' (cached result)' if result.get('cached') else ''}, "
            "session finished"
        ]
        _emit(success_envelope(command, corr, result), human, fmt, ExitCode.OK)
    except ReportRejected as exc:
        error = ErrorPayload(
            error_code="REPORT_REJECTED",
            message=str(exc),
            allowed_actions=["session check-report --file <report.json>", "session abandon"],
            next_action="session check-report --file <report.json>",
        )
        envelope = failure_envelope(command, corr, error)
        envelope["error"]["check"] = exc.check
        _emit(envelope, [f"error: {exc}", *_check_lines(exc.check)], fmt, ExitCode.PRECONDITION_FAILED)
    except (IdempotencyConflict, StaleRevision) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session report --idempotency-key <fresh-key>"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (SessionPrecondition, EvidencePrecondition) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session abandon"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


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


@scoring_app.command("replay")
def scoring_replay(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Recompute all scores from the event log under the pinned policy and
    verify the fold reproduces byte-identically. Read-only: scores ARE the fold."""
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
            failure_envelope("scoring.replay", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    try:
        with open_storage(layout) as storage:
            report = replay_scores(storage.store, PolicyRegistry(storage._conn, SystemClock()))
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("scoring.replay", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )
    if not report["consistent"]:
        error = ErrorPayload(
            error_code="REPLAY_DIVERGED",
            message="two folds over the same events produced different snapshots -- determinism is broken.",
            allowed_actions=["doctor", "database check"],
            next_action="doctor",
        )
        _emit(
            failure_envelope("scoring.replay", corr, error),
            ["replay DIVERGED"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )
    human = [
        f"scoring replay: consistent under {report['policy_version']}",
        f"  events: {report['events']}, targets: {report['targets']}",
        f"  snapshot hash: {report['snapshot_hash']}",
    ]
    _emit(success_envelope("scoring.replay", corr, report), human, fmt, ExitCode.OK)


@scoring_transitions_app.command("backfill")
def scoring_transitions_backfill(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Append missing canonical state-transition facts in source order."""
    command = "scoring.transitions.backfill"
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope(command, corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    request_hash = payload_hash({"command": command, "root": str(layout.root)})
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            with UnitOfWork(storage.store, SystemClock()) as uow:
                if idempotency_key:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                    if isinstance(prior, CachedResult):
                        _emit(
                            success_envelope(command, corr, {**dict(prior.value), "cached": True}),
                            ["score transitions backfill (cached result)"],
                            fmt,
                            ExitCode.OK,
                        )
                backfill_result = backfill_state_transitions(storage.store, registry, uow)
                if idempotency_key:
                    uow.record_result(idempotency_key, request_hash, dict(backfill_result))
            result: dict[str, object] = {
                **backfill_result,
                "coverage": transition_coverage(storage.store),
            }
        _emit(
            success_envelope(command, corr, {**result, "cached": False}),
            [f"state transitions: {result['created']} created / {result['scanned']} sources"],
            fmt,
            ExitCode.OK,
        )
    except (IdempotencyConflict, KernelError) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "scoring replay"],
            next_action="curriculum activate",
        )
        exit_code = (
            ExitCode.CONFLICT if isinstance(exc, IdempotencyConflict) else ExitCode.PRECONDITION_FAILED
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, exit_code)


@review_app.command("due")
def review_due(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Due and overdue review targets in the canonical priority order
    (loss risk first). Read-only; the backlog recommends, never blocks."""
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
            failure_envelope("review.due", corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND
        )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            _, scheduler_policy = registry.resolve_active(SCHEDULER_KIND)
            _, scoring_policy = registry.resolve_active(SCORING_KIND)
            _, program = registry.resolve_active("curriculum")
            backlog = due_backlog(
                storage.store,
                require_valid_scheduler(scheduler_policy),
                scoring_policy,
                program,
                SystemClock().now(),
                # Per-event pinned scheduler resolution (scheduler 3a): a log
                # spanning a scheduler@1 -> scheduler@2 activation folds every
                # event under the table it was actually assigned under.
                registry=registry,
                # The article tier never leaves the queue; curriculum owns the
                # rule, the scheduler only takes the resulting set.
                permanent_interleave_targets=permanent_interleave_targets(program),
            )
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("review.due", corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED
        )
    data = {"count": len(backlog), "due": backlog}
    human = [f"{len(backlog)} review target(s) due"] + [
        f"  {c['target_ref']}/{c['dimension']} [{c['status']}] R={c['retrievability'][:6]} "
        f"overdue {c['overdue_days']}d"
        for c in backlog[:15]
    ]
    _emit(success_envelope("review.due", corr, data), human, fmt, ExitCode.OK)


def _memory_mutation(
    command: str,
    runner: Any,
    fmt: str,
    root: Path,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> None:
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope(command, corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    spoken = command.replace(".", " ")
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            request_hash = payload_hash({"command": command, "root": str(layout.root)})
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
            report = runner(storage.store, registry, layout.memory_dir)
            emit_projection_updated(storage.store, SystemClock(), SystemRandom(), report)
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, report)
        human = [
            f"{spoken}: {report['pages']} pages, {len(report.get('written', []))} written, "
            f"{report.get('unchanged', 0)} unchanged"
            + (f", {len(report['removed'])} removed" if "removed" in report else "")
        ]
        _emit(success_envelope(command, corr, {**report, "cached": False}), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=[f"{spoken} --idempotency-key <fresh-key>"],
            next_action=f"{spoken} --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@memory_app.command("render")
def memory_render(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Regenerate the Obsidian projection (memory/ zone only). Deterministic:
    unchanged state reproduces identical bytes."""
    _memory_mutation("memory.render", render, fmt, root, idempotency_key, correlation_id)


@memory_app.command("rebuild")
def memory_rebuild(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Full rebuild: regenerate every page and remove orphans -- memory/ ends
    exactly at the render set. notes/ is never touched."""
    _memory_mutation("memory.rebuild", rebuild, fmt, root, idempotency_key, correlation_id)


@memory_app.command("check")
def memory_check_cmd(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Drift check of the generated zone. Read-only: repairs nothing; a
    mismatch is an error (exit 6), pending lag is not."""
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
            failure_envelope("memory.check", corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND
        )
    try:
        with open_storage(layout) as storage:
            report = memory_check(
                storage.store, PolicyRegistry(storage._conn, SystemClock()), layout.memory_dir
            )
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("memory.check", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )
    if report["ok"]:
        _emit(
            success_envelope("memory.check", corr, report),
            [f"memory check: ok ({report['pages']} pages)"],
            fmt,
            ExitCode.OK,
        )
    error = ErrorPayload(
        error_code="MEMORY_DRIFT",
        message=(
            f"drift in the generated zone: {len(report['drifted'])} edited, "
            f"{len(report['missing'])} missing, {len(report['extra'])} extra"
        ),
        allowed_actions=["memory rebuild"],
        next_action="memory rebuild",
    )
    human = ["memory check: DRIFT"] + [
        f"  {kind}: {name}" for kind in ("drifted", "missing", "extra") for name in report[kind]
    ]
    _emit(failure_envelope("memory.check", corr, error), human, fmt, ExitCode.PRECONDITION_FAILED)


def _skill_targets(layout: StorageLayout) -> list[Path]:
    """Where `.agents/skills/` (Codex) and `.claude/skills/` (Claude Code) land
    -- under the storage root, so tests can point `--root` at a scratch
    directory instead of the real project tree (CLAUDE.md)."""
    return [layout.root / ".agents" / "skills", layout.root / ".claude" / "skills"]


@skills_app.command("sync")
def skills_sync(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    agent_skills: _AgentSkillsOpt = Path("agent-skills"),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Lay the canonical Agent Skills out as deterministic copies into
    ``.agents/skills/`` (Codex) and ``.claude/skills/`` (Claude Code).
    Idempotent: unchanged canon rewrites zero bytes (adapters 4.1)."""
    corr = _correlation(correlation_id)
    _require_key("skills.sync", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    targets = _skill_targets(layout)
    request_hash = payload_hash(
        {"command": "skills.sync", "agent_skills": str(agent_skills), "root": str(layout.root)}
    )
    try:
        with open_storage(layout) as storage:
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope("skills.sync", corr, {**dict(prior.value), "cached": True}),
                        ["skills sync (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = adapters_sync(agent_skills, targets, layout.skills_manifest, SystemClock())
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        human = [
            f"skills sync: {result['skills']} skill(s), {len(result['written'])} file(s) written, "
            f"{result['unchanged']} unchanged"
        ]
        _emit(success_envelope("skills.sync", corr, {**result, "cached": False}), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["skills sync --idempotency-key <fresh-key>"],
            next_action="skills sync --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope("skills.sync", corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except AdapterError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["skills sync --agent-skills <dir>"],
            next_action="skills sync --agent-skills <dir>",
        )
        _emit(
            failure_envelope("skills.sync", corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED
        )


@skills_app.command("validate")
def skills_validate(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    agent_skills: _AgentSkillsOpt = Path("agent-skills"),
    correlation_id: _CorrOpt = None,
) -> None:
    """Structure, `cli_calls` resolvability and drift (both directions). Never
    fixes anything -- only `skills sync` does (adapters 4.1, cli 4.4)."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    targets = _skill_targets(layout)
    violations = adapters_validate(
        agent_skills, targets, [descriptor.name for descriptor in command_registry()]
    )
    if not violations:
        _emit(
            success_envelope("skills.validate", corr, {"violations": []}),
            ["skills validate: ok"],
            fmt,
            ExitCode.OK,
        )
    structural = [v for v in violations if v["kind"] in ("structure", "unresolvable_call")]
    if structural:
        error = ErrorPayload(
            error_code=str(structural[0]["code"]),
            message=f"{len(structural)} structural violation(s); first: {structural[0]['message']}",
            allowed_actions=["skills validate"],
            next_action="fix the skill file(s), then skills validate",
        )
        human = ["skills validate: INVALID"] + [f"  - {v['message']}" for v in structural]
        _emit(failure_envelope("skills.validate", corr, error), human, fmt, ExitCode.INVALID_INPUT)
    drift = [v for v in violations if v["kind"] == "drift"]
    error = ErrorPayload(
        error_code=str(drift[0]["code"]),
        message=f"{len(drift)} drifted target(s); first: {drift[0]['message']}",
        allowed_actions=["skills sync"],
        next_action="skills sync --idempotency-key <key>",
    )
    human = ["skills validate: DRIFT"] + [f"  - {v['message']}" for v in drift]
    _emit(failure_envelope("skills.validate", corr, error), human, fmt, ExitCode.PRECONDITION_FAILED)


@skills_app.command("report")
def skills_report_command(
    skill: Annotated[str, typer.Option("--skill", help="Session-pinned skill name.")],
    version: Annotated[str, typer.Option("--version", help="Session-pinned skill version.")],
    status: Annotated[str, typer.Option("--status", help="started | completed | failed")],
    provider: Annotated[str, typer.Option("--provider", help="Reporting tutor provider.")],
    expected_session_revision: _SessionRevisionOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Record an untrusted skill lifecycle self-report for audit comparison."""
    command = "skills.report"
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    request_hash = payload_hash(
        {
            "command": command,
            "session": session,
            "skill": skill,
            "version": version,
            "status": status,
            "provider": provider,
            "expected_session_revision": expected_session_revision,
        }
    )
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session(command, corr, fmt, storage, session)
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope(command, corr, {**dict(prior.value), "cached": True}),
                        ["skill report (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = report_skill(
                storage.store,
                SystemClock(),
                SystemRandom(),
                session_id,
                skill_name=skill,
                version=version,
                status=status,
                expected_session_revision=expected_session_revision,
                provider=provider,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope(command, corr, result), [f"skill {skill}@{version}: {status}"], fmt, ExitCode.OK
        )
    except (AdapterError, SessionRevisionConflict, IdempotencyConflict) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "skills report"],
            next_action="session status",
        )
        code = (
            ExitCode.CONFLICT
            if isinstance(exc, (SessionRevisionConflict, IdempotencyConflict))
            else ExitCode.INVALID_INPUT
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, code)


@adapters_app.command("capture-turn")
def adapters_capture_turn_command(
    provider: Annotated[str, typer.Option("--provider", help="Provider identity.")],
    provider_message_id: Annotated[
        str, typer.Option("--provider-message-id", help="Provider-global immutable message id.")
    ],
    content: Annotated[str, typer.Option("--content", help="Exact local raw user-turn text.")],
    expected_session_revision: _SessionRevisionOpt,
    byte_start: Annotated[int, typer.Option("--byte-start", help="Inclusive UTF-8 byte offset.")] = 0,
    byte_end: Annotated[
        int | None, typer.Option("--byte-end", help="Exclusive UTF-8 byte offset; defaults to full text.")
    ] = None,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    session: _SessionOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Capture an untrusted user turn before learner-facing processing."""
    command = "adapters.capture-turn"
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    request_hash = payload_hash(
        {
            "command": command,
            "session": session,
            "provider": provider,
            "provider_message_id": provider_message_id,
            "content": content,
            "byte_start": byte_start,
            "byte_end": byte_end,
            "expected_session_revision": expected_session_revision,
        }
    )
    try:
        with open_storage(layout) as storage:
            session_id = _resolve_session(command, corr, fmt, storage, session)
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    prior = uow.check_idempotency(idempotency_key, request_hash)
                if isinstance(prior, CachedResult):
                    _emit(
                        success_envelope(command, corr, {**dict(prior.value), "cached": True}),
                        ["user turn capture (cached result)"],
                        fmt,
                        ExitCode.OK,
                    )
            result = capture_user_turn(
                storage.store,
                SystemClock(),
                SystemRandom(),
                session_id,
                provider=provider,
                provider_message_id=provider_message_id,
                content=content,
                expected_session_revision=expected_session_revision,
                byte_start=byte_start,
                byte_end=byte_end,
            )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(success_envelope(command, corr, result), ["user turn captured"], fmt, ExitCode.OK)
    except (AdapterError, SessionRevisionConflict, IdempotencyConflict) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "adapters capture-turn"],
            next_action="session status",
        )
        code = (
            ExitCode.CONFLICT
            if isinstance(exc, (SessionRevisionConflict, IdempotencyConflict))
            else ExitCode.INVALID_INPUT
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, code)


@adapters_app.command("compare")
def adapters_compare_cmd(
    fmt: _FormatOpt = "text",
    correlation_id: _CorrOpt = None,
) -> None:
    """Parity over recorded observable effects (adapters 4.4): per fixture,
    per adapter, whether every required effect fired and no forbidden one did.
    Diagnostic; mutates nothing. OPEN-24: fixtures carry pre-recorded effect
    sets rather than driving a live agent."""
    corr = _correlation(correlation_id)
    results = adapters_compare(DEFAULT_FIXTURES)
    failed = [r for r in results if not r.passed]
    data = {
        "fixtures": len(DEFAULT_FIXTURES),
        "results": [r.as_dict() for r in results],
        "all_passed": not failed,
    }
    human = [f"adapters compare: {len(results) - len(failed)}/{len(results)} passed"] + [
        f"  {r.fixture_id}/{r.adapter}: "
        + (
            "ok"
            if r.passed
            else f"FAIL missing={list(r.missing_required)} forbidden={list(r.present_forbidden)}"
        )
        for r in results
    ]
    if not failed:
        _emit(success_envelope("adapters.compare", corr, data), human, fmt, ExitCode.OK)
    error = ErrorPayload(
        error_code="ADAPTER_PARITY_MISMATCH",
        message=f"{len(failed)}/{len(results)} fixture/adapter result(s) failed parity",
        allowed_actions=["adapters compare"],
        next_action="adapters compare",
    )
    _emit(failure_envelope("adapters.compare", corr, error), human, fmt, ExitCode.PRECONDITION_FAILED)


@audit_app.command("session")
def audit_session_command(
    session_id: Annotated[str, typer.Argument(help="Session id.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Read the complete authoritative session trail and obligations."""
    corr = _correlation(correlation_id)
    with open_storage(resolve_layout(root)) as storage:
        registry = PolicyRegistry(storage._conn, SystemClock())
        view = session_view(storage.store, session_id)
        data = {**view, "obligations": obligations(storage.store, registry, session_id)}
    _emit(success_envelope("audit.session", corr, data), [f"audit session {session_id}"], fmt, ExitCode.OK)


@audit_app.command("correlation")
def audit_correlation_command(
    correlation_id_value: Annotated[str, typer.Argument(help="CLI correlation id.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Read all facts emitted by one CLI invocation."""
    corr = _correlation(correlation_id)
    with open_storage(resolve_layout(root)) as storage:
        data = correlation_view(storage.store, correlation_id_value)
    _emit(
        success_envelope("audit.correlation", corr, data),
        [f"audit correlation {correlation_id_value}"],
        fmt,
        ExitCode.OK,
    )


@audit_app.command("target")
def audit_target_command(
    target_id: Annotated[str, typer.Argument(help="Topic or lexicon target id.")],
    dimension: Annotated[str | None, typer.Option("--dimension", help="Optional dimension filter.")] = None,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Read the causally ordered history of one learner target."""
    corr = _correlation(correlation_id)
    with open_storage(resolve_layout(root)) as storage:
        data = target_history(storage.store, target_id, dimension)
    _emit(success_envelope("audit.target", corr, data), [f"audit target {target_id}"], fmt, ExitCode.OK)


@availability_app.command("show")
def availability_show(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Show declared rhythm, observed rhythm, divergence and any proposal."""
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
            failure_envelope("availability.show", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            _, policy = registry.resolve_active(CONTROL_KIND)
            result = availability_get(storage.store, require_valid(policy), SystemClock())
        human = [
            f"availability revision {result['revision']}",
            f"  declared: {result['declared']}",
            f"  observed: {result['observed']}",
            f"  divergence: {result['divergence_ppm']}",
        ]
        _emit(success_envelope("availability.show", corr, result), human, fmt, ExitCode.OK)
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("availability.show", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


@app.command("why")
def why_command(
    step: Annotated[str, typer.Option("--step", help="Persisted planned-step id.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Explain a persisted composition decision; read-only and replay-safe."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope("why", corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    try:
        with open_storage(layout) as storage:
            trace = explain(storage.store, step)
        data = {"step_id": step, "trace": trace}
        human = [
            f"step {step}: decision {trace['decision_id']}",
            f"  rules: {', '.join(trace['rule_refs'])}",
        ]
        _emit(success_envelope("why", corr, data), human, fmt, ExitCode.OK)
    except DecisionTraceUnavailable as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session peek"],
            next_action="session status",
        )
        _emit(failure_envelope("why", corr, error), [f"error: {exc}"], fmt, ExitCode.NOT_FOUND)


@availability_app.command("set")
def availability_set_command(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    sessions_per_week_milli: Annotated[
        int | None, typer.Option("--sessions-per-week-milli", help="1000 means one session per week.")
    ] = None,
    typical_minutes: Annotated[
        int | None, typer.Option("--typical-minutes", help="Declared typical session length.")
    ] = None,
    next_available_at: Annotated[
        str | None, typer.Option("--next-available-at", help="Aware ISO-8601 instant.")
    ] = None,
    blackout_until: Annotated[
        str | None, typer.Option("--blackout-until", help="Aware ISO-8601 instant.")
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Replace the declared availability profile; no implicit reconciliation."""
    corr = _correlation(correlation_id)
    _require_key("availability.set", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(
            failure_envelope("availability.set", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    declared = {
        key: value
        for key, value in {
            "sessions_per_week_milli": sessions_per_week_milli,
            "typical_minutes": typical_minutes,
            "next_available_at": next_available_at,
            "blackout_until": blackout_until,
        }.items()
        if value is not None
    }
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            version, policy = registry.resolve_active(CONTROL_KIND)
            require_valid(policy)
            result = availability_set(
                storage.store,
                SystemClock(),
                SystemRandom(),
                declared,
                idempotency_key=idempotency_key,
                control_policy_version=version,
            )
        human = [
            f"availability revision {result['revision']} ({'updated' if result['updated'] else 'unchanged'})"
        ]
        _emit(success_envelope("availability.set", corr, result), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["availability set --idempotency-key <fresh-key>"],
            next_action="availability set --idempotency-key <fresh-key>",
        )
        _emit(
            failure_envelope("availability.set", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.CONFLICT,
        )
    except AvailabilityInvalid as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["availability set --help"],
            next_action="availability set --help",
        )
        _emit(
            failure_envelope("availability.set", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.INVALID_INPUT,
        )
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("availability.set", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


@tunables_app.command("list")
def tunables_list_command(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    owner: Annotated[str | None, typer.Option("--owner", help="Exact catalogue owner label.")] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """List every versioned tunable and its allowed range."""
    command = "tunables.list"
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            items = list_tunables(PolicyRegistry(storage._conn, SystemClock()), owner=owner)
        result = {"count": len(items), "parameters": items}
        _emit(
            success_envelope(command, corr, result),
            [f"{len(items)} tunable parameter(s)", *[f"  {item['parameter_id']}" for item in items]],
            fmt,
            ExitCode.OK,
        )
    except (KernelError, TunableCatalogueInvalid) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate"],
            next_action="curriculum activate",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@calibration_app.command("list")
def calibration_list_command(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """List pending and applied calibration proposals."""
    command = "calibration.list"
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    with open_storage(layout) as storage:
        items = list_calibrations(storage.store)
    result = {"count": len(items), "proposals": items}
    _emit(
        success_envelope(command, corr, result),
        [f"{len(items)} calibration proposal(s)"],
        fmt,
        ExitCode.OK,
    )


def _calibration_mutation(
    command: str,
    request: dict[str, Any],
    runner: Any,
    fmt: str,
    root: Path,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> None:
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    request_hash = payload_hash({"command": command, **request})
    try:
        with open_storage(layout) as storage:
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
            result = runner(storage)
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope(command, corr, {**result, "cached": False}),
            [f"{command}: {result.get('proposal_id')}"],
            fmt,
            ExitCode.OK,
        )
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=[f"{command.replace('.', ' ')} --idempotency-key <fresh-key>"],
            next_action=f"{command.replace('.', ' ')} --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (CalibrationPrecondition, TunableCatalogueInvalid) as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["tunables list", "calibration list"],
            next_action="tunables list",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@calibration_app.command("propose")
def calibration_propose_command(
    parameter: Annotated[str, typer.Option("--parameter", help="Tunable parameter_id.")],
    value: Annotated[str, typer.Option("--value", help="Integer or decimal string.")],
    rationale: Annotated[str, typer.Option("--rationale", help="Evidence behind the proposal.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Create a pending proposal without changing any active value."""
    parsed: int | str = int(value) if value.lstrip("-").isdigit() else value

    def runner(storage: Any) -> dict[str, Any]:
        return propose_calibration(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            parameter,
            parsed,
            rationale=rationale,
        )

    _calibration_mutation(
        "calibration.propose",
        {"parameter": parameter, "value": parsed, "rationale": rationale},
        runner,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@calibration_app.command("confirm")
def calibration_confirm_command(
    proposal: Annotated[str, typer.Option("--proposal", help="Pending proposal id.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Confirm a proposal and atomically activate its owner-policy successor."""

    def runner(storage: Any) -> dict[str, Any]:
        return confirm_calibration(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            proposal,
        )

    _calibration_mutation(
        "calibration.confirm",
        {"proposal": proposal},
        runner,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@app.command("metrics")
def metrics_command(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Policy quality metrics and report-only hysteresis alerts."""
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
            failure_envelope("metrics", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    try:
        with open_storage(layout) as storage:
            registry = PolicyRegistry(storage._conn, SystemClock())
            _, control_policy = registry.resolve_active(CONTROL_KIND)
            control_policy = require_valid(control_policy)
            backlog: list[dict[str, Any]] = []
            try:
                _, scheduler_policy = registry.resolve_active(SCHEDULER_KIND)
                _, scoring_policy = registry.resolve_active(SCORING_KIND)
                _, program = registry.resolve_active("curriculum")
                backlog = due_backlog(
                    storage.store,
                    require_valid_scheduler(scheduler_policy),
                    require_valid_scoring(scoring_policy),
                    program,
                    SystemClock().now(),
                    registry=registry,
                    permanent_interleave_targets=permanent_interleave_targets(program),
                )
            except KernelError:
                # Neighbor state is optional for this read: backlog metrics say
                # no-data while event-only/session metrics remain available.
                backlog = []
            result = policy_metrics(storage.store, control_policy, SystemClock().now(), backlog=backlog)
        active_alerts = [alert["id"] for alert in result["alerts"] if alert["active"]]
        human = [
            f"policy metrics as of {result['as_of']}",
            *[f"  {item['id']}: {item['value']}" for item in result["metrics"]],
            f"  active alerts: {', '.join(active_alerts) if active_alerts else 'none'}",
        ]
        _emit(success_envelope("metrics", corr, result), human, fmt, ExitCode.OK)
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(
            failure_envelope("metrics", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.PRECONDITION_FAILED,
        )


@app.command("status")
def status_command(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Current evaluative state: per-target mastery, stability, knowledge states.

    Working level and Learning Score report `no-data` until enough evidence
    exists -- an honest gap, never a zero (scoring 5)."""
    corr = _correlation(correlation_id)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(failure_envelope("status", corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND)
    try:
        with open_storage(layout) as storage:
            report = replay_scores(storage.store, PolicyRegistry(storage._conn, SystemClock()))
    except KernelError as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum activate", "doctor"],
            next_action="curriculum activate",
        )
        _emit(failure_envelope("status", corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)
    scores = report["scores"]
    with open_storage(layout) as storage:
        registry = PolicyRegistry(storage._conn, SystemClock())
        _, scoring_policy = registry.resolve_active(SCORING_KIND)
        _, program = registry.resolve_active("curriculum")
        folded = fold_scores(storage.store, scoring_policy)
        levels = working_levels(
            folded,
            program,
            scoring_policy,
            # The low-confidence starting level a scored placement gives each
            # skill (scoring@2); empty under an older pin.
            placement=placement_levels(storage.store, program, scoring_policy),
            # The placement's writing band is PROVISIONAL (learning-model 6):
            # it never enters `measured_working_level`, only the estimate below.
            placement_writing=placement_writing_level(storage.store, scoring_policy),
        )
        measured = measured_working_level(levels)
        provisional = provisional_working_estimate(levels, self_reported=self_reported_levels(storage.store))
        score = learning_score(folded, program, scoring_policy, measured)
        xp = xp_ledger(storage.store, scoring_policy)
        compliance = tutor_compliance(storage.store, registry)
        # Honest, separate lexicon progress (learner 5, handoff H): curriculum
        # LexicalItems counted by knowledge state, and the personal lexicon by
        # linked/unlinked. ACTIVE and MASTERED stay separate -- no single
        # ambiguous "learned_words".
        state_key = {
            "NEW": "new",
            "LEARNING": "learning",
            "ACTIVE": "active",
            "MASTERED": "mastered",
            "AT_RISK": "at_risk",
        }
        curriculum_lexicon = {"new": 0, "learning": 0, "active": 0, "mastered": 0, "at_risk": 0}
        for unit in program.get("lexicon", []):
            found = folded.get(str(unit.get("id")))
            knowledge = found.knowledge_state if found is not None else "NEW"
            curriculum_lexicon[state_key.get(knowledge, "new")] += 1
        personal_lexicon = personal_lexicon_summary(storage.store)
    automaticity = report["automaticity"]
    data = {
        "targets": scores,
        "target_count": len(scores),
        "policy_version": report["policy_version"],
        "skills": levels,
        "measured_working_level": measured,  # None = no-data, never A1 by default
        # Measured where present, else provisional (placement writing /
        # self-report), every borrowed row flagged (scoring 4).
        "provisional_working_estimate": provisional,
        "learning_score": score,  # None = no-data, never 0
        "tutor_compliance": compliance,
        "lexicon_progress": {"curriculum": curriculum_lexicon, "personal": personal_lexicon},
        # A SEPARATE block on purpose (scoring 3d): "is this on autopilot yet?"
        # is a different question from Mastery or knowledge state, and answering
        # it with either number would be dishonest. `no-policy` = not measured.
        "automaticity": {
            "status": automaticity["status"],
            "policy_version": automaticity["policy_version"],
            "targets": automaticity["targets"],
        },
        "xp": {
            "total": xp["total"],
            "practice_days": xp["practice_days"],
            "streak": xp["streak"],
        },
    }
    human = [f"status: {len(scores)} scored target(s) under {report['policy_version']}"]
    for ref, state in list(scores.items())[:10]:
        mastery = ", ".join(f"{d}={v}" for d, v in state["mastery"].items()) or "no mastery yet"
        human.append(f"  {ref} [{state['knowledge_state']}] {mastery}")
    for skill, info in levels.items():
        shown = info["level"] or "no-data"
        human.append(
            f"  {skill}: {shown} (confidence {info['confidence']}, "
            f"basis {info['basis'] or 'no-data'}, {info['active_topics']} active"
            + (", provisional)" if info["provisional"] else ")")
        )
    human.append(f"  working level: {measured or 'no-data'} · learning score: {score or 'no-data'}")
    human.append(
        f"  provisional estimate: {provisional['level'] or 'no-data'}"
        + (" (provisional)" if provisional["provisional"] else "")
    )
    human.append(
        "  tutor compliance: "
        + (str(compliance["score"]) if compliance["status"] == "measured" else "no-data")
    )
    human.append(f"  lexicon: curriculum {curriculum_lexicon} · personal {personal_lexicon}")
    human.append(f"  xp: {xp['total']} over {xp['practice_days']} day(s), streak {xp['streak']}")
    if automaticity["status"] == "measured":
        human.append(f"  automaticity ({automaticity['policy_version']}):")
        for ref, axis in list(automaticity["targets"].items())[:10]:
            human.append(
                f"    {ref}: {axis['state']} "
                f"({axis['blocks_observed']} block(s), accuracy {axis['accuracy_ppm']} ppm)"
            )
    else:
        human.append("  automaticity: no-data")
    _emit(success_envelope("status", corr, data), human, fmt, ExitCode.OK)


def _lexicon_write(
    command: str,
    source: str,
    fmt: str,
    root: Path,
    surface: str,
    note_ru: str | None,
    linked_item: str | None,
    session: str | None,
    provider: str | None,
    expected_session_revision: int | None,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> None:
    """Shared shape of ``lexicon add`` / ``lexicon encounter`` (learner 3): the
    engine accepts only facts (surface, note, source, explicit linked_item,
    provenance) -- there is no path to a Mastery/knowledge value. Idempotent
    replay is answered before the write; a dangling link is NOT_FOUND, a bad
    surface INVALID_INPUT, a stale fence CONFLICT."""
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    spoken = command.replace(".", " ")
    layout = resolve_layout(root)
    try:
        with open_storage(layout) as storage:
            program: dict[str, Any] | None = None
            if linked_item is not None:
                try:
                    _, program = PolicyRegistry(storage._conn, SystemClock()).resolve_active("curriculum")
                except NoActivePolicy as exc:
                    error = ErrorPayload(
                        error_code="NO_ACTIVE_CURRICULUM",
                        message=f"{exc}; a linked entry needs an active curriculum to resolve against.",
                        allowed_actions=["curriculum activate", f"{spoken} (without --linked-item)"],
                        next_action="curriculum activate",
                    )
                    _emit(
                        failure_envelope(command, corr, error),
                        [f"error: {exc}"],
                        fmt,
                        ExitCode.PRECONDITION_FAILED,
                    )
            request_hash = payload_hash(
                {
                    "command": command,
                    "surface": surface,
                    "note_ru": note_ru,
                    "source": source,
                    "linked_item": linked_item,
                    "session": session,
                    "provider": provider,
                    "expected_session_revision": expected_session_revision,
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
            if command == "lexicon.encounter":
                assert session is not None and expected_session_revision is not None
                result = lexicon_encounter(
                    storage.store,
                    SystemClock(),
                    SystemRandom(),
                    session,
                    surface=surface,
                    note_ru=note_ru,
                    linked_item_id=linked_item,
                    program=program,
                    provider=provider,
                    expected_session_revision=expected_session_revision,
                )
            else:
                result = lexicon_add(
                    storage.store,
                    SystemClock(),
                    SystemRandom(),
                    surface=surface,
                    note_ru=note_ru,
                    source=source,
                    linked_item_id=linked_item,
                    program=program,
                    session_id=session,
                    provider=provider,
                    expected_session_revision=expected_session_revision,
                )
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        human = [
            f"{result['source']} lexicon entry {result['surface']!r} "
            + (f"→ {result['linked_item_id']}" if result.get("linked_item_id") else "(unlinked)")
        ]
        _emit(
            success_envelope(command, corr, {**result, "cached": result.get("cached", False)}),
            human,
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
    except LinkedItemNotFound as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["curriculum lexicon", f"{spoken} (without --linked-item)"],
            next_action="curriculum lexicon",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.NOT_FOUND)
    except LexiconEntryInvalid as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=[f"{spoken} --surface <word>"],
            next_action="fix the input and retry",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.INVALID_INPUT)
    except SessionRevisionConflict as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["session status", "session resume"],
            next_action="session status",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)


_SurfaceOpt = Annotated[str, typer.Option("--surface", help="The word or chunk (surface form).")]
_NoteRuOpt = Annotated[
    str | None, typer.Option("--note-ru", help="Optional Russian note/translation for the entry.")
]
_LinkedItemOpt = Annotated[
    str | None,
    typer.Option("--linked-item", help="Explicit ACTIVE-curriculum LexicalItem id (leave empty if unknown)."),
]


@lexicon_app.command("add")
def lexicon_add_cmd(
    surface: _SurfaceOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    note_ru: _NoteRuOpt = None,
    linked_item: _LinkedItemOpt = None,
    session: _SessionOpt = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Provider provenance, when session-bound.")
    ] = None,
    expected_session_revision: Annotated[
        int | None,
        typer.Option("--expected-session-revision", help="CAS token; required when --session is given."),
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Add a word to the learner's personal lexicon (source=learner).

    Enrollment, never evidence: no Mastery, no XP, no review schedule. Optional
    ``--linked-item`` references an existing curriculum LexicalItem (never a
    topic); leave it empty for an unknown word."""
    _lexicon_write(
        "lexicon.add",
        "learner",
        fmt,
        root,
        surface,
        note_ru,
        linked_item,
        session,
        provider,
        expected_session_revision,
        idempotency_key,
        correlation_id,
    )


@lexicon_app.command("encounter")
def lexicon_encounter_cmd(
    surface: _SurfaceOpt,
    session: Annotated[str, typer.Option("--session", help="Active session the encounter happened in.")],
    expected_session_revision: _SessionRevisionOpt,
    provider: Annotated[str, typer.Option("--provider", help="Tutor provider that used/explained the word.")],
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    note_ru: _NoteRuOpt = None,
    linked_item: _LinkedItemOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Record a session-driven encounter (source=encountered): the tutor used or
    explained a word the learner did not know / asked to translate.

    Explaining a word is enrollment, not evidence -- it never moves Mastery.
    Leave ``--linked-item`` empty when the word is not in the curriculum."""
    _lexicon_write(
        "lexicon.encounter",
        "encountered",
        fmt,
        root,
        surface,
        note_ru,
        linked_item,
        session,
        provider,
        expected_session_revision,
        idempotency_key,
        correlation_id,
    )


@lexicon_app.command("list")
def lexicon_list_cmd(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    source: Annotated[
        str | None, typer.Option("--source", help="Filter by source: learner | encountered.")
    ] = None,
    linked: Annotated[
        bool | None, typer.Option("--linked/--unlinked", help="Filter linked or unlinked entries.")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """List the personal lexicon (read-only fold). Deterministic order."""
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
            failure_envelope("lexicon.list", corr, error), ["error: not initialized"], fmt, ExitCode.NOT_FOUND
        )
    with open_storage(layout) as storage:
        entries = lexicon_list(storage.store, source=source, linked=linked)
        summary = personal_lexicon_summary(storage.store)
    data = {"count": len(entries), "entries": entries, "summary": summary}
    human = [f"{len(entries)} personal-lexicon entr{'y' if len(entries) == 1 else 'ies'}"] + [
        f"  {e['surface']} [{e['source']}]"
        + (f" → {e['linked_item_id']}" if e.get("linked_item_id") else " (unlinked)")
        for e in entries
    ]
    _emit(success_envelope("lexicon.list", corr, data), human, fmt, ExitCode.OK)


@learner_preferences_app.command("show")
def learner_preferences_show(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    correlation_id: _CorrOpt = None,
) -> None:
    """Show the learner's current LearnerPreferences snapshot (learner 4a).

    Read-only fold; never mutates. Returns the documented defaults at
    ``preferences_version`` 0 before the learner ever called `preferences set`.
    """
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
            failure_envelope("learner.preferences.show", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    with open_storage(layout) as storage:
        result = preferences_get(storage.store)
    human = [
        f"preferences v{result['preferences_version']}: round_size={result['round_size']}, "
        f"explanation_language={result['explanation_language']}, "
        f"timed_limit_seconds={result['timed_limit_seconds']}, feedback_mode={result['feedback_mode']}, "
        f"preferred_drill_forms={result['preferred_drill_forms']}"
    ]
    _emit(success_envelope("learner.preferences.show", corr, result), human, fmt, ExitCode.OK)


@learner_preferences_app.command("set")
def learner_preferences_set_cmd(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    round_size: Annotated[
        int | None, typer.Option("--round-size", help="Drill-round size (learner 4a): integer in [3, 12].")
    ] = None,
    explanation_language: Annotated[
        str | None, typer.Option("--explanation-language", help="ru | en.")
    ] = None,
    timed_limit_seconds: Annotated[
        int | None,
        typer.Option("--timed-limit-seconds", help="Default timed-form limit: integer in [60, 900]."),
    ] = None,
    feedback_mode: Annotated[
        str | None, typer.Option("--feedback-mode", help="stage_dependent | always_explain.")
    ] = None,
    preferred_drill_forms: Annotated[
        str | None,
        typer.Option(
            "--preferred-drill-forms",
            help="Comma-separated subset of ru_to_en_sentence,frame_recall,cue_to_sentence,"
            "transformation,minimal_pair; an empty value clears it.",
        ),
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Merge the given field(s) over the current LearnerPreferences snapshot and
    publish ONE full-snapshot ``LEARNER_PREFERENCES_UPDATED`` event (learner 4a).

    Preferences never influence scoring -- no field enters a formula,
    admissibility, Mastery, level, XP or the automaticity axis (learner 4a
    MUST NOT). Only the fields named on the command line change; everything
    else carries over unchanged.
    """
    corr = _correlation(correlation_id)
    _require_key("learner.preferences.set", corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    if not layout.db.exists():
        error = ErrorPayload(
            error_code="DATABASE_NOT_FOUND",
            message=f"{layout.db} does not exist.",
            allowed_actions=["init"],
            next_action="init",
        )
        _emit(
            failure_envelope("learner.preferences.set", corr, error),
            ["error: not initialized"],
            fmt,
            ExitCode.NOT_FOUND,
        )
    changes: dict[str, Any] = {}
    if round_size is not None:
        changes["round_size"] = round_size
    if explanation_language is not None:
        changes["explanation_language"] = explanation_language
    if timed_limit_seconds is not None:
        changes["timed_limit_seconds"] = timed_limit_seconds
    if feedback_mode is not None:
        changes["feedback_mode"] = feedback_mode
    if preferred_drill_forms is not None:
        changes["preferred_drill_forms"] = [
            item.strip() for item in preferred_drill_forms.split(",") if item.strip()
        ]
    try:
        with open_storage(layout) as storage:
            result = preferences_set(
                storage.store,
                SystemClock(),
                SystemRandom(),
                changes=changes,
                idempotency_key=idempotency_key,
            )
        human = [
            f"preferences v{result['preferences_version']} "
            f"({'cached' if result.get('cached') else 'updated'})"
        ]
        _emit(success_envelope("learner.preferences.set", corr, result), human, fmt, ExitCode.OK)
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=["learner preferences set --idempotency-key <fresh-key>"],
            next_action="learner preferences set --idempotency-key <fresh-key>",
        )
        _emit(
            failure_envelope("learner.preferences.set", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.CONFLICT,
        )
    except PreferencesInvalid as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["learner preferences set --help"],
            next_action="learner preferences set --help",
        )
        _emit(
            failure_envelope("learner.preferences.set", corr, error),
            [f"error: {exc}"],
            fmt,
            ExitCode.INVALID_INPUT,
        )


_PlacementOpt = Annotated[
    str | None, typer.Option("--placement", help="Placement id; defaults to the active placement.")
]


def _resolve_placement(command: str, corr: str, fmt: str, storage: Any, placement: str | None) -> str:
    placement_id = placement if placement is not None else active_placement_id(storage.store)
    if placement_id is None or get_placement(storage.store, placement_id) is None:
        error = ErrorPayload(
            error_code="PLACEMENT_NOT_FOUND",
            message="no such placement (and no active placement to default to).",
            allowed_actions=["placement start"],
            next_action="placement start",
        )
        _emit(failure_envelope(command, corr, error), ["error: no placement"], fmt, ExitCode.NOT_FOUND)
    return placement_id


def _placement_command(
    command: str,
    hash_inputs: dict[str, Any],
    runner: Any,
    describe: Any,
    fmt: str,
    root: Path,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> None:
    """Shared envelope for the placement mutations: idempotent replay first,
    then the runner, mapping placement/self-assessment refusals to stable codes."""
    corr = _correlation(correlation_id)
    _require_key(command, corr, fmt, idempotency_key)
    layout = resolve_layout(root)
    spoken = command.replace(".", " ")
    try:
        with open_storage(layout) as storage:
            request_hash = payload_hash({"command": command, "root": str(layout.root), **hash_inputs})
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
            result = runner(storage, corr)
            if idempotency_key:
                with UnitOfWork(storage.store, SystemClock()) as uow:
                    uow.record_result(idempotency_key, request_hash, result)
        _emit(
            success_envelope(command, corr, {**result, "cached": False}), describe(result), fmt, ExitCode.OK
        )
    except IdempotencyConflict as exc:
        error = ErrorPayload(
            error_code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            allowed_actions=[f"{spoken} --idempotency-key <fresh-key>"],
            next_action=f"{spoken} --idempotency-key <fresh-key>",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.CONFLICT)
    except (SelfAssessmentInvalid, UnknownForm) as exc:
        error = ErrorPayload(
            error_code=getattr(exc, "code", "INVALID_INPUT"),
            message=str(exc),
            allowed_actions=["placement start", "placement decline --self-assessment <json>"],
            next_action="fix the input and retry",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.INVALID_INPUT)
    except PlacementPrecondition as exc:
        error = ErrorPayload(
            error_code=exc.code,
            message=str(exc),
            allowed_actions=["placement start", "placement resume", "placement abandon"],
            next_action="placement start",
        )
        _emit(failure_envelope(command, corr, error), [f"error: {exc}"], fmt, ExitCode.PRECONDITION_FAILED)


@placement_app.command("start")
def placement_start(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    form: Annotated[
        str | None, typer.Option("--form", help="Form selector; defaults to the shipped form.")
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Open a placement: select a fixed authored form (seed, version), pin the
    policies and return the item prompts for verbatim presentation."""

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        return start_placement(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            form_selector=form,
        )

    def describe(result: dict[str, Any]) -> list[str]:
        selection = result.get("form_selection") or {}
        lines = [
            f"placement {result['placement_id']} started (form {result['form_version']})",
            f"  sections: {', '.join(result['sections'])} · {len(result['items'])} items"
            + (f" · ~{result['target_minutes']} min" if result.get("target_minutes") else ""),
            f"  selected: {selection.get('basis', 'default')}"
            + ("" if selection.get("cooldown_elapsed", True) else " (inside the form cooldown)"),
        ]
        if result.get("passages"):
            lines.append(
                "  passages: "
                + ", ".join(f"{passage['passage_id']} [{passage['cefr']}]" for passage in result["passages"])
            )
        return lines

    _placement_command(
        "placement.start", {"form": form}, runner, describe, fmt, root, idempotency_key, correlation_id
    )


@placement_app.command("answer")
def placement_answer(
    input_file: _InputOpt,
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    placement: _PlacementOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Checkpoint one section's answers. The input file carries
    {section, answers: {item_id: raw_answer}} and, for the writing section,
    {observations: {item_id: [rubric observation, ...]}}."""
    corr = _correlation(correlation_id)
    payload = _read_input_json("placement.answer", corr, fmt, input_file)

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        placement_id = _resolve_placement("placement.answer", corr, fmt, storage, placement)
        return answer_placement(
            storage.store,
            SystemClock(),
            SystemRandom(),
            placement_id,
            section=str(payload.get("section", "")),
            answers=dict(payload.get("answers", {})),
            observations=dict(payload.get("observations", {})),
        )

    def describe(result: dict[str, Any]) -> list[str]:
        nxt = result.get("next_section") or "none (ready to submit)"
        lines = [
            f"placement {result['placement_id']}: section {result['section']} checkpointed",
            f"  next section: {nxt}",
        ]
        if result.get("observed_items"):
            lines.append(f"  rubric observations stored for: {', '.join(result['observed_items'])}")
        return lines

    _placement_command(
        "placement.answer",
        {"placement": placement, "input": payload},
        runner,
        describe,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@placement_app.command("resume")
def placement_resume(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    placement: _PlacementOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Resume a placement within its window: state + the next section."""

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        placement_id = _resolve_placement("placement.resume", corr, fmt, storage, placement)
        return resume_placement(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            placement_id,
        )

    def describe(result: dict[str, Any]) -> list[str]:
        return [
            f"placement {result['placement_id']} resumed [{result['status']}]",
            f"  next section: {result.get('next_section') or 'none (ready to submit)'}",
        ]

    _placement_command(
        "placement.resume",
        {"placement": placement},
        runner,
        describe,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@placement_app.command("submit")
def placement_submit(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    placement: _PlacementOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Terminal, idempotent submit: grade the form and hand off to scoring
    (origin=placement, ACTIVE ceiling). A repeat returns the stored result."""

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        placement_id = _resolve_placement("placement.submit", corr, fmt, storage, placement)
        return submit_placement(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            placement_id,
        )

    def describe(result: dict[str, Any]) -> list[str]:
        lines = [
            f"placement {result['placement_id']} {result['status']}"
            + (" (already scored)" if result.get("already") else ""),
            f"  evidence: {result['evidence_count']} · outcomes: {result['outcome_count']}",
        ]
        skills = result.get("skills") or {}
        for skill, info in sorted(skills.items()):
            lines.append(
                f"  {skill}: {info['level'] or 'no-data'} "
                f"(confidence {info['confidence']}, basis {info['basis']})"
            )
        if not skills:
            # Honest: a placement that measured no band gives no level at all.
            lines.append("  starting level: no-data (no band reached its coverage floor)")
        lines.append("  read `trainer status` for the working level")
        return lines

    _placement_command(
        "placement.submit",
        {"placement": placement},
        runner,
        describe,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@placement_app.command("abandon")
def placement_abandon(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    placement: _PlacementOpt = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Abandon a placement (STARTED/IN_PROGRESS only); forbidden after submit."""

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        placement_id = _resolve_placement("placement.abandon", corr, fmt, storage, placement)
        event = abandon_placement(storage.store, SystemClock(), SystemRandom(), placement_id)
        return {"placement_id": placement_id, "status": "ABANDONED", "event_id": event.id}

    def describe(result: dict[str, Any]) -> list[str]:
        return [f"placement {result['placement_id']}: ABANDONED"]

    _placement_command(
        "placement.abandon",
        {"placement": placement},
        runner,
        describe,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


@placement_app.command("decline")
def placement_decline(
    fmt: _FormatOpt = "text",
    root: _RootOpt = Path(),
    self_assessment: Annotated[
        str | None,
        typer.Option(
            "--self-assessment", help='Per-skill object, e.g. {"schema_version":1,"levels":{"grammar":"A2"}}.'
        ),
    ] = None,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Required with --format json (cli 4.3).")
    ] = None,
    correlation_id: _CorrOpt = None,
) -> None:
    """Decline placement (blocks nothing). --self-assessment is a per-core-skill
    object (a scalar is rejected); each level is a provisional working estimate."""
    corr = _correlation(correlation_id)
    parsed_self: Any | None = None
    if self_assessment is not None:
        try:
            parsed_self = json.loads(self_assessment)
        except ValueError as exc:
            error = ErrorPayload(
                error_code="INVALID_INPUT",
                message=f"--self-assessment is not valid JSON: {exc}",
                allowed_actions=['placement decline --self-assessment \'{"schema_version":1,"levels":{}}\''],
                next_action="fix the JSON and retry",
            )
            _emit(
                failure_envelope("placement.decline", corr, error),
                [f"error: {exc}"],
                fmt,
                ExitCode.INVALID_INPUT,
            )

    def runner(storage: Any, corr: str) -> dict[str, Any]:
        return decline_placement(
            storage.store,
            PolicyRegistry(storage._conn, SystemClock()),
            SystemClock(),
            SystemRandom(),
            self_assessment=parsed_self,
        )

    def describe(result: dict[str, Any]) -> list[str]:
        levels = result.get("self_reported_levels") or {}
        rendered = ", ".join(f"{skill}={level}" for skill, level in levels.items()) or "none"
        return [f"placement declined ({result['placement_id']})", f"  self-reported: {rendered}"]

    _placement_command(
        "placement.decline",
        {"self_assessment": parsed_self},
        runner,
        describe,
        fmt,
        root,
        idempotency_key,
        correlation_id,
    )


def _wants_json(argv: list[str]) -> bool:
    if "--format=json" in argv:
        return True
    return any(arg == "--format" and argv[i + 1 : i + 2] == ["json"] for i, arg in enumerate(argv))


def _provided_correlation(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item.startswith("--correlation-id="):
            return item.split("=", 1)[1]
        if item == "--correlation-id" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def run(argv: list[str]) -> int:
    """Invoke the app; guarantee an envelope and a closed exit code (cli 4.1/4.2).

    An exception escaping unwrapped would hand the agent unparseable garbage;
    even internal errors must come back as a valid ``ok: false`` envelope.
    Usage errors are recognized by the ``format_message`` protocol rather than
    by class: typer vendors its argument-parsing library, so the concrete
    exception type is not part of any public surface we could import.
    """
    correlation_id = _provided_correlation(argv) or new_ulid(SystemClock(), SystemRandom())
    correlation_token = _RUN_CORRELATION.set(correlation_id)
    envelope_token = _LAST_ENVELOPE.set(None)
    command = telemetry_command_name(argv)
    db = telemetry_database_path(argv)
    telemetry_session_id = telemetry_session_hint(argv, db)
    invocation_id = record_invocation(
        db,
        SystemClock(),
        SystemRandom(),
        command=command,
        correlation_id=correlation_id,
        argv=argv,
        session_id=telemetry_session_id,
    )
    exit_code = int(ExitCode.OK)
    try:
        # In non-standalone mode the framework *returns* the exit code carried
        # by a raised Exit instead of re-raising it; both paths are honored.
        result = app(args=argv, standalone_mode=False)
        if isinstance(result, int):
            exit_code = result
    except typer.Exit as exc:
        exit_code = int(exc.exit_code)
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
                envelope = failure_envelope("usage", correlation_id, error)
                _LAST_ENVELOPE.set(envelope)
                print_json_envelope(envelope)
            else:
                sys.stderr.write(f"error: {message}\n")
            exit_code = int(ExitCode.USAGE)
        elif _wants_json(argv):
            error = ErrorPayload(
                error_code="INTERNAL",
                message=f"{type(exc).__name__}: {exc}",
                allowed_actions=["doctor"],
                next_action="doctor",
            )
            envelope = failure_envelope("internal", correlation_id, error)
            _LAST_ENVELOPE.set(envelope)
            print_json_envelope(envelope)
            exit_code = int(ExitCode.INTERNAL)
        else:
            sys.stderr.write(f"internal error: {type(exc).__name__}: {exc}\n")
            exit_code = int(ExitCode.INTERNAL)
    finally:
        last_envelope = _LAST_ENVELOPE.get()
        # ``init`` creates the database during dispatch; in that one case the
        # invocation fact is appended immediately afterwards and still precedes
        # its terminal fact in canonical sequence.
        if invocation_id is None:
            invocation_id = record_invocation(
                db,
                SystemClock(),
                SystemRandom(),
                command=command,
                correlation_id=correlation_id,
                argv=argv,
                session_id=telemetry_session_id,
            )
        if invocation_id is not None:
            record_terminal(
                db,
                SystemClock(),
                SystemRandom(),
                command=command,
                correlation_id=correlation_id,
                invocation_id=invocation_id,
                exit_code=exit_code,
                envelope=last_envelope,
                session_id=telemetry_session_id,
            )
        _LAST_ENVELOPE.reset(envelope_token)
        _RUN_CORRELATION.reset(correlation_token)
    return exit_code


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))
