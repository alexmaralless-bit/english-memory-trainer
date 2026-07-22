"""Kernel error types with stable codes (foundation 3.4, 3.5).

Each error carries a machine-stable ``code`` so the future CLI can put it in the
response envelope's ``error_code`` (cli 4.2) and an agent can branch on it.
Codes are part of the contract: renaming one is a breaking change.
"""

from __future__ import annotations


class KernelError(Exception):
    """Base for kernel errors. ``code`` is stable and machine-readable."""

    code: str = "KERNEL_ERROR"


class IdempotencyConflict(KernelError):
    """Same idempotency key replayed with a different payload (foundation 3.4).

    A retry of the *same* command returns the cached result; a *different*
    command reusing the key is a caller bug and fails stably rather than
    silently overwriting.
    """

    code = "IDEMPOTENCY_CONFLICT"


class StaleRevision(KernelError):
    """Compare-and-set saw an out-of-date aggregate revision (foundation 3.5).

    Means "retry with fresh state", distinct from a precondition failure.
    """

    code = "STALE_REVISION"


class SessionRevisionConflict(KernelError):
    """A session-bound mutation used an obsolete public fence token."""

    code = "SESSION_REVISION_CONFLICT"

    def __init__(self, *, session_id: str, expected: int, current: int) -> None:
        super().__init__(
            f"session {session_id} is at revision {current}, caller expected {expected}; "
            "resume or status and retry with a fresh idempotency key"
        )
        self.session_id = session_id
        self.expected_session_revision = expected
        self.current_session_revision = current


class AppendOnlyViolation(KernelError):
    """An attempt to update or delete the append-only event log (foundation 3.3)."""

    code = "APPEND_ONLY_VIOLATION"


class PinnedPolicyUnavailable(KernelError):
    """A pinned policy version does not resolve in the registry (foundation 3.6).

    Replay and scoring pin the exact policy versions they ran under and must
    resolve them by id. If a pinned version is missing, that is a hard error --
    never a silent fallback to the active version or an alias -- because the two
    could differ and quietly change a reproduced result.
    """

    code = "PINNED_POLICY_UNAVAILABLE"


class NoActivePolicy(KernelError):
    """No active version is set for a policy kind (foundation 3.6).

    The active-resolve path (e.g. ``production_eligible`` at delivery) needs a
    current version; its absence is a configuration error, distinct from a
    pinned version failing to resolve.
    """

    code = "NO_ACTIVE_POLICY"
