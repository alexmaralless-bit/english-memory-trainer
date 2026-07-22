# OPEN-11 mini-concept: optimistic session revision

Date: 2026-07-22  
Status: owner decision required; no canon changes proposed or applied

## Finding

`wiki/flows/continuation.md` requires a stale concurrent session mutation to
fail, but the authoritative contract still leaves the mechanism open in
`wiki/OPEN.md` OPEN-11: idempotency scope and multi-aggregate CAS are not
specified. The existing public surface has several different concurrency
domains:

- `session next` / `session replan` use `expected_plan_version` and CAS the
  `session_plan` aggregate; the first `next` can also change the session status;
- `record_attempt` creates an attempt and can update notes, but does not mutate
  the session aggregate;
- `close_review` CASes a review assignment;
- `record_rendered_exercise` appends an immutable render fact;
- `finish` / `abandon` CAS the session and also inspect or close attempt/review
  aggregates and clear the active-session pointer;
- `resume` appends `AGENT_ATTACHED` without changing the session state.

Adding a parameter named `expected_session_revision` only to signatures would
close the test symptom, not the concurrency invariant. A real implementation
must decide which of those operations share one conflict domain and how its CAS
composes with `plan_version`, review CAS and idempotent retries.

## Decision required

### Option A — coarse session fence (recommended for the personal tool)

Every public mutation associated with a live session CASes and increments one
`session_revision`, even when its domain payload lives in another aggregate.
`next` and `replan` must match both `expected_session_revision` and
`expected_plan_version`; the transaction advances both. `record_attempt`,
render, observed-error, review-close, resume, finish and abandon advance the
session fence in the same UoW as their domain write.

Trade-offs: simplest client model and deliberately serializes two tutors; more
false conflicts; every command path must join the session UoW; cached
idempotent replay must be defined to return its original success before or
after checking a now-stale fence.

### Option B — command-specific revision vector

Expose the relevant tokens per command, for example
`{session_revision, plan_version, review_revision}`. A command checks only the
aggregates it actually changes.

Trade-offs: fewer false conflicts and makes multi-aggregate dependencies
explicit; substantially larger CLI/API contract, and the continuation client
must retain several tokens rather than one session token.

### Option C — session event-stream high-water mark

Treat the latest sequence for the session correlation id as an ETag and reject
an append when it changed. Aggregate CAS remains separate.

Trade-offs: naturally covers append-only render/attempt/attach facts; requires a
new kernel conditional-append primitive and a precise rule for events whose
correlation id is not the session. It is the broadest foundation change.

## Secondary choices that must be fixed with the option

1. Exact mutation set: whether `resume`/`AGENT_ATTACHED`, render, note-only and
   observed-error writes advance the token.
2. Idempotency precedence: whether a retry with the same key and payload returns
   the cached response even when its expected revision is now stale.
3. Response contract: every mutating response must return the new token, and
   `start`/`resume`/`peek` must expose the current token so a cold tutor can act.
4. Conflict envelope: stable error code and fields for current vs expected
   session revision.
5. Interaction with `plan_version`: both tokens required (Option A/B), or a
   single token replaces plan CAS (a separate, more disruptive decision).

## Recommendation and acceptance test

Choose Option A, keep `plan_version` as a second, narrower CAS token, and make
same-key/same-payload idempotent replay win before the stale-fence check. This
matches the single-learner threat model and makes accidental concurrent tutors
fail safely.

Once approved, the strict xfail in
`tests/integration/test_tutor_swap.py::test_public_mutations_expose_optimistic_session_revision`
should be replaced by a scenario test: two callers read the same pair of
tokens; the first records a valid mutation; the second receives the stable
session-revision conflict and creates no event or aggregate change. Separate
tests must cover `next`/`replan` dual-token behavior and idempotent retry
precedence.
