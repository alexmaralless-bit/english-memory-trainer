# English Memory Trainer — Operating Runbook

One page for any AI agent (Claude Code, Codex) or developer to operate this app correctly on first read. This complements — does not duplicate — `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex), which own the invariant rules and source-of-truth ordering in full.

## 0. If you arrived from a link

This repository is a work sample for one specific claim: **it was built by AI
agents under a spec-first process, and the commit history says so.**

- 194 commits over four days (19–22 July 2026); **158 of them carry a
  `Co-Authored-By:` trailer** naming the agent that wrote the code —
  Claude Opus 4.8, Claude Fable 5 or Codex. Check with
  `git log --format=%B | grep -c Co-Authored-By`.
- The specs came first and own the code. Every module spec in `wiki/modules/`
  declares the code it owns, e.g. `**Bounded context**: src/english_trainer/scheduler/`,
  and is marked as *target* state rather than after-the-fact documentation.
  Requirements are written as `MUST` with traceability tags back to the review
  that produced them.
- Agents are driven by committed procedures, not by chat: ten skills in
  `agent-skills/`, deployed as read-only copies into `.claude/skills/` and
  `.agents/skills/`, with the invariants owned by `CLAUDE.md` and `AGENTS.md`.
- Working memory is separated from canon: `wiki/` is canon, `staging/` holds
  the session journal, handoffs and reviews — including an independent PASS
  verdict on Phase 2 and a task delegated to one agent and reviewed by another.

What is *not* here: a mechanical spec-sync gate. In this project the discipline
is visible but not enforced by a hook; the enforcing version lives in a closed
project. That gap is stated in `wiki/README.md` under
"Что сознательно НЕ переняли".

Licensing: code under MIT, `curriculum/` data under CC BY-SA 4.0 — see
`LICENSE`, `curriculum/LICENSE` and `ATTRIBUTIONS.md`.

## 1. What it is

A local-first, deterministic Python CLI for learning American English with interchangeable AI tutors (Claude Code, Codex, or others). The `trainer` engine is the **sole authority** over learner state — SQLite + an append-only JSONL event log, projected read-only into an Obsidian vault. Chat context is never memory: any agent can resume a session or a whole learner history from engine state alone. Scope is text-only — Reading, Writing, grammar, vocabulary. Listening and Speaking are intentionally, permanently out of scope `[PD-2026-07-22]`. Status: **Phase 2 (vertical slice) complete** — 12 modules implemented, 55 CLI commands published, full test suite green (see `wiki/roadmap.md` for the current line).

## 2. Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e . --group dev      # or: uv sync

# Deploy the 10 canonical skills into .claude/skills/ (Claude Code) and
# .agents/skills/ (Codex) so each provider auto-discovers them. These target
# directories are committed deterministic COPIES of agent-skills/ canon —
# never hand-edit them; only `trainer skills sync` writes them.
trainer skills sync --idempotency-key <key> --format json
trainer skills validate --format json     # confirm no drift after sync

# Sanity-check the local environment and state.
trainer doctor
```

Run `trainer doctor` first whenever diagnosing a broken local setup.

## 3. Skill catalog

All 10 skills live in `agent-skills/` (canon) and are synced as read-only copies. Each is a narrow operating procedure over a slice of the CLI — never a license to bypass it.

| Skill | Purpose | Main `trainer` commands |
|---|---|---|
| `run-english-session` | Run a full session start to finish: work the plan, record attempts, close it correctly. | `session start/peek/next/replan/finish/abandon/status`, `exercise rendered`, `attempt record/finalize`, `review close` |
| `run-placement-assessment` | First-contact calibration session: gather evidence across topics without assuming a starting level. | `session start/peek/next/finish`, `exercise rendered`, `attempt record/finalize`, `status` |
| `run-spaced-review` | A session focused on the due/overdue review backlog rather than new material. | `review due/close`, `session start/peek/next/finish`, `exercise rendered`, `attempt record/finalize` |
| `teach-english-topic` | Explain one grammar/lexicon topic mid-session from authored curriculum content, not improvisation. | `curriculum show/lexicon`, `session peek/next`, `exercise rendered`, `attempt record` |
| `coach-english-conversation` | Run a free-conversation step with no structured exercise or answer key. | `session peek/next/status`, `attempt record` |
| `correct-learner-output` | Give feedback on an already-recorded attempt; drive an open attempt to a score. | `attempt record/finalize`, `review close` |
| `assess-english-gate` | Run a gate-checkpoint step and honestly report the engine's result. | `session peek/next`, `exercise rendered`, `attempt record/finalize`, `status` |
| `finish-english-session` | Correctly finish or abandon the current session: clear the pending set first. | `session status/finish/abandon`, `attempt finalize`, `review close` |
| `audit-english-tutor` | Read-only: reconcile what happened in a session against what skills prescribed and the engine's deterministic state. | `session status`, `scoring replay`, `status`, `review due`, `memory check`, `adapters compare` |
| `maintain-english-curriculum` | Change authored `curriculum/` content and sync/validate skills, never touching learner state. | `curriculum validate/show/lexicon/activate`, `skills validate/sync` |

## 4. Run a session end-to-end

Every mutating command needs `--idempotency-key` under `--format json`; use a fresh key per logical call and a stable one only when intentionally retrying. Mutations against a live session additionally carry a coarse optimistic fence, `--expected-session-revision` (a Phase 2 addition); `session next`/`session replan` also carry `--expected-plan-version`. Both tokens come from the prior response (`session start`/`status`/`resume`/`peek`/`next`/`replan`).

### Bootstrap (once per environment)

```bash
trainer init --idempotency-key init-001 --format json

trainer curriculum validate --format json
trainer curriculum activate --version <curriculum-version-id> \
  --idempotency-key curr-act-001 --format json
```

### Start and drive a session

```bash
# Opens the session: pins active policies, composes the plan.
trainer session start --provider claude-code --format json \
  --idempotency-key sess-start-001
# -> session_id, plan_version, session_revision, pinned_versions, required_skills

# Look at the next step without consuming it (read-only).
trainer session peek --session <SESSION_ID> --format json

# Claim (delivers) the step: CAS mutation, bumps plan_version.
trainer session next --session <SESSION_ID> \
  --expected-plan-version <V> --expected-session-revision <R> \
  --idempotency-key sess-next-001 --format json

# Structured exercises only: persist the rendered snapshot BEFORE the learner sees it.
trainer exercise rendered --session <SESSION_ID> --step <STEP_ID> \
  --input exercise.json --expected-session-revision <R> \
  --idempotency-key ex-rendered-001 --format json

# Record the learner's attempt against the delivered step.
trainer attempt record --session <SESSION_ID> --step <STEP_ID> \
  --exercise-instance <EXERCISE_INSTANCE_ID> --input attempt.json \
  --expected-session-revision <R> --idempotency-key att-rec-001 --format json

# Open-ended answers only: run the pinned rubric pipeline to settle score/disposition.
trainer attempt finalize --attempt <ATTEMPT_ID> --session <SESSION_ID> \
  --expected-session-revision <R> --idempotency-key att-fin-001 --format json

# Close a due review target once its attempts are assessed; the engine computes the outcome.
trainer review close --review <REVIEW_ASSIGNMENT_ID> --session <SESSION_ID> \
  --expected-session-revision <R> --idempotency-key rev-close-001 --format json

# Plan exhausted or context changed: recompose the unpresented remainder.
trainer session replan --session <SESSION_ID> \
  --expected-plan-version <V> --expected-session-revision <R> \
  --idempotency-key sess-replan-001 --format json

# Finish requires an empty pending set (all attempts finalized, all review targets closed).
trainer session finish --session <SESSION_ID> --expected-session-revision <R> \
  --idempotency-key sess-finish-001 --format json

# Otherwise, to stop without a result (never leave a session dangling):
trainer session abandon --session <SESSION_ID> --expected-session-revision <R> \
  --idempotency-key sess-abandon-001 --format json
```

### Resume (tutor swap / lost chat / cold start)

```bash
# One call returns full session state + tutor briefing + notes, and attaches
# the resuming provider (AGENT_ATTACHED) atomically with the resume.
trainer session resume --provider codex --session <SESSION_ID> \
  --idempotency-key sess-resume-001 --format json
```

### Placement (diagnostic, fixed-form)

```bash
trainer placement start --format json --idempotency-key plc-start-001
trainer placement answer --input section-answers.json \
  --idempotency-key plc-answer-001 --format json
trainer placement resume --idempotency-key plc-resume-001 --format json   # after an interruption
trainer placement submit --idempotency-key plc-submit-001 --format json  # terminal, idempotent
trainer placement abandon --idempotency-key plc-abandon-001 --format json     # STARTED/IN_PROGRESS only
trainer placement decline --idempotency-key plc-decline-001 --format json \
  --self-assessment '{"schema_version":1,"levels":{"grammar":"A2"}}'
```

## 5. Hard invariants

- Read learner state only through the CLI — never edit SQLite rows, the JSONL event log, scores, or generated `memory/` files directly.
- Every assessment needs stored evidence; merely mentioning a topic is not evidence. Never fabricate scores, and never for an uncovered modality (Listening/Speaking).
- Finish sessions only through `trainer session finish` (or `session abandon` to stop honestly); close review only through `review close`; settle open attempts only through `attempt finalize`.
- Change curriculum only through the `maintain-english-curriculum` workflow, then run `curriculum validate` (and `curriculum activate` once clean).
- Agent-facing commands emit exactly one valid JSON envelope on stdout with `--format json`; diagnostics go to stderr; exit codes come from a closed, stable set.
- Determinism is non-negotiable: the same events, timestamps, and pinned policy versions must always fold to the same learner state — `trainer scoring replay` reproduces it and fails loudly (`REPLAY_DIVERGED`) if it doesn't.

## 6. Verify / develop

```bash
pytest                                   # kernel determinism + lexicon invariants (no network)
ruff check .
ruff format --check src tests
mypy src                                 # strict; kernel is fully typed
```

Run `trainer doctor` first when diagnosing a local setup problem.

## 7. Where deeper docs live

- `CLAUDE.md` (Claude Code) / `AGENTS.md` (Codex) — full invariant rules, source-of-truth ordering, commands.
- `wiki/` — accepted specs; `wiki/README.md` is the constitution (read before writing any spec).
- `wiki/roadmap.md` — the single source of "where we are now".
- `wiki/flows/session.md`, `continuation.md`, `placement.md` — the full end-to-end scenarios behind §4 above.
- `agent-skills/` — canonical skill definitions (synced, never hand-edited at the target paths).
