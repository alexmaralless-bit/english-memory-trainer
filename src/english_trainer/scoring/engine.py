"""The deterministic scoring fold (scoring 2-4b; roadmap 2.3 increment 1).

Scores are a pure function of the event log and the pinned policy: the fold
consumes ``EVIDENCE_ADDED``, ``REVIEW_OUTCOME`` and ``OVERDUE_AT_RISK_TRIGGERED``
in canonical ``sequence`` order and produces per-(target, dimension) Mastery
plus per-target Stability and knowledge state. Every arithmetic step runs in
the policy's fixed Decimal context (precision 28, ROUND_HALF_EVEN) -- no IEEE
float anywhere -- so two folds over the same events are byte-identical, which
``trainer scoring replay`` turns into a checkable guarantee.

What this increment honestly computes:

- **Mastery deltas** from objective evidence (correct/incorrect, mode weight,
  hint-scaled independence, per-session cap). Rubric-based evidence joins the
  same channel when rubric@1 exists (P.5); the rubric_cap is enforced here
  already so the arrival is a data change, not a code change.
- **Stability** per target: the initial value on first admissible evidence,
  outcome-driven growth/shrink. Retrievability is time-dependent and is
  computed at read time, never stored -- the replay hash covers only
  time-independent state.
- **Knowledge state** by the TOTAL transition table (canon 3): every
  (state, outcome) pair is defined, impossible pairs are audited no-ops, and
  ``AT_RISK`` enters only from the scheduler's replayable overdue event --
  never from a wall clock.
- **Origin rules** (canon 4b): ``control_probe`` evidence can never reduce
  anything; ``placement`` evidence cannot lift a state above ACTIVE.

Aggregates (working level, Learning Score, XP) fold on top in the next
increments; the per-target core computed here is their only input.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from english_trainer.kernel.store import EventStore
from english_trainer.scoring.policy import scoring_context

# Consumed event contracts (published by evidence / scheduler). Literals on
# purpose: events are the module boundary (scoring depends on kernel only).
EVIDENCE_ADDED_EVENT = "evidence.added"
REVIEW_OUTCOME_EVENT = "review.outcome"
OVERDUE_AT_RISK_EVENT = "review.overdue_at_risk"

NEW = "NEW"
LEARNING = "LEARNING"
ACTIVE = "ACTIVE"
MASTERED = "MASTERED"
AT_RISK = "AT_RISK"
_STEADY = (ACTIVE, MASTERED)

OUTCOMES = ("PROGRESS", "CONFIRMED", "REGRESSION", "RECOVERED", "INSUFFICIENT_EVIDENCE")

_HUNDRED = Decimal(100)
_ZERO = Decimal(0)
_ONE = Decimal(1)


def transition(state: str, outcome: str, prior_steady_state: str | None) -> tuple[str, str | None]:
    """The total transition table (canon 3): ``(new_state, prior_steady)``.

    Impossible pairs (e.g. RECOVERED on NEW) are no-ops by contract, never
    errors -- a corrupted or late outcome must not crash replay.
    """
    if outcome == "INSUFFICIENT_EVIDENCE":
        return state, prior_steady_state
    if state == NEW:
        if outcome in ("PROGRESS", "CONFIRMED"):
            return LEARNING, prior_steady_state
        return NEW, prior_steady_state
    if state == LEARNING:
        if outcome == "CONFIRMED":
            return ACTIVE, prior_steady_state
        return LEARNING, prior_steady_state
    if state == ACTIVE:
        if outcome == "CONFIRMED":
            return MASTERED, prior_steady_state
        if outcome == "REGRESSION":
            return LEARNING, prior_steady_state
        return ACTIVE, prior_steady_state
    if state == MASTERED:
        if outcome == "REGRESSION":
            return ACTIVE, prior_steady_state
        return MASTERED, prior_steady_state
    if state == AT_RISK:
        if outcome in ("CONFIRMED", "RECOVERED"):
            restored = prior_steady_state if prior_steady_state in _STEADY else ACTIVE
            return restored, None
        if outcome == "REGRESSION":
            return LEARNING, None
        return AT_RISK, prior_steady_state
    return state, prior_steady_state  # unknown state: audited no-op, never a crash


@dataclass
class TargetState:
    """Per-target fold state; every number is a Decimal under the policy context."""

    mastery: dict[str, Decimal] = field(default_factory=dict)  # per dimension
    stability_days: Decimal | None = None
    knowledge_state: str = NEW
    prior_steady_state: str | None = None
    evidence_count: int = 0
    session_gain: dict[str, Decimal] = field(default_factory=dict)  # session_id -> granted mastery
    rubric_gain: Decimal = _ZERO
    audit: list[str] = field(default_factory=list)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return min(max(value, low), high)


def fold_scores(store: EventStore, policy: dict[str, Any]) -> dict[str, TargetState]:
    """Fold the whole event log into per-target scoring state."""
    context = scoring_context(policy)
    mastery_cfg = policy["mastery"]
    stability_cfg = policy["stability"]
    origin_cfg = policy.get("origin_rules") or {}

    def dec(value: Any) -> Decimal:
        return context.create_decimal(str(value))

    base_delta = dec(mastery_cfg["base_delta"])
    weights = {k: dec(v) for k, v in mastery_cfg["mode_weights"].items()}
    hint_penalty = dec(mastery_cfg["hint_penalty_per_hint"])
    hint_floor = dec(mastery_cfg["hint_penalty_floor"])
    session_cap = dec(mastery_cfg["session_cap"])
    rubric_cap = dec(mastery_cfg["rubric_cap"])
    regression_penalty = dec(mastery_cfg["regression_penalty"])
    initial_stability = dec(stability_cfg["initial_stability_days"])
    growth_base = dec(stability_cfg["success_growth_base"])
    damping = dec(stability_cfg["growth_damping_days"])
    shrink = dec(stability_cfg["regression_shrink_factor"])
    qualities = {k: dec(v) for k, v in stability_cfg["outcome_quality"].items()}

    targets: dict[str, TargetState] = {}

    def target_state(ref: str) -> TargetState:
        if ref not in targets:
            targets[ref] = TargetState()
        return targets[ref]

    for event in store.read():  # canonical sequence order (foundation 3.3)
        if event.type == EVIDENCE_ADDED_EVENT:
            payload = event.payload
            primary = payload.get("primary_target")
            if not primary or not primary.get("target_ref"):
                continue  # target-less evidence (free conversation) scores nothing yet
            ref = str(primary["target_ref"])
            dimension = str(primary.get("dimension") or "recognition")
            state = target_state(ref)
            state.evidence_count += 1
            if state.stability_days is None:
                state.stability_days = initial_stability

            origin = str(payload.get("origin") or "session")
            basis = str(payload.get("assessment_basis") or "objective_check")
            if basis == "objective_check":
                # Objective checks are binary: an incorrect answer gives no
                # delta (monotonicity, canon 2.1 -- decreases arrive only via
                # a confirmed REGRESSION outcome), a correct one full quality.
                if not bool(payload.get("correct")):
                    continue
                quality = _ONE
            else:
                # Graduated rubric quality (P.5 PD-2 B): the engine-computed
                # score_ppm scales the positive delta. Collapsing it back to a
                # Boolean would make the four-level scale fictitious. Zero
                # quality adds nothing; it is never a punishment.
                quality = context.divide(
                    context.create_decimal(int(payload.get("score_ppm") or 0)), Decimal(1_000_000)
                )
                if quality <= 0:
                    continue

            weight = weights.get(dimension, weights["recognition"])
            hints = int(payload.get("hints") or 0)
            independence = _clamp(_ONE - hint_penalty * Decimal(hints), hint_floor, _ONE)
            delta = context.multiply(
                context.multiply(context.multiply(base_delta, weight), independence), quality
            )

            session_id = str(payload.get("session_id") or "")
            granted = state.session_gain.get(session_id, _ZERO)
            room = session_cap - granted
            if room <= 0:
                state.audit.append(f"session-cap: {event.id}")
                continue
            delta = min(delta, room)
            if basis != "objective_check":
                rubric_room = rubric_cap - state.rubric_gain
                if rubric_room <= 0:
                    state.audit.append(f"rubric-cap: {event.id}")
                    continue
                delta = min(delta, rubric_room)
                state.rubric_gain += delta
            state.session_gain[session_id] = granted + delta
            current = state.mastery.get(dimension, _ZERO)
            state.mastery[dimension] = _clamp(current + delta, _ZERO, _HUNDRED)
            _ = origin  # placement evidence gains mastery normally; only the state is capped

        elif event.type == REVIEW_OUTCOME_EVENT:
            payload = event.payload
            ref = str(payload.get("target_ref") or "")
            if not ref:
                continue
            outcome = str(payload.get("outcome") or "")
            if outcome not in OUTCOMES:
                target_state(ref).audit.append(f"unknown-outcome: {event.id}")
                continue
            origin = str(payload.get("origin") or "session")
            state = target_state(ref)
            if (
                origin == "control_probe"
                and origin_cfg.get("control_probe_no_negative", True)
                and outcome == "REGRESSION"
            ):
                # No-negative (canon 4b): a probe can never punish.
                state.audit.append(f"probe-regression-suppressed: {event.id}")
                continue
            new_state, prior = transition(state.knowledge_state, outcome, state.prior_steady_state)
            if origin == "placement":
                ceiling = str(origin_cfg.get("placement_state_ceiling", ACTIVE))
                order = [NEW, LEARNING, ACTIVE, MASTERED]
                if new_state in order and order.index(new_state) > order.index(ceiling):
                    state.audit.append(f"placement-ceiling: {event.id}")
                    new_state = ceiling
            state.knowledge_state = new_state
            state.prior_steady_state = prior
            # Stability update from the outcome
            if state.stability_days is None:
                state.stability_days = initial_stability
            if outcome in qualities:
                quality = qualities[outcome]
                factor = _ONE + context.divide(
                    context.multiply(growth_base - _ONE, quality),
                    _ONE + context.divide(state.stability_days, damping),
                )
                state.stability_days = context.multiply(state.stability_days, factor)
            elif outcome == "REGRESSION":
                state.stability_days = context.multiply(state.stability_days, shrink)
                dimension = str(payload.get("dimension") or "recognition")
                current = state.mastery.get(dimension, _ZERO)
                state.mastery[dimension] = _clamp(current - regression_penalty, _ZERO, _HUNDRED)

        elif event.type == OVERDUE_AT_RISK_EVENT:
            ref = str(event.payload.get("target_ref") or "")
            if not ref:
                continue
            state = target_state(ref)
            if state.knowledge_state in _STEADY:
                # AT_RISK enters ONLY from this replayable event (canon 3):
                # "knew it, at risk of forgetting" -- never from a wall clock.
                state.prior_steady_state = state.knowledge_state
                state.knowledge_state = AT_RISK

    return targets


def retrievability(stability_days: Decimal, elapsed_days: Decimal, policy: dict[str, Any]) -> Decimal:
    """``exp(-elapsed / stability)`` in the pinned context (canon 2.2).

    Time-dependent by nature: computed at read time, never part of replay state.
    """
    context = scoring_context(policy)
    if stability_days <= 0:
        return _ZERO
    with decimal.localcontext(context):
        return (-context.divide(elapsed_days, stability_days)).exp()


def snapshot(targets: dict[str, TargetState]) -> dict[str, Any]:
    """The canonically-encodable, time-independent view of the fold -- the
    object ``trainer scoring replay`` hashes and compares."""
    out: dict[str, Any] = {}
    for ref in sorted(targets):
        state = targets[ref]
        out[ref] = {
            "mastery": {dim: str(value) for dim, value in sorted(state.mastery.items())},
            "stability_days": str(state.stability_days) if state.stability_days is not None else None,
            "knowledge_state": state.knowledge_state,
            "prior_steady_state": state.prior_steady_state,
            "evidence_count": state.evidence_count,
            "audit": list(state.audit),
        }
    return out
