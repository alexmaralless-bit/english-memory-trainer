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
        name="curriculum.texts", owner_module="curriculum", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="curriculum.activate", owner_module="curriculum", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.start", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.propose", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    # The brief/report protocol [PD-2026-09-23]: `check-report` validates a
    # lesson report and writes nothing; `report` commits it atomically and
    # finishes the session, so it requires the key in json mode.
    CommandDescriptor(
        name="session.check-report", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="session.report", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.abandon", owner_module="lessons", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="session.status", owner_module="lessons", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="availability.show", owner_module="control", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="availability.set", owner_module="control", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(name="why", owner_module="control", mutating=False, requires_idempotency_key=False),
    CommandDescriptor(name="metrics", owner_module="control", mutating=False, requires_idempotency_key=False),
    CommandDescriptor(
        name="tunables.list", owner_module="control", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="calibration.list", owner_module="control", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="calibration.propose", owner_module="control", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="calibration.confirm", owner_module="control", mutating=True, requires_idempotency_key=True
    ),
    # Scoring (0.4 part 2): scores are a pure fold over the event log -- both
    # commands are read-only by construction.
    CommandDescriptor(
        name="scoring.replay", owner_module="scoring", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="scoring.transitions.backfill",
        owner_module="scoring",
        mutating=True,
        requires_idempotency_key=True,
    ),
    CommandDescriptor(name="status", owner_module="scoring", mutating=False, requires_idempotency_key=False),
    # The learner's personal lexicon (learner 0.11, roadmap living-layer): add /
    # encounter are mutating (they append LEARNER_LEXICON_ENTRY_ADDED and, when
    # session-bound, advance the fence), so they require the key in json mode;
    # list is a read-only fold.
    CommandDescriptor(
        name="lexicon.add", owner_module="learner", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="lexicon.encounter", owner_module="learner", mutating=True, requires_idempotency_key=True
    ),
    CommandDescriptor(
        name="lexicon.list", owner_module="learner", mutating=False, requires_idempotency_key=False
    ),
    # Scheduler (0.4 part 3): the backlog recommends, never blocks.
    CommandDescriptor(
        name="review.due", owner_module="scheduler", mutating=False, requires_idempotency_key=False
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
    CommandDescriptor(
        name="skills.report", owner_module="adapters", mutating=True, requires_idempotency_key=True
    ),
    # Adapter parity (adapters 4.4): diagnostic over recorded effect sets,
    # never a live agent run (OPEN-24) -- mutates nothing.
    CommandDescriptor(
        name="adapters.compare", owner_module="adapters", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="adapters.capture-turn",
        owner_module="adapters",
        mutating=True,
        requires_idempotency_key=True,
    ),
    CommandDescriptor(
        name="audit.session", owner_module="audit", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="audit.correlation", owner_module="audit", mutating=False, requires_idempotency_key=False
    ),
    CommandDescriptor(
        name="audit.target", owner_module="audit", mutating=False, requires_idempotency_key=False
    ),
    # Session resume (lessons 4b/5): state + the rebuilt lesson brief,
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
    # LearnerPreferences (learner 4a, roadmap Д8): the form a session takes --
    # round size, explanation language, drill forms, timed limit, feedback
    # mode. `set` publishes a full-snapshot LEARNER_PREFERENCES_UPDATED, so it
    # requires the key in json mode; `show` is a read-only fold.
    CommandDescriptor(
        name="learner.preferences.show",
        owner_module="learner",
        mutating=False,
        requires_idempotency_key=False,
    ),
    CommandDescriptor(
        name="learner.preferences.set", owner_module="learner", mutating=True, requires_idempotency_key=True
    ),
)


def command_registry() -> tuple[CommandDescriptor, ...]:
    """The registered command surface (cli 3)."""
    return _COMMANDS
