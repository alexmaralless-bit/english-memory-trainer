# P.3 phase 2 handoff report

> Date: 2026-07-21.
> Role: P.3 phase 2 executor.
> Canon rule: `wiki/` was not edited. Canon changes are submitted as patch
> proposals only.

## Produced artifacts

- `curriculum/policies/generation-v1.yaml` — proposed payload for future
  `generation@1` registry policy.
- `curriculum/policies/README.md` — short catalog purpose and constraints.
- `staging/handoff/2026-07-21-P3-canon-patches.md` — exact old-to-new canon
  patch proposals for owner verification.
- `staging/handoff/2026-07-21-P3-phase2-report.md` — this handoff.
- `staging/handoff/2026-07-21-P2-report.md` — append-only postscript only,
  noting that the old two-tier grammar snapshot is superseded by current
  `big-five | core | tail` canon/data.

No `wiki/`, `src/`, `tests/`, `agent-skills/`, topic, lexicon, or root
`Irregular Verbs.md` content was edited.

## Canon patch proposals

| Wiki file | Proposed edits | PD decisions implemented |
|---|---:|---|
| `wiki/modules/curriculum.md` | 6 | PD-3 C, PD-4 A, PD-5 D, PD-6 A |
| `wiki/product/lexical-system.md` | 4 | PD-3 C, PD-4 A, PD-5 D, PD-7 A |
| `wiki/modules/lessons.md` | 4 | PD-1 A, PD-2 A |
| `wiki/modules/control.md` | 5 | PD-1 A, PD-2 A, PD-3 C, PD-4 A, PD-5 D, PD-6 A |
| `wiki/modules/evidence.md` | 4 | PD-1 A, PD-2 A |
| `wiki/modules/scoring.md` | 3 | PD-1 A, PD-2 A, PD-3 C, PD-4 A |
| `wiki/glossary.md` | 4 | PD-1 A, PD-2 A, PD-3 C, PD-4 A, PD-5 D |
| `wiki/OPEN.md` | 4 | PD-1 A, PD-2 A, PD-3 C, PD-4 A, PD-5 D, PD-6 A, PD-7 A |
| `wiki/roadmap.md` | 4 | PD-1 A, PD-2 A, PD-3 C, PD-4 A, PD-5 D, PD-6 A, PD-7 A |

`wiki/platform/foundation.md` has no proposed patch. PD-6 is satisfied through
domain event names carried in the existing kernel envelopes/correction
mechanism; no kernel business-rule example is needed.

## `generation-v1.yaml` coverage

The policy payload covers the accepted concept sections:

- A. Generation policy:
  - `policy_id`, `schema_version`, canonical encoding, no-float rule;
  - supported dimensions and allowed step types;
  - exercise schemas per dimension and special handling for word formation /
    lexeme form slots;
  - typical-error distractor rules with `distractor_error_ref`;
  - active safety predicates for delivery, render, bank reuse, and placement;
  - `EXERCISE_RENDERED` minimum payload metadata from PD-1 A;
  - own-text/no-excerpt constraints.
- B. Bank lifecycle:
  - statuses `generated | accepted | rejected | retired`;
  - admission only after assessed attempt or maintainer fast-path from PD-2 A;
  - acceptance, rejection, retirement reasons;
  - canonical dedup key;
  - revalidation before reuse.
- C. Living layer:
  - candidate fields and candidate-not-schedulable boundary;
  - `maintain-english-curriculum` acceptance workflow;
  - hybrid currency aging from PD-3 C;
  - `dated` recognition-only default with explicit historical/register
    recognition override from PD-4 A;
  - no third-party excerpts.
- D. Unlinked lexicon coverage:
  - hybrid lexicon-first micro lane + auto-link candidates from PD-5 D;
  - advisory cap: one lexicon-first growth item per balanced session unless
    maintenance or explicit vocabulary practice.

Advisory integer values included:

- `frequency_tier_weights.big-five.weight = 10000`
- `frequency_tier_weights.core.weight = 8500`
- `frequency_tier_weights.tail.weight = 3500`
- lexicon-first balanced session cap = `1`
- currency review intervals: `30`, `90`, `180`, `365` days
- prompt-fault retirement calibration = `3`
- maintainer-rejection retirement calibration = `2`

All booleans are represented as strings in the policy payload. The YAML
self-check rejects parsed `float` and parsed `bool` values.

## P2 report postscript

The appended postscript does not rewrite the original P.2 report. It states:

- original P.2 tier notes were a two-tier snapshot;
- current canon/data use `big-five | core | tail`;
- current A1-A2 Grammar Engine distribution is:
  - `big-five`: 17
  - `core`: 23
  - `tail`: 5

This matches the current topic files and the P.3 concept input notes.

## New decisions needed

No new product-behavior fork was found.

One implementation naming point is intentionally left as a proposal, not a
silent decision: the canon patch proposes the future CLI spelling
`trainer exercise rendered` for recording `EXERCISE_RENDERED`. The owner may
rename that command during canon application without changing the accepted P.3
mechanics.

## Self-check

YAML parse and policy scalar check:

```text
.\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; data=yaml.safe_load(Path('curriculum/policies/generation-v1.yaml').read_text(encoding='utf-8')); bad=[]

def walk(x,p='root'):
    if isinstance(x,float) or isinstance(x,bool): bad.append((p,type(x).__name__,x))
    elif isinstance(x,dict):
        for k,v in x.items(): walk(v,f'{p}.{k}')
    elif isinstance(x,list):
        for i,v in enumerate(x): walk(v,f'{p}[{i}]')
walk(data)
assert data['policy_id']=='generation@1'
assert not bad, bad
print('yaml ok; policy_id='+data['policy_id']+'; no float/bool values')"

yaml ok; policy_id=generation@1; no float/bool values
```

Whitespace check:

```text
git diff --check -- curriculum\policies staging\handoff\2026-07-21-P2-report.md staging\handoff\2026-07-21-P3-canon-patches.md

warning: in the working copy of 'staging/handoff/2026-07-21-P2-report.md', LF will be replaced by CRLF the next time Git touches it
```

Exit code was `0`; the message is a Git line-ending warning, not a diff
whitespace error.

Full test suite:

```text
.\.venv\Scripts\python.exe -m pytest -q

........................................................................ [ 35%]
........................................................................ [ 71%]
..........................................................               [100%]
```

Pytest emitted only the existing sandbox cache warning:

```text
PytestCacheWarning: could not create cache path ... .pytest_cache ... [WinError 5] Отказано в доступе
```

Ruff:

```text
.\.venv\Scripts\ruff.exe check .
All checks passed!

.\.venv\Scripts\ruff.exe format --check src tests
53 files already formatted
```

Mypy:

```text
.\.venv\Scripts\mypy.exe src
Success: no issues found in 29 source files
```

## Working tree note

Expected P.3 phase 2 changes:

- `curriculum/policies/README.md`
- `curriculum/policies/generation-v1.yaml`
- `staging/handoff/2026-07-21-P2-report.md`
- `staging/handoff/2026-07-21-P3-canon-patches.md`
- `staging/handoff/2026-07-21-P3-phase2-report.md`

Pre-existing untracked file left untouched:

- `Irregular Verbs.md`
