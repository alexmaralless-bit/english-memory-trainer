"""The canonical Agent Skills: parsing, deterministic sync, validate, resolve
(adapters 2-4; CLAUDE.md "agent-skills/... synced as deterministic copies").

Canon lives at ``agent-skills/<name>/SKILL.md``. ``.agents/skills/`` (Codex)
and ``.claude/skills/`` (Claude Code) are derived, byte-identical copies --
never hand-edited. A skill is a short markdown file with YAML frontmatter
(name, version, description, required_inputs, forbidden_actions, cli_calls,
outputs, postconditions) followed by a ``## Steps`` body; the skill is a
*hint* to the tutor, never a mechanism the engine relies on for correctness
(adapters 1).

Three operations, deliberately separate:

- :func:`sync` -- write deterministic copies into every target dir. Idempotent:
  unchanged canon rewrites zero bytes (mirrors ``memory.render``'s
  write-only-if-changed discipline).
- :func:`validate` -- read-only. Checks structure, that every ``cli_call``
  resolves in ``command_registry()``, and drift in *both* directions (a copy
  edited by hand, or the canon edited without a following sync). Never fixes
  anything; only ``sync`` does (adapters 4.1).
- :func:`resolve` -- the pinned-version lookup ``lessons.start_session`` calls
  synchronously, before any session aggregate is written (lessons 4b [P0-Q1]).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from english_trainer.adapters.errors import SkillDrift, SkillInvalid, SkillUnavailable
from english_trainer.kernel.clock import Clock
from english_trainer.kernel.encoding import payload_hash
from english_trainer.storage.layout import StorageLayout

SKILL_FILENAME = "SKILL.md"

# The canonical set named by adapters 2. Not enforced by `sync`/`validate` --
# any subdirectory of `agent_skills_dir` carrying a well-formed SKILL.md is
# synced and validated -- but named here for reference and for tests that
# assert the shipped canon matches the contract exactly.
CANONICAL_SKILL_NAMES: tuple[str, ...] = (
    "run-english-session",
    "run-placement-assessment",
    "run-spaced-review",
    "teach-english-topic",
    "coach-english-conversation",
    "correct-learner-output",
    "assess-english-gate",
    "finish-english-session",
    "audit-english-tutor",
    "maintain-english-curriculum",
)

_REQUIRED_FIELDS = (
    "name",
    "version",
    "description",
    "required_inputs",
    "forbidden_actions",
    "cli_calls",
    "outputs",
    "postconditions",
)
_LIST_FIELDS = (
    "required_inputs",
    "forbidden_actions",
    "cli_calls",
    "outputs",
    "postconditions",
)
_DELIM = "---"


@dataclass(frozen=True)
class ParsedSkill:
    """One parsed ``SKILL.md`` -- frontmatter fields plus the markdown body."""

    name: str
    version: str
    description: str
    required_inputs: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    cli_calls: tuple[str, ...]
    outputs: tuple[str, ...]
    postconditions: tuple[str, ...]
    body: str
    content_hash: str


@dataclass(frozen=True)
class SkillSyncManifest:
    """One skill's sync record (adapters 2): what and where, and its hash."""

    skill_name: str
    version: str
    content_hash: str
    targets: tuple[str, ...]
    synced_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "version": self.version,
            "content_hash": self.content_hash,
            "targets": list(self.targets),
            "synced_at": self.synced_at,
        }


def _split_frontmatter(text: str, *, source: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIM:
        raise SkillInvalid(f"{source}: must start with a '---' frontmatter block")
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIM:
            frontmatter_text = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            try:
                parsed = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError as exc:
                raise SkillInvalid(f"{source}: frontmatter is not valid YAML: {exc}") from exc
            if not isinstance(parsed, dict):
                raise SkillInvalid(f"{source}: frontmatter must be a YAML mapping")
            return parsed, body
    raise SkillInvalid(f"{source}: frontmatter is not closed with a second '---'")


def parse_skill(text: str, *, source: str) -> ParsedSkill:
    """Parse one ``SKILL.md`` document (frontmatter + body).

    Content hash via :func:`~english_trainer.kernel.encoding.payload_hash` over
    the raw text (adapters 4.1): any byte difference -- not just a structural
    one -- is what ``validate`` treats as drift.
    """
    frontmatter, body = _split_frontmatter(text, source=source)
    missing = [field for field in _REQUIRED_FIELDS if field not in frontmatter]
    if missing:
        raise SkillInvalid(f"{source}: missing frontmatter field(s): {', '.join(missing)}")
    for field in _LIST_FIELDS:
        value = frontmatter[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise SkillInvalid(f"{source}: {field} must be a list of strings")
    description = str(frontmatter["description"])
    if not description.strip():
        raise SkillInvalid(f"{source}: description must not be empty")
    name = str(frontmatter["name"])
    if not name.strip():
        raise SkillInvalid(f"{source}: name must not be empty")
    return ParsedSkill(
        name=name,
        version=str(frontmatter["version"]),
        description=description,
        required_inputs=tuple(frontmatter["required_inputs"]),
        forbidden_actions=tuple(frontmatter["forbidden_actions"]),
        cli_calls=tuple(frontmatter["cli_calls"]),
        outputs=tuple(frontmatter["outputs"]),
        postconditions=tuple(frontmatter["postconditions"]),
        body=body,
        content_hash=payload_hash({"content": text}),
    )


def load_canonical_skill(agent_skills_dir: Path | str, name: str) -> ParsedSkill:
    """Parse ``<agent_skills_dir>/<name>/SKILL.md``; raise if it is missing."""
    path = Path(agent_skills_dir) / name / SKILL_FILENAME
    if not path.is_file():
        raise SkillUnavailable(f"canonical skill {name!r} not found under {agent_skills_dir}")
    return parse_skill(path.read_text(encoding="utf-8"), source=f"{name}/{SKILL_FILENAME}")


def discover_canonical_skills(agent_skills_dir: Path | str) -> tuple[ParsedSkill, ...]:
    """Every canonical skill under ``agent_skills_dir``, sorted by name.

    A subdirectory without a ``SKILL.md`` is silently not a skill (nothing to
    sync); a subdirectory WITH one that fails to parse propagates
    :class:`~english_trainer.adapters.errors.SkillInvalid` -- sync must not
    silently skip a broken canon file.
    """
    root = Path(agent_skills_dir)
    if not root.is_dir():
        return ()
    names = sorted(entry.name for entry in root.iterdir() if (entry / SKILL_FILENAME).is_file())
    return tuple(load_canonical_skill(root, name) for name in names)


def resolve(name: str, version: str, agent_skills_dir: Path | str) -> ParsedSkill:
    """Return the pinned skill content, or raise :class:`SkillUnavailable`.

    This is the synchronous check ``lessons.start_session`` runs BEFORE
    opening its commit UnitOfWork (lessons 4b [P0-Q1]): a session never gets
    created if a required skill fails to resolve here.
    """
    skill = load_canonical_skill(agent_skills_dir, name)
    if skill.version != str(version):
        raise SkillUnavailable(
            f"skill {name!r} version {version!r} is unavailable; canon is at version {skill.version!r}"
        )
    return skill


def manifest_path_for(layout: StorageLayout) -> Path:
    """Where the :class:`SkillSyncManifest` lives (adapters 6: storage owns
    the path, via :class:`~english_trainer.storage.layout.StorageLayout`)."""
    return layout.skills_manifest


def sync(
    agent_skills_dir: Path | str,
    targets: Sequence[Path | str],
    manifest_path: Path | str,
    clock: Clock,
) -> dict[str, Any]:
    """Deterministic copies of every canonical skill into each target dir.

    Idempotent (adapters 4.1): a target whose bytes already match the canon is
    left untouched -- a second ``sync`` over unchanged canon writes zero bytes.
    Writes ``manifest_path`` as JSON: one :class:`SkillSyncManifest` entry per
    skill.
    """
    canon_dir = Path(agent_skills_dir)
    if not canon_dir.is_dir():
        from english_trainer.adapters.errors import AdapterError

        raise AdapterError(f"{canon_dir} does not exist; nothing to sync")
    target_dirs = [Path(target) for target in targets]
    skills = discover_canonical_skills(canon_dir)
    now = clock.now().isoformat()

    written: list[str] = []
    unchanged = 0
    manifest_entries: list[dict[str, Any]] = []
    for skill in skills:
        raw = (canon_dir / skill.name / SKILL_FILENAME).read_bytes()
        target_paths: list[str] = []
        for target_dir in target_dirs:
            dest = target_dir / skill.name / SKILL_FILENAME
            dest.parent.mkdir(parents=True, exist_ok=True)
            target_paths.append(str(dest))
            if dest.exists() and dest.read_bytes() == raw:
                unchanged += 1
                continue
            dest.write_bytes(raw)
            written.append(str(dest))
        manifest_entries.append(
            SkillSyncManifest(
                skill_name=skill.name,
                version=skill.version,
                content_hash=skill.content_hash,
                targets=tuple(target_paths),
                synced_at=now,
            ).as_dict()
        )

    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(
        json.dumps(manifest_entries, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "skills": len(skills),
        "targets": [str(target) for target in target_dirs],
        "written": written,
        "unchanged": unchanged,
        "manifest": manifest_entries,
    }


def validate(
    agent_skills_dir: Path | str,
    targets: Sequence[Path | str],
    registry_command_names: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Read-only violations: structure, unresolvable ``cli_calls``, drift.

    Never repairs anything -- only ``sync`` does (adapters 4.1, cli 4.4). Each
    violation is ``{skill, kind, target, code, message}`` with ``kind`` one of
    ``"structure"``, ``"unresolvable_call"`` (both map to ``INVALID_INPUT``)
    or ``"drift"`` (maps to ``PRECONDITION_FAILED`` + ``next_action:
    skills.sync``) -- the CLI 4.2 distinction, decided here so the CLI layer
    only has to dispatch on ``kind``.

    ``registry_command_names`` defaults to the live ``command_registry()``
    (adapters depends on ``cli.registry`` for exactly this, adapters 6); a
    caller may pass an explicit iterable instead (e.g. in tests).
    """
    canon_dir = Path(agent_skills_dir)
    target_dirs = [Path(target) for target in targets]
    if registry_command_names is None:
        from english_trainer.cli.registry import command_registry

        registry_command_names = [descriptor.name for descriptor in command_registry()]
    known_commands = set(registry_command_names)

    violations: list[dict[str, Any]] = []
    if not canon_dir.is_dir():
        violations.append(
            {
                "skill": None,
                "kind": "structure",
                "target": None,
                "code": SkillInvalid.code,
                "message": f"{canon_dir} does not exist: no canon to validate",
            }
        )
        return violations

    names = sorted(entry.name for entry in canon_dir.iterdir() if entry.is_dir())
    for name in names:
        path = canon_dir / name / SKILL_FILENAME
        if not path.is_file():
            violations.append(
                {
                    "skill": name,
                    "kind": "structure",
                    "target": None,
                    "code": SkillInvalid.code,
                    "message": f"{name}: missing {SKILL_FILENAME}",
                }
            )
            continue
        raw_canon = path.read_bytes()
        try:
            skill = parse_skill(raw_canon.decode("utf-8"), source=f"{name}/{SKILL_FILENAME}")
        except SkillInvalid as exc:
            violations.append(
                {"skill": name, "kind": "structure", "target": None, "code": exc.code, "message": str(exc)}
            )
            continue

        for call in skill.cli_calls:
            if call not in known_commands:
                violations.append(
                    {
                        "skill": name,
                        "kind": "unresolvable_call",
                        "target": None,
                        "code": SkillInvalid.code,
                        "message": f"{name}: cli_call {call!r} does not resolve in command_registry()",
                    }
                )

        for target_dir in target_dirs:
            dest = target_dir / name / SKILL_FILENAME
            if not dest.is_file():
                violations.append(
                    {
                        "skill": name,
                        "kind": "drift",
                        "target": str(dest),
                        "code": SkillDrift.code,
                        "message": f"{name}: not synced to {dest} (`trainer skills sync`)",
                    }
                )
                continue
            if dest.read_bytes() != raw_canon:
                violations.append(
                    {
                        "skill": name,
                        "kind": "drift",
                        "target": str(dest),
                        "code": SkillDrift.code,
                        "message": f"{name}: {dest} has diverged from canon (`trainer skills sync`)",
                    }
                )
    return violations
