# Phase 2 completion journal — 2026-07-22

Append-only implementation trail for the ordered completion handoff.

## 2.8c — Availability

- Commit: `87104d4` (`Add deterministic availability control`).
- Implemented the integer-only declared profile and replay-derived observed profile, including exact calendar-week windows, lower medians, honest `no-data`, budget precedence, divergence proposals, and the long-break predicate.
- `compose_plan` accepts an optional `availability_long_break=False`; the default path is byte-identical. A true value runs the bounded critical boost after starvation and before ordinary review without overshoot or cap/floor violations.
- Added atomic/idempotent `availability_set`, read-only `availability_get`, `AVAILABILITY_UPDATED`, and registered `trainer availability show|set`.
- Gates: full pytest `429 passed, 1 xfailed`; `ruff check .` clean; `ruff format --check src tests` clean (135 files); `mypy src` clean (69 source files).
- Finding: Windows ships no IANA tzdb by default. The fold resolves UTC and fixed offsets using stdlib alone and resolves IANA names through `zoneinfo` when the host supplies tzdata; an unavailable zone is rejected stably rather than silently interpreted.

## 2.8d — Decision trace (complete)

- Commit: `2076a5e` (`Persist control decision traces`).
- Every materialized step now carries classification rules, risk/stake/retrievability, saturation, quotas, bucket occupancy, applied signal ids, pins, and active safety as either computed inputs, immutable facts, or catalogue references.
- Traces are stored in immutable per-step aggregates in the same UoW as plan creation/replan, so a later dropped step remains explainable. `trainer why --step` reads the saved fact and never recomputes history.
- `STEP_PRESENTED` now captures the delivery-time (not composition-time) predicted Retrievability for review assignments.
- Gates: full pytest green with the pre-existing OPEN-11 xfail; ruff/format/mypy strict clean.

## 2.8d — Policy metrics (complete, one upstream producer finding)

- Commit: `c53f18d` (`Add deterministic control metrics`).
- Added all seven v1 metric folds, integer ppm/basis-point arithmetic, exact windows/minimum sample rules, nearest-rank p90, last-presentation calibration matching, and honest `no-data`.
- Alerts use only terminal balanced-session DeliveryLedger facts, keep separate enter/exit thresholds and consecutive runs, and report choices without changing composition.
- `trainer metrics` is read-only; missing neighboring policy state makes only dependent metrics `no-data`.
- Finding: `lapse_rate_after_mastered` consumes the canonical `STATE_TRANSITION` event, but the existing scoring implementation does not yet publish that canonical event. The fold is covered with synthetic contract events and remains honestly `no-data` in live data until the scoring producer is wired; silently deriving a second scoring state machine inside control was rejected.
- Gates: full pytest green with the pre-existing OPEN-11 xfail; ruff/format/mypy strict clean.

## 2.8d — Tunables catalogue/calibration (blocked by missing owner data)

- Status: not implemented; strict xfail `test_versioned_tunable_catalogue_exists_with_bidirectional_control_coverage` records the boundary.
- Finding: §4.9 supplies `allowed_range`, `unit`, `observed_by`, and trace mapping only for one `review_max` example, while requiring complete rows for every control parameter and previously declared neighboring tunable. Inventing the missing ranges would violate the handoff's no-PD rule and would make activation constraints look authoritative without an approved source.
- Owner decision needed: approve the complete catalogue metadata (or a rule that derives it) before `tunables list` and calibration propose/confirm can be implemented honestly.

## 2.8e — Exercise-bank reuse and observed errors

- Commit: `40b44b3` (`Wire exercise bank reuse and observed errors`).
- Composition now selects accepted bank items conservatively and deterministically by exact step type, target, dimension, and context. The step carries exactly one source: `bank_item_id` or `generation_directive`.
- `session next` re-reads the authoritative accepted state, revalidates target/lexicon safety against the active curriculum, resolves the immutable rendered snapshot, and commits `STEP_PRESENTED` plus `ExerciseUse` in one UoW. A safety change leaves the plan version untouched. Reused snapshots are valid attempt inputs through the published `exercise.used` fact; delivery alone creates no evidence.
- Added `trainer observed record`: the engine derives target/dimension and rubric-owned error family/severity from an assessed attempt, validates the exact UTF-8 span, rejects agent-supplied verdicts and `contradicts_machine_result`, and emits `evidence.error_observed`. Semantic duplicate observations are idempotent.
- The real evidence event now feeds `recurring_error_keys`; an integration test proves two emitted observations activate the recurring-error risk branch in classification.
- Gates: full pytest `441 passed, 2 xfailed` (443 collected); `ruff check .` clean; `ruff format --check src tests` clean (143 files); `mypy src` clean (72 source files).

## Lessons wiring — live control inputs

- Commit: `7e5a172` (`Activate live control inputs in lessons`).
- `session start` and `session replan` now fold active learner signals, probe requests, saturation, recurring observed errors, terminal-session deferrals, starvation qualification, and AvailabilityProfile state from the authoritative log before composition.
- Probe signal consumption, plan/assignment state, `SESSION_COMPOSED`, and immutable decision traces commit in the same UoW. Composition events persist eligible/excluded review facts, allowing terminal session events to advance the deferral fold without a second mutable counter.
- End-to-end tests prove: `too_easy` produces and consumes one control probe; `need_more_practice` raises a live urgency class; repeated real exposures make a target deferrable; three terminal systematic deferrals qualify and admit the target through the starvation reserve; declared availability changes the live session budget.
- New optional live fields remain absent from the historical `compose_plan` result when their inputs are omitted, preserving the default canonical shape.
- OPEN-11 remains intentionally open. The contract requires optimistic session revision but `wiki/OPEN.md` explicitly leaves multi-aggregate CAS and idempotency scope unresolved. `staging/concepts/2026-07-22-open11-session-revision-concept.md` documents the concrete aggregate conflict and three options; coarse session fencing is recommended. The strict xfail remains a truthful executable finding.
- Gates: full pytest `447 passed, 2 xfailed` (449 collected); `ruff check .` clean; `ruff format --check src tests` clean (144 files); `mypy src` clean (72 source files).

## 2.9 — Trust contour (blocked by missing contract decisions)

- Status: no runtime implementation. Two strict xfails in `tests/audit/test_trust_contour_contract.py` preserve the missing adapter-ingress and `audit.obligations` surfaces as executable findings.
- The current adapters boundary handles Agent Skill files and parity fixtures; it receives no provider user messages. The requested `provider_message_id` + hash + span therefore has no honest capture point.
- The event log contains domain outcomes but no persisted Command/CLI invocation or refusal facts. Inferring compliance from successful domain events would make rejected forbidden actions and read-only obligations invisible.
- Scoring names three obligation families, but no versioned obligations payload defines applicability, effect matching, denominator, correlation rules, policy selection, or incomplete-history behavior. Skill lifecycle self-report event names also have no reporting channel by design.
- `staging/concepts/2026-07-22-2.9-trust-contour-concept.md` presents four owner decisions and recommends: raw UTF-8 capture for this local tool, adapter-owned idempotent ingress, append-only command/result observation in the authoritative event log, and an explicit versioned obligations payload.
- Session lease remains unimplemented as required: it is MAY and no real simultaneous-agent need was established.
- Expected final gates after adding the two markers: `447 passed, 4 xfailed` (451 collected), with Ruff/format/mypy strict clean.

## Final handoff summary

- Completed implementation commits: Availability `87104d4`; immutable DecisionTrace `2076a5e`; deterministic metrics `c53f18d`; bank reuse + observed errors `40b44b3`; live lessons/control wiring `7e5a172`.
- Acceptance trail commits: `b5b6e74`, `8430712`, `8efcdaf`, `9eb673b`; 2.9 executable findings and concept: `4b514c9`.
- Implemented behavior is active end-to-end, not only pure helpers: session composition consumes availability, signals/probes, saturation, recurring errors, deferral/starvation and bank state; decision facts and one-shot consumption are transactional.
- Owner decisions still required: complete tunable catalogue metadata/ranges and calibration ownership; canonical scoring `STATE_TRANSITION` producer; OPEN-11 session-revision/multi-aggregate CAS; 2.9 provider ingress, command observation and obligations payload. These are represented by four strict xfails and two mini-concepts, not placeholder success paths.
- Final verification: 451 tests collected — `447 passed, 4 xfailed`; `ruff check .` clean; `ruff format --check src tests` clean (145 files); `mypy src` strict clean (72 source files); CLI registry remains 45 commands.
- Scope hygiene: unrelated pre-existing CRLF/noise files, `wiki/modules/control.md`, generated roadmap HTML, and root `Irregular Verbs.md` were never staged or modified by these commits.

## Owner decisions implemented — Phase 2 complete

- Commit: `2d7373c` (`Complete Phase 2 safety and trust contracts`).
- The owner accepted all four proposed closures. The tunables gap is now a versioned 60-entry `tunables@1` catalogue with integer bounds, read-only listing, and proposal/confirmation that activates a successor owner policy atomically with its calibration fact.
- `evidence@1` now assigns primary `1.0`, secondary `0.5`, and total cap `2.0`; allocation is deterministic, captured in the assessment event, and the scoring fold consumes every accepted allocation without changing the primary Decimal result.
- OPEN-11 is closed by one coarse `session_revision` fence on every public live-session mutation. Same-key cached retries precede the fence; stale writers have no effects. A pinned `lessons@1` stale policy emits a deterministic boundary event and closes pending attempts, reviews, the active pointer, and their causal scoring facts in one UoW.
- Every score-bearing source now has exactly one canonical `scoring.state_transition`, including no-op transitions. The transition is causal to the source event and written in the same UoW; a deterministic backfill covers historical sources. Control's lapse metric reads this canonical producer.
- The trust contour is now executable: adapters persist complete raw UTF-8 user turns with provider-global idempotency and validated spans; the CLI writes outer invocation/terminal telemetry for success, refusal, and failure without raw arguments; `obligations@1` correlates commands, skills, and user-turn evidence over the last ten fully observed terminal sessions; `trainer status` exposes Tutor Compliance.
- [PD-2026-07-22] Product scope is permanent: Reading, Writing, grammar, vocabulary, and text chat. Listening and Speaking are intentionally learned elsewhere and are neither product capabilities nor future-roadmap items.
- Final gates: `463 tests collected`; full pytest `463 passed / 0 xfail`; `tests/kernel/test_replay.py` `4 passed`; `ruff check .` clean; `ruff format --check src tests` clean (`162 files`); `mypy src` strict clean (`83 source files`); curriculum validation `ok: true`, `275 topics`, `1142 lexicon`, `0 errors`, `0 warnings`; all `10` policy YAML files parse.
- OPEN is reduced from 13 to 7 non-blocking items: OPEN-9, OPEN-22, OPEN-23, OPEN-24, OPEN-27, OPEN-28, and OPEN-29. The next step is independent acceptance followed by real-use calibration, not another implementation phase.
