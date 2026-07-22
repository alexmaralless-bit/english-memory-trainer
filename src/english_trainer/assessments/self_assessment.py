"""Self-assessment on decline: a per-core-skill object, never a scalar
(assessments 5 [R-5]; flows/placement rereview A-R3).

When a learner declines placement they MAY report a working estimate of their
level. The canon forbids a bare scalar: from ``"A2"`` the engine could not tell
whether the learner means one global estimate or A2 in every skill, so a scalar
is rejected with a stable error. The admitted shape is an object keyed by
core-skill id::

    {"schema_version": 1, "levels": {"grammar": "A2", "reading": "B1"}}

A partial object is allowed -- a missing skill stays ``unknown`` and gets no
default and no broadcast of another skill's value. Each reported level is a
provisional working estimate, fully overridden by the first admissible evidence
for *that* skill (learner model; out of this module's scope, captured for the
consumer in the event).
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.errors import KernelError

SELF_ASSESSMENT_SCHEMA_VERSION = 1


class SelfAssessmentInvalid(KernelError):
    """The self-assessment is not the admitted per-skill object (R-5).

    Distinct, stable code so an agent can branch on it: a scalar, an unknown
    skill id, or an out-of-range CEFR level all refuse here rather than being
    silently coerced.
    """

    code = "SELF_ASSESSMENT_INVALID"


def normalize_self_assessment(
    self_assessment: Any,
    *,
    core_skills: tuple[str, ...],
    cefr_levels: tuple[str, ...],
) -> dict[str, str]:
    """Validate and return ``{skill: level}`` for the provided skills only.

    Raises :class:`SelfAssessmentInvalid` for a scalar, a non-object payload, an
    unknown skill id, a non-string/out-of-range level, or a wrong schema
    version. Missing skills are simply absent from the result (``unknown``).
    """
    if isinstance(self_assessment, (str, int, float, bool)):
        raise SelfAssessmentInvalid(
            "self_assessment must be an object keyed by core-skill id, not a scalar "
            "level: a single value cannot say whether it means one skill or all four (R-5)"
        )
    if not isinstance(self_assessment, dict):
        raise SelfAssessmentInvalid("self_assessment must be a JSON object with schema_version and levels")
    if self_assessment.get("schema_version") != SELF_ASSESSMENT_SCHEMA_VERSION:
        raise SelfAssessmentInvalid(
            f"self_assessment.schema_version must be {SELF_ASSESSMENT_SCHEMA_VERSION}"
        )
    levels = self_assessment.get("levels")
    if not isinstance(levels, dict):
        raise SelfAssessmentInvalid("self_assessment.levels must be an object keyed by core-skill id")

    reported: dict[str, str] = {}
    for skill, level in levels.items():
        if skill not in core_skills:
            raise SelfAssessmentInvalid(
                f"self_assessment.levels: {skill!r} is not a core skill {sorted(core_skills)}"
            )
        if not isinstance(level, str) or level not in cefr_levels:
            raise SelfAssessmentInvalid(
                f"self_assessment.levels.{skill}: {level!r} is not a CEFR level {list(cefr_levels)}"
            )
        reported[skill] = level
    # A partial object (including an empty levels map) is admissible: the missing
    # skills stay unknown, never defaulted.
    return dict(sorted(reported.items()))
