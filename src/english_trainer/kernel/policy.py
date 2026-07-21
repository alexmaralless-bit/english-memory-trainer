"""Versioned policy registry with pinning and retention (foundation 3.6, OPEN-9).

Determinism rests on pinning: a command, session or piece of evidence records the
exact policy versions it ran under, and replay resolves those versions **by id**,
never the current active one -- activation is not retroactive (foundation 3.6, 5).
This registry is where those versions live.

Two resolve paths, deliberately separate:

- **pinned** (`resolve_pinned`) -- for replay and scoring. Resolves the exact
  version an event pinned. If it is missing, that is a hard
  :class:`PinnedPolicyUnavailable`, never a silent fallback to active or an alias:
  the two could differ and quietly change a reproduced result.
- **active** (`resolve_active`) -- for the safety-overlay / ``production_eligible``
  decision made at delivery time (foundation 3.6). Follows the current active
  pointer per kind.

Every version is an **immutable content snapshot**, content-addressed by the same
canonical hash as event payloads. Re-registering the same (kind, version) with the
same content is a no-op; with different content it is refused. Rows are retained
forever -- deprecation is a status change (`registered -> deprecated -> retired`),
not a deletion -- so a pin can always be resolved (retention != immutability).

Deferred (OPEN-9): deprecation *mappings* (1:1 / split / merge) and alias/migration
resolution. This increment implements immutable registration, pinned/active
resolve, retention, and the deprecated/retired lifecycle; the migration graph is a
later increment and business kinds (curriculum/scoring/scheduler/control/
generation/rubric) own their own version semantics.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from english_trainer.kernel.clock import Clock
from english_trainer.kernel.encoding import canonical_and_hash
from english_trainer.kernel.errors import KernelError, NoActivePolicy, PinnedPolicyUnavailable

# The policy kinds the platform expects (foundation 3.6). Not enforced -- the
# kernel is a mechanism and modules own their kinds -- but named for reference.
KNOWN_KINDS = frozenset({"curriculum", "scoring", "scheduler", "control", "generation", "rubric"})


class PolicyRegistry:
    """Immutable, retained store of versioned policy snapshots (foundation 3.6)."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    # -- registration --------------------------------------------------------

    def register(self, kind: str, version_id: str, content: dict[str, Any]) -> str:
        """Register an immutable snapshot; return its content hash.

        Idempotent for identical content. Re-registering the same (kind,
        version_id) with *different* content is refused -- a version's content is
        frozen once written (foundation 3.6).
        """
        canonical, digest = canonical_and_hash(content)
        try:
            self._conn.execute(
                "INSERT INTO policies (kind, version_id, content, content_hash, status, created_at) "
                "VALUES (?,?,?,?, 'registered', ?);",
                (kind, version_id, canonical.decode("ascii"), digest, self._clock.now().isoformat()),
            )
        except sqlite3.IntegrityError:
            # Primary-key clash: the version already exists. Same content is a
            # no-op; different content violates immutability.
            existing = self._row(kind, version_id)
            if existing is None or existing["content_hash"] != digest:
                raise KernelError(
                    f"policy {kind}:{version_id} is already registered with different content; "
                    "a version's content is immutable"
                ) from None
        return digest

    # -- pinned resolve (replay / scoring) -----------------------------------

    def resolve_pinned(self, kind: str, version_id: str) -> dict[str, Any]:
        """Return the exact pinned version's content, or raise
        :class:`PinnedPolicyUnavailable` (never a silent fallback)."""
        row = self._row(kind, version_id)
        if row is None:
            raise PinnedPolicyUnavailable(f"pinned policy {kind}:{version_id} does not resolve")
        parsed: dict[str, Any] = json.loads(row["content"])
        return parsed

    def content_hash(self, kind: str, version_id: str) -> str:
        row = self._row(kind, version_id)
        if row is None:
            raise PinnedPolicyUnavailable(f"pinned policy {kind}:{version_id} does not resolve")
        return str(row["content_hash"])

    def status(self, kind: str, version_id: str) -> str:
        row = self._row(kind, version_id)
        if row is None:
            raise PinnedPolicyUnavailable(f"pinned policy {kind}:{version_id} does not resolve")
        return str(row["status"])

    # -- active resolve (delivery / production eligibility) ------------------

    def activate(self, kind: str, version_id: str) -> None:
        """Point ``kind``'s active version at ``version_id``.

        The version must exist and not be retired. Not retroactive: existing pins
        keep resolving to whatever they pinned (foundation 3.6). The API check
        gives the polite error; the ``policy_active_not_retired_*`` triggers are
        the guarantee -- each statement is atomic, so an activate racing a retire
        cannot leave the pointer on a retired version.
        """
        row = self._row(kind, version_id)
        if row is None:
            raise PinnedPolicyUnavailable(f"cannot activate unknown policy {kind}:{version_id}")
        if row["status"] == "retired":
            raise KernelError(f"cannot activate retired policy {kind}:{version_id}")
        try:
            self._conn.execute(
                "INSERT INTO policy_active (kind, version_id, activated_at) VALUES (?,?,?) "
                "ON CONFLICT(kind) DO UPDATE SET version_id = excluded.version_id, "
                "activated_at = excluded.activated_at;",
                (kind, version_id, self._clock.now().isoformat()),
            )
        except sqlite3.IntegrityError as exc:
            raise KernelError(f"cannot activate policy {kind}:{version_id}: {exc}") from exc

    def active_version(self, kind: str) -> str:
        row = self._conn.execute("SELECT version_id FROM policy_active WHERE kind = ?;", (kind,)).fetchone()
        if row is None:
            raise NoActivePolicy(f"no active policy for kind {kind!r}")
        return str(row["version_id"])

    def resolve_active(self, kind: str) -> tuple[str, dict[str, Any]]:
        """Return the active ``(version_id, content)`` for ``kind``."""
        version_id = self.active_version(kind)
        return version_id, self.resolve_pinned(kind, version_id)

    # -- deprecation lifecycle (retention preserved) -------------------------

    def deprecate(self, kind: str, version_id: str, *, retire: bool = False) -> None:
        """Mark a version ``deprecated`` (discouraged) or ``retired`` (not
        activatable). Content and the row are retained either way, so a pin to
        this version still resolves (foundation 3.6).

        Transitions are one-way: ``retired`` is terminal -- a retired version can
        never come back as deprecated (and thus never be re-activated). Retiring
        the currently-active version is refused: activate a replacement first.
        Both rules are also enforced by triggers, so a direct SQL update or an
        interleaved activate cannot slip past the API checks.
        """
        row = self._row(kind, version_id)
        if row is None:
            raise PinnedPolicyUnavailable(f"cannot deprecate unknown policy {kind}:{version_id}")
        if row["status"] == "retired":
            raise KernelError(f"policy {kind}:{version_id} is retired; retired is terminal")
        if retire:
            active = self._conn.execute(
                "SELECT version_id FROM policy_active WHERE kind = ?;", (kind,)
            ).fetchone()
            if active is not None and active["version_id"] == version_id:
                raise KernelError(
                    f"cannot retire the active policy {kind}:{version_id}; activate a replacement first"
                )
        try:
            self._conn.execute(
                "UPDATE policies SET status = ? WHERE kind = ? AND version_id = ?;",
                ("retired" if retire else "deprecated", kind, version_id),
            )
        except sqlite3.IntegrityError as exc:
            raise KernelError(f"cannot change status of {kind}:{version_id}: {exc}") from exc

    # -- internals -----------------------------------------------------------

    def _row(self, kind: str, version_id: str) -> sqlite3.Row | None:
        row = self._conn.execute(
            "SELECT content, content_hash, status FROM policies WHERE kind = ? AND version_id = ?;",
            (kind, version_id),
        ).fetchone()
        return cast("sqlite3.Row | None", row)
