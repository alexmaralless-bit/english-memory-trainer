"""``trainer scoring replay``: the determinism guarantee made checkable
(foundation 5; scoring 8; roadmap 2.3).

Replays the scoring fold from the event log under the PINNED policy and proves
two things: (1) two independent folds over the same events produce a
byte-identical canonical snapshot (same hash), and (2) the fold is
prefix-consistent -- folding everything at once equals folding a prefix and
continuing. Read-only: replay never writes scores anywhere; scores ARE the
fold.
"""

from __future__ import annotations

from typing import Any

from english_trainer.kernel.encoding import payload_hash
from english_trainer.kernel.errors import NoActivePolicy
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.scoring.engine import fold_scores, snapshot
from english_trainer.scoring.policy import SCORING_KIND, require_valid


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

    return {
        "policy_version": version,
        "targets": len(first),
        "events": store.count(),
        "snapshot_hash": first_hash,
        "consistent": consistent,
        "scores": first,
    }
