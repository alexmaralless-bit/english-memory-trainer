"""Skill lifecycle event names (adapters 3; canon [P0-Q3]).

``SKILL_REQUIRED`` is engine-emitted, inside the ``session.start`` UnitOfWork,
once every required skill has resolved (lessons 4b [P0-Q1]): it records that
the session's manifest pinned a given skill at a given version.

``SKILL_STARTED`` / ``SKILL_COMPLETED`` / ``SKILL_FAILED`` are self-reported by
the agent, not the engine, and are named here only. They are **UNTRUSTED**:
they are not evidence, never move Mastery, and do not by themselves close a
Tutor Compliance obligation -- only observable CLI calls and the domain events
they produce do (adapters 3, scoring 5). A ``SKILL_COMPLETED`` unaccompanied by
any matching domain effect means the agent reported work that never happened;
that mismatch is itself the diagnostic signal, not something this increment
double-checks by emitting the event for the agent. Emitting them is out of
engine scope here: there is no agent self-report channel yet, and inventing
one would fabricate compliance data before the reporting protocol exists.
"""

from __future__ import annotations

SKILL_REQUIRED = "skill.required"
SKILL_STARTED = "skill.started"
SKILL_COMPLETED = "skill.completed"
SKILL_FAILED = "skill.failed"
