"""Loading the authored program from ``curriculum/`` (curriculum 2, 4; roadmap 2.1).

The program is authored as YAML (levels, tracks, one module per file, topics per
level, lexicon per catalog file, reconstruction texts per topic file, provenance
manifest). The loader reads it into
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

# One file per CEFR level, loaded in pedagogical order; missing files load as
# empty (the skeleton grows level by level -- P.1e authors B1-C2).
TOPIC_FILES = ("a1.yaml", "a2.yaml", "b1.yaml", "b2.yaml", "c1.yaml", "c2.yaml")

# Reconstruction texts (curriculum 2d) live one file per topic; the directory is
# optional exactly like the other authored inputs.
TEXTS_SUBDIR = ("texts", "reconstruction")

# Placement forms (flows/placement; assessments 3) live one file per form under
# ``curriculum/assessments``; the directory is optional in the same way, so a
# snapshot registered before the forms existed still resolves.
ASSESSMENTS_SUBDIR = ("assessments",)


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolved_topic_title(topic: dict[str, Any]) -> str:
    """Learner-facing title, authored when available and deterministic otherwise."""
    authored = str(topic.get("title") or "").strip()
    if authored:
        return authored
    tail = str(topic.get("id") or "English topic").rsplit(".", 1)[-1]
    return tail.replace("-", " ").replace("_", " ").strip().title()


def load_program(root: Path) -> dict[str, Any]:
    """Load the whole authored program from ``root`` (usually ``curriculum/``).

    Returns a plain dict: ``levels``, ``tracks``, ``modules``, ``topics``,
    ``lexicon``, ``texts``, ``placement_forms``, ``provenance``. Missing
    optional files load as empty lists -- including ``texts`` and
    ``placement_forms``, so a snapshot registered before the reconstruction
    corpus or the placement forms existed still resolves (readers use
    ``program.get("texts", [])``).
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
    for topic in topics:
        # All 275 topics now expose a title through the loaded/snapshotted
        # contract. Authors can replace this compatibility title in YAML
        # without changing any consumer schema.
        topic["title"] = _resolved_topic_title(topic)

    lexicon: list[dict[str, Any]] = []
    lexicon_dir = root / "lexicon"
    if lexicon_dir.is_dir():
        for path in sorted(lexicon_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            loaded = _read_yaml(path) or {}
            lexicon.extend(loaded.get("lexical_items", []))

    texts: list[dict[str, Any]] = []
    texts_dir = root.joinpath(*TEXTS_SUBDIR)
    if texts_dir.is_dir():
        for path in sorted(texts_dir.glob("*.yaml")):
            loaded = _read_yaml(path) or {}
            schema_version = loaded.get("schema_version")
            for entry in loaded.get("texts", []):
                if isinstance(entry, dict) and schema_version is not None:
                    # The file-level schema_version is stamped on every entry so
                    # the validator stays total over one flat list (the same
                    # shape the lexicon has) instead of needing the file tree.
                    entry.setdefault("schema_version", schema_version)
                texts.append(entry)

    placement_forms: list[dict[str, Any]] = []
    forms_dir = root.joinpath(*ASSESSMENTS_SUBDIR)
    if forms_dir.is_dir():
        # One file = one authored form, in file order (the form_version is the
        # deterministic seed, so the order only fixes the snapshot bytes).
        for path in sorted(forms_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            loaded = _read_yaml(path)
            if isinstance(loaded, dict) and loaded:
                placement_forms.append(loaded)

    provenance_path = root / "lexicon" / "_provenance.yaml"
    provenance = _read_yaml(provenance_path) if provenance_path.exists() else {}

    return {
        "levels": levels,
        "tracks": tracks,
        "modules": modules,
        "topics": topics,
        "lexicon": lexicon,
        "texts": texts,
        "placement_forms": placement_forms,
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


def rubric_profile_refs(root: Path) -> frozenset[str]:
    """Every ``rubric:<profile_id>`` the shipped rubric policies define.

    The placement forms reference rubric profiles by ref, and a dangling ref
    would only surface when a learner's writing fragment could not be assessed
    -- so the curriculum validator resolves them at authoring time. The refs
    come from the policy FILES shipped beside the program, which is exactly
    what ``curriculum activate`` registers.
    """
    refs: set[str] = set()
    for kind, _version, payload in load_policies(root):
        if kind != "rubric":
            continue
        for profile_id, profile in (payload.get("rubric_profiles") or {}).items():
            ref = profile.get("rubric_ref") if isinstance(profile, dict) else None
            refs.add(str(ref) if ref else f"rubric:{profile_id}")
    return frozenset(refs)


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
