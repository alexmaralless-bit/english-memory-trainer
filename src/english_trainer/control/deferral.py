"""The ``deferral_count`` lifecycle and starvation qualification (control 4.5 [R-6]).

A ``due`` target is a candidate, not a right (control 4.1): systematic selection
can pass it over session after session. The starvation reserve (control 4.4 step
6 / 4.5 [CTRL-7]) guarantees it is not starved forever -- but only for targets
that have *qualified*, and qualification is this fold.

``deferral_count`` is keyed ``(target_ref, dimension)`` -- like ``SaturationState``,
per-dimension so that presenting a target's recognition dimension does not clear
a deferral standing against its weak production. The counter **changes at most
once per session** [R-6], at the session's ``FINISHED``/``ABANDONED``:

- ``+1`` when the pair was an eligible review candidate of the session, was
  admitted to none of its recorded revisions purely by systematic selection, and
  was not excluded by a learner signal;
- reset to ``0`` when a ``STEP_PRESENTED`` delivered it (presentation dominates);
- otherwise unchanged. Several replans of one session never multiply the change.

Reaching ``deferrals_to_qualify`` opens one qualification episode and fixes
``qualified_at_session_seq``; the first subsequent **admission** (a step in a
recorded revision, not necessarily a delivery) closes it, so an admitted-but-
unpresented target does not capture the reserve forever. Without a
``STEP_PRESENTED`` a new episode opens only after a fresh systematic deferral in
a later terminalized session. The reserve order
``(qualified_at_session_seq asc, deferral_count desc, retrievability asc,
target_id asc, dimension_id asc)`` then lets older episodes go first -- new ones
never overtake open ones -- which is what makes the waiting bound
``ceil(|Q| / reserved_steps_per_session)`` hold (control 4.5 [R-6, RR2-8]).

The lessons composition boundary records which review candidates were
*eligible* and which a learner signal *excluded* in ``SESSION_COMPOSED``. The
fold can also take an explicit ``eligibility`` mapping for projections and
tests; absent both sources it defaults to empty, so missing historical facts do
not manufacture deferrals.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from english_trainer.control.saturation import EVENT_SESSION_STARTED, EVENT_STEP_PRESENTED, Key, target_pairs
from english_trainer.kernel.envelopes import DomainEvent

EVENT_SESSION_COMPOSED = "session.composed"
EVENT_SESSION_FINISHED = "session.finished"
EVENT_SESSION_ABANDONED = "session.abandoned"

# eligibility[session_id] = {"eligible": {Key, ...}, "excluded": {Key, ...}}.
Eligibility = Mapping[str, Mapping[str, Iterable[Key]]]


@dataclass(frozen=True)
class DeferralState:
    """Per-``(target_ref, dimension)`` starvation standing (control 4.5).

    ``qualified_at_session_seq`` is the session sequence at which the *currently
    open* qualification episode reached the threshold, or ``None`` when no episode
    is open (never qualified, or the last one was closed by admission/reset).
    """

    deferral_count: int = 0
    qualified_at_session_seq: int | None = None


def _seq(event: DomainEvent) -> int:
    return event.sequence if event.sequence is not None else 0


def _pair(item: Any) -> Key | None:
    """A ``(target_ref, dimension)`` from a tuple or a ``{target_ref, dimension}``."""
    if isinstance(item, tuple):
        return (str(item[0]), str(item[1]))
    if isinstance(item, Mapping):
        ref, dim = item.get("target_ref"), item.get("dimension")
        if ref is not None and dim is not None:
            return (str(ref), str(dim))
    return None


def _pairs(items: Iterable[Any]) -> set[Key]:
    out: set[Key] = set()
    for item in items:
        key = _pair(item)
        if key is not None:
            out.add(key)
    return out


def reduce_deferrals(
    events: Iterable[DomainEvent],
    policy: dict[str, Any],
    *,
    eligibility: Eligibility | None = None,
) -> dict[Key, DeferralState]:
    """Fold terminalized sessions into per-``(target, dimension)`` ``DeferralState``.

    Deterministic: events in canonical ``sequence`` order, deduped by ``event_id``;
    per-session categories resolved in sorted key order at each terminalization.
    """
    to_qualify = int(policy["starvation"]["deferrals_to_qualify"])

    seen: set[str] = set()
    session_seq = 0
    seq_of: dict[str, int] = {}
    admitted: dict[str, set[Key]] = defaultdict(set)
    presented: dict[str, set[Key]] = defaultdict(set)
    composed_eligible: dict[str, set[Key]] = defaultdict(set)
    composed_excluded: dict[str, set[Key]] = defaultdict(set)

    count: dict[Key, int] = {}
    episode: dict[Key, int | None] = {}

    def terminalize(session_id: str) -> None:
        seq = seq_of.get(session_id, session_seq)
        if eligibility is not None:
            snapshot = eligibility.get(session_id) or {}
            eligible = _pairs(snapshot.get("eligible", ()))
            excluded = _pairs(snapshot.get("excluded", ()))
        else:
            eligible = composed_eligible.get(session_id, set())
            excluded = composed_excluded.get(session_id, set())
        adm = admitted.get(session_id, set())
        pres = presented.get(session_id, set())

        for key in sorted(eligible | adm | pres):
            if key in pres:
                # Presentation dominates: the target got attention -> reset.
                count[key] = 0
                episode[key] = None
            elif key in adm:
                # Admitted but not presented: close any open episode, count held.
                episode[key] = None
            elif key in eligible and key not in excluded:
                # Systematic deferral: the single per-session increment [R-6].
                count[key] = count.get(key, 0) + 1
                if count[key] >= to_qualify and episode.get(key) is None:
                    episode[key] = seq

    for event in sorted(events, key=_seq):
        if event.id in seen:
            continue
        seen.add(event.id)
        etype = event.type
        session_id = str(event.correlation_id)
        if etype == EVENT_SESSION_STARTED:
            session_seq += 1
            seq_of[session_id] = session_seq
            continue
        if etype == EVENT_SESSION_COMPOSED:
            for step in event.payload.get("steps") or []:
                if str(step.get("kind")) == "review":
                    key = _pair(step)
                    if key is not None:
                        admitted[session_id].add(key)
            composed_eligible[session_id] |= _pairs(event.payload.get("eligible_review") or [])
            composed_excluded[session_id] |= _pairs(event.payload.get("excluded_review") or [])
            continue
        if etype == EVENT_STEP_PRESENTED:
            presented[session_id].update(target_pairs(event.payload))
            continue
        if etype in (EVENT_SESSION_FINISHED, EVENT_SESSION_ABANDONED):
            terminalize(session_id)
            continue

    out: dict[Key, DeferralState] = {}
    for key in set(count) | set(episode):
        deferrals = count.get(key, 0)
        open_episode = episode.get(key)
        if deferrals > 0 or open_episode is not None:
            out[key] = DeferralState(deferral_count=deferrals, qualified_at_session_seq=open_episode)
    return out


def qualified_candidates(
    review_candidates: Iterable[dict[str, Any]],
    deferrals: Mapping[Key, DeferralState],
) -> list[dict[str, Any]]:
    """Review candidates whose ``(target, dimension)`` has an OPEN qualification
    episode -- the starvation reserve set :func:`compose_plan` admits first.

    Each returned candidate carries ``qualified_at_session_seq`` and
    ``deferral_count`` so the reserve order is self-contained. This is the shape
    the lessons wiring hands to ``compose_plan``.
    """
    out: list[dict[str, Any]] = []
    for candidate in review_candidates:
        key = (str(candidate.get("target_ref")), str(candidate.get("dimension")))
        state = deferrals.get(key)
        if state is not None and state.qualified_at_session_seq is not None:
            out.append(
                {
                    **candidate,
                    "deferral_count": state.deferral_count,
                    "qualified_at_session_seq": state.qualified_at_session_seq,
                }
            )
    return out
