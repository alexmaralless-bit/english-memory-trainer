"""rubric@1 structural validation (P.5 [PD-2026-07-22]): the shipped payload
is valid, and every canon-named violation class is refused."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.evidence.rubric import RubricPolicyInvalid, require_valid, validate_rubric_policy

REPO = Path(__file__).resolve().parents[2]


def payload() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "rubric-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_shipped_payload_is_valid() -> None:
    p = payload()
    assert validate_rubric_policy(p) == []
    assert len(p["criterion_catalog"]) == 13
    assert len(p["rubric_profiles"]) == 9
    assert len(p["machine_operations"]) == 9
    assert len(p["error_families"]) == 18
    assert len(p["default_rubric_map"]["entries"]) == 10


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (
            lambda p: p["rubric_profiles"]["production.controlled"]["criteria"][0].update(weight_units=1),
            "weights sum",
        ),
        (lambda p: p["level_scale"].pop("2"), "levels 0..3"),
        (lambda p: p["level_scale"]["1"].update(level_ppm=500000), "level_ppm must be"),
        (
            lambda p: p["default_rubric_map"]["entries"].append(dict(p["default_rubric_map"]["entries"][0])),
            "duplicate",
        ),
        (
            lambda p: p["default_rubric_map"]["entries"][0].update(rubric_ref="rubric:ghost"),
            "dangling rubric_ref",
        ),
        (
            lambda p: p["rubric_profiles"]["conversation.free"].update(rubric_ref="rubric:wrong"),
            "must be rubric:conversation.free",
        ),
        (lambda p: next(iter(p["error_families"].values())).update(severity="fatal"), "severity must be"),
        (
            lambda p: next(iter(p["error_families"].values())).update(score_criterion_id="ghost"),
            "dangling score_criterion_id",
        ),
    ],
)
def test_violations_are_refused(mutate: Any, fragment: str) -> None:
    broken = copy.deepcopy(payload())
    mutate(broken)
    with pytest.raises(RubricPolicyInvalid, match=fragment):
        require_valid(broken)
