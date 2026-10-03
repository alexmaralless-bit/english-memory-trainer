"""``scheduler@2`` activation follows the shipped v1/v2 precedent (e.g.
control-v1.yaml/control-v2.yaml): ``trainer curriculum activate`` registers
and activates every ``curriculum/policies/*.yaml`` file in sorted glob order
(``curriculum/loader.py::load_policies``), so ``scheduler-v2.yaml`` sorts
after ``scheduler-v1.yaml`` and wins the ``scheduler`` kind's active pointer
-- new sessions pin ``scheduler@2`` from then on. Activation is never
retroactive (foundation 3.6): ``scheduler@1`` stays registered and resolves
by its pin.

This test exercises the real ``curriculum/`` directory (the same fixture
``curriculum_dir`` pattern ``tests/cli/test_cli.py`` uses for
``trainer curriculum activate``), but drives the registry directly instead of
the CLI, since this work item's boundary does not include ``cli/``.
"""

from __future__ import annotations

from pathlib import Path

from english_trainer.curriculum.loader import load_policies
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.scheduler.policy import require_valid as require_valid_scheduler

REPO = Path(__file__).resolve().parents[2]
CURRICULUM = REPO / "curriculum"


def test_load_policies_lists_both_scheduler_versions_v2_last() -> None:
    scheduler_entries = [
        (kind, version) for kind, version, _ in load_policies(CURRICULUM) if kind == "scheduler"
    ]
    assert scheduler_entries == [("scheduler", "scheduler@1"), ("scheduler", "scheduler@2")]


def test_activating_every_shipped_policy_selects_v2_for_new_sessions_and_keeps_v1_pinned(
    store, clock
) -> None:
    registry = PolicyRegistry(store._conn, clock)
    # Mirrors cli/app.py's curriculum_activate loop: register + activate every
    # policy file in the order load_policies returns (sorted glob order), so
    # the LAST file registered for a kind wins that kind's active pointer.
    for kind, policy_version, payload in load_policies(CURRICULUM):
        if kind == "scheduler":
            require_valid_scheduler(payload)
        registry.register(kind, policy_version, payload)
        registry.activate(kind, policy_version)

    # New sessions pin whatever is active now: scheduler@2.
    assert registry.active_version("scheduler") == "scheduler@2"

    # Nothing retroactive: scheduler@1 is still registered and resolves by its
    # pin, exactly as replay/resume require (foundation 3.6).
    v1_payload = registry.resolve_pinned("scheduler", "scheduler@1")
    assert v1_payload["policy_id"] == "scheduler@1"
    assert "relearning_ladder_days" not in v1_payload
    assert registry.status("scheduler", "scheduler@1") == "registered"

    v2_payload = registry.resolve_pinned("scheduler", "scheduler@2")
    assert v2_payload["policy_id"] == "scheduler@2"
    assert v2_payload["relearning_ladder_days"] == [1, 2, 4]
