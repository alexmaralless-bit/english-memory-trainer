# Placement end-to-end demo — 2026-07-22

## Result

The deterministic integration scenario passes without findings: **1 passed, 0 xfailed**. It exercises the
public functions used by the placement CLI against a migrated SQLite store, a registered curriculum snapshot,
and the real control, scheduler and scoring policies. No runtime code or test-only placement backdoor is used.

The scenario starts at fixed UTC time `2026-07-22T12:00:00+00:00` with random seed `20260722`. Running the
entire scenario twice in independent databases produces byte-identical `canonical_json` output.

## Activated diagnostic

The test registers and activates curriculum `placement-demo@1`. Its topic IDs explicitly include every target
of shipped form `placement-en-core@1`:

- `grammar.be.identity`
- `vocabulary.core.greeting`
- `reading.gist.short`
- `writing.sentence.simple`

The first placement pins these policy versions:

```yaml
assessments: assessments@1
control: control@1
curriculum: placement-demo@1
generation: generation@1
scheduler: scheduler@1
scoring: scoring@1
```

## First take: lifecycle and scoring ceiling

The engine starts placement `01KY4V4VG0Y1D8E3BVRJ63X6ZX` in `STARTED`. Before any answer, both an attempted
second start and an attempted submit fail with stable code `PLACEMENT_PRECONDITION`.

The learner answers all three `grammar.be.identity` items correctly:

```text
g-be-1 = am
g-be-2 = is
g-be-3 = are
```

Checkpoint changes the placement to `IN_PROGRESS` and points to `vocabulary`. One hour later, `resume` returns
the same placement, the saved `grammar` section, next section `vocabulary`, and deterministic resume boundary
`2026-07-24T12:00:00+00:00`.

The learner then answers `v-greeting-1` with `goodbye`. The objective check records this row as
`correct: false`, `contributing: false`, with fresh exposure weight `1`. It creates no vocabulary evidence and
does not create a negative score target.

Submit at `2026-07-22T13:00:00+00:00` produces:

- status `SCORED`;
- three evidence facts and three `CONFIRMED` outcomes, all for `grammar.be.identity`;
- each evidence fact has `origin: placement` and captured `applied_exposure_weight: "1"`;
- no evidence or outcome for the incorrect vocabulary answer.

Three confirmations would normally progress `NEW → LEARNING → ACTIVE → MASTERED`. The fold instead reports:

```yaml
grammar.be.identity:
  knowledge_state: ACTIVE
  mastery: {recognition: "14.400"}
  evidence_count: 3
  stability_days: "23.13323862018894875467682256"
  audit:
    - "placement-ceiling: 01KY4YJQ40VV0XAST7EEARMZKN"
```

Thus placement evidence raises the verified target to `ACTIVE` but never `MASTERED`. The audit identifies the
exact outcome event on which the ceiling applied.

The lifecycle event sequence is:

| Sequence | Event | Event ID |
|---:|---|---|
| 2 | `placement.started` | `01KY4V4VG02TQQT79C41FH9XD8` |
| 3 | `placement.checkpoint` | `01KY4V4VG0BP643NFW5GDPP5CM` |
| 4 | `placement.resumed` | `01KY4YJQ40QZ1T8FQAR8H6JF5K` |
| 5 | `placement.checkpoint` | `01KY4YJQ40JTHPFQJZQZH4D3S2` |
| 6 | `placement.submitted` | `01KY4YJQ40YJJS0J3JWYJR2EWY` |
| 13 | `placement.scored` | `01KY4YJQ40231TCXGJKC96GWYV` |

Calling submit again returns the stored result with `already: true` and leaves the event count unchanged.
Attempts to answer or abandon the scored placement both fail with `PLACEMENT_PRECONDITION`.

## Second take: exposure cannot become fresh evidence again

The second take is placement `01KY4YMHQ02X8SZQ6X2JAK4960`. It presents and correctly answers the same three
grammar items. Checkpoint event `01KY4YMHQ0ACSZF2JFAJM5C9QR` captures their stable exposure IDs. Scored event
`01KY4YMHQ0NWFA8NP4EG5AH06Q` captures the decision for every row:

```yaml
applied_exposure_weight: "0"
correct: true
contributing: false
```

The second submit reports `evidence_count: 0` and `outcome_count: 0`. No `evidence.added` event has the second
placement as correlation ID, and the complete scoring snapshot remains byte-identical to the snapshot after
the first take. Memorizing the fixed form therefore cannot add mastery.

## Replayable expiry

Placement `01KY4YPCA0W9W1QAQNY14FK3M5` checkpoints a reading answer at
`2026-07-22T13:02:00+00:00`. Recovery is attempted 48 hours and 61 seconds later. `resume` refuses with
`PLACEMENT_PRECONDITION`, terminalizes the aggregate as `EXPIRED`, and writes event
`01KYA3HNW84EDT8HXKRP90GJDF` at the derived boundary:

```yaml
last_activity_at: "2026-07-22T13:02:00+00:00"
boundary_at: "2026-07-24T13:02:00+00:00"
```

The event timestamp equals `boundary_at`; it is not the later recovery clock. Repeating resume and running the
sweeper mint no second expiry event.

The sweeper path is exercised independently with placement `01KYA3HNW8PCRSSYSCAX3ZFGMY`. Its first sweep
returns that ID and emits `01KYF8M8V8KSCEARQZ4P3MCTHW` at deterministic boundary
`2026-07-26T13:03:01+00:00`; its second sweep returns an empty list and changes no event count.

## Self-assessment

A scalar self-assessment `"A2"` is rejected with stable code `SELF_ASSESSMENT_INVALID` and produces no decline
event. The admitted partial object is:

```json
{"schema_version": 1, "levels": {"grammar": "A2", "reading": "B1"}}
```

It creates declined placement `01KYF8M8V8WASMTYDNBZ5DNHRE` with exactly:

```yaml
self_reported_levels: {grammar: A2, reading: B1}
```

`vocabulary` and `writing` remain absent/unknown; neither receives a default or a broadcast `A2`.

## MUST coverage

| Requirement | Status | Evidence |
|---|---|---|
| STARTED → IN_PROGRESS → resume → SCORED | Pass | Same first placement and ordered lifecycle events. |
| Illegal transitions | Pass | Second active start, submit from STARTED, answer/abandon after SCORED all use stable refusal code. |
| Idempotent terminal submit | Pass | Second result has `already: true`; event count is unchanged. |
| Placement ceiling | Pass | Three confirmations end at ACTIVE with `placement-ceiling` audit. |
| Incorrect answers do not punish | Pass | Fresh wrong vocabulary row is non-contributing and creates no score target. |
| Exposure capture/down-weight | Pass | Stable IDs in checkpoint; zero weights in scored event; no second-take evidence. |
| Resume expiry boundary | Pass | Event timestamp and payload equal last activity plus 48 hours. |
| Idempotent expiry sweep | Pass | First sweep expires; second sweep mints nothing. |
| Per-skill self-assessment | Pass | Partial object is exact; scalar has stable rejection; missing skills stay unknown. |
| Event/outbox consistency | Pass | Every placement lifecycle event ID is present in the outbox view. |
| Determinism | Pass | Two independent stores produce equal canonical bytes. |

## Findings

No 2.6 contract gap was found by this end-to-end scenario; no `xfail` is present.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_placement_flow.py --basetemp "<tmp>/pytest" -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_placement_flow.py --basetemp "<tmp>/pytest" -q
.\.venv\Scripts\python.exe -m ruff check tests/integration
.\.venv\Scripts\python.exe -m ruff format --check tests/integration
```

Expected placement result on both runs: `1 passed`.

## Scope audit

This delivery changes only `tests/integration/test_placement_flow.py` and this transcript under
`staging/demos/`. It does not modify `src`, CLI code, architecture tests, root `tests/conftest.py`, the existing
tutor-swap integration test, curriculum, wiki canon, or `Irregular Verbs.md`.
