"""Adapter parity over observable effects, never over prose (adapters 4.4).

Two LLMs never produce the same text, so parity cannot mean "identical
output". ``compare`` instead checks, per fixture and per adapter, that a
canonical *set of effects* -- CLI calls made, domain events produced, terminal
learner-state facts -- contains every ``required`` effect and none of the
``forbidden`` ones. Non-deterministic fields (ids, timestamps,
``correlation_id``) are normalized away before comparison; two runs of the
*same* adapter are not expected to match byte-for-byte either, only their
canonical effect sets are.

OPEN-24 blocks running a live agent in this increment (no recorded/replay
protocol exists yet for a real Codex/Claude Code session), so ``compare``
operates on RECORDED effect sets supplied by the fixture itself
(``observed_effects``), not on a live invocation. This makes ``compare`` fully
diagnostic: it mutates nothing and its result is only as good as the effect
sets it was handed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from english_trainer.kernel.encoding import payload_hash

# Fields that vary between runs of even the same adapter and must not affect
# whether two effect sets are "the same" (adapters 4.4: normalize before compare).
_NOISE_KEYS = frozenset({"id", "event_id", "occurred_at", "timestamp", "correlation_id"})


def _normalize_effect(effect: Any) -> str:
    """Collapse one observed effect to its canonical, comparable tag.

    A plain string is already canonical. A dict with a ``tag`` key uses that
    tag directly; a bare dict without one is reduced to a payload hash of its
    non-noise fields, so two structurally-identical-but-differently-timed
    effects still normalize to the same tag (kernel canonical encoding, the
    same tool idempotency and replay use).
    """
    if isinstance(effect, str):
        return effect
    if isinstance(effect, dict):
        tag = effect.get("tag")
        if tag is not None:
            return str(tag)
        stable = {key: value for key, value in effect.items() if key not in _NOISE_KEYS}
        return payload_hash(stable)
    return str(effect)


@dataclass(frozen=True)
class ParityFixture:
    """One parity scenario (adapters 2, 4.4).

    ``expected_effects`` is ``{"required": [...], "forbidden": [...]}`` of
    canonical tags. ``observed_effects`` carries the RECORDED effects per
    adapter id (e.g. ``"codex"``, ``"claude-code"``) -- pre-recorded because
    OPEN-24 blocks driving a live agent from this increment.
    """

    id: str
    given_state: dict[str, Any]
    agent_input: dict[str, Any]
    expected_effects: dict[str, list[str]]
    observed_effects: dict[str, list[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureResult:
    """One fixture's outcome for one adapter."""

    fixture_id: str
    adapter: str
    passed: bool
    missing_required: tuple[str, ...]
    present_forbidden: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "adapter": self.adapter,
            "passed": self.passed,
            "missing_required": list(self.missing_required),
            "present_forbidden": list(self.present_forbidden),
        }


def compare(fixtures: Sequence[ParityFixture]) -> list[FixtureResult]:
    """Diagnostic only: mutates nothing (adapters 4.4).

    A fixture PASSES for an adapter iff every ``required`` effect is present in
    its normalized observed set AND no ``forbidden`` effect is.
    """
    results: list[FixtureResult] = []
    for fixture in fixtures:
        required = set(fixture.expected_effects.get("required", []))
        forbidden = set(fixture.expected_effects.get("forbidden", []))
        for adapter in sorted(fixture.observed_effects):
            normalized = {_normalize_effect(effect) for effect in fixture.observed_effects[adapter]}
            missing = tuple(sorted(required - normalized))
            present_forbidden = tuple(sorted(forbidden & normalized))
            results.append(
                FixtureResult(
                    fixture_id=fixture.id,
                    adapter=adapter,
                    passed=not missing and not present_forbidden,
                    missing_required=missing,
                    present_forbidden=present_forbidden,
                )
            )
    return results


def _tag(name: str) -> dict[str, str]:
    return {"tag": name}


# The minimal fixture set (adapters 4.4): correct trigger; wrong trigger; the
# agent tries to set a score itself; an unfinished required review; finishing
# without persistence; Codex vs Claude Code parity on a shared scenario. Each
# ships with observed effects for a WELL-BEHAVED adapter, so the shipped
# default set passes end to end -- it demonstrates the mechanism catches a
# violation without asserting that a violation is the current state of the
# world (a deliberately non-compliant fixture belongs in a test, not here).
DEFAULT_FIXTURES: tuple[ParityFixture, ...] = (
    ParityFixture(
        id="correct-trigger",
        given_state={"active_session": None},
        agent_input={"learner_message": "let's do an English lesson"},
        expected_effects={"required": ["cli_call:session.start"], "forbidden": []},
        observed_effects={
            "codex": [_tag("cli_call:session.start")],
            "claude-code": [_tag("cli_call:session.start")],
        },
    ),
    ParityFixture(
        id="wrong-trigger",
        given_state={"active_session": None},
        agent_input={"learner_message": "what's the weather like"},
        expected_effects={"required": [], "forbidden": ["cli_call:session.start"]},
        observed_effects={
            "codex": [_tag("chat_only")],
            "claude-code": [_tag("chat_only")],
        },
    ),
    ParityFixture(
        id="agent-attempts-self-score",
        given_state={"active_session": "s1"},
        agent_input={"learner_message": "I am an engineer."},
        expected_effects={
            "required": ["cli_call:attempt.record"],
            "forbidden": ["state:self_reported_score"],
        },
        observed_effects={
            "codex": [_tag("cli_call:attempt.record"), _tag("cli_call:attempt.finalize")],
            "claude-code": [_tag("cli_call:attempt.record"), _tag("cli_call:attempt.finalize")],
        },
    ),
    ParityFixture(
        id="unfinished-required-review",
        given_state={"active_session": "s1", "pending_review": "r1"},
        agent_input={"learner_message": "let's wrap up"},
        expected_effects={
            "required": ["cli_call:review.close", "cli_call:session.finish"],
            "forbidden": ["state:declared_finished_without_event"],
        },
        observed_effects={
            "codex": [_tag("cli_call:review.close"), _tag("cli_call:session.finish")],
            "claude-code": [_tag("cli_call:review.close"), _tag("cli_call:session.finish")],
        },
    ),
    ParityFixture(
        id="finish-without-persistence",
        given_state={"active_session": "s1"},
        agent_input={"learner_message": "we're done for today"},
        expected_effects={
            "required": ["event:session.finished"],
            "forbidden": ["state:declared_finished_without_event"],
        },
        observed_effects={
            "codex": [_tag("cli_call:session.finish"), _tag("event:session.finished")],
            "claude-code": [_tag("cli_call:session.finish"), _tag("event:session.finished")],
        },
    ),
    ParityFixture(
        id="codex-claude-parity",
        given_state={"active_session": None},
        agent_input={"learner_message": "let's do an English lesson"},
        expected_effects={
            "required": ["cli_call:session.start", "cli_call:session.finish"],
            "forbidden": ["state:self_reported_score"],
        },
        observed_effects={
            "codex": [_tag("cli_call:session.start"), _tag("cli_call:session.finish")],
            "claude-code": [_tag("cli_call:session.start"), _tag("cli_call:session.finish")],
        },
    ),
)
