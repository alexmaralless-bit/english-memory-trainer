"""Typed, time-sortable identifiers (foundation contract 3.1).

Domain IDs are typed, not bare strings, so a ``SessionId`` cannot be passed
where an ``EvidenceId`` is meant. The generated value is ULID-like: a 48-bit
millisecond timestamp followed by 80 random bits, Crockford base32 encoded, so
IDs sort by creation time and collide only within the same millisecond under an
astronomically small probability.

Generation goes through the injected ``Clock`` and ``RandomSource`` (never the
system clock or ``random``), which is what keeps ID streams reproducible under a
``FixedClock`` + ``SeededRandomSource`` in tests.
"""

from __future__ import annotations

from typing import NewType

from english_trainer.kernel.clock import Clock, RandomSource

# Crockford base32: no I, L, O, U (avoids ambiguity). 32 symbols.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIME_LEN = 10  # 48 bits -> 10 base32 chars
_RAND_LEN = 16  # 80 bits -> 16 base32 chars
_ULID_LEN = _TIME_LEN + _RAND_LEN


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    if value:
        raise ValueError("value too large for the requested length")
    return "".join(reversed(chars))


def new_ulid(clock: Clock, random: RandomSource) -> str:
    """A ULID-like string: millisecond timestamp + 80 random bits, sortable."""
    millis = int(clock.now().timestamp() * 1000)
    if not 0 <= millis < (1 << 48):
        raise ValueError("timestamp out of 48-bit ULID range")
    rand = int.from_bytes(random.token_bytes(10), "big")
    return _encode(millis, _TIME_LEN) + _encode(rand, _RAND_LEN)


def is_ulid(value: str) -> bool:
    """True if ``value`` is a well-formed ULID-like id from this module."""
    return len(value) == _ULID_LEN and all(c in _ALPHABET for c in value)


# Typed IDs. NewType keeps them distinct under mypy strict while staying plain
# strings at runtime (cheap, JSON-friendly). Each business module owns the
# entities; the kernel only supplies the id primitives.
#
# Honest limitation: NewType is a *static* aid only. It has no runtime identity,
# and the envelopes (foundation 3.3) store ``id`` as a bare ``str`` -- pydantic
# neither sees nor enforces these types. So a ``SessionId`` handed to a field
# expecting an ``EventId`` is caught by mypy at call sites that stay typed, but
# nothing rejects a mistyped id once it has been widened to ``str`` (e.g. read
# back from the store). Treat these as discipline the type-checker helps keep,
# not a runtime guarantee.
EventId = NewType("EventId", str)
CommandId = NewType("CommandId", str)
SessionId = NewType("SessionId", str)
AttemptId = NewType("AttemptId", str)
EvidenceId = NewType("EvidenceId", str)
ReviewId = NewType("ReviewId", str)
TopicId = NewType("TopicId", str)


def new_event_id(clock: Clock, random: RandomSource) -> EventId:
    """A fresh, time-sortable :data:`EventId`."""
    return EventId(new_ulid(clock, random))


def new_command_id(clock: Clock, random: RandomSource) -> CommandId:
    """A fresh, time-sortable :data:`CommandId`."""
    return CommandId(new_ulid(clock, random))


def new_session_id(clock: Clock, random: RandomSource) -> SessionId:
    """A fresh, time-sortable :data:`SessionId`."""
    return SessionId(new_ulid(clock, random))


def new_attempt_id(clock: Clock, random: RandomSource) -> AttemptId:
    """A fresh, time-sortable :data:`AttemptId`."""
    return AttemptId(new_ulid(clock, random))


def new_evidence_id(clock: Clock, random: RandomSource) -> EvidenceId:
    """A fresh, time-sortable :data:`EvidenceId`."""
    return EvidenceId(new_ulid(clock, random))


def new_review_id(clock: Clock, random: RandomSource) -> ReviewId:
    """A fresh, time-sortable :data:`ReviewId`."""
    return ReviewId(new_ulid(clock, random))
