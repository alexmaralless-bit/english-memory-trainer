# Phase 2 completion — independent review handoff

> Date: 2026-07-22
> Implementation commit: `2d7373c` (`Complete Phase 2 safety and trust contracts`)
> Canon/roadmap commit: `9c41105` (`Finalize the Reading and Writing roadmap`)
> Review rule: the author does not accept their own fixes; this report is evidence for an independent reviewer.

## 1. Requested outcome

The owner accepted all four completion proposals and made the product boundary permanent:

1. replace the tunables/calibration placeholder with an executable versioned catalogue;
2. complete multi-credit evidence and session crash/concurrency safety;
3. publish a canonical total scoring-transition stream;
4. implement the trust contour needed for auditable tutor compliance.

The product now covers Reading, Writing, grammar, vocabulary, and text chat. Listening and Speaking are intentionally learned elsewhere. They are not deferred features and must not return to the roadmap.

## 2. Result

Phase 2 is implemented end to end. The previous four strict-xfail findings are now ordinary passing behavior tests. Current executable inventory:

- 12 runtime modules;
- 55 CLI commands;
- 10 shipped policy payloads;
- 463 collected tests, 0 xfail;
- 275 curriculum topics and 1142 lexical items with no validation errors or warnings;
- 7 remaining OPEN items, all non-blocking for normal use.

## 3. Review matrix

### R1 — Versioned tunables and calibration

**Root cause.** Control exposed policy metrics and tunable references, but the complete catalogue, bounds, ownership, and atomic application workflow did not exist. Inventing an unversioned side table would have made replay and activation dishonest.

**Implementation.**

- `curriculum/policies/tunables-v1.yaml`: exact 60-entry catalogue: 48 leaves of `control_policy@1` plus 12 neighboring tunables. Every value is integer/string canonical data. The accepted `review_max` range is `3000..6000`; parameters without an approved empirical range are explicitly frozen at their current value rather than given invented precision.
- `src/english_trainer/control/tunables.py:173`: deterministic catalogue listing and owner filtering.
- `src/english_trainer/control/tunables.py:206`: proposal validates catalogue identity, type, unit, and allowed range without mutating active policy.
- `src/english_trainer/control/tunables.py:270`: confirmation creates and activates a successor version of the owning policy. `policy.version_activated` and `calibration.applied` are causal facts committed in one UoW. Identical retry is idempotent.
- `curriculum/policies/{assessments,evidence,lessons,obligations}-v1.yaml`: neighboring tunables now have versioned owners.
- CLI surfaces: `tunables list`, `calibration list`, `calibration propose`, `calibration confirm`.

**Proof tests.**

- `tests/control/test_tunables.py:72` — every declared owner leaf resolves exactly once.
- `tests/control/test_tunables.py:83` — confirmation activates a successor and records a causal application atomically.
- `tests/control/test_tunable_catalogue_contract.py` — previous strict xfail removed.

**Reviewer probes.** Verify exact catalogue coverage, attempt one out-of-range proposal, repeat a successful confirmation with the same idempotency key, and inject failure between successor activation and application-event append; neither half may commit alone.

### R2 — Multi-credit evidence

**Root cause.** An assessed answer could exercise multiple targets, but scoring consumed only one primary target. Secondary learning was either invisible or required recomputation from mutable policy.

**Implementation.**

- `curriculum/policies/evidence-v1.yaml`: primary weight `1.0`, secondary weight `0.5`, total cap `2.0`, stored as decimal strings.
- `src/english_trainer/evidence/policy.py:38`: resolves the pinned evidence policy, with a deterministic compatibility fallback for historical manifests.
- `src/english_trainer/evidence/policy.py:74`: primary-first allocation; secondary targets are canonical-sorted; excess candidates remain visible with `used=false`, zero contribution, and reason `total_cap`.
- Objective and rubric finalization capture the complete allocation in immutable assessment events.
- `src/english_trainer/scoring/engine.py` consumes every accepted allocation while preserving the historical primary Decimal calculation.

**Proof tests.**

- `tests/evidence/test_multi_credit.py:22` — canonical primary-first capped allocation.
- `tests/evidence/test_multi_credit.py:43` — the scoring fold consumes secondary credit and keeps excluded targets auditable.

**Reviewer probes.** Permute secondary-target input order and compare canonical events byte for byte. Supply enough targets to exceed `2.0`; the visible rejected tail must be stable and must not affect the fold.

### R3 — Coarse session revision and crash-safe stale recovery

**Root cause.** `plan_version` protected only plan mutations. Two tutors could still mutate other parts of one live session using stale state. Stale-session cleanup also needed one versioned policy and one atomic terminalization path.

**Implementation.**

- `src/english_trainer/kernel/session_fence.py:20`: reads the authoritative coarse revision.
- `src/english_trainer/kernel/session_fence.py:28`: loads a live session for mutation and rejects a mismatch with stable `SESSION_REVISION_CONFLICT` before effects.
- `src/english_trainer/kernel/session_fence.py:44`: bumps the token inside the caller's UoW.
- Every public live-session mutation requires keyword-only `expected_session_revision`: next/replan, exercise render, attempt record/finalize, observed-error record, review close, finish, abandon, adapter user-turn capture, and skill report. `next`/`replan` additionally retain `plan_version`.
- CLI request hashes include the revision. An identical cached retry is resolved before the live revision check, so idempotency and optimistic concurrency do not conflict.
- `curriculum/policies/lessons-v1.yaml`: pinned `stale_session_days=7`.
- `src/english_trainer/lessons/sessions.py:140`: deterministic stale boundary (`last_activity_at + threshold`), closes pending attempts and review obligations, clears the active pointer, emits causal scoring transitions, and terminalizes in one UoW. Repeated sweep is a no-op.

**Proof tests.**

- `tests/lessons/test_sessions.py:190` — one writer succeeds and the stale writer leaves no effect.
- `tests/lessons/test_sessions.py:223` — pinned boundary, idempotent sweep, pending cleanup, and slot release.
- `tests/integration/test_tutor_swap.py:433` — end-to-end provider swap, state/notes trust boundary, surviving review obligation, finish gate, and deterministic continuation.
- `tests/integration/test_tutor_swap.py:481` — public mutation signatures expose the mandatory fence; the former strict xfail is removed.

**Reviewer probes.** Read one revision, issue two different mutations with it, and assert exactly one effect and one increment. Inject `BaseException` at commit during sweep and assert that session, attempts, reviews, pointer, transitions, events, and outbox are all old or all new.

### R4 — Canonical scoring transitions

**Root cause.** Control's lapse metric expected a canonical state-transition fact, but scoring produced no such total stream. Deriving a second state machine inside control would diverge from scoring replay.

**Implementation.**

- `src/english_trainer/scoring/transitions.py:51`: one `scoring.state_transition` for every score-bearing source, including same-state no-op transitions. IDs are derived deterministically; every transition carries its causal source.
- `src/english_trainer/scoring/transitions.py:105`: ordered idempotent backfill for historical source events.
- Attempt/review finalization, scheduler overdue transitions, placement scoring, explicit abandon, and stale abandonment write the source and transition in the same UoW.
- `src/english_trainer/control/metrics.py` consumes this canonical stream and reports `no-data` when coverage is incomplete instead of silently reconstructing state.

**Proof tests.**

- `tests/scoring/test_transitions.py:21` — causal, ordered, idempotent backfill.
- `tests/scoring/test_transitions.py:59` — no-op source still gets exactly one audit fact.
- `tests/lessons/test_review_loop.py` — abandon/stale review outcomes and their transitions are atomic and have no coverage gap.

**Reviewer probes.** Build mixed historical sources with an intentional transition gap, confirm the metric is not asserted as complete, run backfill twice, and verify byte-identical transition order and zero remaining gaps.

### R5 — Provider ingress and untrusted skill reporting

**Root cause.** The adapter layer had no provider user-message ingress, so user-turn evidence could not be correlated honestly. Skill lifecycle evidence was also self-report without a persisted untrusted boundary.

**Implementation.**

- `src/english_trainer/adapters/ingress.py:61`: captures the complete raw UTF-8 user turn, SHA-256 hash, validated byte span, provider and provider-global message identity.
- Same provider/message/content retry is idempotent. Reuse with different content is a stable conflict. The complete raw content is retained because this is a private personal tool and the owner chose auditability over redaction at ingress.
- Skill report records the pinned skill content hash and declared CLI calls, but remains explicitly untrusted and cannot change learner/scoring state.
- Both mutations share the coarse session fence.

**Proof tests.**

- `tests/adapters/test_ingress.py:64` — exact text/hash/span and provider-global identity.
- `tests/adapters/test_ingress.py:123` — untrusted skill report and shared session fence.

**Reviewer probes.** Retry the same provider message before and after another session mutation; exact retry must remain cached, while changed text with the same provider identity must fail without a new event.

### R6 — Outer CLI telemetry, obligations, and Tutor Compliance

**Root cause.** Successful domain events could not prove that an agent followed the required protocol: read-only calls and rejected forbidden actions were invisible. Scoring named obligation families but no versioned matching policy existed.

**Implementation.**

- `src/english_trainer/cli/telemetry.py:104` and `:148`: outer invocation and terminal facts wrap the command dispatcher. Success, stable refusal, and unexpected failure are observable. Raw arguments and secrets are not stored; telemetry carries command name, redacted argument-shape hash, outcome, error code, correlation, and session hint when resolvable.
- `curriculum/policies/obligations-v1.yaml`: versioned ten-session observation window and three obligation families: required command sequence, required pinned skills, and user-turn evidence.
- `src/english_trainer/audit/views.py:97`: read-only per-session obligation correlation separates declaration/self-report from engine-observed effects.
- `src/english_trainer/scoring/compliance.py:14`: Tutor Compliance uses the last N fully observed terminal sessions only. Partial telemetry remains pending and never becomes a false failure.
- `trainer status` exposes the compliance result; audit commands expose the underlying facts.

**Proof tests.**

- `tests/cli/test_telemetry.py:17` — read-only and refused commands are visible; raw argument values are absent.
- `tests/audit/test_obligations.py:22` — self-report and observed effect remain distinct; audit is read-only.
- `tests/audit/test_trust_contour_contract.py` — both former strict-xfail contract checks removed.

**Reviewer probes.** Run one read-only command, one rejected mutating command, and one successful mutation with a secret-like argument. Confirm two outer facts per invocation, no raw value leakage, stable correlation, and no compliance denominator until the session is fully observed and terminal.

### R7 — Permanent product boundary and status sources

**Implementation.**

- `docs/design-direction.md` is now explicit that Listening/Speaking are outside both current scope and future roadmap.
- The older brief/build prompt carry precedence banners so their historical voice/listening examples are non-normative.
- `wiki/product/learning-model.md` forbids proxy scores and future planning for excluded modalities.
- `wiki/OPEN.md` moves OPEN-11/19/20/21/26/32 to resolved and leaves exactly OPEN-9/22/23/24/27/28/29 open.
- `wiki/roadmap.md` records Phase 2 complete, 463/0, 55 commands, 10 policies, 7 OPEN, and dogfooding/calibration as the next useful activity.
- `English Memory Trainer — Roadmap.html` is the synchronized standalone roadmap view.
- `staging/journal/2026-07-22-phase2-completion.md` was extended append-only; earlier findings were not rewritten away.

**Reviewer probes.** Search normative canon/curriculum for forbidden phase markers (the architecture test owns accepted history exclusions), verify OPEN table counts, and confirm no roadmap item proposes Listening/Speaking.

## 4. Reproduction commands and observed results

Run from repository root with the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .tmp_pytest_review\full -q
.\.venv\Scripts\python.exe -m pytest --collect-only
.\.venv\Scripts\python.exe -m pytest tests\kernel\test_replay.py --basetemp .tmp_pytest_review\replay -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -c "from english_trainer.cli.app import run; run(['curriculum','validate','--format','json'])"
.\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; fs=sorted(Path('curriculum/policies').glob('*.yaml')); [yaml.safe_load(p.read_text(encoding='utf-8')) for p in fs]; print(len(fs))"
```

Author's final observed results:

```text
pytest:                         463 passed, 0 xfail
pytest --collect-only:          463 tests collected
kernel replay:                  4 passed (subprocess determinism included)
ruff check:                     All checks passed
ruff format --check:            162 files already formatted
mypy src:                       Success, 83 source files
curriculum validate:            ok=true, topics=275, lexicon=1142,
                                 errors=[], warnings=[]
policy YAML parse:              10 files
HTML structural check:          13 unique ids, 6 internal links,
                                 0 duplicate ids, 0 missing anchors
```

Pytest may warn that `.pytest_cache` cannot be written in a restricted Windows sandbox; this does not affect test execution. A run using `C:\tmp` as `--basetemp` was rejected by the sandbox with `WinError 5`; the complete rerun under the workspace passed. Reviewers should use a writable explicit `--basetemp`.

## 5. Commit and scope audit

### `2d7373c` — runtime and executable contracts

- 65 files;
- 4499 insertions, 347 deletions;
- contains only `curriculum/policies/**`, `src/english_trainer/**`, and `tests/**` needed by the accepted completion work.

### `9c41105` — canon, journal, and roadmap

- 20 files;
- 763 insertions, 89 deletions;
- updates `docs/**`, relevant `wiki/**`, the append-only completion journal, and the standalone HTML roadmap.

The root `Irregular Verbs.md` was not touched. Pre-existing local edits in `AGENTS.md`, `CLAUDE.md`, and four lexicon files were neither staged nor committed. The untracked `English Memory Trainer — Roadmap_files/` directory was also left untouched; the committed HTML is self-contained and does not require it.

## 6. Remaining non-blocking questions

- OPEN-9 — long-term pinned-policy retention/deprecation mappings;
- OPEN-22 — empirical learner-priority formula;
- OPEN-23 — CLI compatibility lifetime policy;
- OPEN-24 — live-LLM parity fixture protocol;
- OPEN-27 — empirical control-policy calibration;
- OPEN-28 — empirical gate thresholds;
- OPEN-29 — richer calendar availability.

None blocks deterministic personal use of the current Reading/Writing trainer. OPEN-27 and OPEN-28 specifically require real usage data; authoring more precision before dogfooding would be fabrication.

## 7. Requested independent verdict

Review `2d7373c` against the accepted four decisions and the current canon, then verify `9c41105` describes the implementation without overclaiming. Suggested verdict format:

1. `PASS`, `PASS-with-findings`, or `FAIL`;
2. status of R1–R7 individually;
3. any in-scope data-corruption, partial-state, determinism, or normal-API lifecycle defect with `file:line` and a reproducer;
4. non-blocking/out-of-scope observations separately;
5. exact outputs of the reproduction commands.
