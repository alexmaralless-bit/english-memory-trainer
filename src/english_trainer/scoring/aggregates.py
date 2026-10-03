"""Derived aggregates: working CEFR level, Learning Score, XP (scoring 4-7).

All aggregates are projections over the per-target fold -- they never feed
back into per-target Mastery (no cycles), and every "no data" answer is an
honest ``None``, never a zero: with one learner most aggregates stay noise
for a long time, and pretending otherwise would fake progress (canon 4.10).

- **Working level** (canon 4): per-skill CEFR = the highest whole band with
  coverage -- at least ``min_topics`` distinct topics of that band in state
  ACTIVE or better feeding the skill through the versioned ``core_skill_map``,
  with confidence at or above the floor. An unmeasured area is *unknown* and
  never lifts a level. The overall ``measured_working_level`` is not higher
  than the weakest core skill; any unknown core skill keeps it unknown --
  conservative by contract. Under ``scoring@2`` a skill with no evidence-backed
  level yet may carry the band its last **placement** measured, tagged
  ``confidence: low`` / ``basis: placement`` so a one-shot diagnostic is never
  read as accumulated evidence (canon 4c). The separate
  ``provisional_working_estimate`` adds the claims that are explicitly *not*
  measurements -- the placement's provisional writing band and the learner's
  ``self_reported_level`` -- each flagged ``provisional``, so a learner who has
  just taken the placement gets a starting point without any of it leaking into
  Learning Score or gating.
- **Learning Score** (canon 5): the mean Mastery of ACTIVE+ topics of the
  measured band. ``None`` while the measured level is unknown -- ``no-data``,
  not 0.
- **XP** (canon 7): a pure fold over awardable source events -- finalized
  (assessed) attempts and closed review outcomes -- with mutually exclusive
  eligibility, award-once by source id, and a deterministic daily cap applied
  in ``sequence`` order per UTC practice day (the learner timezone joins with
  the learner module). Being a fold, the ledger is award-once under replay by
  construction; materialized ``XP_AWARDED`` events arrive with the projection
  layer that publishes them outward. Abandoned sessions keep the XP of their
  already-finalized sources; there are no penalties and no deductions.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

from english_trainer.kernel.store import EventStore
from english_trainer.scoring.engine import ACTIVE, MASTERED, TargetState
from english_trainer.scoring.policy import scoring_context

ATTEMPT_RECORDED_EVENT = "attempt.recorded"
PLACEMENT_SCORED_EVENT = "placement.scored"
PLACEMENT_DECLINED_EVENT = "placement.declined"
ATTEMPT_STATE_CHANGED_EVENT = "attempt.state_changed"
REVIEW_OUTCOME_EVENT = "review.outcome"

CONFIDENCE_ORDER = ("very_low", "low", "medium", "high")
#: LexicalItems are not topics and carry no ``track``; the core-skill map
#: addresses them through the lexical track (canon 4).
LEXICON_TRACK = "vocabulary-chunks"
BAND_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")
#: The one core skill a placement never measures objectively (canon 4c).
WRITING_SKILL = "writing"
#: A self-reported level is the weakest possible claim about a skill.
SELF_REPORT_CONFIDENCE = "very_low"
SELF_REPORT_BASIS = "self_report"

_STEADY = (ACTIVE, MASTERED)


def _confidence(count: int, thresholds: dict[str, Any]) -> str:
    if count >= int(thresholds.get("high", 10)):
        return "high"
    if count >= int(thresholds.get("medium", 5)):
        return "medium"
    if count >= int(thresholds.get("low", 2)):
        return "low"
    return "very_low"


def _skills_of_track(policy: dict[str, Any], track: str) -> set[str]:
    """The core skills a track's topics feed at full weight (canon 4)."""
    row = (policy.get("core_skill_map") or {}).get(track) or {}
    skills: set[str] = set()
    for cell in row.values():
        if isinstance(cell, dict) and cell.get("skill") and str(cell.get("weight")) == "1.0":
            skills.add(str(cell["skill"]))
    return skills


def _skill_of_target(policy: dict[str, Any], track: str, dimension: str) -> str | None:
    """The core skill a (track, dimension) pair feeds at FULL weight (canon 4).

    A reduced weight (a reading component of a writing task) is a partial
    contribution to Mastery, never a reason to call the band measured for that
    skill -- so only 1.0 cells map a placement item onto a skill.
    """
    cell = ((policy.get("core_skill_map") or {}).get(track) or {}).get(dimension)
    if isinstance(cell, dict) and cell.get("skill") and str(cell.get("weight")) == "1.0":
        return str(cell["skill"])
    return None


def placement_bands(
    scored_items: list[dict[str, Any]], program: dict[str, Any], policy: dict[str, Any]
) -> dict[str, str]:
    """Per-skill band measured by ONE placement (scoring@2 ``placement``).

    The rule, deliberately conservative: a band counts for a skill when at
    least that skill's floor of **distinct** topics of that band had ALL their
    placement items answered correctly; the highest such band is the skill's
    starting level. A topic with one wrong item does not count at all and an
    unmeasured band is unknown (never "probably fine").

    The floors are per skill (``placement.min_topics_by_skill``,
    [PD-2026-09-22]): a form spends its minutes very differently across skills
    -- a grammar band carries 5-8 one-item topics, a vocabulary band 4-5
    lexical items, a reading band 3 questions on one passage -- so one shared
    floor of 5 would leave reading structurally unmeasurable and cap vocabulary
    at B2. A skill with no floor (writing) is never measured here: it gets the
    provisional rule of :func:`placement_writing_band` instead, which is exactly
    the provisional-only contract of learning-model 6.

    Returns ``{}`` when the pinned policy has no ``placement`` section
    (scoring@1): old pins keep their behaviour byte for byte.
    """
    config = policy.get("placement")
    if not isinstance(config, dict):
        return {}
    floors_cfg = config.get("min_topics_by_skill")
    floors = {
        str(skill): int(floor)
        for skill, floor in (floors_cfg or {}).items()
        if isinstance(floor, int) and not isinstance(floor, bool)
    }
    tracks = {
        str(topic.get("id")): str(topic.get("track") or "")
        for topic in program.get("topics") or []
        if isinstance(topic, dict)
    }
    lexicon = {str(unit.get("id")) for unit in program.get("lexicon") or [] if isinstance(unit, dict)}

    # (skill, band, target) -> every item of that target was correct.
    per_target: dict[tuple[str, str, str], bool] = {}
    for row in scored_items:
        if not isinstance(row, dict):
            continue
        band = str(row.get("band") or "")
        target = str(row.get("target_ref") or "")
        if band not in BAND_ORDER or not target:
            continue
        track = tracks.get(target) or (LEXICON_TRACK if target in lexicon else "")
        skill = _skill_of_target(policy, track, str(row.get("dimension") or ""))
        if skill is None:
            continue
        key = (skill, band, target)
        per_target[key] = per_target.get(key, True) and row.get("correct") is True

    counts: dict[str, dict[str, int]] = {}
    for (skill, band, _target), fully_correct in per_target.items():
        if fully_correct:
            counts.setdefault(skill, {})[band] = counts.setdefault(skill, {}).get(band, 0) + 1
    out: dict[str, str] = {}
    for skill, bands in counts.items():
        floor = floors.get(skill)
        if floor is None:
            continue  # no objective floor for this skill (writing): not measured
        for band in BAND_ORDER:  # ascending: the highest covered band wins
            if bands.get(band, 0) >= floor:
                out[skill] = band
    return out


def placement_writing_band(scored_items: list[dict[str, Any]], policy: dict[str, Any]) -> str | None:
    """The PROVISIONAL writing band of one placement (learning-model 6).

    Writing is never measured objectively here: the highest band whose writing
    item was settled by the rubric at or above
    ``placement.writing.provisional_threshold_ppm`` becomes a *provisional*
    estimate, carried with ``confidence: very_low`` and ``basis: placement`` and
    never entering ``measured_working_level`` -- the full writing band still
    needs >= 2 independent non-placement items (canon 4b). A fragment below the
    threshold says nothing at all: ``None``, never a lower band.
    """
    config = policy.get("placement")
    if not isinstance(config, dict):
        return None
    writing_cfg = config.get("writing")
    if not isinstance(writing_cfg, dict):
        return None
    threshold = writing_cfg.get("provisional_threshold_ppm")
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        return None
    best: str | None = None
    for row in scored_items:
        if not isinstance(row, dict) or row.get("basis") != "rubric":
            continue
        band = str(row.get("band") or "")
        score = row.get("score_ppm")
        if band not in BAND_ORDER or isinstance(score, bool) or not isinstance(score, int):
            continue
        if score < threshold:
            continue
        if best is None or BAND_ORDER.index(band) > BAND_ORDER.index(best):
            best = band
    return best


def placement_skill_levels(
    scored_items: list[dict[str, Any]], program: dict[str, Any], policy: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """:func:`placement_bands` decorated with the policy's confidence/basis."""
    config = policy.get("placement") or {}
    bands = placement_bands(scored_items, program, policy)
    confidence = str(config.get("confidence", "low"))
    basis = str(config.get("basis", "placement"))
    return {
        skill: {"level": band, "confidence": confidence, "basis": basis}
        for skill, band in sorted(bands.items())
    }


def last_placement_rows(store: EventStore) -> list[dict[str, Any]]:
    """The scored rows of the learner's LAST ``placement.scored`` fact.

    A fold over published facts -- scoring reads the event log, never the
    assessments module (foundation 4). A later placement replaces an earlier
    one: it is one designated measurement, not accumulating session evidence.
    """
    rows: list[dict[str, Any]] = []
    for event in store.read():  # canonical sequence order: the last one wins
        if event.type == PLACEMENT_SCORED_EVENT:
            rows = [item for item in event.payload.get("scored_items") or [] if isinstance(item, dict)]
    return rows


def placement_levels(store: EventStore, program: dict[str, Any], policy: dict[str, Any]) -> dict[str, str]:
    """Per-skill objective band from the learner's last scored placement."""
    rows = last_placement_rows(store)
    if not rows:
        return {}
    return placement_bands(rows, program, policy)


def placement_writing_level(store: EventStore, policy: dict[str, Any]) -> str | None:
    """The provisional writing band of the learner's last scored placement."""
    rows = last_placement_rows(store)
    if not rows:
        return None
    return placement_writing_band(rows, policy)


def self_reported_levels(store: EventStore) -> dict[str, str]:
    """Per-skill ``self_reported_level`` from the last declined placement.

    Stored and reported strictly apart from anything measured (learner 4): it
    only ever reaches :func:`provisional_working_estimate`, never
    ``measured_working_level``, Learning Score or gating.
    """
    reported: dict[str, str] = {}
    for event in store.read():
        if event.type == PLACEMENT_DECLINED_EVENT:
            levels = event.payload.get("self_reported_levels")
            reported = (
                {str(skill): str(level) for skill, level in levels.items()}
                if isinstance(levels, dict)
                else {}
            )
    return reported


def working_levels(
    scores: dict[str, TargetState],
    program: dict[str, Any],
    policy: dict[str, Any],
    *,
    placement: dict[str, str] | None = None,
    placement_writing: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-skill measured level: highest band with coverage, or unknown.

    ``placement`` supplies the per-skill objective bands of the last scored
    placement (scoring@2). They are a *starting* estimate: they fill only a
    skill whose session evidence does not yet reach the confidence floor, carry
    the policy's ``low`` confidence, and are marked ``basis: placement`` so
    nothing downstream mistakes a one-shot diagnostic for accumulated evidence.
    The first skill-level evidence that clears the floor replaces both the band
    and the basis through the normal rolling rule.

    ``placement_writing`` is the placement's PROVISIONAL writing band
    ([PD-2026-09-22], learning-model 6). It fills the writing row only when
    writing has no measured level, and the row is flagged ``provisional: True``
    with the policy's ``writing.confidence``: a single rubric fragment is an
    estimate to start from, so it feeds the provisional estimate and is read as
    *unknown* by :func:`measured_working_level`. Every other row carries
    ``provisional: False`` -- the flag is part of the shape, never implied by
    its absence.
    """
    level_cfg = policy.get("working_level") or {}
    min_topics = int(level_cfg.get("min_topics", 5))
    floor = str(level_cfg.get("confidence_floor", "medium"))
    thresholds = level_cfg.get("confidence_thresholds") or {}

    # skill -> band -> distinct ACTIVE+ topics feeding it.
    counts: dict[str, dict[str, set[str]]] = {}
    all_skills: set[str] = set()
    for track in policy.get("core_skill_map") or {}:
        all_skills |= _skills_of_track(policy, track)
    for topic in program.get("topics", []):
        topic_id = str(topic.get("id"))
        state = scores.get(topic_id)
        if state is None or state.knowledge_state not in _STEADY:
            continue
        band = str(topic.get("cefr", ""))
        for skill in _skills_of_track(policy, str(topic.get("track", ""))):
            counts.setdefault(skill, {}).setdefault(band, set()).add(topic_id)

    placement_cfg = policy.get("placement")
    # No ``placement`` section = an old pin: the argument is ignored outright,
    # so scoring@1 produces exactly the rows it always produced.
    placement_bands_by_skill = dict(placement or {}) if isinstance(placement_cfg, dict) else {}
    writing_band = placement_writing if isinstance(placement_cfg, dict) else None
    placement_cfg = placement_cfg or {}
    out: dict[str, dict[str, Any]] = {}
    floor_rank = CONFIDENCE_ORDER.index(floor) if floor in CONFIDENCE_ORDER else 2
    for skill in sorted(all_skills):
        bands = counts.get(skill, {})
        total = len(set().union(*bands.values())) if bands else 0
        confidence = _confidence(total, thresholds)
        level: str | None = None
        if CONFIDENCE_ORDER.index(confidence) >= floor_rank:
            for band in BAND_ORDER:
                if len(bands.get(band, ())) >= min_topics:
                    level = band  # highest covered band wins (iteration ascends)
        basis: str | None = "evidence" if level is not None else None
        provisional = False
        if level is None and placement_bands_by_skill.get(skill):
            level = placement_bands_by_skill[skill]
            confidence = str(placement_cfg.get("confidence", "low"))
            basis = str(placement_cfg.get("basis", "placement"))
        if level is None and skill == WRITING_SKILL and writing_band:
            level = writing_band
            confidence = str((placement_cfg.get("writing") or {}).get("confidence", "very_low"))
            basis = str(placement_cfg.get("basis", "placement"))
            provisional = True
        out[skill] = {
            "level": level,
            "confidence": confidence,
            "basis": basis,  # None = no level yet, never a fabricated source
            "provisional": provisional,
            "active_topics": total,
        }
    return out


def measured_working_level(levels: dict[str, dict[str, Any]]) -> str | None:
    """Not higher than the weakest core skill; any unknown skill keeps the
    overall level unknown (conservative by contract, canon 4).

    A ``provisional`` row (the placement's writing estimate) counts as unknown
    here: the measured field is evidence-only, and a full writing band still
    needs >= 2 independent non-placement items (canon 4b)."""
    if not levels:
        return None
    measured: list[str] = []
    for state in levels.values():
        if state["level"] is None or state.get("provisional"):
            return None
        measured.append(str(state["level"]))
    return min(measured, key=BAND_ORDER.index)


def provisional_working_estimate(
    levels: dict[str, dict[str, Any]],
    *,
    self_reported: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The honest "where do we start" estimate: measured where present, else
    provisional (canon 4, "measured vs provisional").

    Per skill it takes the measured row when there is one and otherwise the
    weakest available claim -- the placement's provisional writing band, else
    the learner's ``self_reported_level`` -- always flagged ``provisional`` with
    its own ``basis``. The overall ``level`` is again not higher than the
    weakest skill and stays ``None`` while any skill is unknown. Learning Score
    and gating never read this field; briefing and recommendations may show it
    *with* the flag.
    """
    reported = dict(self_reported or {})
    skills: dict[str, dict[str, Any]] = {}
    for skill, state in sorted(levels.items()):
        row = {
            "level": state.get("level"),
            "confidence": state.get("confidence"),
            "basis": state.get("basis"),
            "provisional": bool(state.get("provisional")),
        }
        if row["level"] is None and reported.get(skill):
            row = {
                "level": reported[skill],
                "confidence": SELF_REPORT_CONFIDENCE,
                "basis": SELF_REPORT_BASIS,
                "provisional": True,
            }
        skills[skill] = row
    bands = [str(row["level"]) for row in skills.values() if row["level"] is not None]
    level = min(bands, key=BAND_ORDER.index) if skills and len(bands) == len(skills) else None
    return {
        "level": level,
        "provisional": any(row["provisional"] for row in skills.values()),
        "skills": skills,
    }


def learning_score(
    scores: dict[str, TargetState],
    program: dict[str, Any],
    policy: dict[str, Any],
    measured_level: str | None,
) -> str | None:
    """Mean Mastery of ACTIVE+ topics of the measured band; None = no-data."""
    if measured_level is None:
        return None
    context = scoring_context(policy)
    # The mean runs inside the pinned context so the bare ``+`` inside ``sum``
    # uses precision 28 / ROUND_HALF_EVEN too, not the ambient thread context
    # (hermetic aggregate, matching ``fold_scores``).
    with decimal.localcontext(context):
        values: list[Decimal] = []
        for topic in program.get("topics", []):
            if str(topic.get("cefr")) != measured_level:
                continue
            state = scores.get(str(topic.get("id")))
            if state is None or state.knowledge_state not in _STEADY or not state.mastery:
                continue
            per_dimension = list(state.mastery.values())
            values.append(context.divide(sum(per_dimension, Decimal(0)), Decimal(len(per_dimension))))
        if not values:
            return None
        return str(context.divide(sum(values, Decimal(0)), Decimal(len(values))))


def xp_ledger(store: EventStore, policy: dict[str, Any]) -> dict[str, Any]:
    """The XP fold: award-once sources, mutually exclusive kinds, daily cap."""
    xp_cfg = policy.get("xp") or {}
    base = xp_cfg.get("base_amounts") or {}
    attempt_award = int(base.get("attempt_finalized", 0))
    review_award = int(base.get("review_closed", 0))
    daily_cap = int(xp_cfg.get("daily_cap", 0))

    awarded_sources: set[str] = set()
    by_day: dict[str, int] = {}
    awards: list[dict[str, Any]] = []
    total = 0

    for event in store.read():  # sequence order: the cap is deterministic
        if event.type == ATTEMPT_RECORDED_EVENT and event.payload.get("status") == "assessed":
            # Objective checks are recorded already-assessed.
            source_id = str(event.payload.get("attempt_id"))
            kind, amount = "attempt_finalized", attempt_award
        elif event.type == ATTEMPT_STATE_CHANGED_EVENT and event.payload.get("to_status") == "assessed":
            # Rubric finalization: an open answer is recorded then assessed via
            # attempt.state_changed (finalize_attempt), never recorded-assessed.
            # Award-once by attempt_id keeps the objective and rubric paths
            # mutually exclusive -- an attempt is counted on exactly one fact.
            source_id = str(event.payload.get("attempt_id"))
            kind, amount = "attempt_finalized", attempt_award
        elif event.type == REVIEW_OUTCOME_EVENT:
            source_id = str(event.payload.get("review_id") or event.id)
            kind, amount = "review_closed", review_award
        else:
            continue
        if amount <= 0 or source_id in awarded_sources:
            continue  # award-once, independent of replay
        awarded_sources.add(source_id)
        day = event.occurred_at.date().isoformat()  # UTC practice day (v1)
        room = daily_cap - by_day.get(day, 0)
        if room <= 0:
            continue  # over the cap: the excess is simply not awarded
        granted = min(amount, room)
        by_day[day] = by_day.get(day, 0) + granted
        total += granted
        awards.append({"source_id": source_id, "award_kind": kind, "practice_day": day, "amount": granted})

    streak = _current_streak(sorted(by_day))
    return {
        "total": total,
        "by_day": by_day,
        "awards": awards,
        "practice_days": len(by_day),
        "streak": streak,
    }


def _current_streak(days: list[str]) -> int:
    """Consecutive practice days ending at the LAST practice day -- a pure
    property of the ledger (the "is it still alive today" question needs the
    clock and belongs to the presentation layer)."""
    if not days:
        return 0
    from datetime import date, timedelta
    from itertools import pairwise

    streak = 1
    for earlier, later in pairwise(days):
        if date.fromisoformat(later) - date.fromisoformat(earlier) == timedelta(days=1):
            streak += 1
        else:
            streak = 1
    return streak
