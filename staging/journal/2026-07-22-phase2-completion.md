# Phase 2 completion journal — 2026-07-22

Append-only implementation trail for the ordered completion handoff.

## 2.8c — Availability

- Commit: `87104d4` (`Add deterministic availability control`).
- Implemented the integer-only declared profile and replay-derived observed profile, including exact calendar-week windows, lower medians, honest `no-data`, budget precedence, divergence proposals, and the long-break predicate.
- `compose_plan` accepts an optional `availability_long_break=False`; the default path is byte-identical. A true value runs the bounded critical boost after starvation and before ordinary review without overshoot or cap/floor violations.
- Added atomic/idempotent `availability_set`, read-only `availability_get`, `AVAILABILITY_UPDATED`, and registered `trainer availability show|set`.
- Gates: full pytest `429 passed, 1 xfailed`; `ruff check .` clean; `ruff format --check src tests` clean (135 files); `mypy src` clean (69 source files).
- Finding: Windows ships no IANA tzdb by default. The fold resolves UTC and fixed offsets using stdlib alone and resolves IANA names through `zoneinfo` when the host supplies tzdata; an unavailable zone is rejected stably rather than silently interpreted.
