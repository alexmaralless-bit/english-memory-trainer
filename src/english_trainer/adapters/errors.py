"""Adapters error types with stable codes (adapters 3, 5; kernel/errors.py).

Every error carries a machine-stable ``code`` so the CLI can put it in the
response envelope's ``error_code`` and an agent can branch on it -- the same
contract the kernel's own errors follow (foundation 3.4-3.6).
"""

from __future__ import annotations

from english_trainer.kernel.errors import KernelError


class AdapterError(KernelError):
    """Base for adapters-module errors."""

    code = "ADAPTER_ERROR"


class SkillInvalid(AdapterError):
    """A skill's ``SKILL.md`` violates the required structure (adapters 4.3).

    Raised by parsing; a skill missing a required frontmatter field or
    carrying a malformed list must never be treated as a resolvable skill.
    """

    code = "SKILL_INVALID"


class SkillDrift(AdapterError):
    """A synced copy and its canon have diverged (adapters 4.1).

    Drift is caught in both directions: a copy hand-edited after sync, or the
    canon edited without a following ``trainer skills sync``. ``validate``
    never fixes it -- only ``sync`` does (adapters 4.1, cli 4.4).
    """

    code = "SKILL_DRIFT"


class SkillUnavailable(AdapterError):
    """The requested ``(name, version)`` does not resolve (adapters 4.2).

    This is what `lessons.start_session` calls synchronously, before any
    session aggregate is written: an unresolvable pin fails the start outright
    (lessons 4b [P0-Q1]), never a silent fallback to a different version.
    """

    code = "SKILL_UNAVAILABLE"


class ProviderMessageConflict(AdapterError):
    """A provider reused its global message id for different immutable bytes."""

    code = "PROVIDER_MESSAGE_CONFLICT"


class UserTurnInvalid(AdapterError):
    """A captured user turn or its UTF-8 byte span is malformed."""

    code = "USER_TURN_INVALID"


class SkillReportInvalid(AdapterError):
    """A skill report does not match a skill pinned by the session."""

    code = "SKILL_REPORT_INVALID"
