"""Spec-text invariants as a machine-checked gate (PD-2026-07-22).

The canon describes ONE product target: beta/MVP phase tags are banned from
normative spec text -- priority governs order and intensity, never scope
[PD-2026-07-21]. This gate keeps the ban from regressing (the tags once came
back through the authoring template itself).

Exemptions, decided explicitly with the invariant:

- ``wiki/roadmap.md`` -- the status/history document; order and phasing is
  exactly what it exists to record;
- «История изменений» sections of specs -- history is never rewritten;
- ``staging/`` -- append-only journals and review reports quote the old terms.

The pattern covers spelling variants (``post-beta``, ``post_mvp``, ``post
mvp``, ...) and the observed ``psot-*`` typo family, case-insensitively.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PHASE_MARKER = re.compile(r"(?:post|psot)[-_ ]?(?:beta|mvp)|\[mvp\]", re.IGNORECASE)
HISTORY_HEADING = "## История изменений"


def _normative_text(path: Path) -> str:
    """A spec's normative body: everything above its history section."""
    return path.read_text(encoding="utf-8").split(HISTORY_HEADING)[0]


def test_wiki_normative_text_carries_no_phase_markers() -> None:
    violations: list[str] = []
    for path in sorted((REPO / "wiki").rglob("*.md")):
        if path.name == "roadmap.md":
            continue  # status + history live here by constitution
        for number, line in enumerate(_normative_text(path).splitlines(), 1):
            if PHASE_MARKER.search(line):
                violations.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:100]}")
    assert not violations, "phase markers in normative canon (PD-2026-07-22):\n" + "\n".join(violations)


def test_curriculum_data_carries_no_phase_markers() -> None:
    violations: list[str] = []
    for path in sorted((REPO / "curriculum").rglob("*")):
        if path.suffix.lower() not in {".md", ".yaml", ".yml"} or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PHASE_MARKER.search(line):
                violations.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:100]}")
    assert not violations, "phase markers in curriculum data (PD-2026-07-22):\n" + "\n".join(violations)


def test_the_gate_itself_can_fail() -> None:
    # The negative probe: the pattern actually recognizes every variant family.
    for sample in ("post-mvp", "post_beta", "POST MVP", "psot-beta", "[mvp]", "`[post-mvp]`"):
        assert PHASE_MARKER.search(sample), sample
    assert not PHASE_MARKER.search("приоритет управляет порядком, не составом")
