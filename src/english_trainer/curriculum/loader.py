"""Loading the authored program from ``curriculum/`` (curriculum 2, 4; roadmap 2.1).

The program is authored as YAML (levels, tracks, one module per file, topics per
level, lexicon per catalog file, provenance manifest). The loader reads it into
one plain in-memory structure; it validates nothing -- validation is a separate,
total pass (:mod:`~english_trainer.curriculum.validate`), so a broken file still
loads far enough to be *reported* rather than crashing the tool.

``snapshot_payload`` turns a loaded program into the immutable policy snapshot
registered under the ``curriculum`` kind (foundation 3.6). Canonical encoding
bans floats (they have no single representation at rest), while the authored
lexicon carries corpus ``frequency_score`` floats -- at this boundary every
non-integer number becomes its shortest-repr string, deterministically, so the
same files always produce the same snapshot hash.
"""

from __future__ import annotations

import datetime as _datetime
from pathlib import Path
from typing import Any

import yaml

TOPIC_FILES = ("a1.yaml", "a2.yaml", "b1.yaml")


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_program(root: Path) -> dict[str, Any]:
    """Load the whole authored program from ``root`` (usually ``curriculum/``).

    Returns a plain dict: ``levels``, ``tracks``, ``modules``, ``topics``,
    ``lexicon``, ``provenance``. Missing optional files load as empty lists.
    """
    levels = (_read_yaml(root / "levels.yaml") or {}).get("levels", [])
    tracks = (_read_yaml(root / "tracks.yaml") or {}).get("tracks", [])

    modules: list[dict[str, Any]] = []
    modules_dir = root / "modules"
    if modules_dir.is_dir():
        for path in sorted(modules_dir.glob("*.yaml")):
            loaded = _read_yaml(path)
            if loaded:
                modules.append(loaded)

    topics: list[dict[str, Any]] = []
    topics_dir = root / "topics"
    if topics_dir.is_dir():
        for name in TOPIC_FILES:
            path = topics_dir / name
            if path.exists():
                topics.extend((_read_yaml(path) or {}).get("topics", []))

    lexicon: list[dict[str, Any]] = []
    lexicon_dir = root / "lexicon"
    if lexicon_dir.is_dir():
        for path in sorted(lexicon_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            loaded = _read_yaml(path) or {}
            lexicon.extend(loaded.get("lexical_items", []))

    provenance_path = root / "lexicon" / "_provenance.yaml"
    provenance = _read_yaml(provenance_path) if provenance_path.exists() else {}

    return {
        "levels": levels,
        "tracks": tracks,
        "modules": modules,
        "topics": topics,
        "lexicon": lexicon,
        "provenance": provenance or {},
    }


def _normalize(value: Any) -> Any:
    """Make a loaded value canonically encodable, deterministically.

    Floats become their shortest-repr strings (the canonical payload contract
    bans floats: one value, one byte form; ``repr`` is platform- and
    hash-seed-independent). YAML timestamps (``retrieved_at`` in provenance)
    become ISO strings.
    """
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, _datetime.datetime | _datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def snapshot_payload(program: dict[str, Any]) -> dict[str, Any]:
    """The immutable, canonically-encodable snapshot of a loaded program."""
    normalized = _normalize(program)
    return {"schema_version": 1, **normalized}


def load_policies(root: Path) -> list[tuple[str, str, dict[str, Any]]]:
    """Engine policies shipped with the curriculum (``policies/*.yaml``).

    Returns ``(kind, version_id, payload)`` per file, deterministically
    ordered. The kind is the ``policy_id`` prefix before ``@`` (so
    ``control@1`` registers under kind ``control``); a file without a
    ``policy_id`` is skipped -- validation, not loading, reports shape
    problems. Floats are NOT normalized away here: a float in a policy is a
    contract violation the validator must refuse, not a value to launder.
    """
    policies_dir = root / "policies"
    out: list[tuple[str, str, dict[str, Any]]] = []
    if not policies_dir.is_dir():
        return out
    for path in sorted(policies_dir.glob("*.yaml")):
        loaded = _read_yaml(path)
        if not isinstance(loaded, dict):
            continue
        policy_id = str(loaded.get("policy_id", ""))
        if "@" not in policy_id:
            continue
        out.append((policy_id.split("@")[0], policy_id, loaded))
    return out
