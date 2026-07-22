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
    CommandDescriptor(
        name="observed.record", owner_module="evidence", mutating=True, requires_idempotency_key=True
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
    # Learner control signals (control 4.7, roadmap 2.8a): a nudge to the next
    # composition, never a plan edit. Mutating -- it records a signal event (and
    # for too_easy a PROBE_REQUESTED) -- so it requires the key in json mode.
    CommandDescriptor(name="signal", owner_module="control", mutating=True, requires_idempotency_key=True),
    CommandDescriptor(
        name="availability.show", owner_module="control", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="availability.set", owner_module="control", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(name="why", owner_module="control", mutating=False, requires_idempotency_key=False),
    CommandDescriptor(name="metrics", owner_module="control", mutating=False, requires_idempotency_key=False),
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
    # The Obsidian projection (0.6): render/rebuild mutate generated files
    # (never learner state); check is read-only and repairs nothing.
    CommandDescriptor(
        name="memory.render", owner_module="memory", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="memory.rebuild", owner_module="memory", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="memory.check", owner_module="memory", mutating=False, requires_idempotency_key=False
    ),
    # Agent Skills (adapters, roadmap 2.5): sync lays canon out as deterministic
    # copies; validate is read-only (structure, cli_call resolvability, drift).
    CommandDescriptor(
        name="skills.sync", owner_module="adapters", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="skills.validate", owner_module="adapters", mutating=False, requires_idempotency_key=False
    ),
    # Adapter parity (adapters 4.4): diagnostic over recorded effect sets,
    # never a live agent run (OPEN-24) -- mutates nothing.
    CommandDescriptor(
        name="adapters.compare", owner_module="adapters", mutating=False, requires_idempotency_key=False
    ),
    # Session resume (lessons 4b/5): full state + tutor briefing + notes,
    # attaching the resuming agent (AGENT_ATTACHED) in the same UoW.
    CommandDescriptor(
        name="session.resume", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    # Placement diagnostics (assessments 2-5, roadmap 2.6): fixed forms with a
    # checkpoint/resume lifecycle and one terminal idempotent submit. Every
    # command mutates (start creates, answer checkpoints, resume publishes
    # RESUMED, submit scores, abandon/decline terminalize), so each requires the
    # idempotency key in json mode.
    CommandDescriptor(
        name="placement.start", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="placement.answer", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="placement.resume", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="placement.submit", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="placement.abandon", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="placement.decline", owner_module="assessments", mutating=True, requires_idempotency_key=True
    ),
)


def command_registry() -> tuple[CommandDescriptor, ...]:
    """The registered command surface (cli 3)."""
    return _COMMANDS
