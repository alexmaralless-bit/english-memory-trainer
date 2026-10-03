# How this project is built with AI agents

English Memory Trainer is designed, implemented and reviewed almost entirely by AI agents, under one human who owns the product and who is also the learner. This page describes the process as it appears in the repository: the documents, the roles, the checks and one complete phase as a worked example. Every claim links to a file or a commit you can inspect.

## Knowledge zones

| Zone | Role | Rule |
|---|---|---|
| `wiki/` | **Canon**: the specs that describe what the product must be | Written only after the owner approves a concept |
| `wiki/roadmap.md` | The only place that says "where we are" | Statuses are kept by hand, and specs never copy them |
| `wiki/OPEN.md` | The only register of unresolved questions | Each open question names the contract that closes it |
| `staging/` | **Not canon.** Provenance: concepts, journals, reviews, handoff prompts, demos | Journals are append-only, and nothing may cite staging as a norm |
| `docs/` | Original brief, build prompt, agreed design direction | The brief and build prompt are frozen; the design direction wins on conflict |

The wiki has its own constitution, [`wiki/README.md`](../wiki/README.md). Its main rules:

- **One product target per spec.** A spec describes the final state with no beta/MVP phase tags [PD-2026-07-22]. Order and status live only in the roadmap, and priority governs order, never scope. This rule is machine-checked: [`tests/architecture/test_spec_invariants.py`](../tests/architecture/test_spec_invariants.py) fails if a phase tag appears in normative wiki or curriculum text.
- **One module = one spec.** Each `wiki/modules/<name>.md` follows a template, so the whole truth about a module reads top to bottom in one file.
- **Glossary first.** A term is defined once in [`wiki/glossary.md`](../wiki/glossary.md) and used by name everywhere else.
- **No code facts from memory.** A spec states facts about the code only by reference (`file.py::symbol`).
- **No hedge words in MUST zones.** "TODO" or "decide later" is not allowed: a rule is either written or registered as an OPEN.

Most other constitution rules are kept by hand on purpose. Heavier machinery, such as a norm registry, pre-commit wiki gates and an executable roadmap, was considered and deferred, and the constitution records the trigger for revisiting each one. Machine checks live where the rules touch code and data: an architecture-boundary test ([`tests/architecture/test_boundaries.py`](../tests/architecture/test_boundaries.py)), `trainer curriculum validate`, `tools/check_authoring.py`, and `trainer skills validate` for drift between the canonical skills and their provider copies.

## Decisions belong to the human

- **Concept → "ок" → canon.** Every non-trivial change starts as a concept in `staging/concepts/`. Canon is written only after the owner explicitly says "ок".
- **Product decisions** are made only by the owner and marked `[PD-YYYY-MM-DD]` in the spec and the journal. An agent that finds a fork asks, or registers an OPEN. It never resolves the fork itself. A PD can reverse earlier canon, and the reversal is written down: `docs/design-direction.md` §1 records how [PD-2026-09-23] reversed "the agent never grades itself".
- **The OPEN registry** holds every unresolved question with its trigger and owning contract. Live use keeps feeding it: OPEN-40 to OPEN-43 came from the first live placement and lesson on 2026-09-23.

## Roles

| Role | Who | Does |
|---|---|---|
| Owner, learner | The human | Decides product forks, approves concepts, runs live lessons |
| Architect, acceptor | Claude (main session) | Maps the code, writes concepts and plans, splits work into waves, accepts or rejects deliveries, writes the journal |
| Implementers | Claude subagents (the larger model for hard work, a smaller one for routine work) and Codex for some deliveries | Build one wave item each, within the files they are assigned |
| Independent reviewers | Codex and fresh Claude contexts | Red-team contracts and deliveries. The roadmap counts 14 red-team runs in the contract phase ([`staging/reviews/`](../staging/reviews/)) |

The key rule is that **an author never accepts their own work**. Acceptance means the owner reruns the checks independently: the **full** `pytest` suite in the project venv (never a subset scoped to the change), `ruff`, `mypy --strict`, `trainer skills validate`, `trainer adapters compare`, `trainer scoring replay` and `trainer memory check`. One example is [`staging/reviews/2026-07-22-phase2-completion-verdict.md`](../staging/reviews/2026-07-22-phase2-completion-verdict.md), an independent PASS that reproduced the gates with its own run.

## Safety nets

- **Determinism.** The same events, timestamps and pinned policy versions always produce the same learner state. `trainer scoring replay` recomputes every score and fails with `REPLAY_DIVERGED` on any difference.
- **Golden replay.** [`tests/scoring/test_golden_replay.py`](../tests/scoring/test_golden_replay.py) replays a committed event log and checks that the scores do not change. This is what allowed Phase 4 to delete a whole protocol safely.
- **Versioned policies.** A behaviour change ships as a new policy version (`obligations@4`, `evidence@2`). Old sessions keep their pinned versions, and replay stays reproducible.
- **Waves with disjoint file ownership.** Parallel implementers never edit the same files, and CLI registration has a single owner in its wave.
- **Live lessons as acceptance.** A phase is finished only when a real lesson runs through it. Findings from that lesson go into the journal or `OPEN.md`.

## Worked example: Phase 4, "brief → report"

**Trigger.** The first live lesson on 2026-09-23 ran on a step-by-step protocol and took about 25 engine calls for 4 tasks. It needed compare-and-set (CAS) tokens at every step. A format slip silently made a free answer stop counting, and the plan could not adapt to "I already know this". The owner asked for the engine to *propose and record* while the tutor *teaches and grades*. See the journal: [`staging/journal/2026-09-23-brief-report.md`](../staging/journal/2026-09-23-brief-report.md).

**Decisions.** The owner made seven product decisions, PD-A to PD-G [PD-2026-09-23]: the protocol is one brief and one report; a lost chat is recovered through `resume` with no local draft; the tutor decides correctness; the verdict scale is 1.0 / 0.5 / 0; automaticity is measured by accuracy only (no latency); tutor verdicts have no trust cap and are audited after the fact; and the brief's requirements are warnings only.

**Concept.** [`staging/concepts/2026-09-23-lesson-brief-report-concept.md`](../staging/concepts/2026-09-23-lesson-brief-report-concept.md) sets out the key principle: *keep the event contract and change only who produces the events*. All consumers (scoring, scheduler, control, audit, memory) keep reading the same events, so old logs replay unchanged. The concept also defines the brief and report schemas, the atomic write path, the new policies, the list of deletions, and the waves with their file ownership.

**Waves** (roadmap section "Фаза 4" in [`wiki/roadmap.md`](../wiki/roadmap.md)):

| Wave | Content | Commit |
|---|---|---|
| W0 | Concept + journal. Owner: "ок, канон можно писать" | `13819b5` |
| W1 | Four parallel implementers on disjoint files: evidence report builders + `evidence@2`; the `tutor_verdict` scoring branch + golden replay; the lexicon builder; `obligations@4` + `lessons@2` | `cecc823` |
| W2 | Core, one implementer: `lessons/brief.py` and `lessons/report.py` (`check_report`, atomic `commit_report`) | `c4f3cdc` |
| W3/W4 | CLI (`session check-report`, `session report`) and removal of the step-by-step protocol (about 5.8k lines of `src/` removed); skills rewritten for the new protocol; canon updated across 7 module specs, 2 flows, glossary, design direction, `CLAUDE.md`/`AGENTS.md` | `e7dc693` |
| W5 | Acceptance: full suite, lint, strict typing, skills and adapter checks, replay of the owner's real database unchanged. Gaps found during acceptance were fixed in their own commits | `2006174`, `ac1fef6` |

**Acceptance by a live lesson** (2026-09-24). A real lesson on possessive pronouns with 8 items took **3 engine calls** (`start`, `check-report`, `report`), and the report was accepted on the first check. The lesson surfaced one issue: the compliance check expected a separate skill self-report. The fix was to count the lesson report itself as that self-report, which closed the phase in `ac1fef6`. Work that falls outside the phase (frame content fixes, placement OPENs) went to the journal and the roadmap instead of expanding the phase.

## What this process is not

It does not add CI: the checks run locally and are listed in `CLAUDE.md`. It does not let agents keep memory of their own: an agent's context is disposable, and continuity lives in the wiki, the journal and the engine's event log. It does not give agents product authority: every fork above was decided by the human.
