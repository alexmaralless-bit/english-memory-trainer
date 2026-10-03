# Case study: from a chatty step-by-step API to a brief/report protocol for an AI tutor

**TL;DR.** English Memory Trainer pairs an AI tutor (Claude Code, Codex) with a deterministic Python engine that stores evidence, schedules reviews and computes levels. The first live lesson showed that the engine was micromanaging the tutor: about 25 engine calls for a 4-item lesson, a compare-and-set token on every step, and three failure modes that lost or distorted data. I redesigned the tutor-engine boundary as **brief → lesson in chat → validated report**. On the next live lesson, 8 items took **3 engine calls**, and the report was accepted on the first check. Replay of the existing data stayed byte-identical. The CLI went from 67 to 50 commands, `src/` shrank by about 2.1k lines net (about 5.8k removed in the deletion wave), and all 948 tests pass. Concept to close took about 14 hours (2026-09-23 → 2026-09-24).

## Context

A local-first learning engine ([README](../README.md)): the LLM tutor teaches in chat, the engine is the memory. State is an append-only event log in SQLite, and every score must be reproducible from it (`trainer scoring replay`).

## Problem

The tutor operated the engine step by step (`session next` → `exercise rendered` → `attempt record` → …). The first real lesson (2026-09-23) showed ([journal](../staging/journal/2026-09-23-brief-report.md)):

- **Chattiness:** ~25 engine calls for 4 items, a session-revision (CAS) token on every mutating call.
- **A rigid plan:** "I already know this" still got the introduction and recognition steps.
- **Silent, irreversible data loss:** one malformed field (`rubric_criterion_ref`) made a free-text answer non-contributing, with no way to undo it.
- **A false error:** `session start` with explicit `--profile/--topic` failed with "stale proposal".
- **A wrong grade:** a correct answer was rejected for a missing final period.

## Diagnosis

Not five bugs but one design choice: the engine owned the lesson flow *and* the grading, so the component that actually understands language had to ask permission at every step. Every round trip was another chance for a format slip, a stale token or a mechanical grading mistake. The fix had to keep what the engine does well (deterministic aggregation, scheduling, levels, an auditable log) and hand the lesson back to the tutor.

## Decision

**Principle: keep the event contract and change only who produces the events.** Scoring, the scheduler, lesson control, audit and the memory projection all read the same event types (`attempt.recorded`, `evidence.added`, `review.outcome`, `evidence.error_observed`, …). A single validated report becomes their only producer, so consumers stay untouched and old logs replay unchanged ([concept](../staging/concepts/2026-09-23-lesson-brief-report-concept.md)).

The new protocol:

1. **Brief** (`session start`, [`lessons/brief.py`](../src/english_trainer/lessons/brief.py)): topic facts, due reviews, recent errors, an advisory plan and a `report_contract`.
2. **Lesson in chat**, with zero engine calls.
3. **Check** (`session check-report`): a dry run returning accepted/rejected per item with a stable reason code (`learner_form_not_in_answer`, `review_mismatch`, …) and its would-be effect.
4. **Report** (`session report`, [`lessons/report.py`](../src/english_trainer/lessons/report.py)): one atomic transaction writes evidence, review outcomes and lexicon and finishes the session; any rejected item means nothing is written.

I made seven explicit product decisions (recorded as `[PD-2026-09-23]`). The main ones:

- **The tutor decides correctness.** The engine never re-grades; it stores prompt, verbatim answer, verdict and error cause, and derives text spans itself.
- **Verdict scale** correct 1.0 / partial 0.5 / incorrect 0. A partial answer confirms a due review.
- **No trust cap on the tutor.** Verdicts are audited afterwards against the stored answers.
- **Brief requirements are warnings, not rejections**, and a lost chat is recovered with `session resume` rather than a local draft.

## Execution

Waves with disjoint file ownership, so parallel streams never touched the same files:

- **W0:** the concept and the decisions, approved before any code changed.
- **W1:** evidence builders and `evidence@2`, a `tutor_verdict` scoring branch, compliance obligations `obligations@4`.
- **W2:** the core, `build_brief`, `check_report` and `commit_report`.
- **W3/W4:** new CLI commands; 19 step-by-step commands and their modules removed; skills and specs rewritten.
- **W5:** acceptance.

Safety nets:

- **Golden replay.** [`tests/scoring/test_golden_replay.py`](../tests/scoring/test_golden_replay.py) replays a log from the retired protocol; the replay hash of the real database was identical at W1 and at final acceptance.
- **Versioned policies.** Old sessions keep their pinned versions; old event types stay readable.
- **Dry run + atomic commit**, covered end to end by [`tests/integration/test_report_flow.py`](../tests/integration/test_report_flow.py) (rejected reports, cached retries).
- **Live acceptance.** The phase closed only after a real lesson; it surfaced one gap (a compliance check expected a separate self-report), fixed by counting the report itself.

## Results

| | Before | After |
|---|---|---|
| Engine calls per lesson | ~25 for 4 items | 3 for 8 items (`start`, `check-report`, `report`) |
| Concurrency tokens | CAS token on every step | none. One idempotency key on the report |
| Malformed input | silently and irreversibly non-contributing | rejected at the dry-run check with a reason code, nothing written |
| Grading | mechanical key match (a missing period failed a correct answer) | tutor verdict, stored verbatim and auditable |
| CLI surface | 67 commands | 50 commands |
| `src/` size | 28,729 lines | 26,659 lines (−2,070 net, −5.8k in the deletion wave) |
| Tests | 936 passing | 948 passing |
| Replay of existing data | — | byte-identical |

On the live lesson, the report passed the check on the first attempt, and every audit obligation was satisfied.

## What transfers to other projects

- **Design agent-facing APIs around the agent's unit of work, not the engine's internals.** One brief in, one report out beats a step-by-step state machine: fewer tokens, less latency, fewer failure points.
- **Validate before you commit, and make the commit all-or-nothing.** Per-item reason codes let the agent fix its own output; atomicity rules out half-written state.
- **Let the LLM judge and keep the engine deterministic.** The model makes judgment calls; the system of record stores them verbatim, aggregates reproducibly and keeps them auditable.
- **Redesign safely behind a stable event contract.** When consumers read events, you can replace the producer wholesale, and a golden replay test shows you broke nothing.
