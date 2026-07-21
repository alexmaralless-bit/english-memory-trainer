"""Point-in-time snapshots of the local state (foundation 3.9).

A snapshot is a plain copy of the authoritative database plus its derived
artifacts, taken **only after** a WAL checkpoint: copying a live WAL database
without checkpointing can capture a state no transaction ever committed. The
``-wal``/``-shm`` sidecar files are never part of a snapshot (foundation 3.9;
they are also gitignored).

Each snapshot is a timestamped directory under ``<root>/snapshots/`` with a
``manifest.json`` recording the sha256 of every copied file, so a later
``database check``-style verification can prove the copy intact. The timestamp
comes from the injected clock -- two snapshots in the same second collide
loudly rather than silently overwriting.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.errors import KernelError
from english_trainer.kernel.store import connect
from english_trainer.storage.layout import StorageLayout


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_snapshot(layout: StorageLayout, clock: Clock) -> dict[str, Any]:
    """Checkpoint, copy, and manifest the current state. Returns the manifest.

    File copying cannot share the database transaction, so snapshot creation is
    at-least-once under crashes: a retry after a crash may leave an extra
    snapshot directory behind. That is benign -- snapshots are independent
    copies -- and the idempotency layer of the CLI prevents *replays* of the
    same request from creating duplicates.
    """
    if not layout.db.exists():
        raise KernelError(f"nothing to snapshot: {layout.db} does not exist")

    # Checkpoint first, on a dedicated connection that is closed before any
    # copying starts: the copy must see one committed, self-contained file.
    conn = connect(layout.db)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()

    created_at = clock.now()
    directory = layout.snapshots_dir / f"{created_at:%Y%m%dT%H%M%S}Z"
    if directory.exists():
        raise KernelError(f"snapshot {directory.name} already exists; retry after the clock advances")
    directory.mkdir(parents=True)

    copied: dict[str, str] = {}
    for source in (layout.db, layout.export):
        if source.exists() and source.suffix not in (".db-wal", ".db-shm"):
            target = directory / source.name
            shutil.copy2(source, target)
            copied[source.name] = _sha256_file(target)
    if layout.memory_dir.exists():
        # Generated Markdown is stored next to the snapshot (foundation 3.9).
        shutil.copytree(layout.memory_dir, directory / layout.memory_dir.name)
        copied[layout.memory_dir.name + "/"] = "directory"

    manifest: dict[str, Any] = {
        "created_at": created_at.isoformat(),
        "directory": directory.name,
        "files": copied,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="ascii"
    )
    return manifest
