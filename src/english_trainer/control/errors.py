"""Stable control-module errors (control 3, 4.2; cli 4.2).

Each carries a machine-stable ``code`` for the CLI envelope. Composition
refusals (:class:`BudgetTooSmall`, :class:`NoCandidates`) mean "this is not
allowed now -- do something else" (PRECONDITION_FAILED). The step-delivery
errors (plan-version CAS conflicts, signal/probe refusals) went away with the
per-step protocol [PD-2026-09-23].
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


class AvailabilityInvalid(KernelError):
    """The declared availability profile is not the integer-only schema from
    control 4.7a, or one of its timestamps is not an aware ISO instant."""

    code = "AVAILABILITY_INVALID"
