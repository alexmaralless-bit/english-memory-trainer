"""The starvation reserve inside the composition pipeline (control 4.4 step 6 /
4.5 [CTRL-7]): unconditional admission before review-by-class, the reserve order,
the STARVATION_STEP_DOES_NOT_FIT waiting bound, and byte-determinism.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from english_trainer.control.compose import compose_plan
from english_trainer.control.policy import step_cost
from english_trainer.kernel.encoding import canonical_json

REPO = Path(__file__).resolve().parents[2]
EMPTY_PROGRAM: dict[str, Any] = {"topics": [], "lexicon": []}


def policy() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / "control-v1.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def rc(
    cid: str,
    urgency: str,
    retr_ppm: int,
    *,
    step_type: str = "spontaneous_production",
    qualified_seq: int | None = None,
    deferral_count: int = 0,
) -> dict[str, Any]:
    """A normalized review candidate the pipeline can admit and materialize."""
    return {
        "candidate_id": cid,
        "kind": "review",
        "bucket": "review",
        "step_type": step_type,
        "expected_seconds": step_cost(policy(), step_type),
        "target_ref": cid,
        "dimension": "spontaneous_production",
        "urgency_class": urgency,
        "stake_rank": 2,
        "retrievability_ppm": retr_ppm,
        "deferral_count": deferral_count,
        "qualified_at_session_seq": qualified_seq,
        "criteria_ref": None,
        "context_id": f"review|{step_type}",
        "lexicon_first": False,
        "lexicon_refs": [],
        "schedule_epoch": 0,
    }


def compose(**overrides: Any) -> dict[str, Any]:
    counter = iter(range(10_000))
    defaults: dict[str, Any] = {
        "program": EMPTY_PROGRAM,
        "policy": policy(),
        "generation_version": "generation@1",
        "mode": "balanced",
        "total_seconds": 1800,
        "new_id": lambda: f"id-{next(counter):04d}",
    }
    defaults.update(overrides)
    return compose_plan(**defaults)


def review_targets(plan: dict[str, Any]) -> list[str]:
    return [s["target_ref"] for s in plan["steps"] if s["kind"] == "review"]


# -- the reserve admits a starved target that class-ordering would crowd out --


def test_reserve_admits_the_qualified_target_before_review_by_class() -> None:
    # review_cap at 1800 balanced = 810s; each spontaneous_production step is 360s,
    # so review-by-class fits only two. Two criticals would take both slots and
    # crowd out the high-retrievability (maintenance) qualified target.
    c1 = rc("crit-1", "critical", 100_000)
    c2 = rc("crit-2", "critical", 200_000)
    starved = rc("starved", "maintenance", 900_000, qualified_seq=1, deferral_count=3)
    candidates = [c1, c2, starved]

    without = compose(review_candidates=copy.deepcopy(candidates))
    assert "starved" not in review_targets(without)  # crowded out by the two criticals
    assert {"crit-1", "crit-2"} <= set(review_targets(without))

    with_reserve = compose(
        review_candidates=copy.deepcopy(candidates), starvation_candidates=[copy.deepcopy(starved)]
    )
    targets = review_targets(with_reserve)
    # The reserve seats the starved target first; one critical is displaced.
    assert "starved" in targets
    assert len(targets) == 2 and "crit-2" not in targets


def test_reserve_bypasses_the_review_cap_it_precedes() -> None:
    # A lone qualified step of 360s admitted even though review_cap here is only
    # 270s (600s balanced * 4500bp): the reserve is unconditional (4.5 [CTRL-7]).
    starved = rc("starved", "maintenance", 900_000, qualified_seq=1, deferral_count=3)
    plan = compose(
        total_seconds=780,
        review_candidates=[copy.deepcopy(starved)],
        starvation_candidates=[copy.deepcopy(starved)],
    )
    assert "starved" in review_targets(plan)
    # review planned (360) exceeds the cap floor(780*4500/10000)=351 -> bypassed.
    assert plan["budget"]["planned"]["review"] == 360


# -- the reserve order and the waiting bound (control 4.5 [R-6, RR2-8]) -------


def test_reserve_order_is_oldest_qualification_first() -> None:
    older = rc("older", "maintenance", 500_000, qualified_seq=1)
    younger = rc("younger", "maintenance", 100_000, qualified_seq=2)  # better retrievability
    two_slots = copy.deepcopy(policy())
    two_slots["starvation"]["reserved_steps_per_session"] = 2
    plan = compose(
        policy=two_slots,
        review_candidates=[copy.deepcopy(younger), copy.deepcopy(older)],
        starvation_candidates=[copy.deepcopy(younger), copy.deepcopy(older)],
    )
    # qualified_at_session_seq asc wins over the younger's lower retrievability.
    assert review_targets(plan) == ["older", "younger"]


def test_waiting_bound_admits_two_episodes_within_two_sessions() -> None:
    # |Q| = 2, reserved_steps_per_session = 1 => bound ceil(2/1) = 2 sessions.
    # transfer_task steps (480s): after one reserve step the 810s cap blocks the
    # other from review-by-class, so the younger episode genuinely waits.
    older = rc("older", "maintenance", 500_000, step_type="transfer_task", qualified_seq=1)
    younger = rc("younger", "maintenance", 600_000, step_type="transfer_task", qualified_seq=2)

    first = compose(
        review_candidates=[copy.deepcopy(older), copy.deepcopy(younger)],
        starvation_candidates=[copy.deepcopy(older), copy.deepcopy(younger)],
    )
    assert review_targets(first) == ["older"]  # oldest seated, younger waits (FIFO)

    # Next composition: the older episode is closed (admitted), only the younger
    # remains in Q -> it is seated. Both admitted within two sessions.
    second = compose(
        review_candidates=[copy.deepcopy(younger)],
        starvation_candidates=[copy.deepcopy(younger)],
    )
    assert review_targets(second) == ["younger"]


def test_a_step_too_large_records_starvation_step_does_not_fit() -> None:
    # 600s: the choice floor takes free conversation (300s), leaving 300s -- a
    # 360s reserve step does not fit, so the episode is not consumed.
    starved = rc("starved", "maintenance", 900_000, qualified_seq=1)
    plan = compose(
        total_seconds=600,
        review_candidates=[copy.deepcopy(starved)],
        starvation_candidates=[copy.deepcopy(starved)],
    )
    assert "STARVATION_STEP_DOES_NOT_FIT" in plan["waivers"]
    assert "starved" not in review_targets(plan)


# -- backward compatibility and determinism ----------------------------------


def test_default_path_is_unchanged_by_the_new_parameter() -> None:
    candidates = [rc("crit-1", "critical", 100_000)]
    omitted = compose(review_candidates=copy.deepcopy(candidates))
    explicit_none = compose(review_candidates=copy.deepcopy(candidates), starvation_candidates=None)
    assert canonical_json(omitted) == canonical_json(explicit_none)


def test_reserve_composition_is_byte_deterministic() -> None:
    starved = rc("starved", "maintenance", 900_000, qualified_seq=1, deferral_count=3)
    kwargs: dict[str, Any] = {
        "review_candidates": [copy.deepcopy(starved)],
        "starvation_candidates": [copy.deepcopy(starved)],
    }
    first = canonical_json(compose(**copy.deepcopy(kwargs)))
    second = canonical_json(compose(**copy.deepcopy(kwargs)))
    assert first == second
