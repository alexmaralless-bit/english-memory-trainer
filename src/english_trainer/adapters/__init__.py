"""Adapters: the tutor is a replaceable part (contract adapters; roadmap 2.5).

Owns the canonical Agent Skills (``agent-skills/``), lays them out as
deterministic copies for Codex (``.agents/skills/``) and Claude Code
(``.claude/skills/``), and checks that switching tutors does not change what
happens to the learner. A skill is a hint, not an enforcement mechanism: the
engine's own invariants -- via :mod:`~english_trainer.cli` -- are what make
learning correct; skills only raise the odds a tutor behaves well. Whether it
did is measured after the fact (Tutor Compliance, scoring 5), never assumed.
"""

from __future__ import annotations

from english_trainer.adapters.compare import (
    DEFAULT_FIXTURES,
    FixtureResult,
    ParityFixture,
    compare,
)
from english_trainer.adapters.errors import AdapterError, SkillDrift, SkillInvalid, SkillUnavailable
from english_trainer.adapters.events import (
    SKILL_COMPLETED,
    SKILL_FAILED,
    SKILL_REQUIRED,
    SKILL_STARTED,
)
from english_trainer.adapters.skills import (
    CANONICAL_SKILL_NAMES,
    ParsedSkill,
    SkillSyncManifest,
    discover_canonical_skills,
    load_canonical_skill,
    manifest_path_for,
    parse_skill,
    resolve,
    sync,
    validate,
)

__all__ = [
    "CANONICAL_SKILL_NAMES",
    "DEFAULT_FIXTURES",
    "SKILL_COMPLETED",
    "SKILL_FAILED",
    "SKILL_REQUIRED",
    "SKILL_STARTED",
    "AdapterError",
    "FixtureResult",
    "ParityFixture",
    "ParsedSkill",
    "SkillDrift",
    "SkillInvalid",
    "SkillSyncManifest",
    "SkillUnavailable",
    "compare",
    "discover_canonical_skills",
    "load_canonical_skill",
    "manifest_path_for",
    "parse_skill",
    "resolve",
    "sync",
    "validate",
]
