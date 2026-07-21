"""Storage layout, open_storage lifetime, and checkpointed snapshots
(foundation 3.9; roadmap 1.3)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from english_trainer.kernel.clock import FixedClock, SeededRandomSource
from english_trainer.kernel.envelopes import make_event
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.ids import new_ulid
from english_trainer.kernel.store import connect
from english_trainer.kernel.uow import UnitOfWork
from english_trainer.storage.layout import open_storage, resolve_layout
from english_trainer.storage.snapshot import create_snapshot

EPOCH = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def _seed_one_event(root: Path) -> None:
    layout = resolve_layout(root)
    clock = FixedClock(EPOCH)
    rnd = SeededRandomSource(1)
    with open_storage(layout) as storage, UnitOfWork(storage.store, clock) as uow:
        uow.append(
            [
                make_event(
                    id=new_ulid(clock, rnd),
                    type="demo",
                    occurred_at=clock.now(),
                    actor="engine",
                    correlation_id="c",
                    payload={"i": 1},
                )
            ]
        )


def test_layout_is_the_single_path_authority(tmp_path: Path) -> None:
    layout = resolve_layout(tmp_path)
    assert layout.db == tmp_path / "trainer.db"
    assert layout.export == tmp_path / "trainer.events.jsonl"
    assert layout.snapshots_dir == tmp_path / "snapshots"
    assert layout.memory_dir == tmp_path / "memory"


def test_open_storage_creates_migrates_and_roundtrips(tmp_path: Path) -> None:
    _seed_one_event(tmp_path)
    layout = resolve_layout(tmp_path)
    with open_storage(layout) as storage:
        events = list(storage.store.read())
    assert [event.type for event in events] == ["demo"]


def test_snapshot_copies_db_and_export_with_manifest(tmp_path: Path) -> None:
    _seed_one_event(tmp_path)
    layout = resolve_layout(tmp_path)
    layout.export.write_text('{"sequence":1}\n', encoding="ascii")

    manifest = create_snapshot(layout, FixedClock(EPOCH))
    directory = layout.snapshots_dir / manifest["directory"]
    assert directory.is_dir()
    assert (directory / "trainer.db").exists()
    assert (directory / "trainer.events.jsonl").exists()

    # No WAL/SHM sidecars in the snapshot (foundation 3.9).
    assert not list(directory.glob("*-wal")) and not list(directory.glob("*-shm"))

    # The manifest hashes match the copied bytes.
    stored = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    for name, digest in stored["files"].items():
        if digest == "directory":
            continue
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest

    # The copy is a valid, checkpointed database containing the event.
    conn = connect(directory / "trainer.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM events;").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_snapshot_same_second_collides_loudly(tmp_path: Path) -> None:
    _seed_one_event(tmp_path)
    layout = resolve_layout(tmp_path)
    clock = FixedClock(EPOCH)
    create_snapshot(layout, clock)
    with pytest.raises(KernelError, match="already exists"):
        create_snapshot(layout, clock)  # frozen clock: same directory name
    clock.advance(seconds=1)
    second = create_snapshot(layout, clock)  # a later instant works
    assert (layout.snapshots_dir / second["directory"]).is_dir()


def test_snapshot_without_database_is_refused(tmp_path: Path) -> None:
    with pytest.raises(KernelError, match="does not exist"):
        create_snapshot(resolve_layout(tmp_path), FixedClock(EPOCH))


def test_snapshot_includes_memory_vault_when_present(tmp_path: Path) -> None:
    _seed_one_event(tmp_path)
    layout = resolve_layout(tmp_path)
    layout.memory_dir.mkdir()
    (layout.memory_dir / "topic.md").write_text("# generated\n", encoding="utf-8")

    manifest = create_snapshot(layout, FixedClock(EPOCH))
    directory = layout.snapshots_dir / manifest["directory"]
    assert (directory / "memory" / "topic.md").read_text(encoding="utf-8") == "# generated\n"
