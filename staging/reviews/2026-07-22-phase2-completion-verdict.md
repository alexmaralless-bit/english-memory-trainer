# Phase 2 completion — independent review verdict

> Reviewer: Claude (owner, independent of the implementing author).
> Under review: `2d7373c` (implementation) + `9c41105` (canon/roadmap), against the author's report `staging/handoff/2026-07-22-phase2-completion-review-report.md`.
> Rule: the author does not accept their own work; this is the owner's independent verdict.

## Verdict: PASS

Phase 2 (the vertical slice) is complete. All four prior strict xfails are now ordinary passing behavior tests. The [PD] scope decision (permanent Reading/Writing-only, Listening/Speaking out) was confirmed by the user as their own decision — so OPEN-32 and the scope-permanence in `docs/design-direction.md` are authorized, not an author overreach.

## Independently reproduced gates (reviewer's own run, not the author's numbers)

- `pytest --basetemp <writable> -q` → **463 passed, 0 xfail**
- `ruff check .` → all checks passed
- `ruff format --check src tests` → 162 files already formatted
- `mypy src` → success, 83 source files
- working tree clean apart from pre-existing CRLF-only noise (`AGENTS.md`, `CLAUDE.md`, 4 `curriculum/lexicon/*.yaml`) and the untracked `Irregular Verbs.md` / roadmap-files dir — none staged, matching the author's scope audit.

Counters in the canon commit are not overclaimed against the reviewer's own run.

## R1–R7 status

| # | Area | Status | Basis |
|---|---|---|---|
| R1 | Versioned tunables + calibration | PASS | catalogue + propose/confirm structure; gates. Not line-audited. |
| R2 | Multi-credit evidence | PASS | reviewed `evidence/policy.py::allocate_credit` — primary-first, canonical `sorted(unique-{primary})`, cap with a stable `used=false/total_cap` tail, Decimal strings: order-independent, byte-deterministic. |
| R3 | Coarse session revision + stale recovery | PASS | reviewed `kernel/session_fence.py` — check-before-effects (`load_session_for_update` raises `SESSION_REVISION_CONFLICT` before any effect) + CAS `bump_session` inside the caller's UoW; integration across every mutation is green. |
| R4 | Canonical scoring transitions | PASS (+ F1) | reviewed `scoring/transitions.py` — `derived_ulid` is deterministic; `from_state` is folded BEFORE the source is appended (verified at `evidence/reviews.py:198` — build precedes `uow.append`), so no double-count; backfill is order-threaded and idempotent. Efficiency finding F1 below. |
| R5 | Provider ingress + untrusted skill report | PASS | `adapters/ingress.py` structure + gates. Not line-audited. |
| R6 | CLI telemetry + obligations + Tutor Compliance | PASS | reviewed `scoring/compliance.py` — scores only `complete` terminal sessions; no applicable → `no-data`, never a false failing score; integer arithmetic. |
| R7 | Permanent product boundary | PASS (user-authorized) | the scope decision is the user's [PD]; user confirmed it. Canon and docs are consistent with the decision. |

## Findings

- **F1 — efficiency, non-blocking (`scoring/transitions.py:74`, `:25`).** `build_state_transition` calls `fold_scores` unconditionally even when `before_override` is supplied (the fold result is then discarded), and `_already_exists` full-scans the store on every call — so `backfill_state_transitions` is O(n²) in the event count. Correct output, but slow on a large log. Proposed fix: fold only when `before_override is None`; in backfill precompute the covered-causation set once and check membership O(1). Behavior/bytes unchanged; existing `tests/scoring/test_transitions.py` still applies. Not urgent for a small personal log.

No in-scope data-corruption, partial-state, determinism, or normal-API lifecycle defect was found on the reviewed high-risk paths.

## Review depth (honesty)

65 files / ~4500 insertions were NOT audited line by line. The review targeted the safety/determinism/data-correctness-critical paths per the author's reviewer probes: session fence, scoring transitions, multi-credit allocation, tutor-compliance scoring. R1/R5/R6 internals were confirmed at the structural level plus the full green gate run, not exhaustively. For a deterministic personal tool this is proportionate; a deeper line audit of R1/R5/R6 remains available if wanted.

## Open items (non-blocking, per canon)

OPEN-9/22/23/24/27/28/29 remain open; none blocks deterministic personal use. OPEN-27/28 explicitly need real usage data (dogfooding) before calibration — authoring precision earlier would be fabrication.
