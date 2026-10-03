"""Learner control signals and probes: the READ side (control 4.7; roadmap 2.8a).

A signal is a **discriminated union by ``kind``** with per-kind payload and one
of two expiry types [R-11]:

- ``expires_at`` -- a UTC timestamp (``snooze``/``until`` and
  ``not_relevant_now``); the signal is active while ``now < expires_at``;
- ``expires_after_session_seq`` -- an integer session number
  (``too_repetitive``/``need_more_practice``/``prefer_different_context``/
  ``lesson_request``); the signal is active for a composition with
  ``session_seq <= expires_after``.

``too_easy`` is one-shot: it is consumed atomically when a composition actually
adds the probe step it requests. ``session_seq`` is the monotonic per-learner
session number, DERIVED here from the ``SESSION_STARTED`` event stream (its
count; ``0`` if none) -- signals read published events, they never import
lessons/evidence/scheduler code.

The write path (``trainer signal`` / ``record_signal``, publishing
``LEARNER_SIGNAL_RECORDED`` and, for ``too_easy``, ``PROBE_REQUESTED``) was
removed with the per-step protocol [PD-2026-09-23]. Signals already in the
log stay in force until they expire: :func:`active_signals` folds them, the
precedence rules (:func:`apply_signals`) and the probe candidate
(:func:`build_probe_candidate`) stay pure and keep feeding composition
(compose 4.4 steps 3a/6a), so a historic log composes exactly as before.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from english_trainer.control.policy import step_cost
from english_trainer.kernel.store import EventStore

# Event names control owns (control 3b, 6). ``LEARNER_SIGNAL_RECORDED`` and
# ``PROBE_REQUESTED`` are no longer written (the ``signal`` command was
# removed) but historic logs carry them; ``SIGNAL_CONSUMED`` is still written
# when a composition admits a historic probe.
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


# Strong -> weak application order (control 4.7 precedence list). Exclusions are
# strongest; too_easy (probe only, no class change) is weakest.
_KIND_RANK: dict[str, int] = {
    "snooze": 0,
    "not_relevant_now": 0,
    "need_more_practice": 1,
    "prefer_different_context": 2,
    "too_repetitive": 3,
    "too_easy": 4,
    "lesson_request": 5,
}

# Non-exclusion target-scoped kinds: their presence on a target overrides a
# conflicting *domain*-scoped exclusion for that target (control 4.7
# "target-scope beats a conflicting domain-scope signal").
_OVERRIDE_KINDS = frozenset({"need_more_practice", "prefer_different_context", "too_repetitive", "too_easy"})

# The urgency ladder, weakest -> strongest (control 4.5 classes).
_LADDER: tuple[str, ...] = ("deferrable", "maintenance", "normal", "important", "critical")


# -- event-derived learner facts (control 4.7) -------------------------------


def current_session_seq(store: EventStore) -> int:
    """The monotonic per-learner session number (control 4.7): the count of
    ``SESSION_STARTED`` events. The last started session carries this number;
    ``0`` when no session has ever started."""
    return sum(1 for event in store.read() if event.type == EVENT_SESSION_STARTED)


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
