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
  conservative by contract, self-reported levels live in the provisional
  field once the learner module exists.
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

from decimal import Decimal
from typing import Any

from english_trainer.kernel.store import EventStore
from english_trainer.scoring.engine import ACTIVE, MASTERED, TargetState
from english_trainer.scoring.policy import scoring_context

ATTEMPT_RECORDED_EVENT = "attempt.recorded"
REVIEW_OUTCOME_EVENT = "review.outcome"

CONFIDENCE_ORDER = ("very_low", "low", "medium", "high")
BAND_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")

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


def working_levels(
    scores: dict[str, TargetState], program: dict[str, Any], policy: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Per-skill measured level: highest band with coverage, or unknown."""
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
        out[skill] = {"level": level, "confidence": confidence, "active_topics": total}
    return out


def measured_working_level(levels: dict[str, dict[str, Any]]) -> str | None:
    """Not higher than the weakest core skill; any unknown skill keeps the
    overall level unknown (conservative by contract, canon 4)."""
    if not levels:
        return None
    measured: list[str] = []
    for state in levels.values():
        if state["level"] is None:
            return None
        measured.append(str(state["level"]))
    return min(measured, key=BAND_ORDER.index)


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
