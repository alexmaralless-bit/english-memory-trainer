"""Adapter parity over recorded observable effects, not prose (adapters 4.4)."""

from __future__ import annotations

from english_trainer.adapters.compare import DEFAULT_FIXTURES, ParityFixture, compare


def test_compare_passes_when_required_present_and_nothing_forbidden() -> None:
    fixture = ParityFixture(
        id="ok",
        given_state={},
        agent_input={},
        expected_effects={"required": ["cli_call:session.start"], "forbidden": ["state:self_reported_score"]},
        observed_effects={"claude-code": [{"tag": "cli_call:session.start"}]},
    )
    (result,) = compare([fixture])
    assert result.passed is True
    assert result.missing_required == ()
    assert result.present_forbidden == ()


def test_compare_fails_when_a_required_effect_is_missing() -> None:
    fixture = ParityFixture(
        id="missing",
        given_state={},
        agent_input={},
        expected_effects={"required": ["cli_call:session.start"], "forbidden": []},
        observed_effects={"codex": [{"tag": "chat_only"}]},
    )
    (result,) = compare([fixture])
    assert result.passed is False
    assert result.missing_required == ("cli_call:session.start",)


def test_compare_fails_when_a_forbidden_effect_is_present() -> None:
    fixture = ParityFixture(
        id="forbidden-present",
        given_state={},
        agent_input={},
        expected_effects={"required": [], "forbidden": ["state:self_reported_score"]},
        observed_effects={"codex": [{"tag": "state:self_reported_score"}]},
    )
    (result,) = compare([fixture])
    assert result.passed is False
    assert result.present_forbidden == ("state:self_reported_score",)


def test_compare_normalizes_non_deterministic_fields() -> None:
    # Two "runs" with different ids/timestamps/correlation_id but the same
    # canonical tag must compare equal (adapters 4.4: normalize before compare).
    fixture = ParityFixture(
        id="normalized",
        given_state={},
        agent_input={},
        expected_effects={"required": ["cli_call:session.start"], "forbidden": []},
        observed_effects={
            "codex": [
                {
                    "tag": "cli_call:session.start",
                    "id": "evt-1",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "correlation_id": "corr-1",
                }
            ]
        },
    )
    (result,) = compare([fixture])
    assert result.passed is True


def test_compare_evaluates_multiple_adapters_independently() -> None:
    fixture = ParityFixture(
        id="split",
        given_state={},
        agent_input={},
        expected_effects={"required": ["cli_call:session.start"], "forbidden": []},
        observed_effects={
            "codex": [{"tag": "cli_call:session.start"}],
            "claude-code": [{"tag": "chat_only"}],
        },
    )
    results = {result.adapter: result for result in compare([fixture])}
    assert results["codex"].passed is True
    assert results["claude-code"].passed is False


def test_default_fixtures_cover_the_canon_minimal_set() -> None:
    ids = {fixture.id for fixture in DEFAULT_FIXTURES}
    assert ids == {
        "correct-trigger",
        "wrong-trigger",
        "agent-attempts-self-score",
        "unfinished-required-review",
        "finish-without-persistence",
        "codex-claude-parity",
    }


def test_default_fixtures_all_pass_for_a_well_behaved_adapter() -> None:
    # The shipped set demonstrates the mechanism catches a violation; it does
    # not itself contain one -- every recorded effect set here is what a
    # compliant tutor produces for that scenario.
    results = compare(DEFAULT_FIXTURES)
    assert results  # non-empty: every fixture recorded at least one adapter
    assert all(result.passed for result in results)


def test_codex_claude_parity_fixture_is_symmetric() -> None:
    fixture = next(f for f in DEFAULT_FIXTURES if f.id == "codex-claude-parity")
    results = {result.adapter: result for result in compare([fixture])}
    assert set(results) == {"codex", "claude-code"}
    assert results["codex"].passed and results["claude-code"].passed
