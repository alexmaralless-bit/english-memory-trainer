"""Command registry (cli 2, 3).

Every published command is registered with its owner module, whether it
mutates, and whether it requires an idempotency key. The registry is the source
for ``trainer skills validate`` and the adapters parity check (cli 3) and for
the future command-registry CI gate (foundation 8): a mutation endpoint that is
not registered here is a contract violation, not a convenience.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDescriptor:
    """One published CLI command (cli 2)."""

    name: str
    owner_module: str
    mutating: bool
    requires_idempotency_key: bool
    phase: str = "mvp"


# The commands this increment publishes. Read-only diagnostics never mutate --
# not even to "fix" what they find (cli 4.4); `init` is the bootstrap mutation
# and therefore requires the idempotency key in json mode (cli 4.3).
_COMMANDS: tuple[CommandDescriptor, ...] = (
    CommandDescriptor(name="doctor", owner_module="cli", mutating=False, requires_idempotency_key=False),
    CommandDescriptor(name="init", owner_module="storage", mutating=True, requires_idempotency_key=True),
    CommandDescriptor(
        name="database.check", owner_module="storage", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="snapshot.create", owner_module="storage", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="curriculum.validate", owner_module="curriculum", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="curriculum.show", owner_module="curriculum", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="curriculum.lexicon", owner_module="curriculum", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="curriculum.activate", owner_module="curriculum", mutating=True, requires_idempotency_key=True
    ),
)


def command_registry() -> tuple[CommandDescriptor, ...]:
    """The registered command surface (cli 3)."""
    return _COMMANDS
