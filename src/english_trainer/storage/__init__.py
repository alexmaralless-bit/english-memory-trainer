"""Storage: layout, lifetimes and snapshots of the local state (roadmap 1.3).

The persistence *mechanics* -- migrations, the append-only event table, the
Unit of Work, the outbox -- live in the kernel by design. This module owns what
remains: where the files live (one layout, one authority), how a ready-to-use
handle is opened, the Repository boundary domain code sees instead of sqlite3,
and point-in-time snapshots taken only after a WAL checkpoint.
"""

from __future__ import annotations

from english_trainer.storage.layout import Storage, StorageLayout, open_storage, resolve_layout
from english_trainer.storage.repository import Repository
from english_trainer.storage.snapshot import create_snapshot

__all__ = [
    "Repository",
    "Storage",
    "StorageLayout",
    "create_snapshot",
    "open_storage",
    "resolve_layout",
]
