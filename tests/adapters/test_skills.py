"""Agent Skills: parsing, deterministic sync, read-only validate, resolve
(adapters 2-4; roadmap 2.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.adapters.errors import SkillInvalid, SkillUnavailable
from english_trainer.adapters.skills import (
    discover_canonical_skills,
    load_canonical_skill,
    parse_skill,
    resolve,
    sync,
    validate,
)
from english_trainer.kernel.clock import FixedClock

EPOCH = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)

_VALID_SKILL = """---
name: demo-skill
version: "1"
description: "A demo skill for tests."
required_inputs:
  - "--provider"
forbidden_actions:
  - "не выставлять score самому"
cli_calls:
  - session.start
  - session.finish
outputs:
  - "session summary"
postconditions:
  - "session FINISHED or ABANDONED"
---

## Steps

1. Do the thing.
"""


def _write_canon(root: Path, name: str, text: str = _VALID_SKILL) -> Path:
    canon = root / "agent-skills"
    skill_dir = canon / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return canon


# -- parsing ------------------------------------------------------------------


def test_parse_skill_reads_frontmatter_and_body() -> None:
    skill = parse_skill(_VALID_SKILL, source="demo-skill/SKILL.md")
    assert skill.name == "demo-skill"
    assert skill.version == "1"
    assert skill.cli_calls == ("session.start", "session.finish")
    assert skill.forbidden_actions == ("не выставлять score самому",)
    assert "Do the thing" in skill.body
    assert skill.content_hash  # a real hash was computed


def test_parse_skill_rejects_missing_field() -> None:
    broken = _VALID_SKILL.replace("cli_calls:\n  - session.start\n  - session.finish\n", "")
    with pytest.raises(SkillInvalid, match="cli_calls"):
        parse_skill(broken, source="demo-skill/SKILL.md")


def test_parse_skill_rejects_unclosed_frontmatter() -> None:
    with pytest.raises(SkillInvalid, match="frontmatter"):
        parse_skill("---\nname: x\n", source="x/SKILL.md")


def test_load_canonical_skill_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(SkillUnavailable):
        load_canonical_skill(tmp_path / "agent-skills", "does-not-exist")


def test_discover_canonical_skills_is_sorted(tmp_path: Path) -> None:
    canon = tmp_path / "agent-skills"
    _write_canon(tmp_path, "zzz-skill", _VALID_SKILL.replace("demo-skill", "zzz-skill"))
    _write_canon(tmp_path, "aaa-skill", _VALID_SKILL.replace("demo-skill", "aaa-skill"))
    skills = discover_canonical_skills(canon)
    assert [skill.name for skill in skills] == ["aaa-skill", "zzz-skill"]


def test_discover_canonical_skills_on_missing_dir_is_empty(tmp_path: Path) -> None:
    assert discover_canonical_skills(tmp_path / "nope") == ()


# -- resolve --------------------------------------------------------------


def test_resolve_returns_pinned_content(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    skill = resolve("demo-skill", "1", canon)
    assert skill.name == "demo-skill"
    assert skill.version == "1"


def test_resolve_raises_on_wrong_version(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    with pytest.raises(SkillUnavailable, match="version"):
        resolve("demo-skill", "2", canon)


def test_resolve_raises_on_missing_skill(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    with pytest.raises(SkillUnavailable):
        resolve("no-such-skill", "1", canon)


# -- sync ---------------------------------------------------------------


def test_sync_is_idempotent_and_byte_identical(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    manifest_path = tmp_path / "skill_sync_manifest.json"
    clock = FixedClock(EPOCH)

    first = sync(canon, [codex, claude], manifest_path, clock)
    assert first["skills"] == 1
    assert first["unchanged"] == 0
    assert len(first["written"]) == 2  # one copy per target
    codex_copy = codex / "demo-skill" / "SKILL.md"
    claude_copy = claude / "demo-skill" / "SKILL.md"
    assert codex_copy.read_bytes() == (canon / "demo-skill" / "SKILL.md").read_bytes()
    assert claude_copy.read_bytes() == (canon / "demo-skill" / "SKILL.md").read_bytes()
    assert manifest_path.exists()

    # A second sync over unchanged canon writes zero bytes (adapters 4.1).
    second = sync(canon, [codex, claude], manifest_path, clock)
    assert second["written"] == []
    assert second["unchanged"] == 2


def test_sync_missing_canon_raises(tmp_path: Path) -> None:
    from english_trainer.adapters.errors import AdapterError

    with pytest.raises(AdapterError):
        sync(tmp_path / "nope", [tmp_path / "targets"], tmp_path / "manifest.json", FixedClock(EPOCH))


# -- validate -------------------------------------------------------------


def test_validate_is_clean_right_after_sync(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    sync(canon, [codex, claude], tmp_path / "manifest.json", FixedClock(EPOCH))

    violations = validate(canon, [codex, claude], ["session.start", "session.finish"])
    assert violations == []


def test_validate_catches_hand_edited_copy_as_drift(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    sync(canon, [codex, claude], tmp_path / "manifest.json", FixedClock(EPOCH))

    copy = codex / "demo-skill" / "SKILL.md"
    copy.write_text(copy.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")

    violations = validate(canon, [codex, claude], ["session.start", "session.finish"])
    drift = [v for v in violations if v["kind"] == "drift"]
    assert len(drift) == 1
    assert drift[0]["skill"] == "demo-skill"
    assert str(copy) == drift[0]["target"]


def test_validate_catches_canon_edited_without_resync(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    sync(canon, [codex, claude], tmp_path / "manifest.json", FixedClock(EPOCH))

    # The canon changes AFTER sync -- the copies are now stale, in the other
    # direction (adapters 4.1: drift is caught both ways).
    (canon / "demo-skill" / "SKILL.md").write_text(
        _VALID_SKILL.replace("A demo skill for tests.", "A CHANGED demo skill."), encoding="utf-8"
    )

    violations = validate(canon, [codex, claude], ["session.start", "session.finish"])
    drift_targets = {v["target"] for v in violations if v["kind"] == "drift"}
    assert str(codex / "demo-skill" / "SKILL.md") in drift_targets
    assert str(claude / "demo-skill" / "SKILL.md") in drift_targets


def test_validate_catches_unresolvable_cli_call(tmp_path: Path) -> None:
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    sync(canon, [codex, claude], tmp_path / "manifest.json", FixedClock(EPOCH))

    # `session.finish` is not in this registry's known command names.
    violations = validate(canon, [codex, claude], ["session.start"])
    unresolvable = [v for v in violations if v["kind"] == "unresolvable_call"]
    assert len(unresolvable) == 1
    assert "session.finish" in unresolvable[0]["message"]


def test_validate_catches_broken_structure(tmp_path: Path) -> None:
    canon = tmp_path / "agent-skills"
    broken_dir = canon / "broken-skill"
    broken_dir.mkdir(parents=True)
    (broken_dir / "SKILL.md").write_text("not frontmatter at all", encoding="utf-8")

    violations = validate(canon, [tmp_path / ".agents" / "skills"], ["session.start"])
    assert len(violations) == 1
    assert violations[0]["kind"] == "structure"
    assert violations[0]["skill"] == "broken-skill"


def test_validate_defaults_to_the_live_command_registry(tmp_path: Path) -> None:
    # No third argument: validate must resolve `command_registry()` itself
    # (adapters depends on cli.registry for exactly this).
    canon = _write_canon(tmp_path, "demo-skill")
    codex = tmp_path / ".agents" / "skills"
    claude = tmp_path / ".claude" / "skills"
    sync(canon, [codex, claude], tmp_path / "manifest.json", FixedClock(EPOCH))

    violations = validate(canon, [codex, claude])
    assert violations == []  # session.start / session.finish are real commands
