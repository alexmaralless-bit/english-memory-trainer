"""Correction envelope and correction-aware replay: replacement suppresses
exactly one effect, compensation suppresses none, chains never double-count
(foundation 3.6)."""

from __future__ import annotations

import random

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.corrections import (
    correction_of,
    fold_corrected,
    make_correction_event,
    resolve_corrections,
)
from english_trainer.kernel.envelopes import DomainEvent, make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


def _plain(clock: FixedClock, rnd: SeededRandomSource, kind: str, amount: int) -> DomainEvent:
    return make_event(
        id=new_ulid(clock, rnd),
        type=kind,
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="c",
        payload={"amount": amount},
    )


def _correcting(
    clock: FixedClock,
    rnd: SeededRandomSource,
    target: DomainEvent,
    semantics: str,
    amount: int,
    **extra: object,
) -> DomainEvent:
    return make_correction_event(
        id=new_ulid(clock, rnd),
        type="demo.corrected",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="c",
        corrects_event_id=target.id,
        semantics=semantics,
        payload={"amount": amount},
        **extra,  # type: ignore[arg-type]
    )


def _persist(store: EventStore, clock: FixedClock, events: list[DomainEvent]) -> list[DomainEvent]:
    with UnitOfWork(store, clock) as uow:
        return uow.append(events)


def _total(events: list[DomainEvent]) -> int:
    """An effect that would visibly double-count: the sum of amounts."""
    return fold_corrected(events, lambda acc, e: acc + int(e.payload["amount"]), 0)


def test_replacement_counts_exactly_one_effect(store, clock, random_source) -> None:
    original = _plain(clock, random_source, "score.recorded", 10)
    fix = _correcting(clock, random_source, original, "replacement", 3)
    stored = _persist(store, clock, [original, fix])
    # 10 is replaced by 3: the sum is 3, not 13 and not 10.
    assert _total(stored) == 3
    # The log itself still holds both facts -- only the effect is single-counted.
    assert store.count() == 2


def test_compensation_applies_both_effects(store, clock, random_source) -> None:
    original = _plain(clock, random_source, "xp.awarded", 10)
    counter = _correcting(clock, random_source, original, "compensation", -4)
    stored = _persist(store, clock, [original, counter])
    assert _total(stored) == 6  # ledger-style: both entries count


def test_chain_of_replacements_keeps_only_the_last(store, clock, random_source) -> None:
    a = _plain(clock, random_source, "score.recorded", 10)
    b = _correcting(clock, random_source, a, "replacement", 20)
    stored_ab = _persist(store, clock, [a, b])
    c = _correcting(clock, random_source, stored_ab[1], "replacement", 7)
    stored = stored_ab + _persist(store, clock, [c])
    assert _total(stored) == 7  # not 10, not 20, not any sum of them


def test_parallel_replacements_of_one_target_latest_wins(store, clock, random_source) -> None:
    a = _plain(clock, random_source, "score.recorded", 10)
    first_fix = _correcting(clock, random_source, a, "replacement", 20)
    second_fix = _correcting(clock, random_source, a, "replacement", 30)
    stored = _persist(store, clock, [a, first_fix, second_fix])
    assert _total(stored) == 30  # the earlier replacement is superseded


def test_resolution_is_independent_of_physical_order(store, clock, random_source) -> None:
    a = _plain(clock, random_source, "e", 1)
    b = _correcting(clock, random_source, a, "replacement", 2)
    others = [_plain(clock, random_source, f"e{i}", 100 + i) for i in range(4)]
    stored = _persist(store, clock, [a, b, *others])
    shuffled = stored[:]
    random.Random(5).shuffle(shuffled)
    assert [e.id for e in resolve_corrections(shuffled)] == [e.id for e in resolve_corrections(stored)]
    assert _total(shuffled) == _total(stored)


def test_safety_correction_carries_both_versions(store, clock, random_source) -> None:
    original = _plain(clock, random_source, "exercise.delivered", 1)
    override = make_correction_event(
        id=new_ulid(clock, random_source),
        type="exercise.safety_withdrawn",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="c",
        corrects_event_id=original.id,
        semantics="replacement",
        payload={"amount": 0},
        original_pinned_versions={"generation": "g3", "curriculum": "c7"},
        active_safety_version="safety-9",
    )
    stored = _persist(store, clock, [original, override])
    # Round-trip through the store: audit can name both sides of the override.
    (_, loaded) = list(store.read())
    correction = correction_of(loaded)
    assert correction is not None
    assert correction.original_pinned_versions == {"generation": "g3", "curriculum": "c7"}
    assert correction.active_safety_version == "safety-9"
    assert _total(stored) == 0  # the withdrawn delivery no longer counts


def test_safety_correction_with_one_version_is_refused(clock, random_source) -> None:
    target = _plain(clock, random_source, "e", 1)
    with pytest.raises(KernelError, match="BOTH"):
        _correcting(
            clock,
            random_source,
            target,
            "replacement",
            0,
            active_safety_version="safety-9",  # original_pinned_versions missing
        )


def test_reserved_payload_key_is_refused(clock, random_source) -> None:
    target = _plain(clock, random_source, "e", 1)
    with pytest.raises(KernelError, match="reserved"):
        make_correction_event(
            id=new_ulid(clock, random_source),
            type="t",
            occurred_at=clock.now(),
            actor="engine",
            correlation_id="c",
            corrects_event_id=target.id,
            semantics="replacement",
            payload={"correction": {"smuggled": True}},
        )


def test_unknown_semantics_is_refused(clock, random_source) -> None:
    target = _plain(clock, random_source, "e", 1)
    with pytest.raises(KernelError, match="semantics"):
        _correcting(clock, random_source, target, "undo", 0)


def test_missing_target_is_hard_error(store, clock, random_source) -> None:
    a = _plain(clock, random_source, "e", 1)
    ghost = _plain(clock, random_source, "ghost", 0)  # never persisted
    fix = _correcting(clock, random_source, ghost, "replacement", 2)
    stored = _persist(store, clock, [a, fix])
    with pytest.raises(KernelError, match="unknown event"):
        resolve_corrections(stored)


def test_forward_target_is_hard_error(store, clock, random_source) -> None:
    # A correction must target an EARLIER event; a forward reference (or a
    # cycle built from one) is corrupted data.
    a = _plain(clock, random_source, "e", 1)
    b = _plain(clock, random_source, "e2", 2)
    stored = _persist(store, clock, [a, b])
    forward = make_correction_event(
        id=stored[0].id + "X",  # unique id, irrelevant
        type="t",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="c",
        corrects_event_id=stored[1].id,
        semantics="replacement",
        payload={"amount": 0},
    )
    # Fake a persisted correction that sits BEFORE its target in sequence.
    hacked = forward.model_copy(update={"sequence": 0})
    with pytest.raises(KernelError, match="earlier"):
        resolve_corrections([hacked, *stored])


def test_malformed_correction_block_is_error_not_plain_event(clock, random_source) -> None:
    # A broken block must not silently pass as a plain event -- that would
    # double-count the effect it was meant to replace.
    broken = make_event(
        id=new_ulid(clock, random_source),
        type="t",
        occurred_at=clock.now(),
        actor="engine",
        correlation_id="c",
        payload={"correction": {"semantics": "replacement"}},  # no corrects_event_id
    )
    with pytest.raises(KernelError, match="corrects_event_id"):
        correction_of(broken)


def test_plain_event_has_no_correction(clock, random_source) -> None:
    assert correction_of(_plain(clock, random_source, "e", 1)) is None


def test_correction_survives_store_roundtrip(store, clock, random_source) -> None:
    original = _plain(clock, random_source, "e", 5)
    fix = _correcting(clock, random_source, original, "replacement", 8)
    _persist(store, clock, [original, fix])
    loaded = list(store.read())
    assert _total(loaded) == 8  # resolution works on events read back from SQLite
