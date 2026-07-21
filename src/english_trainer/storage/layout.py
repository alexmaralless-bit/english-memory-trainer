"""Storage layout: where the local state lives (foundation 3.9; roadmap 1.3).

One root directory holds everything the engine persists. The layout is the
single authority on paths -- the CLI's ``--db``/``--export`` defaults derive
from it, and no other module invents file locations:

    <root>/
      trainer.db             authoritative SQLite state (events, outbox, ...)
      trainer.events.jsonl   derived JSONL export (rebuildable, never truth)
      snapshots/             point-in-time copies (trainer snapshot create)
      memory/                generated Obsidian vault (arrives with 0.6 / 2.4)

``open_storage`` wires the pieces the kernel already provides -- connect,
migrate, event store, exporter -- into one handle with a context-manager
lifetime, so callers never assemble them by hand.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from english_trainer.kernel.export import JsonlExporter
from english_trainer.kernel.store import EventStore, connect, migrate

DB_FILENAME = "trainer.db"
EXPORT_FILENAME = "trainer.events.jsonl"
SNAPSHOTS_DIRNAME = "snapshots"
MEMORY_DIRNAME = "memory"


@dataclass(frozen=True)
class StorageLayout:
    """Canonical paths of one trainer home directory."""

    root: Path

    @property
    def db(self) -> Path:
        return self.root / DB_FILENAME

    @property
    def export(self) -> Path:
        return self.root / EXPORT_FILENAME

    @property
    def snapshots_dir(self) -> Path:
        return self.root / SNAPSHOTS_DIRNAME

    @property
    def memory_dir(self) -> Path:
        return self.root / MEMORY_DIRNAME


def resolve_layout(root: Path | str) -> StorageLayout:
    """The layout for ``root`` (no filesystem effects; resolution only)."""
    return StorageLayout(root=Path(root))


class Storage:
    """An open handle over one layout: connection, event store, exporter.

    Owns the connection lifetime; use as a context manager. Domain code keeps
    talking to the kernel abstractions (EventStore, UnitOfWork, exporter) --
    never to sqlite3 directly (foundation 3.9).
    """

    def __init__(self, layout: StorageLayout) -> None:
        self.layout = layout
        self._conn: sqlite3.Connection = connect(layout.db)
        migrate(self._conn)
        self.store = EventStore(self._conn)
        self.exporter = JsonlExporter(layout.export)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_storage(layout: StorageLayout) -> Storage:
    """Open (creating and migrating if needed) the storage under ``layout``."""
    layout.root.mkdir(parents=True, exist_ok=True)
    return Storage(layout)
