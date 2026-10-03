"""Curriculum versioning and activation over the kernel (curriculum 4, 5;
foundation 3.6).

A loaded program becomes an immutable ``curriculum``-kind snapshot in the policy
registry, addressable by version id; sessions and evidence pin that id, and
replay resolves it exactly (never the current active). Activation is
compare-and-set on the currently active version and commits **atomically with
its** ``curriculum.version_activated`` **event** -- the registry pointer and the
announcement can never disagree.

Reads (``get_topic``, ``lexicon_query``, ``texts_for_topic``) are pure functions
over a loaded program: the CLI serves them without touching learner state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from english_trainer.curriculum.loader import snapshot_payload
from english_trainer.kernel.clock import Clock, RandomSource
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import NoActivePolicy, StaleRevision
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.policy import PolicyRegistry
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork

CURRICULUM_KIND = "curriculum"
EVENT_VERSION_ACTIVATED = "curriculum.version_activated"

#: Frames of these topics form the permanent interleaved tier (scheduler 3a,
#: [PD-2026-09-22] PD-F): articles are the one form the method never lets
#: leave the review queue. Spelled once, here -- curriculum is the only layer
#: that may read ``frame_of`` semantics, and every consumer receives the
#: resulting set of target refs as a plain value.
ARTICLE_FRAME_TOPIC_PREFIX = "grammar.articles."


def register_version(registry: PolicyRegistry, program: dict[str, Any], version_id: str) -> str:
    """Register the program as an immutable snapshot; returns its content hash.

    Idempotent for identical content; the same version id with different
    content is refused by the registry (foundation 3.6).
    """
    return registry.register(CURRICULUM_KIND, version_id, snapshot_payload(program))


def active_version(registry: PolicyRegistry) -> str | None:
    try:
        return registry.active_version(CURRICULUM_KIND)
    except NoActivePolicy:
        return None


def activate_version(
    store: EventStore,
    registry: PolicyRegistry,
    clock: Clock,
    random_source: RandomSource,
    version_id: str,
    expected_active: str | None,
    actor: str = "engine",
) -> DomainEvent | None:
    """CAS-activate ``version_id`` and emit the activation event atomically.

    ``expected_active`` must name the version the caller believes is active
    (``None`` for a fresh install); a mismatch raises ``StaleRevision`` --
    "re-read and retry", nothing written. Re-activating the already-active
    version with a correct expectation is a no-op (returns ``None``): replaying
    the same request must not multiply activation events.
    """
    current = active_version(registry)
    if current != expected_active:
        raise StaleRevision(
            f"active curriculum is {current!r}, caller expected {expected_active!r}; "
            "re-read and retry with the fresh value"
        )
    if current == version_id:
        return None
    with UnitOfWork(store, clock) as uow:
        # The registry pointer update joins the UoW transaction (same
        # connection), so pointer and event commit together or not at all.
        registry.activate(CURRICULUM_KIND, version_id)
        (event,) = uow.append(
            [
                make_event(
                    id=new_ulid(clock, random_source),
                    type=EVENT_VERSION_ACTIVATED,
                    occurred_at=clock.now(),
                    actor=actor,
                    correlation_id=new_ulid(clock, random_source),
                    payload={"version": version_id, "previous": current},
                    pinned_versions={CURRICULUM_KIND: version_id},
                )
            ]
        )
    return event


def get_topic(program: dict[str, Any], topic_id: str) -> dict[str, Any] | None:
    for topic in program["topics"]:
        if topic.get("id") == topic_id:
            return cast("dict[str, Any]", topic)
    return None


def texts_for_topic(program: dict[str, Any], topic_id: str) -> list[dict[str, Any]]:
    """Reconstruction texts authored for ``topic_id`` (curriculum 2d).

    Matches the owning ``topic`` only -- ``also_targets`` records the secondary
    grammar a text happens to exercise, not a second owner. Deterministic order
    by id. A program (or a historical snapshot) without ``texts`` yields none.
    """
    matches = [
        text
        for text in program.get("texts") or []
        if isinstance(text, dict) and text.get("topic") == topic_id
    ]
    matches.sort(key=lambda text: str(text.get("id")))
    return matches


def permanent_interleave_targets(program: Mapping[str, Any]) -> frozenset[str]:
    """Target refs of the permanent interleaved tier (scheduler 3a, PD-F).

    A frame is a ``chunk`` lexical item whose ``frame_of`` names the topic
    whose form it carries (lexical-system 1c); the article tier is every frame
    whose topic sits under ``grammar.articles.``. The scheduler stays pure and
    never reads curriculum content, so it takes this classification as an
    injected ``frozenset[str]`` -- and this function is the ONE place that
    knows the rule. Callers that cannot import curriculum (``lessons``,
    ``memory`` -- see the layer allowlist) receive the set, or this callable,
    from the edge that resolved the snapshot.

    Pure over the passed snapshot: a historical curriculum version classifies
    by its OWN frames, not by today's active program.
    """
    return frozenset(
        str(unit["id"])
        for unit in program.get("lexicon") or []
        if isinstance(unit, dict)
        and unit.get("id")
        and str(unit.get("frame_of") or "").startswith(ARTICLE_FRAME_TOPIC_PREFIX)
    )


def lexicon_query(
    program: dict[str, Any],
    *,
    item_type: str | None = None,
    cefr: str | None = None,
    priority_band: str | None = None,
    register: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Filtered lexicon selection (curriculum 4). Deterministic order by id."""
    matches = [
        item
        for item in program["lexicon"]
        if (item_type is None or item.get("type") == item_type)
        and (cefr is None or item.get("cefr") == cefr)
        and (priority_band is None or item.get("curriculum_priority_band") == priority_band)
        and (register is None or item.get("register") == register)
    ]
    matches.sort(key=lambda item: str(item.get("id")))
    return matches[:limit]
