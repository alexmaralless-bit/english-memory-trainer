"""Curriculum module: the authored program as data plus its engine boundary
(curriculum contract 0.3; roadmap 2.1).

Owns loading the YAML program, total validation, versioned registration in the
kernel policy registry and CAS activation with an atomic activation event. The
program is a map, never a lock system: nothing here blocks anything.
"""

from __future__ import annotations

from english_trainer.curriculum.loader import load_program, snapshot_payload
from english_trainer.curriculum.service import (
    CURRICULUM_KIND,
    EVENT_VERSION_ACTIVATED,
    activate_version,
    active_version,
    get_topic,
    lexicon_query,
    register_version,
)
from english_trainer.curriculum.validate import ValidationReport, validate_program

__all__ = [
    "CURRICULUM_KIND",
    "EVENT_VERSION_ACTIVATED",
    "ValidationReport",
    "activate_version",
    "active_version",
    "get_topic",
    "lexicon_query",
    "load_program",
    "register_version",
    "snapshot_payload",
    "validate_program",
]
