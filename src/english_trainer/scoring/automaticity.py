"""The automaticity axis: policy ``automaticity@1`` and its reducer
(scoring 3d; learning-model 4a; [PD-2026-09-22]).

Accuracy and speed are different facts. A learner can know a rule and apply it
correctly while stopping to recall it every time; the method's goal is that the
form comes out without that stop. The three state axes (enrollment / knowledge
state / review status) cannot see that difference, so automaticity is a
**fourth, orthogonal axis** with its own policy kind and its own reducer.

What that buys, and why the separation is not cosmetic: the total transition
table (canon 3), the Mastery formula and the Stability/Retrievability model stay
byte-for-byte as they were, and old evidence replays to exactly the same numbers
as before this module existed. ``AutomaticityState`` never feeds Mastery,
Stability, Retrievability, knowledge state, review status, the working CEFR
level, the Learning Score or XP -- not directly and not through an aggregate.
It is an input for planning (control) and for answering the learner's question
"is this on autopilot yet?" honestly.

**Closed inputs** (canon 3d). Only three facts move the axis:

1. drill-block accuracy -- the share of ``objective_correct`` over the block's
   *answered* items (evidence 4.6). Items the learner never got to are not
   failures and never enter the denominator.
2. per-item ``latency_ms`` inside a drill block.
3. ``response_latency_ms`` on a timed- or spontaneous-form attempt outside the
   drill -- the confirmation leg of the ``automatic`` criterion.

Presentation, explanation and the learner's self-assessment are not inputs.

**Latency is relative, never absolute.** ``baseline_latency_ms`` is the lower
median of the per-item latencies measured on targets that were already ``ACTIVE``
or ``MASTERED`` at the time of measurement, over the last
``baseline_window_sessions`` sessions. With no baseline, ``automatic`` is
unreachable and the target stays ``proceduralized`` -- an absolute millisecond
threshold would compare a learner to nobody in particular. A missing latency
means "not measured" and is never read as zero.

**Aggregation window** (the canon leaves it to the policy): ``accuracy_ppm`` and
``median_latency_ms`` are computed over the **last ``min_blocks`` blocks** of the
target. Accuracy is integer ppm with ``floor`` division over the pooled answered
items of that window -- no float ever touches a decision-bearing number, and
``latency_factor`` is a ``Decimal`` parsed from a string under the fixed context
of canon 2.1 (precision 28, ROUND_HALF_EVEN). Medians are *lower* medians, so an
even-sized sample has one canonical answer.

The fold is a pure function of the event log plus the pinned policy, in
canonical ``sequence`` order, which is what makes ``trainer scoring replay``
able to rebuild the axis and compare it with the recorded
``AUTOMATICITY_UPDATED`` facts.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import derived_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.scoring.policy import reject_floats

AUTOMATICITY_KIND = "automaticity"

# Consumed event contracts. String literals on purpose: events are the module
# boundary (scoring imports kernel only).
EVIDENCE_ADDED_EVENT = "evidence.added"
STATE_TRANSITION_EVENT = "scoring.state_transition"
# The drill-block marker evidence carries (evidence 4.6).
DRILL_BLOCK_FORM = "drill_block"

EVENT_AUTOMATICITY_UPDATED = "scoring.automaticity_updated"

NOT_MEASURED = "not_measured"
DELIBERATE = "deliberate"
PROCEDURALIZED = "proceduralized"
AUTOMATIC = "automatic"
STATES = (NOT_MEASURED, DELIBERATE, PROCEDURALIZED, AUTOMATIC)

# "ACTIVE or above" for the baseline (canon 3d). AT_RISK is deliberately not
# here: it is an overdue fact about the schedule, and its latencies are exactly
# the ones a baseline of *owned* material should not absorb.
BASELINE_KNOWLEDGE_STATES = frozenset({"ACTIVE", "MASTERED"})

# The spontaneous forms outside the drill (generation 1 step types). A timed
# form is recognised by an explicit declared limit on the attempt instead.
SPONTANEOUS_STEP_TYPES = frozenset({"spontaneous_production", "free_conversation"})

# The exact key set of automaticity@1 (canon 3d). Total on purpose: an unknown
# key is a drift or a duplicated-then-renamed entry, and a missing one would
# make the policy non-executable.
_REQUIRED_LITERALS: dict[str, Any] = {
    "policy_id": "automaticity@1",
    "schema_version": 1,
    "status": "accepted",
    "decision_record": "PD-2026-09-22",
    "canonical_encoding": "kernel.canonical_json_v1",
    "numeric_value_rule": "integers_and_decimal_strings_only",
}
_REQUIRED_INTS = (
    "proceduralized_accuracy_ppm",
    "automatic_accuracy_ppm",
    "min_blocks",
    "min_sessions",
    "baseline_window_sessions",
)
POLICY_KEYS = frozenset({*_REQUIRED_LITERALS, *_REQUIRED_INTS, "latency_factor"})

_PPM = 1_000_000


class AutomaticityPolicyInvalid(KernelError):
    """``automaticity@1`` violates its own contract; it must never activate."""

    code = "AUTOMATICITY_POLICY_INVALID"


def automaticity_context() -> decimal.Context:
    """The fixed Decimal context of canon 2.1, shared by every scoring axis."""
    return decimal.Context(prec=28, rounding=decimal.ROUND_HALF_EVEN)


def validate_automaticity_policy(payload: dict[str, Any]) -> list[str]:
    """Return every violation (empty list = valid).

    Floats are refused outright: a YAML ``1.5`` would already have gone through
    a binary rounding before the validator ever saw it, and two platforms could
    disagree about the boundary of ``latency_factor x baseline``.
    """
    errors: list[str] = []
    reject_floats(payload, AUTOMATICITY_KIND, errors)

    unknown = sorted(set(payload) - POLICY_KEYS)
    if unknown:
        errors.append(f"automaticity: unknown key(s) {unknown}; the policy's key set is closed")
    for key, expected in _REQUIRED_LITERALS.items():
        if key not in payload:
            errors.append(f"automaticity.{key}: missing")
        elif payload[key] != expected:
            errors.append(f"automaticity.{key}: must be {expected!r}, got {payload[key]!r}")

    values: dict[str, int] = {}
    for key in _REQUIRED_INTS:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"automaticity.{key}: must be a positive integer")
        else:
            values[key] = value
    for key in ("proceduralized_accuracy_ppm", "automatic_accuracy_ppm"):
        if key in values and values[key] > _PPM:
            errors.append(f"automaticity.{key}: ppm cannot exceed {_PPM}")
    if len({"proceduralized_accuracy_ppm", "automatic_accuracy_ppm"} & set(values)) == 2 and (
        values["automatic_accuracy_ppm"] < values["proceduralized_accuracy_ppm"]
    ):
        errors.append("automaticity.automatic_accuracy_ppm: must be at or above proceduralized_accuracy_ppm")

    factor = payload.get("latency_factor")
    if not isinstance(factor, str):
        errors.append("automaticity.latency_factor: must be a decimal STRING, never a YAML float")
    else:
        try:
            parsed = Decimal(factor)
        except decimal.InvalidOperation:
            errors.append(f"automaticity.latency_factor: {factor!r} is not a parseable decimal string")
        else:
            if not parsed.is_finite() or parsed <= 0:
                errors.append("automaticity.latency_factor: must be finite and positive")
    return errors


def require_valid_automaticity(payload: dict[str, Any]) -> dict[str, Any]:
    errors = validate_automaticity_policy(payload)
    if errors:
        raise AutomaticityPolicyInvalid("; ".join(errors))
    return payload


def parse_automaticity_policy(text: str) -> dict[str, Any]:
    """Parse the policy FILE, refusing duplicate keys, then validate it.

    ``yaml.safe_load`` silently keeps the last of two identical keys, so a file
    that states ``min_blocks`` twice would activate one value while a reader
    sees the other -- a silent determinism hole in a content-addressed,
    replayable policy. The dict-level validator cannot see that, because by then
    the duplicate is already gone.
    """
    import yaml

    class _NoDuplicates(yaml.SafeLoader):
        pass

    def _mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise AutomaticityPolicyInvalid(f"automaticity.{key}: duplicate key in the policy file")
            seen.add(key)
        loader.flatten_mapping(node)
        constructed: dict[Any, Any] = loader.construct_mapping(node, deep=True)
        return constructed

    _NoDuplicates.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
    # _NoDuplicates subclasses SafeLoader: this is a safe load with one extra rule.
    loaded = yaml.load(text, Loader=_NoDuplicates)
    if not isinstance(loaded, dict):
        raise AutomaticityPolicyInvalid("automaticity: the policy file must be a mapping")
    return require_valid_automaticity(loaded)


@dataclass
class AutomaticityState:
    """Per-``LearningTarget`` automaticity (canon 3d).

    ``median_latency_ms`` / ``baseline_latency_ms`` stay ``None`` while nothing
    was measured -- absence is never zero.
    """

    state: str = NOT_MEASURED
    blocks_observed: int = 0
    sessions_observed: int = 0
    accuracy_ppm: int = 0
    median_latency_ms: int | None = None
    baseline_latency_ms: int | None = None
    confirmations: int = 0
    last_updated_at: str | None = None


@dataclass(frozen=True)
class _Block:
    session_id: str
    answered: int
    correct: int
    latencies: tuple[int, ...]


@dataclass
class _Target:
    state: AutomaticityState = field(default_factory=AutomaticityState)
    blocks: list[_Block] = field(default_factory=list)


def _lower_median(values: list[int]) -> int | None:
    """The lower median of a sorted-in-place sample; ``None`` when empty.

    Lower, not mean-of-two: an even sample must have ONE canonical answer that
    is an observed integer, not a value that never happened.
    """
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _latency(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class _Fold:
    """The resumable automaticity fold: ``apply`` one event, in sequence order."""

    def __init__(self, policy: dict[str, Any]) -> None:
        self._context = automaticity_context()
        self._proceduralized = int(policy["proceduralized_accuracy_ppm"])
        self._automatic = int(policy["automatic_accuracy_ppm"])
        self._min_blocks = int(policy["min_blocks"])
        self._min_sessions = int(policy["min_sessions"])
        self._baseline_window = int(policy["baseline_window_sessions"])
        self._latency_factor = self._context.create_decimal(str(policy["latency_factor"]))
        self._targets: dict[str, _Target] = {}
        # Distinct sessions in first-appearance order: the baseline window is
        # the LAST `baseline_window_sessions` of them.
        self._sessions: list[str] = []
        # Knowledge state per target, read from the canonical transition facts
        # (canon 3) rather than recomputed here -- one producer, one truth.
        self._knowledge: dict[str, str] = {}
        # (session_id, latency_ms) measured on ACTIVE+ targets.
        self._baseline_samples: list[tuple[str, int]] = []

    # -- public ------------------------------------------------------------

    @property
    def states(self) -> dict[str, AutomaticityState]:
        return {ref: target.state for ref, target in self._targets.items()}

    def apply(self, event: DomainEvent) -> str | None:
        """Fold one event; return the target whose numbers changed, else ``None``."""
        if event.type == STATE_TRANSITION_EVENT:
            ref = str(event.payload.get("target_ref") or "")
            to_state = str(event.payload.get("to_state") or "")
            if ref and to_state:
                self._knowledge[ref] = to_state
            return None
        if event.type != EVIDENCE_ADDED_EVENT:
            return None

        payload = event.payload
        ref = str((payload.get("primary_target") or {}).get("target_ref") or "")
        if not ref:
            # Target-less evidence (free conversation) measures nobody's speed.
            return None
        session_id = str(payload.get("session_id") or "")
        if session_id and session_id not in self._sessions:
            self._sessions.append(session_id)

        before = self._frozen(ref)
        if str(payload.get("form") or "") == DRILL_BLOCK_FORM:
            if not self._observe_block(ref, session_id, payload):
                return None
        elif _is_confirmation(payload):
            self._target(ref).state.confirmations += 1
        else:
            return None

        self._recompute(ref)
        if self._frozen(ref) == before:
            return None
        self._target(ref).state.last_updated_at = event.occurred_at.isoformat()
        return ref

    # -- internals ---------------------------------------------------------

    def _target(self, ref: str) -> _Target:
        if ref not in self._targets:
            self._targets[ref] = _Target()
        return self._targets[ref]

    def _frozen(self, ref: str) -> tuple[Any, ...]:
        """Everything but ``last_updated_at``: the numbers an update reports."""
        found = self._targets.get(ref)
        state = found.state if found is not None else AutomaticityState()
        return (
            state.state,
            state.blocks_observed,
            state.sessions_observed,
            state.accuracy_ppm,
            state.median_latency_ms,
            state.baseline_latency_ms,
            state.confirmations,
        )

    def _observe_block(self, ref: str, session_id: str, payload: dict[str, Any]) -> bool:
        items = payload.get("items")
        if not isinstance(items, list):
            return False
        answered = 0
        correct = 0
        latencies: list[int] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            objective = item.get("objective_correct")
            if objective is None:
                # Never presented: recorded as unpresented, not as a failure
                # (evidence 4.6). It stays out of the denominator.
                continue
            answered += 1
            if objective is True:
                correct += 1
            latency = _latency(item.get("latency_ms"))
            if latency is not None:
                latencies.append(latency)
        if answered == 0:
            return False  # a block nobody answered is not a measurement
        self._target(ref).blocks.append(_Block(session_id, answered, correct, tuple(latencies)))
        if self._knowledge.get(ref, "NEW") in BASELINE_KNOWLEDGE_STATES:
            self._baseline_samples.extend((session_id, value) for value in latencies)
        return True

    def _baseline(self) -> int | None:
        window = set(self._sessions[-self._baseline_window :])
        return _lower_median([value for session, value in self._baseline_samples if session in window])

    def _recompute(self, ref: str) -> None:
        target = self._target(ref)
        state = target.state
        blocks = target.blocks
        state.blocks_observed = len(blocks)
        state.sessions_observed = len({block.session_id for block in blocks if block.session_id})
        window = blocks[-self._min_blocks :]
        answered = sum(block.answered for block in window)
        correct = sum(block.correct for block in window)
        # Integer ppm, floored: the decision-bearing number stays an integer.
        state.accuracy_ppm = (correct * _PPM) // answered if answered else 0
        state.median_latency_ms = _lower_median([v for block in window for v in block.latencies])
        state.baseline_latency_ms = self._baseline()
        window_sessions = len({block.session_id for block in window if block.session_id})
        state.state = self._next_state(state, len(blocks), window_sessions)

    def _next_state(self, state: AutomaticityState, blocks: int, window_sessions: int) -> str:
        """The total transition table of canon 3d.

        Every (state, observation) pair not named by a row is a no-op, never an
        error, and the axis never falls below ``deliberate``: a speed once
        measured does not become unmeasured.
        """
        current = state.state
        if blocks == 0:
            return current  # a confirmation alone never measures speed
        if current == NOT_MEASURED:
            current = DELIBERATE  # the first drill block on the target
        if state.accuracy_ppm < self._proceduralized:
            # An unsuccessful block demotes to proceduralized -- and no further.
            return PROCEDURALIZED if current in (PROCEDURALIZED, AUTOMATIC) else current
        if current == DELIBERATE and blocks >= self._min_blocks:
            current = PROCEDURALIZED
        if current == PROCEDURALIZED and self._is_automatic(state, window_sessions):
            current = AUTOMATIC
        return current

    def _is_automatic(self, state: AutomaticityState, window_sessions: int) -> bool:
        if state.accuracy_ppm < self._automatic:
            return False
        if state.confirmations < 1:
            return False
        if window_sessions < self._min_sessions:
            return False
        baseline = state.baseline_latency_ms
        median = state.median_latency_ms
        if baseline is None or median is None:
            # No baseline => `automatic` is unreachable by contract. There is no
            # absolute fallback threshold, on purpose.
            return False
        with decimal.localcontext(self._context):
            allowed = self._context.multiply(self._latency_factor, Decimal(baseline))
            return Decimal(median) <= allowed


def _is_confirmation(payload: dict[str, Any]) -> bool:
    """A timed- or spontaneous-form attempt outside the drill (canon 3d).

    It must actually carry a latency: a spontaneous answer whose speed nobody
    measured confirms nothing about speed.
    """
    if _latency(payload.get("response_latency_ms")) is None:
        return False
    step_type = str(payload.get("mode") or payload.get("step_type") or "")
    if step_type in SPONTANEOUS_STEP_TYPES:
        return True
    return bool(payload.get("timed")) or payload.get("declared_limit_seconds") is not None


def fold_automaticity(store: EventStore, policy: dict[str, Any]) -> dict[str, AutomaticityState]:
    """Fold the whole event log into per-target ``AutomaticityState``."""
    fold = _Fold(policy)
    for event in store.read():  # canonical sequence order (foundation 3.3)
        fold.apply(event)
    return fold.states


def automaticity_snapshot(states: dict[str, AutomaticityState]) -> dict[str, Any]:
    """The canonically-encodable view replay hashes and ``status`` reports."""
    out: dict[str, Any] = {}
    for ref in sorted(states):
        state = states[ref]
        out[ref] = {
            "state": state.state,
            "blocks_observed": state.blocks_observed,
            "sessions_observed": state.sessions_observed,
            "accuracy_ppm": state.accuracy_ppm,
            "median_latency_ms": state.median_latency_ms,
            "baseline_latency_ms": state.baseline_latency_ms,
            "confirmations": state.confirmations,
            "last_updated_at": state.last_updated_at,
        }
    return out


# -- the AUTOMATICITY_UPDATED producer ------------------------------------


def _existing_update(store: EventStore, source_event_id: str) -> DomainEvent | None:
    for event in store.read():
        if event.type == EVENT_AUTOMATICITY_UPDATED and event.causation_id == source_event_id:
            return event
    return None


def _update_event(
    source: DomainEvent, version: str, ref: str, from_state: str, state: AutomaticityState
) -> DomainEvent:
    return make_event(
        id=derived_ulid(source.id, EVENT_AUTOMATICITY_UPDATED),
        type=EVENT_AUTOMATICITY_UPDATED,
        occurred_at=source.occurred_at,
        actor="engine",
        provider=source.provider,
        correlation_id=source.correlation_id,
        causation_id=source.id,
        payload={
            "target_ref": ref,
            "from_state": from_state,
            "to_state": state.state,
            "accuracy_ppm": state.accuracy_ppm,
            "median_latency_ms": state.median_latency_ms,
            "baseline_latency_ms": state.baseline_latency_ms,
            "pinned_automaticity_policy": version,
            "causation_id": source.id,
        },
        pinned_versions={AUTOMATICITY_KIND: version},
    )


def build_automaticity_update(
    store: EventStore, registry: PolicyRegistry, source: DomainEvent
) -> DomainEvent | None:
    """The one ``AUTOMATICITY_UPDATED`` fact caused by ``source``, or ``None``.

    Call it inside the same Unit of Work as the scoring update that consumed the
    evidence, exactly like ``build_state_transition``: the axis and the score it
    accompanies must never be able to commit apart. ``source`` is the
    ``evidence.added`` event being appended (it need not be in the store yet).

    Returns ``None`` when the evidence is not an admissible input or when
    neither the state nor any number moved -- unlike the state-transition
    producer, a no-op here mints no fact: nothing observed means nothing to say.
    """
    version = source.pinned_versions.get(AUTOMATICITY_KIND)
    if version is None:
        return None
    existing = _existing_update(store, source.id)
    if existing is not None:
        return existing
    policy = registry.resolve_pinned(AUTOMATICITY_KIND, version)
    fold = _Fold(policy)
    for event in store.read():
        if event.id == source.id:
            continue
        fold.apply(event)
    before = {ref: state.state for ref, state in fold.states.items()}
    ref = fold.apply(source)
    if ref is None:
        return None
    return _update_event(source, version, ref, before.get(ref, NOT_MEASURED), fold.states[ref])


def backfill_automaticity_updates(
    store: EventStore, registry: PolicyRegistry, uow: UnitOfWork
) -> dict[str, int]:
    """Append the missing ``AUTOMATICITY_UPDATED`` facts, in source order.

    Idempotent: ids are derived from the source evidence id, so a second run
    creates nothing. The fold runs once over the log instead of once per source.
    """
    covered = {
        event.causation_id
        for event in store.read()
        if event.type == EVENT_AUTOMATICITY_UPDATED and event.causation_id is not None
    }
    versions = sorted(
        {
            str(event.pinned_versions[AUTOMATICITY_KIND])
            for event in store.read()
            if AUTOMATICITY_KIND in event.pinned_versions
        }
    )
    folds = {version: _Fold(registry.resolve_pinned(AUTOMATICITY_KIND, version)) for version in versions}
    created: list[DomainEvent] = []
    scanned = 0
    for source in store.read():
        version = source.pinned_versions.get(AUTOMATICITY_KIND)
        owner = folds.get(str(version)) if version is not None else None
        for fold in folds.values():
            if fold is not owner:
                fold.apply(source)
        if owner is None or version is None:
            continue
        if source.type != EVIDENCE_ADDED_EVENT:
            owner.apply(source)
            continue
        scanned += 1
        before = {ref: state.state for ref, state in owner.states.items()}
        ref = owner.apply(source)
        if ref is None or source.id in covered:
            continue
        created.append(
            _update_event(source, str(version), ref, before.get(ref, NOT_MEASURED), owner.states[ref])
        )
    if created:
        uow.append(created)
    return {"scanned": scanned, "created": len(created)}


def recorded_automaticity(store: EventStore) -> dict[str, dict[str, Any]]:
    """The last recorded ``AUTOMATICITY_UPDATED`` per target (the saved axis)."""
    out: dict[str, dict[str, Any]] = {}
    for event in store.read():
        if event.type != EVENT_AUTOMATICITY_UPDATED:
            continue
        ref = str(event.payload.get("target_ref") or "")
        if ref:
            out[ref] = dict(event.payload)
    return out


def automaticity_mismatches(store: EventStore, rebuilt: dict[str, Any]) -> list[dict[str, Any]]:
    """Recorded facts that disagree with the rebuilt fold -- a replay error.

    A target with no recorded fact is reported as ``missing`` by the caller, not
    as a mismatch: the producer is wired per call site, and an unwired call site
    is an incompleteness to fix, not a broken determinism claim.
    """
    out: list[dict[str, Any]] = []
    for ref, recorded in sorted(recorded_automaticity(store).items()):
        current = rebuilt.get(ref)
        if current is None:
            out.append({"target_ref": ref, "reason": "rebuilt_missing"})
            continue
        for key in ("accuracy_ppm", "median_latency_ms", "baseline_latency_ms"):
            if recorded.get(key) != current.get(key):
                out.append(
                    {
                        "target_ref": ref,
                        "reason": key,
                        "recorded": recorded.get(key),
                        "rebuilt": current.get(key),
                    }
                )
        if recorded.get("to_state") != current.get("state"):
            out.append(
                {
                    "target_ref": ref,
                    "reason": "state",
                    "recorded": recorded.get("to_state"),
                    "rebuilt": current.get("state"),
                }
            )
    return out
