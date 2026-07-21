"""database_check: green after export, export lag is pending (not an error),
and divergence after catch-up is an error (foundation 2.1)."""

from __future__ import annotations

from pathlib import Path

from english_trainer.kernel.check import database_check
from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.encoding import canonical_json
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.export import JsonlExporter, export_pending
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


def test_check_is_ok_after_full_export(store, clock, random_source, tmp_path: Path) -> None:
    _append(store, clock, random_source, 3)
    exporter = JsonlExporter(tmp_path / "e.jsonl")
    export_pending(store, exporter, clock)
    report = database_check(store, exporter)
    assert report.ok
    assert report.errors == []
    assert report.pending["unexported_events"] == 0


def test_export_lag_is_pending_not_error(store, clock, random_source, tmp_path: Path) -> None:
    _append(store, clock, random_source, 3)
    exporter = JsonlExporter(tmp_path / "e.jsonl")  # nothing exported yet
    report = database_check(store, exporter)
    assert report.ok  # trailing export is healthy, not an integrity error
    assert report.pending["unexported_events"] == 3


def test_partial_export_lag_is_pending(store, clock, random_source, tmp_path: Path) -> None:
    exporter = JsonlExporter(tmp_path / "e.jsonl")
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)  # acknowledged up to 2
    _append(store, clock, random_source, 2, start=2)  # 3, 4 not yet exported
    report = database_check(store, exporter)
    assert report.ok
    assert report.pending["unexported_events"] == 2


def test_divergence_after_catch_up_is_error(store, clock, random_source, tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)

    # Tamper an acknowledged line's payload_hash so it no longer matches.
    records = exporter.records()
    records[0]["payload_hash"] = "0" * 64
    path.write_text(
        "\n".join(canonical_json(record).decode("ascii") for record in records) + "\n",
        encoding="ascii",
    )

    report = database_check(store, exporter)
    assert not report.ok
    assert report.errors


def test_missing_required_table_is_error(store, clock, tmp_path: Path) -> None:
    store._conn.execute("DROP TABLE outbox;")
    report = database_check(store, JsonlExporter(tmp_path / "e.jsonl"))
    assert not report.ok
    assert any("missing tables" in error for error in report.errors)


def test_missing_offsets_table_is_reported_not_raised(store, clock, random_source, tmp_path: Path) -> None:
    # A check must report a broken schema, never crash on it -- even when the
    # missing table is one the check itself queries.
    _append(store, clock, random_source, 1)
    store._conn.execute("DROP TABLE consumer_offsets;")
    report = database_check(store, JsonlExporter(tmp_path / "e.jsonl"))
    assert not report.ok
    assert any("missing tables" in error for error in report.errors)


def test_acknowledged_envelope_tamper_is_divergence(store, clock, random_source, tmp_path: Path) -> None:
    # Divergence is judged on the full envelope, not just sequence + hash: a
    # tampered actor in an acknowledged line must fail the check.
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)

    records = exporter.records()
    records[0]["actor"] = "impostor"
    path.write_text(
        "\n".join(canonical_json(record).decode("ascii") for record in records) + "\n",
        encoding="ascii",
    )

    report = database_check(store, exporter)
    assert not report.ok
    assert any("diverges" in error for error in report.errors)


def test_unreadable_export_is_error_not_crash(store, clock, random_source, tmp_path: Path) -> None:
    # A torn line inside the acknowledged region makes the file unreadable; the
    # check reports it as an error instead of raising.
    path = tmp_path / "e.jsonl"
    exporter = JsonlExporter(path)
    _append(store, clock, random_source, 2)
    export_pending(store, exporter, clock)
    with path.open("a", encoding="ascii") as handle:
        handle.write("not json at all\n")

    report = database_check(store, exporter)
    assert not report.ok
    assert any("unreadable" in error for error in report.errors)
