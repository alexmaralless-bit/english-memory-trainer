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
    CommandDescriptor(
        name="session.start", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.finish", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.abandon", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.status", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    # Step delivery (control defines the behavior, lessons owns the commands):
    # `next` and `replan` are CAS mutations [R-1]; `peek` observes and never
    # publishes (control 4.2).
    CommandDescriptor(
        name="session.peek", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="session.next", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.replan", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    # Evidence persistence (2.2 increment 3): the rendered snapshot commits
    # before the learner sees the prompt (P.3 PD-1 A), attempts reference the
    # delivered step and the snapshot (evidence 4.5 [RR2-3]).
    CommandDescriptor(
        name="exercise.rendered", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="attempt.record", owner_module="evidence", mutating=True, requires_idempotency_key=True
    ),
    # The exercise bank (generation@1 bank_lifecycle, PD-2 A): admission after
    # an assessed attempt or the explicit maintainer fast-path; rejected and
    # retired are terminal.
    CommandDescriptor(
        name="exercise.accept", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="exercise.reject", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="exercise.retire", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="exercise.bank", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    # Scoring (0.4 part 2): scores are a pure fold over the event log -- both
    # commands are read-only by construction.
    CommandDescriptor(
        name="scoring.replay", owner_module="scoring", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(name="status", owner_module="scoring", mutating=False, requires_idempotency_key=False),
    # Scheduler (0.4 part 3): the backlog recommends, never blocks.
    CommandDescriptor(
        name="review.due", owner_module="scheduler", mutating=False, requires_idempotency_key=False
    ),
    # Closing computes the single terminal ReviewOutcome (evidence 4.3): the
    # engine grades, the agent only marks done.
    CommandDescriptor(
        name="review.close", owner_module="evidence", mutating=True, requires_idempotency_key=True
    ),
    # Finalizing an open attempt runs the pinned rubric pipeline and settles
    # atomically (P.5): the engine grades, the agent only reports facts.
    CommandDescriptor(
        name="attempt.finalize", owner_module="evidence", mutating=True, requires_idempotency_key=True
    ),
)


def command_registry() -> tuple[CommandDescriptor, ...]:
    """The registered command surface (cli 3)."""
    return _COMMANDS
