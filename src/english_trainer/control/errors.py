"""Stable control-module errors (control 3, 4.2; cli 4.2).

Each carries a machine-stable ``code`` for the CLI envelope. The distinction
the contract insists on: :class:`PlanVersionConflict` means "re-read the plan
and retry with the fresh version" (CLI exit CONFLICT), while composition
refusals (:class:`BudgetTooSmall`, :class:`NoCandidates`) mean "this is not
allowed now -- do something else" (PRECONDITION_FAILED).
"""

from __future__ import annotations

from english_trainer.kernel.errors import KernelError


class ControlPolicyInvalid(KernelError):
    """The control policy payload violates its own contract (control 3):
    a non-integer decision value, an infeasible share table, or a floor no
    step type can ever reach. Such a version must never activate."""

    code = "CONTROL_POLICY_INVALID"


class BudgetTooSmall(KernelError):
    """``total_seconds`` is below the policy's ``min_total_minutes`` -- the
    composition is refused rather than producing a degenerate plan."""

    code = "BUDGET_TOO_SMALL"


class NoCandidates(KernelError):
    """After all waivers no step was admitted. An empty plan is an error, not
    a result [R-2]: a session with zero steps is never created."""

    code = "NO_CANDIDATES"


class PlanVersionConflict(KernelError):
    """CAS miss on ``expected_plan_version`` (control 4.2 [RR2-7]).

    Carries the current version so the loser can re-read (``peek``) and retry
    with a fresh expectation and a fresh idempotency key.
    """

    code = "PLAN_VERSION_CONFLICT"

    def __init__(self, message: str, *, current_plan_version: int) -> None:
        super().__init__(message)
        self.current_plan_version = current_plan_version
