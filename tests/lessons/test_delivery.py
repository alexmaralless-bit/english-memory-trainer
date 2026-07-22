"""Step delivery under CAS (2.2 increment 2): claiming mutates plan, ledger
and version atomically; peek observes; replan recomposes the remainder."""

from __future__ import annotations

import pytest

from english_trainer.control.errors import PlanVersionConflict
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.session_fence import current_session_revision
from english_trainer.kernel.store import EventStore
from english_trainer.lessons.delivery import next_step, peek_step, production_eligible, replan_session
from english_trainer.lessons.sessions import (
    EVENT_STEP_PRESENTED,
    IN_PROGRESS,
    SessionPrecondition,
    abandon_session,
    get_plan,
    get_session,
    start_session,
)


def _start(store: EventStore, registry: PolicyRegistry, clock, rnd) -> str:
    manifest = start_session(store, registry, clock, rnd, provider="claude-code")
    return str(manifest["session_id"])


def test_start_composes_the_plan_aggregate(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    _, plan, _ = get_plan(store, session_id)
    assert plan["composition_revision"] == 1 and plan["plan_version"] == 1
    assert plan["total_seconds"] == 1800  # policy default: 30 minutes
    assert len(plan["steps"]) == 5  # 3 topics + micro-lane unit + free conversation
    assert plan["active_safety_version"] == "v-test"


def test_peek_is_read_only(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    events_before = store.count()
    view = peek_step(store, session_id)
    assert view["plan_version"] == 1 and view["steps_remaining"] == 5
    assert view["step"]["target_ref"] == "grammar.be.identity"
    assert store.count() == events_before  # nothing published
    _, plan, _ = get_plan(store, session_id)
    assert plan["plan_version"] == 1  # nothing marked


def test_next_claims_atomically_and_flips_the_session(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    result = next_step(
        store,
        registry,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    assert result["plan_version"] == 2
    step = result["step"]
    assert step["target_ref"] == "grammar.be.identity" and step["presented_at"] is not None

    state, _ = get_session(store, session_id)
    assert state["status"] == IN_PROGRESS  # first real work, same transaction

    _, plan, _ = get_plan(store, session_id)
    assert plan["plan_version"] == 2
    assert plan["budget"]["planned"]["growth"] == 900  # 1200 - 300 moved out...
    assert plan["ledger"]["presented"]["growth"] == 300  # ...and in here
    assert plan["ledger"]["remaining_seconds"] == 1500

    presented = [e for e in store.read() if e.type == EVENT_STEP_PRESENTED]
    assert len(presented) == 1
    payload = presented[0].payload
    assert payload["targets"] == [{"target_ref": "grammar.be.identity", "dimension": "recognition"}]
    assert payload["plan_version"] == 2 and payload["active_safety_version"] == "v-test"
    # Exactly one exercise source (control 4.3a).
    assert "generation_directive_hash" in payload and "bank_item_id" not in payload


def test_stale_version_is_a_conflict_with_the_current_version(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    next_step(
        store,
        registry,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )
    with pytest.raises(PlanVersionConflict) as caught:
        next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            expected_plan_version=1,
        )
    assert caught.value.current_plan_version == 2
    _, plan, _ = get_plan(store, session_id)
    assert plan["plan_version"] == 2  # the losing claim wrote nothing


def test_exhausted_plan_points_to_replan(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    for version in range(1, 6):
        next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            expected_plan_version=version,
        )
    with pytest.raises(SessionPrecondition, match="exhausted"):
        next_step(
            store,
            registry,
            clock,
            random_source,
            session_id,
            expected_session_revision=current_session_revision(store, session_id),
            expected_plan_version=6,
        )


def test_replan_recomposes_only_the_remainder(store, registry, clock, random_source) -> None:
    session_id = _start(store, registry, clock, random_source)
    _, before, _ = get_plan(store, session_id)
    surviving = {s["candidate_id"]: s["step_id"] for s in before["steps"][1:]}
    first = next_step(
        store,
        registry,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=1,
    )

    result = replan_session(
        store,
        registry,
        clock,
        random_source,
        session_id,
        expected_session_revision=current_session_revision(store, session_id),
        expected_plan_version=2,
    )
    assert result["composition_revision"] == 2 and result["plan_version"] == 3

    _, plan, _ = get_plan(store, session_id)
    assert plan["ledger"]["presented"]["growth"] == 300  # the fact survives replan
    assert plan["ledger"]["remaining_seconds"] == 1500
    presented = [s for s in plan["steps"] if s["presented_at"] is not None]
    assert [s["step_id"] for s in presented] == [first["step"]["step_id"]]  # kept verbatim
    for step in plan["steps"]:
        if step["presented_at"] is None:
            # The presented target is out of growth; survivors keep their ids.
            assert step.get("target_ref") != "grammar.be.identity"
            if step["candidate_id"] in surviving:
                assert step["step_id"] == surviving[step["candidate_id"]]


def test_first_exposure_spans_sessions(store, registry, clock, random_source) -> None:
    first = _start(store, registry, clock, random_source)
    next_step(
        store,
        registry,
        clock,
        random_source,
        first,
        expected_session_revision=current_session_revision(store, first),
        expected_plan_version=1,
    )
    abandon_session(
        store,
        clock,
        random_source,
        first,
        expected_session_revision=current_session_revision(store, first),
    )

    second = _start(store, registry, clock, random_source)
    view = peek_step(store, second)
    # grammar.be.identity had a STEP_PRESENTED in the abandoned session: it is
    # no longer first exposure anywhere (control 4.3), growth starts at the
    # next topic.
    assert view["step"]["target_ref"] == "grammar.pronouns.possessives"


def test_production_eligible_guards_restricted_units() -> None:
    program = {"lexicon": [{"id": "slang.x", "usage_policy": "recognition_only"}]}
    production = {
        "step_type": "controlled_production",
        "generation_directive": {"lexicon_refs": ["slang.x"]},
    }
    eligible, reason = production_eligible(production, program)
    assert not eligible and reason is not None and "recognition-only" in reason
    intro = {"step_type": "new_material_intro", "generation_directive": {"lexicon_refs": ["slang.x"]}}
    assert production_eligible(intro, program) == (True, None)
