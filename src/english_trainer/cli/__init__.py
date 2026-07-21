"""CLI: the single boundary through which the outside world -- including the
AI tutor -- reads and changes learner state (cli 1).

No business logic lives here: commands translate arguments into domain-module
calls and serialize the result into the stable envelope contract. This
increment covers the kernel-facing surface (doctor, init, database check);
learning commands arrive with their owning modules.
"""

from __future__ import annotations

from english_trainer.cli.app import app, main, run
from english_trainer.cli.envelope import SCHEMA_VERSION, ErrorPayload, ExitCode
from english_trainer.cli.registry import CommandDescriptor, command_registry

__all__ = [
    "SCHEMA_VERSION",
    "CommandDescriptor",
    "ErrorPayload",
    "ExitCode",
    "app",
    "command_registry",
    "main",
    "run",
]
