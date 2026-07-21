"""JSONL derived export: canonical lines, byte-identical rebuild, and a tail
that reconciles after a crash between file append and offset commit
(foundation 2.1)."""

from __future__ import annotations

from pathlib import Path

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.export import JsonlExporter, export_pending, rebuild_export
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import EventStore
from english_trainer.kernel.uow import UnitOfWork


def _append(store: EventStore, clock: FixedClock, rnd: SeededRandomSource, n: int, start: int = 0) -> None:
    with UnitOfWork(store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type=f"e{start + i}",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="c",
                    payload={"i": start + i},
                )
                for i in range(n)
            ]
        )


def test_export_writes_one_canonical_line_per_event(store, clock, random_source, tmp_path: Path) -> None:
    _append(store, clock, random_source, 3)
    path = tmp_path / "events.jsonl"
    exporter = JsonlExporter(path)
    assert export_pending(store, exporter, clock) == 3
    assert [record["sequence"] for record in exporter.records()] == [1, 2, 3]
    # Canonical lines have sorted keys, so each starts with the first key, "actor".
    first_line = path.read_text(encoding="ascii").splitlines()[0]
    assert first_line.startswith('{"actor":"engine"')


def test_export_is_incremental_and_idempotent(store, clock, random_source, tmp_path: Path) -> None:
    exporter = JsonlExporter(tmp_path / "e.jsonl")
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)
    assert export_pending(store, exporter, clock) == 0  # no new events
    _append(store, clock, random_source, 1, start=2)
    assert export_pending(store, exporter, clock) == 1
    assert len(exporter.records()) == 3


def test_full_rebuild_is_byte_identical_to_incremental(store, clock, random_source, tmp_path: Path) -> None:
    _append(store, clock, random_source, 5)
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    export_pending(store, exporter, clock)
    incremental = path.read_bytes()
    rebuild_export(store, exporter, clock)
    assert path.read_bytes() == incremental


def test_reconcile_trims_uncommitted_tail_no_duplicate(store, clock, random_source, tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)  # file + offset at sequence 2

    _append(store, clock, random_source, 1, start=2)  # sequence 3 now exists
    (third,) = [event for event in store.read() if event.sequence == 3]
    exporter.apply(third)  # crash window: line written, offset still 2
    assert len(exporter.records()) == 3

    # Next delivery reconciles the orphan line away, then re-delivers exactly once.
    assert export_pending(store, exporter, clock) == 1
    assert [record["sequence"] for record in exporter.records()] == [1, 2, 3]


def test_rebuild_of_empty_log_is_empty_file(store, clock, tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    rebuild_export(store, exporter, clock)
    assert path.read_text(encoding="ascii") == ""


def test_reconcile_truncates_a_torn_partial_line(store, clock, random_source, tmp_path: Path) -> None:
    # A crash mid-write leaves a truncated, unparseable final line. It is by
    # construction un-acknowledged (acknowledged lines were fully written before
    # their offset committed), so recovery trims it instead of crashing.
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)  # acknowledged up to 2

    with path.open("a", encoding="ascii") as handle:
        handle.write('{"sequence":3')  # torn write: no closing brace, no newline

    _append(store, clock, random_source, 1, start=2)  # the real event 3
    assert export_pending(store, exporter, clock) == 1  # reconciled, then delivered once
    assert [record["sequence"] for record in exporter.records()] == [1, 2, 3]
