"""The automaticity-loop forms (generation@3) as the lesson brief carries them
(lessons 4b; [PD-2026-09-23]).

The forms exist only under the SESSION-PINNED generation policy, and the brief
hands the tutor, per advisory plan step, the authored material it builds the
items from -- the frames of the primary and contrast targets, or the chosen
reconstruction text -- deterministically, from the pinned snapshot plus the
event log. That material is a VIEW: the persisted plan keeps the directive
control composed. (The render-time snapshot validation, content hash and bank
dedup went away with the step-delivery protocol.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.lessons.brief import recent_reconstruction_text_ids
from english_trainer.lessons.forms import choose_reconstruction_text, directive_view
from english_trainer.lessons.sessions import get_plan, start_session

REPO = Path(__file__).resolve().parents[2]

PRESENT_PERFECT = "grammar.present-perfect.result"
PAST_SIMPLE = "grammar.past-simple.finished-time"
ARTICLES = "grammar.articles.second-mention"


def _frame(topic: str, slug: str, title: str) -> dict[str, Any]:
    return {
        "id": f"chunk.{slug}",
        "type": "chunk",
        "title": title,
        "cefr": "A2",
        "curriculum_priority_band": "CORE",
        "register": "neutral",
        "transparency": "transparent",
        "domains": ["work"],
        "meaning_ru": f"смысл {slug}",
        "frame_of": topic,
        "carries": ["tense:present-perfect"],
        "slot_hint_ru": "глагол в третьей форме",
        "examples": [f"{title.replace('___', 'sent the report')}"],
        "contrast": {"frame": "I sent ___", "note_ru": "прошедшее время и явная дата"},
        "trap": {
            "learner_form": "I already sent the report.",
            "correction": "I've already sent the report.",
            "cause_ru": "результат сейчас требует Present Perfect",
        },
        "usage_policy": "safe_to_use",
        "currency": "current",
        "transformations": ["authored"],
    }


PP_FRAMES = [
    _frame(PRESENT_PERFECT, "pp.already-sent", "I've already ___"),
    _frame(PRESENT_PERFECT, "pp.just-finished", "I've just ___"),
    _frame(PRESENT_PERFECT, "pp.not-yet", "I haven't ___ yet"),
]
PS_FRAMES = [_frame(PAST_SIMPLE, "ps.sent-yesterday", "I ___ yesterday")]
ART_FRAMES = [_frame(ARTICLES, "art.the-report", "the ___ I mentioned")]


def _topic(topic_id: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": topic_id,
        "track": "Grammar Engine",
        "cefr": "A2",
        "frequency_tier": "big-five",
        "dimensions": ["recognition", "controlled_production"],
        "contexts": ["status-update"],
        "lexicon": [frame["id"] for frame in frames],
    }


# Two reconstruction texts on the drilled topic, authored out of id order so the
# "first by id" rule is visible rather than accidental.
TEXTS = [
    {
        "schema_version": 1,
        "id": "text.recon.present-perfect-result.migration",
        "topic": PRESENT_PERFECT,
        "title": "Migration update",
        "cefr": "A2",
        "carries": ["tense:present-perfect"],
        "domain": "work",
        "context": "deployment-update",
        "text": "We have already migrated the data and the exports have finished.",
        "word_count": 11,
        "keywords": ["already", "migrate", "exports", "finish"],
        "target_spans": ["have already migrated", "have finished"],
        "transformations": ["authored"],
    },
    {
        "schema_version": 1,
        "id": "text.recon.present-perfect-result.handover",
        "topic": PRESENT_PERFECT,
        "title": "Handover note",
        "cefr": "A2",
        "carries": ["tense:present-perfect"],
        "domain": "work",
        "context": "handover",
        "text": "I have just finished the handover and I have not closed the ticket yet.",
        "word_count": 14,
        "keywords": ["just", "finish", "handover", "ticket"],
        "target_spans": ["have just finished", "have not closed"],
        "transformations": ["authored"],
    },
]

PROGRAM: dict[str, Any] = {
    "schema_version": 1,
    "topics": [
        _topic(PRESENT_PERFECT, PP_FRAMES),
        _topic(PAST_SIMPLE, PS_FRAMES),
        _topic(ARTICLES, ART_FRAMES),
    ],
    "lexicon": [*PP_FRAMES, *PS_FRAMES, *ART_FRAMES],
    "texts": TEXTS,
}


def _policy(filename: str) -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / "curriculum" / "policies" / filename).read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def v3_registry(store: EventStore, clock: FixedClock) -> PolicyRegistry:
    """A registry pinning the automaticity layer: control@3 + generation@3.

    generation@1/@2 and control@1/@2 stay registered beside them -- the point of
    a version is that the old ones remain resolvable for the sessions that
    pinned them.
    """
    registry = PolicyRegistry(store._conn, clock)
    registry.register("curriculum", "v-test", PROGRAM)
    registry.activate("curriculum", "v-test")
    for kind, filename, version in (
        ("control", "control-v1.yaml", "control@1"),
        ("control", "control-v2.yaml", "control@2"),
        ("control", "control-v3.yaml", "control@3"),
        ("generation", "generation-v1.yaml", "generation@1"),
        ("generation", "generation-v2.yaml", "generation@2"),
        ("generation", "generation-v3.yaml", "generation@3"),
        ("rubric", "rubric-v1.yaml", "rubric@1"),
    ):
        registry.register(kind, version, _policy(filename))
        registry.activate(kind, version)
    return registry


def _start_drill(
    store: EventStore,
    registry: PolicyRegistry,
    clock: FixedClock,
    random_source: SeededRandomSource,
) -> dict[str, Any]:
    return start_session(
        store,
        registry,
        clock,
        random_source,
        provider="claude-code",
        lesson_profile="drill",
        target_ref=PRESENT_PERFECT,
    )


def _brief_steps(manifest: dict[str, Any], step_type: str) -> list[dict[str, Any]]:
    return [step for step in manifest["brief"]["plan"]["steps"] if step["step_type"] == step_type]


# -- the brief carries the authored frames -----------------------------------


def test_the_drill_step_carries_mode_round_size_and_the_authored_frames(
    store: EventStore, v3_registry: PolicyRegistry, clock, random_source
) -> None:
    manifest = _start_drill(store, v3_registry, clock, random_source)
    blocks = _brief_steps(manifest, "drill_block")
    assert blocks, "the drill profile composes drill blocks"
    step = blocks[0]
    material = step["material"]

    assert material["form"] == "drill_block"
    assert material["mode"] in ("blocked", "interleaved")
    assert material["round_size"] == 6 and step["round_size"] == 6
    assert material["rounds"] == 2
    assert material["primary_target"]["target_ref"] == PRESENT_PERFECT
    frames = {frame["frame_ref"]: frame for frame in material["frames"] if frame["role"] == "target"}
    assert set(frames) == {frame["id"] for frame in PP_FRAMES}
    one = frames["chunk.pp.already-sent"]
    assert one["title"] == "I've already ___"
    assert one["meaning_ru"] and one["examples"] and one["contrast"] and one["trap"]


def test_an_interleaved_block_carries_the_contrast_targets_frames(
    store: EventStore, v3_registry: PolicyRegistry, clock, random_source
) -> None:
    manifest = _start_drill(store, v3_registry, clock, random_source)
    interleaved = [
        step for step in _brief_steps(manifest, "drill_block") if step.get("drill_mode") == "interleaved"
    ]
    if not interleaved:
        pytest.skip("this program yields no contrast set large enough to interleave")
    material = interleaved[0]["material"]
    assert material["contrast_targets"]
    assert {frame["role"] for frame in material["frames"]} == {"target", "contrast"}


def test_the_persisted_plan_keeps_the_directive_control_composed(
    store: EventStore, v3_registry: PolicyRegistry, clock, random_source
) -> None:
    """The widened directive is a VIEW: the stored plan never copies the frames."""
    manifest = _start_drill(store, v3_registry, clock, random_source)
    step = _brief_steps(manifest, "drill_block")[0]
    _, plan, _ = get_plan(store, manifest["session_id"])
    stored = next(s for s in plan["steps"] if s["step_id"] == step["step_id"])["generation_directive"]
    assert "frames" not in stored
    assert step["material"]["frames"]


def test_activating_v3_leaves_the_earlier_versions_resolvable(
    store: EventStore, v3_registry: PolicyRegistry, clock
) -> None:
    for version in ("generation@1", "generation@2", "generation@3"):
        assert v3_registry.resolve_pinned("generation", version)["policy_id"] == version


# -- reconstruction text selection ------------------------------------------


def test_reconstruction_text_selection_is_deterministic_and_rotates() -> None:
    first = choose_reconstruction_text(PROGRAM, PRESENT_PERFECT, recent_text_ids=[])
    again = choose_reconstruction_text(PROGRAM, PRESENT_PERFECT, recent_text_ids=[])
    assert first is not None and first["id"] == "text.recon.present-perfect-result.handover"
    assert again == first  # "first by id", not authored order and not random

    second = choose_reconstruction_text(PROGRAM, PRESENT_PERFECT, recent_text_ids=[first["id"]])
    assert second is not None and second["id"] == "text.recon.present-perfect-result.migration"

    # Every text used inside the window: the rule falls back to the first by id
    # rather than refusing to deliver the step.
    exhausted = choose_reconstruction_text(
        PROGRAM, PRESENT_PERFECT, recent_text_ids=[text["id"] for text in TEXTS]
    )
    assert exhausted is not None and exhausted["id"] == first["id"]
    assert choose_reconstruction_text(PROGRAM, PAST_SIMPLE, recent_text_ids=[]) is None


def test_the_material_avoids_the_text_used_in_the_last_presentations(
    store: EventStore, v3_registry: PolicyRegistry, clock, random_source
) -> None:
    """A historic rendered reconstruction (the removed step protocol) still
    counts toward the rotation window, so the next reconstruction proposes the
    OTHER text."""
    used = TEXTS[1]
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="exercise.rendered",
                    occurred_at=clock.now(),
                    actor="agent",
                    correlation_id="historic-session",
                    payload={"form": "reconstruction", "text_id": used["id"]},
                )
            ]
        )
    recent = recent_reconstruction_text_ids(store)
    assert recent == [used["id"]]
    step = {
        "step_type": "reconstruction",
        "targets": [{"target_ref": PRESENT_PERFECT, "dimension": "controlled_production", "role": "new"}],
    }
    view = directive_view(step, PROGRAM, _policy("generation-v3.yaml"), recent_text_ids=recent)
    assert view is not None
    assert view["text_id"] == "text.recon.present-perfect-result.migration"


# -- learner preferences -----------------------------------------------------


def test_round_size_and_timed_limit_follow_the_learner_preference(
    store: EventStore, v3_registry: PolicyRegistry, clock, random_source
) -> None:
    """A recorded preference reaches the composed step and the brief material."""
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type="learner.preferences_updated",
                    occurred_at=clock.now(),
                    actor="learner",
                    correlation_id="learner",
                    payload={"round_size": 4, "timed_limit_seconds": 300},
                )
            ]
        )
    manifest = _start_drill(store, v3_registry, clock, random_source)
    block = _brief_steps(manifest, "drill_block")[0]
    assert block["round_size"] == 4
    assert block["material"]["round_size"] == 4
    (timed,) = _brief_steps(manifest, "timed_writing")
    assert timed["declared_limit_seconds"] == 300
    assert timed["material"]["declared_limit_seconds"] == 300
