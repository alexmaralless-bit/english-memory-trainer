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


class AppendOnlyViolation(KernelError):
    """An attempt to update or delete the append-only event log (foundation 3.3)."""

    code = "APPEND_ONLY_VIOLATION"
