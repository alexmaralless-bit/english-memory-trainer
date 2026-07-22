"""Learner control signals and probes (control 4.7; roadmap 2.8a).

The learner nudges the composition without touching knowledge state. A signal
is a **discriminated union by ``kind``** with per-kind payload and one of two
expiry types [R-11]:

- ``expires_at`` -- a UTC timestamp (``snooze``/``until`` and
  ``not_relevant_now``); the signal is active while ``now < expires_at``;
- ``expires_after_session_seq`` -- an integer session number
  (``too_repetitive``/``need_more_practice``/``prefer_different_context``); the
  signal is active for a composition with ``session_seq <= expires_after``.

``too_easy`` is one-shot: it is consumed atomically when a composition actually
adds the probe step it requests (control 4.7). ``session_seq`` is the monotonic
per-learner session number, DERIVED here from the ``SESSION_STARTED`` event
stream (its count; ``0`` if none) so this increment stays inside the control
bounded context -- signals read published events, they never import
lessons/evidence/scheduler code.

Recording a signal NEVER mutates the live plan (control 4.7): ``record_signal``
saves the signal and publishes ``LEARNER_SIGNAL_RECORDED``; for ``too_easy`` it
also mints a stable engine ``probe_id`` and publishes ``PROBE_REQUESTED``. When
a session is active the return carries ``next_action: session.replan`` -- the
agent may not insert the probe itself. The precedence rules (:func:`apply_signals`)
and the probe candidate (:func:`build_probe_candidate`) are pure and feed the
composition pipeline (compose 4.4 steps 3a/6a).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from english_trainer.control.errors import ProbePrecondition, SignalInvalid
from english_trainer.control.policy import step_cost
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import CachedResult, UnitOfWork

# Published event names control emits (control 3b, 6). Lowercase dotted, like
# every other module's event types; defined here because control owns them.
EVENT_SIGNAL_RECORDED = "control.learner_signal_recorded"
EVENT_SIGNAL_CONSUMED = "control.signal_consumed"
EVENT_PROBE_REQUESTED = "control.probe_requested"

# Published event names control *consumes* to derive session_seq, the active
# session and the live plan version. These are lessons' event types; control
# reads them off the log (it never imports lessons -- same discipline as
# ``lessons.presented_targets`` reading STEP_PRESENTED).
EVENT_SESSION_STARTED = "session.started"
EVENT_SESSION_FINISHED = "session.finished"
EVENT_SESSION_ABANDONED = "session.abandoned"
EVENT_SESSION_COMPOSED = "session.composed"
EVENT_STEP_PRESENTED = "session.step_presented"

SIGNAL_KINDS: tuple[str, ...] = (
    "too_easy",
    "too_repetitive",
    "need_more_practice",
    "not_relevant_now",
    "snooze",
    "prefer_different_context",
)

# Strong -> weak application order (control 4.7 precedence list). Exclusions are
# strongest; too_easy (probe only, no class change) is weakest.
_KIND_RANK: dict[str, int] = {
    "snooze": 0,
    "not_relevant_now": 0,
    "need_more_practice": 1,
    "prefer_different_context": 2,
    "too_repetitive": 3,
    "too_easy": 4,
}

# Non-exclusion target-scoped kinds: their presence on a target overrides a
# conflicting *domain*-scoped exclusion for that target (control 4.7
# "target-scope beats a conflicting domain-scope signal").
_OVERRIDE_KINDS = frozenset({"need_more_practice", "prefer_different_context", "too_repetitive", "too_easy"})

# The urgency ladder, weakest -> strongest (control 4.5 classes).
_LADDER: tuple[str, ...] = ("deferrable", "maintenance", "normal", "important", "critical")

# requested_difficulty by the source step type (control 4.7): a closed enum.
_DIFFICULTY_BY_SOURCE: dict[str, str] = {
    "new_material_intro": "spontaneous_production",
    "recognition_check": "spontaneous_production",
    "controlled_production": "spontaneous_production",
    "gate_item": "spontaneous_production",
    "spontaneous_production": "transfer_task",
    "integration_task": "transfer_task",
    "free_conversation": "transfer_task",
    "transfer_task": "transfer_task",
}


# -- timestamps --------------------------------------------------------------


def _normalize_ts(value: Any, field: str) -> str:
    """Parse an ISO-8601 instant and return its canonical UTC ISO string.

    A naive instant is read as UTC; anything unparseable is a stable
    :class:`SignalInvalid`. Storing one representation keeps replay byte-stable.
    """
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise SignalInvalid(f"{field} is not a valid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


# -- event-derived learner facts (control 4.7) -------------------------------


def current_session_seq(store: EventStore) -> int:
    """The monotonic per-learner session number (control 4.7): the count of
    ``SESSION_STARTED`` events. The last started session carries this number;
    ``0`` when no session has ever started (a signal recorded before any
    session uses ``current_session_seq = 0``)."""
    return sum(1 for event in store.read() if event.type == EVENT_SESSION_STARTED)


def _active_session(events: list[DomainEvent]) -> str | None:
    """The one active (STARTED/IN_PROGRESS) session, or ``None`` -- the last
    started session with no FINISHED/ABANDONED. At most one is ever active."""
    started: list[str] = []
    closed: set[str] = set()
    for event in events:
        if event.type == EVENT_SESSION_STARTED:
            started.append(str(event.correlation_id))
        elif event.type in (EVENT_SESSION_FINISHED, EVENT_SESSION_ABANDONED):
            closed.add(str(event.correlation_id))
    for session_id in reversed(started):
        if session_id not in closed:
            return session_id
    return None


def _current_plan_version(events: list[DomainEvent], session_id: str) -> int:
    """The live ``plan_version`` of a session, read off the log: the max version
    across its ``SESSION_COMPOSED`` and ``STEP_PRESENTED`` events (each mutation
    bumps it, control 4.2). ``0`` if the session has none yet."""
    version = 0
    for event in events:
        if str(event.correlation_id) != session_id:
            continue
        if event.type in (EVENT_SESSION_COMPOSED, EVENT_STEP_PRESENTED):
            version = max(version, int(event.payload.get("plan_version") or 0))
    return version


# -- signal validation (the discriminated union, control 4.7) ----------------


def build_signal(
    kind: str,
    payload: dict[str, Any],
    current_seq: int,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Validate one signal and return its canonical record (no id yet).

    Rejects an unknown ``kind`` or a missing/contradictory payload with a stable
    :class:`SignalInvalid`; computes the expiry per kind (control 4.7 table).
    """
    if kind not in SIGNAL_KINDS:
        raise SignalInvalid(f"unknown signal kind {kind!r}; expected one of {', '.join(SIGNAL_KINDS)}")

    target = payload.get("target_ref")
    domain = payload.get("domain")
    until = payload.get("until")
    expires_at = payload.get("expires_at")
    avoid_context = payload.get("avoid_context")

    default_effect = int(policy["signals"]["default_effect_sessions"])
    exposure_window = int(policy["saturation"]["exposure_window_sessions"])

    record: dict[str, Any] = {
        "kind": kind,
        "target_ref": None,
        "domain": None,
        "avoid_context": None,
        "expires_at": None,
        "expires_after_session_seq": None,
    }

    def _require(value: Any, message: str) -> None:
        if value is None or value == "":
            raise SignalInvalid(message)

    if kind == "too_easy":
        _require(target, "too_easy requires --target")
        record["target_ref"] = str(target)
        # One-shot: neither expiry field; consumed atomically by the probe it mints.
    elif kind == "too_repetitive":
        # target_ref is optional; a target-less signal shifts every non-risk review.
        record["target_ref"] = str(target) if target is not None else None
        record["expires_after_session_seq"] = current_seq + exposure_window
    elif kind == "need_more_practice":
        _require(target, "need_more_practice requires --target")
        record["target_ref"] = str(target)
        record["expires_after_session_seq"] = current_seq + default_effect
    elif kind == "not_relevant_now":
        if bool(target) == bool(domain):
            raise SignalInvalid("not_relevant_now requires exactly one of --target or --domain")
        _require(expires_at, "not_relevant_now requires --expires-at")
        record["target_ref"] = str(target) if target else None
        record["domain"] = str(domain) if domain else None
        record["expires_at"] = _normalize_ts(expires_at, "--expires-at")
    elif kind == "snooze":
        _require(target, "snooze requires --target")
        _require(until, "snooze requires --until")
        record["target_ref"] = str(target)
        record["expires_at"] = _normalize_ts(until, "--until")
    elif kind == "prefer_different_context":
        _require(target, "prefer_different_context requires --target")
        _require(avoid_context, "prefer_different_context requires --avoid-context")
        record["target_ref"] = str(target)
        record["avoid_context"] = str(avoid_context)
        record["expires_after_session_seq"] = current_seq + default_effect
    return record


def _is_active(record: dict[str, Any], current_seq: int, now: datetime) -> bool:
    """Whether a signal is still in force for a composition (control 4.7)."""
    exp_seq = record.get("expires_after_session_seq")
    if exp_seq is not None:
        return current_seq <= int(exp_seq)
    exp_at = record.get("expires_at")
    if exp_at is not None:
        return now < datetime.fromisoformat(str(exp_at))
    # too_easy: one-shot, in force until a SIGNAL_CONSUMED retires it.
    return True


def _scope(record: dict[str, Any]) -> tuple[str, str | None]:
    """The (scope-kind, scope-key) a signal is keyed on for supersede."""
    if record.get("target_ref") is not None:
        return ("target", str(record["target_ref"]))
    if record.get("domain") is not None:
        return ("domain", str(record["domain"]))
    return ("global", None)


def active_signals(store: EventStore, current_seq: int, now: datetime) -> list[dict[str, Any]]:
    """The signals in force for the next composition (control 4.7).

    Folds ``LEARNER_SIGNAL_RECORDED`` minus ``SIGNAL_CONSUMED``, drops expired
    ones (both expiry types), and applies supersede: a later signal of the same
    ``kind`` and scope replaces the earlier (``superseded_by``). Returned in the
    deterministic strong->weak order (kind rank, then sequence) so composition
    stays byte-identical. Target-vs-domain conflict is resolved per candidate in
    :func:`apply_signals`, where the target->domain membership is known.
    """
    recorded: list[tuple[int, str, dict[str, Any]]] = []
    consumed: set[str] = set()
    for event in store.read():
        if event.type == EVENT_SIGNAL_RECORDED:
            recorded.append(
                (int(event.sequence or 0), str(event.payload["signal_id"]), dict(event.payload["signal"]))
            )
        elif event.type == EVENT_SIGNAL_CONSUMED:
            consumed.add(str(event.payload["signal_id"]))

    live = [
        (seq, sid, rec)
        for seq, sid, rec in recorded
        if sid not in consumed and _is_active(rec, current_seq, now)
    ]

    # Supersede: the last signal (by sequence) of each (kind, scope) wins.
    best: dict[tuple[str, tuple[str, str | None]], tuple[int, str, dict[str, Any]]] = {}
    for seq, sid, rec in sorted(live, key=lambda item: item[0]):
        best[(rec["kind"], _scope(rec))] = (seq, sid, rec)

    survivors = sorted(best.values(), key=lambda item: (_KIND_RANK[item[2]["kind"]], item[0]))
    return [{**rec, "signal_id": sid, "sequence": seq} for seq, sid, rec in survivors]


# -- precedence over classified candidates (control 4.7, pure) ---------------


def _override_targets(signals: list[dict[str, Any]]) -> set[str]:
    return {
        str(s["target_ref"])
        for s in signals
        if s.get("target_ref") is not None and s["kind"] in _OVERRIDE_KINDS
    }


def _candidate_domain(candidate: dict[str, Any]) -> str | None:
    domain = candidate.get("domain")
    if domain is not None:
        return str(domain)
    context = str(candidate.get("context_id") or "")
    head = context.split("|", 1)[0]
    return head or None


def is_excluded(candidate: dict[str, Any], signals: list[dict[str, Any]]) -> bool:
    """Whether ``snooze``/``not_relevant_now`` excludes this candidate's target
    (control 4.7 step 1). A domain-scoped ``not_relevant_now`` is overridden for
    a target that carries a conflicting non-exclusion target-scoped signal."""
    target = candidate.get("target_ref")
    domain = _candidate_domain(candidate)
    overrides = _override_targets(signals)
    target_key = None if target is None else str(target)
    for signal in signals:
        if signal["kind"] not in ("snooze", "not_relevant_now"):
            continue
        scope_target = signal.get("target_ref")
        scope_domain = signal.get("domain")
        if scope_target is not None and target_key is not None and str(scope_target) == target_key:
            return True
        matches_domain = scope_domain is not None and domain is not None and str(scope_domain) == domain
        # target-scope beats a conflicting domain-scope signal (control 4.7).
        overridden = target_key is not None and target_key in overrides
        if matches_domain and not overridden:
            return True
    return False


def _shift_up(urgency: str) -> str:
    """need_more_practice: one step deferrable->maintenance->normal->important;
    important/critical unchanged (control 4.7)."""
    if urgency not in _LADDER:
        return urgency
    index = _LADDER.index(urgency)
    if urgency in ("important", "critical"):
        return urgency
    return _LADDER[index + 1]


def _shift_down(urgency: str) -> str:
    """too_repetitive: one step normal->maintenance->deferrable; deferrable and
    the risk classes unchanged (control 4.7)."""
    if urgency in ("critical", "important", "deferrable") or urgency not in _LADDER:
        return urgency
    return _LADDER[_LADDER.index(urgency) - 1]


def _is_risk(candidate: dict[str, Any]) -> bool:
    return bool(candidate.get("risk")) or candidate.get("urgency_class") in ("critical", "important")


def _trace_signal(candidate: dict[str, Any], signal: dict[str, Any]) -> None:
    signal_id = signal.get("signal_id")
    if signal_id is not None:
        candidate.setdefault("applied_signal_ids", []).append(str(signal_id))


def apply_signals(
    candidates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply active signals to classified review candidates in the control 4.7
    order, returning ``(surviving_candidates, waivers)``. Pure: the input list
    is not mutated. Deterministic -- the shift order follows the numbered list,
    not the order signals were recorded in.

    1. ``snooze``/``not_relevant_now`` exclude the target;
    2. ``need_more_practice`` shifts one class up;
    3. ``prefer_different_context`` drops candidates in ``avoid_context``
       (``NO_ALLOWED_CONTEXT`` when a target loses every option);
    4. ``too_repetitive`` shifts one class down (``risk == false`` only);
    5. ``too_easy`` leaves the class unchanged (it mints a probe elsewhere).
    """
    waivers: list[str] = []
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        by_kind[signal["kind"]].append(signal)

    # Step 1: exclusion.
    survivors = [dict(candidate) for candidate in candidates if not is_excluded(candidate, signals)]

    # Step 2: need_more_practice shifts up.
    for candidate in survivors:
        for signal in by_kind["need_more_practice"]:
            if str(signal.get("target_ref")) == str(candidate.get("target_ref")):
                candidate["urgency_class"] = _shift_up(str(candidate["urgency_class"]))
                _trace_signal(candidate, signal)
                break

    # Step 3: prefer_different_context excludes matching contexts.
    avoid_by_target: dict[str, set[str]] = defaultdict(set)
    for signal in by_kind["prefer_different_context"]:
        avoid_by_target[str(signal["target_ref"])].add(str(signal["avoid_context"]))
    if avoid_by_target:
        kept = [
            candidate
            for candidate in survivors
            if str(candidate.get("context_id"))
            not in avoid_by_target.get(str(candidate.get("target_ref")), set())
        ]
        remaining = {str(candidate.get("target_ref")) for candidate in kept}
        had = {str(candidate.get("target_ref")) for candidate in survivors}
        for target in sorted(avoid_by_target):
            if target in had and target not in remaining:
                waivers.append("NO_ALLOWED_CONTEXT")
        survivors = kept

    # Step 4: too_repetitive shifts down (non-risk only).
    for candidate in survivors:
        if _is_risk(candidate):
            continue
        for signal in by_kind["too_repetitive"]:
            scope_target = signal.get("target_ref")
            if scope_target is None or str(scope_target) == str(candidate.get("target_ref")):
                candidate["urgency_class"] = _shift_down(str(candidate["urgency_class"]))
                _trace_signal(candidate, signal)
                break

    # Step 5: too_easy -- no class change (the probe is built by compose 6a),
    # but the decision trace still records that the live signal was consulted.
    for candidate in survivors:
        for signal in by_kind["too_easy"]:
            if str(signal.get("target_ref")) == str(candidate.get("target_ref")):
                _trace_signal(candidate, signal)
    return survivors, waivers


# -- probe derivation (control 4.7) ------------------------------------------


def derive_probe(events: list[DomainEvent], target_ref: str, active_session_id: str | None) -> dict[str, Any]:
    """Derive the probe parameters for a ``too_easy`` target (control 4.7).

    Uses the last-by-sequence ``STEP_PRESENTED`` whose ``targets[]`` contains
    the goal (the active session first, else anywhere); with several dimensions
    in one event, ``dimension_id asc``. ``requested_difficulty`` steps up from
    the source step type; ``avoid_context`` is that step's context. Refuses with
    ``PRECONDITION_FAILED {reason: no_presented_step}`` when the target was never
    delivered.
    """
    candidates: list[tuple[int, bool, dict[str, Any], str | None]] = []
    for event in events:
        if event.type != EVENT_STEP_PRESENTED:
            continue
        targets = event.payload.get("targets") or []
        matching = [t for t in targets if str(t.get("target_ref")) == str(target_ref)]
        if not matching:
            continue
        dims = sorted(str(t["dimension"]) for t in matching if t.get("dimension") is not None)
        dimension = dims[0] if dims else None
        in_active = active_session_id is not None and str(event.correlation_id) == active_session_id
        candidates.append((int(event.sequence or 0), in_active, dict(event.payload), dimension))

    if not candidates:
        raise ProbePrecondition(
            f"no_presented_step: target {target_ref} has never been delivered, so a probe "
            "cannot derive its difficulty or avoid_context",
            reason="no_presented_step",
        )

    active_only = [item for item in candidates if item[1]]
    _, _, source, dimension = max(active_only or candidates, key=lambda item: item[0])
    source_step_type = str(source.get("step_type"))
    return {
        "target_ref": str(target_ref),
        "dimension": dimension,
        "requested_difficulty": _DIFFICULTY_BY_SOURCE.get(source_step_type, "transfer_task"),
        "avoid_context": source.get("context_id"),
    }


def build_probe_candidate(
    policy: dict[str, Any],
    *,
    probe_id: str,
    signal_id: str,
    target_ref: str,
    dimension: str | None,
    requested_difficulty: str,
    avoid_context: str | None,
) -> dict[str, Any]:
    """The ``kind=probe`` -> ``choice`` bucket candidate the pipeline first-fits
    (control 4.3a/4.7). ``step_type`` equals ``requested_difficulty`` (both are
    the closed enum ``spontaneous_production | transfer_task``); ``source_rank``
    ``0`` makes the probe outrank every other choice candidate."""
    return {
        "candidate_id": f"probe:{target_ref}",
        "kind": "probe",
        "bucket": "choice",
        "step_type": requested_difficulty,
        "expected_seconds": step_cost(policy, requested_difficulty),
        "target_ref": str(target_ref),
        "dimension": dimension,
        "context_id": f"probe|{requested_difficulty}",
        "avoid_context": avoid_context,
        "probe_id": probe_id,
        "signal_id": signal_id,
        "requested_difficulty": requested_difficulty,
        "lexicon_first": False,
        "lexicon_refs": [],
        "topic_hint": None,
        "sort_rank": 0,  # source_rank: probe is 0 (control 4.4 step 4)
    }


# -- record_signal (control 3b/4.7) ------------------------------------------


def record_signal(
    store: EventStore,
    clock: Clock,
    random_source: RandomSource,
    *,
    kind: str,
    payload: dict[str, Any],
    policy: dict[str, Any],
    idempotency_key: str | None = None,
    actor: str = "engine",
) -> dict[str, Any]:
    """Record a learner control signal (control 4.7). Idempotent by
    ``(operation, idempotency_key)``.

    Saves the signal and publishes ``LEARNER_SIGNAL_RECORDED`` in one UnitOfWork;
    for ``too_easy`` it also mints a stable engine ``probe_id`` and publishes
    ``PROBE_REQUESTED`` -- but it NEVER mutates the live plan. When a session is
    active the return carries ``next_action: session.replan``, ``session_id``,
    ``current_plan_version`` and (for ``too_easy``) ``probe_id``: the plan effect
    lands only on the next ``compose_session`` or an explicit ``replan``.
    """
    request_hash = payload_hash({"command": "signal", "kind": kind, "payload": payload})

    with UnitOfWork(store, clock) as uow:
        if idempotency_key is not None:
            prior = uow.check_idempotency(idempotency_key, request_hash)
            if isinstance(prior, CachedResult):
                # Idempotent replay: the stored result comes back, nothing is
                # re-derived and no second event is written (control 4.7).
                return {**prior.value, "cached": True}

        # Validation and probe derivation run inside the transaction so a refusal
        # rolls the (empty) UoW back and writes nothing. One event snapshot feeds
        # every derivation (session_seq, active session, plan version, probe).
        events = list(store.read())
        current_seq = sum(1 for event in events if event.type == EVENT_SESSION_STARTED)
        signal_record = build_signal(kind, payload, current_seq, policy)
        active_id = _active_session(events)

        probe_params: dict[str, Any] | None = None
        probe_id: str | None = None
        if kind == "too_easy":
            probe_params = derive_probe(events, str(signal_record["target_ref"]), active_id)
            probe_id = new_ulid(clock, random_source)

        signal_id = new_ulid(clock, random_source)
        recorded_at = clock.now().isoformat()
        pinned = {"control": str(policy.get("policy_id") or "control@1")}

        new_events = [
            make_event(
                id=new_ulid(clock, random_source),
                type=EVENT_SIGNAL_RECORDED,
                occurred_at=clock.now(),
                actor=actor,
                correlation_id=active_id or signal_id,
                payload={
                    "signal_id": signal_id,
                    "recorded_at": recorded_at,
                    "current_session_seq": current_seq,
                    "signal": signal_record,
                },
                pinned_versions=pinned,
            )
        ]
        if probe_params is not None and probe_id is not None:
            new_events.append(
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_PROBE_REQUESTED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=active_id or signal_id,
                    payload={
                        "probe_id": probe_id,
                        "signal_id": signal_id,
                        "target_ref": probe_params["target_ref"],
                        "dimension": probe_params["dimension"],
                        "requested_difficulty": probe_params["requested_difficulty"],
                        "avoid_context": probe_params["avoid_context"],
                    },
                    pinned_versions=pinned,
                )
            )
        uow.append(new_events)

        result: dict[str, Any] = {"signal_id": signal_id, "kind": kind, "recorded": True}
        if active_id is not None:
            # Recording never edits the plan; the agent must replan explicitly.
            result["next_action"] = "session.replan"
            result["session_id"] = active_id
            result["current_plan_version"] = _current_plan_version(events, active_id)
        if probe_params is not None and probe_id is not None:
            result["probe_id"] = probe_id
            result["probe"] = probe_params

        if idempotency_key is not None:
            uow.record_result(idempotency_key, request_hash, result)
    return {**result, "cached": False}
