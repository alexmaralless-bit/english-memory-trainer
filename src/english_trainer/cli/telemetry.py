"""Outer-transport CLI telemetry for deterministic audit correlation.

The facts deliberately contain no argument values or response messages.  A
read-only command may therefore leave an audit fact while its domain operation
remains read-only: telemetry is written by this outer transport, not by the
queried module and cannot alter learner state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from english_trainer.cli.registry import command_registry
from english_trainer.kernel.aggregates import read_aggregate
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore, connect
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.storage.layout import DB_FILENAME

COMMAND_INVOKED = "cli.command_invoked"
COMMAND_TERMINATED = "cli.command_terminated"


def command_name(argv: list[str]) -> str:
    plain = [item for item in argv if item and not item.startswith("-")]
    names = sorted((item.name for item in command_registry()), key=lambda value: -len(value.split(".")))
    for name in names:
        parts = name.split(".")
        if plain[: len(parts)] == parts:
            return name
    return "usage"


def database_path(argv: list[str]) -> Path:
    for index, item in enumerate(argv):
        if item.startswith("--db="):
            return Path(item.split("=", 1)[1])
        if item == "--db" and index + 1 < len(argv):
            return Path(argv[index + 1])
    root = Path()
    for index, item in enumerate(argv):
        if item.startswith("--root="):
            root = Path(item.split("=", 1)[1])
        elif item == "--root" and index + 1 < len(argv):
            root = Path(argv[index + 1])
    return root / DB_FILENAME


def session_hint(argv: list[str], db: Path) -> str | None:
    """Resolve only the safe session identity, never arbitrary argument text."""
    for index, item in enumerate(argv):
        if item.startswith("--session="):
            return item.split("=", 1)[1]
        if item == "--session" and index + 1 < len(argv):
            return argv[index + 1]
    opened = _open_existing(db)
    if opened is None:
        return None
    conn, _ = opened
    try:
        pointer = read_aggregate(conn, "session_pointer", "active")
        value = pointer[0].get("session_id") if pointer is not None else None
        return str(value) if value else None
    finally:
        conn.close()


def _argv_shape(argv: list[str]) -> list[str]:
    shape: list[str] = []
    skip_value = False
    for item in argv:
        if skip_value:
            shape.append("<value>")
            skip_value = False
        elif item.startswith("--"):
            option = item.split("=", 1)[0]
            shape.append(option)
            skip_value = "=" not in item
        elif item.startswith("-"):
            shape.append(item)
        else:
            shape.append(item if len(shape) < 3 else "<value>")
    return shape


def _open_existing(path: Path) -> tuple[Any, EventStore] | None:
    if not path.is_file():
        return None
    conn = None
    try:
        conn = connect(path)
        conn.execute("SELECT 1 FROM events LIMIT 1;").fetchone()
    except Exception:
        if conn is not None:
            conn.close()
        return None
    return conn, EventStore(conn)


def record_invocation(
    db: Path,
    clock: Clock,
    random_source: RandomSource,
    *,
    command: str,
    correlation_id: str,
    argv: list[str],
    session_id: str | None,
) -> str | None:
    opened = _open_existing(db)
    if opened is None:
        return None
    conn, store = opened
    try:
        try:
            event_id = new_ulid(clock, random_source)
            with UnitOfWork(store, clock) as uow:
                uow.append(
                    [
                        make_event(
                            id=event_id,
                            type=COMMAND_INVOKED,
                            occurred_at=clock.now(),
                            actor="cli-transport",
                            correlation_id=correlation_id,
                            payload={
                                "command": command,
                                "request_shape_hash": payload_hash({"argv_shape": _argv_shape(argv)}),
                                "session_id": session_id,
                                "trust": "observed_transport_fact",
                            },
                        )
                    ]
                )
            return event_id
        except Exception:
            # Preserve the diagnostic path when the event/outbox schema itself
            # is broken. The failed UnitOfWork has already rolled back.
            return None
    finally:
        conn.close()


def record_terminal(
    db: Path,
    clock: Clock,
    random_source: RandomSource,
    *,
    command: str,
    correlation_id: str,
    invocation_id: str,
    exit_code: int,
    envelope: dict[str, Any] | None,
    session_id: str | None,
) -> None:
    opened = _open_existing(db)
    if opened is None:
        return
    conn, store = opened
    try:
        ok = bool(envelope and envelope.get("ok"))
        data = dict(envelope.get("data") or {}) if envelope else {}
        error = dict(envelope.get("error") or {}) if envelope else {}
        safe_payload: dict[str, Any] = {
            "command": command,
            "outcome": "success" if ok else "refused" if envelope else "failed",
            "exit_code": exit_code,
            "error_code": error.get("error_code"),
            "trust": "observed_transport_fact",
        }
        for key in ("session_id", "attempt_id", "review_id", "placement_id"):
            if data.get(key) is not None:
                safe_payload[key] = data[key]
        if "session_id" not in safe_payload and session_id is not None:
            safe_payload["session_id"] = session_id
        try:
            with UnitOfWork(store, clock) as uow:
                uow.append(
                    [
                        make_event(
                            id=new_ulid(clock, random_source),
                            type=COMMAND_TERMINATED,
                            occurred_at=clock.now(),
                            actor="cli-transport",
                            correlation_id=correlation_id,
                            causation_id=invocation_id,
                            payload=safe_payload,
                        )
                    ]
                )
        except Exception:
            return
    finally:
        conn.close()
