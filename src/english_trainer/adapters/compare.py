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

A fixture may also constrain ORDER (``expected_effects["ordered"]``): entries
``"<before> -> <after>"`` require that whenever ``<after>`` was observed, a
``<before>`` was observed earlier in the same recorded sequence (e.g. a
``session report`` must follow a ``session check-report``). Presence itself
stays the job of ``required``: an ordering whose ``<after>`` never happened is
not a violation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from english_trainer.kernel.encoding import payload_hash

# Fields that vary between runs of even the same adapter and must not affect
# whether two effect sets are "the same" (adapters 4.4: normalize before compare).
_NOISE_KEYS = frozenset({"id", "event_id", "occurred_at", "timestamp", "correlation_id"})
_ORDER_SEPARATOR = " -> "


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
    canonical tags, optionally with ``"ordered": ["<before> -> <after>", ...]``.
    ``observed_effects`` carries the RECORDED effects per adapter id (e.g.
    ``"codex"``, ``"claude-code"``), in the order they happened --
    pre-recorded because OPEN-24 blocks driving a live agent from this
    increment.
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
    order_violations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "adapter": self.adapter,
            "passed": self.passed,
            "missing_required": list(self.missing_required),
            "present_forbidden": list(self.present_forbidden),
            "order_violations": list(self.order_violations),
        }


def _order_violations(ordered: Sequence[str], sequence: Sequence[str]) -> tuple[str, ...]:
    """The ``"<before> -> <after>"`` constraints ``sequence`` breaks.

    Broken iff ``<after>`` occurs and no ``<before>`` occurs before its FIRST
    occurrence. A malformed entry (no separator) is reported as violated, so a
    typo in a fixture fails loudly instead of silently checking nothing.
    """
    violations: list[str] = []
    for constraint in ordered:
        before, separator, after = constraint.partition(_ORDER_SEPARATOR)
        if not separator or not before.strip() or not after.strip():
            violations.append(constraint)
            continue
        before, after = before.strip(), after.strip()
        if after not in sequence:
            continue
        if before not in sequence[: sequence.index(after)]:
            violations.append(constraint)
    return tuple(sorted(set(violations)))


def compare(fixtures: Sequence[ParityFixture]) -> list[FixtureResult]:
    """Diagnostic only: mutates nothing (adapters 4.4).

    A fixture PASSES for an adapter iff every ``required`` effect is present in
    its normalized observed set, no ``forbidden`` effect is, and every
    ``ordered`` constraint holds over the recorded sequence.
    """
    results: list[FixtureResult] = []
    for fixture in fixtures:
        required = set(fixture.expected_effects.get("required", []))
        forbidden = set(fixture.expected_effects.get("forbidden", []))
        ordered = list(fixture.expected_effects.get("ordered", []))
        for adapter in sorted(fixture.observed_effects):
            sequence = [_normalize_effect(effect) for effect in fixture.observed_effects[adapter]]
            normalized = set(sequence)
            missing = tuple(sorted(required - normalized))
            present_forbidden = tuple(sorted(forbidden & normalized))
            order_violations = _order_violations(ordered, sequence)
            results.append(
                FixtureResult(
                    fixture_id=fixture.id,
                    adapter=adapter,
                    passed=not missing and not present_forbidden and not order_violations,
                    missing_required=missing,
                    present_forbidden=present_forbidden,
                    order_violations=order_violations,
                )
            )
    return results


def _tag(name: str) -> dict[str, str]:
    return {"tag": name}


# The minimal fixture set (adapters 4.4), on the brief/report protocol
# [PD-2026-09-23]: correct trigger; wrong trigger; the tutor files its verdicts
# through the checked report (this replaces "agent-attempts-self-score", which
# forbade tutor grading -- reversed by PD-2026-09-23; what stays forbidden is
# fabricating evidence, not judging it); an unfinished required review; finishing
# without persistence; Codex vs Claude Code parity on a shared scenario. Each
# ships with observed effects for a WELL-BEHAVED adapter, so the shipped
# default set passes end to end -- it demonstrates the mechanism catches a
# violation without asserting that a violation is the current state of the
# world (a deliberately non-compliant fixture belongs in a test, not here).
#
# Tags beyond ``cli_call:``/``event:`` name facts an auditor reads off the chat
# transcript against the stored ``lesson.reported`` (skill audit-english-tutor):
# ``report:fabricated_item`` -- an item with no matching exchange in the chat;
# ``report:non_verbatim_answer`` -- a ``raw_answer`` that is not the learner's
# words; ``report:latency_reported`` -- a response time the chat cannot measure
# (PD-2026-09-23); ``report:reviews_addressed`` -- every pending review is an
# item with its ``review_id`` or a ``reviews_skipped`` entry with a reason.
_REPORT_PATH = ("cli_call:session.check-report", "cli_call:session.report")
_CHECK_BEFORE_REPORT = "cli_call:session.check-report -> cli_call:session.report"
_STEP_PROTOCOL_CALLS = [
    "cli_call:attempt.record",
    "cli_call:attempt.finalize",
    "cli_call:review.close",
    "cli_call:session.finish",
]
_FABRICATION = ["report:fabricated_item", "report:non_verbatim_answer", "report:latency_reported"]


def _report_path(*extra: str) -> list[dict[str, str]]:
    return [_tag(name) for name in (*_REPORT_PATH, *extra)]


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
        id="tutor-verdict-report",
        given_state={"active_session": "s1", "chat_items": ["I am an engineer."]},
        agent_input={"learner_message": "I am an engineer."},
        expected_effects={
            "required": [*_REPORT_PATH, "event:lesson.reported"],
            "forbidden": [*_FABRICATION, *_STEP_PROTOCOL_CALLS, "state:self_reported_score"],
            "ordered": [_CHECK_BEFORE_REPORT],
        },
        observed_effects={
            "codex": _report_path("event:lesson.reported"),
            "claude-code": _report_path("event:lesson.reported"),
        },
    ),
    ParityFixture(
        id="unfinished-required-review",
        given_state={"active_session": "s1", "pending_review": "r1"},
        agent_input={"learner_message": "let's wrap up"},
        expected_effects={
            "required": [*_REPORT_PATH, "report:reviews_addressed", "event:session.finished"],
            "forbidden": ["state:declared_finished_without_event", *_STEP_PROTOCOL_CALLS],
            "ordered": [_CHECK_BEFORE_REPORT],
        },
        observed_effects={
            "codex": _report_path("report:reviews_addressed", "event:session.finished"),
            "claude-code": _report_path("report:reviews_addressed", "event:session.finished"),
        },
    ),
    ParityFixture(
        id="finish-without-persistence",
        given_state={"active_session": "s1"},
        agent_input={"learner_message": "we're done for today"},
        expected_effects={
            "required": ["event:lesson.reported", "event:session.finished"],
            "forbidden": ["state:declared_finished_without_event", "cli_call:session.finish"],
            "ordered": [_CHECK_BEFORE_REPORT, "event:lesson.reported -> event:session.finished"],
        },
        observed_effects={
            "codex": _report_path("event:lesson.reported", "event:session.finished"),
            "claude-code": _report_path("event:lesson.reported", "event:session.finished"),
        },
    ),
    ParityFixture(
        id="codex-claude-parity",
        given_state={"active_session": None},
        agent_input={"learner_message": "let's do an English lesson"},
        expected_effects={
            "required": ["cli_call:session.start", *_REPORT_PATH],
            "forbidden": ["state:self_reported_score", *_FABRICATION, *_STEP_PROTOCOL_CALLS],
            "ordered": [
                "cli_call:session.start -> cli_call:session.check-report",
                _CHECK_BEFORE_REPORT,
            ],
        },
        observed_effects={
            "codex": [_tag("cli_call:session.start"), *_report_path()],
            "claude-code": [_tag("cli_call:session.start"), *_report_path()],
        },
    ),
)
