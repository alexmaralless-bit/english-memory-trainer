"""The pure signal-precedence function over classified review candidates
(control 4.7): exclusions, the two class shifts, NO_ALLOWED_CONTEXT, and
target-scope beating a conflicting domain-scope signal."""

from __future__ import annotations

from typing import Any

from english_trainer.control.signals import apply_signals


def cand(
    target: str,
    urgency: str = "normal",
    *,
    context: str = "review|recognition_check",
    domain: str | None = None,
    risk: bool | None = None,
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "candidate_id": f"review:{target}",
        "target_ref": target,
        "urgency_class": urgency,
        "context_id": context,
    }
    if domain is not None:
        candidate["domain"] = domain
    if risk is not None:
        candidate["risk"] = risk
    return candidate


def classes(candidates: list[dict[str, Any]]) -> dict[str, str]:
    return {c["target_ref"]: c["urgency_class"] for c in candidates}


def test_snooze_and_not_relevant_now_exclude_the_target() -> None:
    candidates = [cand("a"), cand("b"), cand("c")]
    signals = [{"kind": "snooze", "target_ref": "a"}, {"kind": "not_relevant_now", "target_ref": "b"}]
    survivors, waivers = apply_signals(candidates, signals)
    assert [c["target_ref"] for c in survivors] == ["c"] and waivers == []


def test_not_relevant_now_domain_excludes_the_whole_domain() -> None:
    candidates = [cand("a", domain="work"), cand("b", domain="home")]
    survivors, _ = apply_signals(candidates, [{"kind": "not_relevant_now", "domain": "work"}])
    assert [c["target_ref"] for c in survivors] == ["b"]


def test_need_more_practice_shifts_one_class_up() -> None:
    candidates = [cand("a", "deferrable"), cand("b", "normal"), cand("c", "important")]
    signals = [
        {"kind": "need_more_practice", "target_ref": "a"},
        {"kind": "need_more_practice", "target_ref": "b"},
        {"kind": "need_more_practice", "target_ref": "c"},
    ]
    survivors, _ = apply_signals(candidates, signals)
    # deferrable -> maintenance, normal -> important, important unchanged (4.7).
    assert classes(survivors) == {"a": "maintenance", "b": "important", "c": "important"}


def test_prefer_different_context_excludes_context_and_waives_when_empty() -> None:
    candidates = [cand("a", context="email|transfer_task"), cand("b", context="chat|transfer_task")]
    signals = [
        {"kind": "prefer_different_context", "target_ref": "a", "avoid_context": "email|transfer_task"}
    ]
    survivors, waivers = apply_signals(candidates, signals)
    # 'a' had only its avoided context -> dropped and NO_ALLOWED_CONTEXT; 'b' stays.
    assert [c["target_ref"] for c in survivors] == ["b"]
    assert waivers == ["NO_ALLOWED_CONTEXT"]


def test_too_repetitive_shifts_down_only_non_risk_candidates() -> None:
    candidates = [cand("a", "normal"), cand("b", "maintenance"), cand("c", "critical")]
    signals = [
        {"kind": "too_repetitive", "target_ref": "a"},
        {"kind": "too_repetitive", "target_ref": "b"},
        {"kind": "too_repetitive", "target_ref": "c"},
    ]
    survivors, _ = apply_signals(candidates, signals)
    # normal -> maintenance, maintenance -> deferrable; the risk class is untouched.
    assert classes(survivors) == {"a": "maintenance", "b": "deferrable", "c": "critical"}


def test_too_repetitive_skips_an_explicit_risk_candidate() -> None:
    candidates = [cand("a", "normal", risk=True)]
    survivors, _ = apply_signals(candidates, [{"kind": "too_repetitive", "target_ref": "a"}])
    assert classes(survivors) == {"a": "normal"}  # risk=true blocks the down-shift


def test_too_easy_leaves_classes_unchanged() -> None:
    candidates = [cand("a", "normal")]
    survivors, waivers = apply_signals(candidates, [{"kind": "too_easy", "target_ref": "a"}])
    assert classes(survivors) == {"a": "normal"} and waivers == []


def test_target_scope_beats_a_conflicting_domain_scope_signal() -> None:
    # A domain not_relevant_now would exclude the whole 'work' domain, but a
    # target-scoped need_more_practice on 'a' conflicts, so 'a' survives; 'b',
    # with no target signal, is still excluded (control 4.7).
    candidates = [cand("a", domain="work"), cand("b", domain="work")]
    signals = [
        {"kind": "not_relevant_now", "domain": "work"},
        {"kind": "need_more_practice", "target_ref": "a"},
    ]
    survivors, _ = apply_signals(candidates, signals)
    assert [c["target_ref"] for c in survivors] == ["a"]
