"""Response envelope and exit codes -- the machine contract of the CLI (cli 2, 4).

Every command answers with one **total** envelope: success and failure share a
single shape and differ only in ``ok``, so an agent never guesses what it is
reading. With ``--format json`` stdout carries exactly one JSON document and
nothing else; all diagnostics go to stderr. The human format (the default) is
deliberately *not* a contract -- only the JSON form is versioned.

Exit codes are a closed set (cli 4.2); adding one is a contract change. The
distinction the contract insists on: ``CONFLICT`` means "retry with fresh
state", ``PRECONDITION_FAILED`` means "this is not allowed now -- do something
else". Every failure names ``allowed_actions`` and a recommended
``next_action``: a refusal without an exit would leave the agent in a retry
loop (cli 4.1).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

SCHEMA_VERSION = 1


class ExitCode(IntEnum):
    """The closed exit-code set (cli 4.2). Stable; extension = contract change."""

    OK = 0
    INTERNAL = 1
    USAGE = 2
    INVALID_INPUT = 3
    NOT_FOUND = 4
    CONFLICT = 5
    PRECONDITION_FAILED = 6


@dataclass(frozen=True)
class ErrorPayload:
    """A machine-readable refusal (cli 2). ``next_action`` is mandatory."""

    error_code: str
    message: str
    next_action: str
    allowed_actions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "allowed_actions": list(self.allowed_actions),
            "next_action": self.next_action,
        }


def success_envelope(command: str, correlation_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": command,
        "correlation_id": correlation_id,
        "data": data,
    }


def failure_envelope(command: str, correlation_id: str, error: ErrorPayload) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "command": command,
        "correlation_id": correlation_id,
        "error": error.as_dict(),
    }


def print_json_envelope(envelope: dict[str, Any]) -> None:
    """Print the one JSON document the agent will parse. Nothing else may reach
    stdout in json mode (cli 4.1)."""
    sys.stdout.write(json.dumps(envelope, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


def print_human(lines: list[str]) -> None:
    """Human-facing output (the default format). Explicitly NOT a contract --
    its shape may change freely (cli 4.1)."""
    sys.stdout.write("\n".join(lines) + "\n")
