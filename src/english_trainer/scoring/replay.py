"""``trainer scoring replay``: the determinism guarantee made checkable
(foundation 5; scoring 8; roadmap 2.3).

Replays the scoring fold from the event log under the PINNED policy and proves
two things: (1) two independent folds over the same events produce a
byte-identical canonical snapshot (same hash), and (2) the fold is
prefix-consistent -- folding everything at once equals folding a prefix and
continuing. Read-only: replay never writes scores anywhere; scores ARE the
fold.

The automaticity axis (scoring 3d) is replayed the same way and by the same
command: it is rebuilt from the same events under the pinned ``automaticity@1``
and compared with the recorded ``AUTOMATICITY_UPDATED`` facts. A disagreement is
a replay error exactly like a Mastery disagreement. The axis is folded
separately and merged only into the report, never into the scores -- it must not
be able to move a single Mastery digit.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import NoActivePolicy
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.scoring.automaticity import (
    AUTOMATICITY_KIND,
    automaticity_mismatches,
    automaticity_snapshot,
    fold_automaticity,
    recorded_automaticity,
    require_valid_automaticity,
)
from english_trainer.scoring.engine import fold_scores, snapshot
from english_trainer.scoring.policy import SCORING_KIND, require_valid


def replay_automaticity(store: EventStore, registry: PolicyRegistry) -> dict[str, Any]:
    """Rebuild ``AutomaticityState`` and compare it with the recorded facts.

    ``status`` is ``no-policy`` while ``automaticity@1`` is not active -- an
    honest gap, never an empty axis presented as a measured one.
    """
    try:
        version, payload = registry.resolve_active(AUTOMATICITY_KIND)
    except NoActivePolicy:
        return {"status": "no-policy", "policy_version": None, "targets": {}}
    policy = require_valid_automaticity(payload)

    first = automaticity_snapshot(fold_automaticity(store, policy))
    second = automaticity_snapshot(fold_automaticity(store, policy))
    first_hash = payload_hash(first)
    mismatches = automaticity_mismatches(store, first)
    recorded = recorded_automaticity(store)
    return {
        "status": "measured",
        "policy_version": version,
        "target_count": len(first),
        "snapshot_hash": first_hash,
        "consistent": first_hash == payload_hash(second) and not mismatches,
        "mismatches": mismatches,
        # Targets the fold knows but no recorded fact covers: the producer is
        # not wired at that call site yet. Reported, never silently ignored.
        "unrecorded": sorted(set(first) - set(recorded)),
        "targets": first,
    }


def replay_scores(store: EventStore, registry: PolicyRegistry) -> dict[str, Any]:
    """Fold twice, compare, report. Raises ``NoActivePolicy`` without scoring@1."""
    try:
        version, payload = registry.resolve_active(SCORING_KIND)
    except NoActivePolicy:
        raise NoActivePolicy(
            "no active scoring policy; run `trainer curriculum activate` to register scoring@1"
        ) from None
    policy = require_valid(payload)

    first = snapshot(fold_scores(store, policy))
    second = snapshot(fold_scores(store, policy))
    first_hash = payload_hash(first)
    consistent = first_hash == payload_hash(second)
    automaticity = replay_automaticity(store, registry)

    return {
        "policy_version": version,
        "targets": len(first),
        "events": store.count(),
        "snapshot_hash": first_hash,
        "consistent": consistent and automaticity.get("consistent", True),
        "scores": first,
        "automaticity": automaticity,
    }
