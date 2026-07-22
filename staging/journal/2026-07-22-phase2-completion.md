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
