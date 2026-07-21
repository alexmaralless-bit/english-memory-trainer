# Review: forbidden post-beta/post-MVP phase markers in specifications

> Date: 2026-07-22
> Scope: canonical specifications under `wiki/`, with `curriculum/` checked as the executable boundary
> Mode: read-only review; no canon, curriculum, source, or test files changed
> Verdict: **FAIL**

## Executive summary

No literal `post-beta`, `psot-beta`, or their underscore/space variants exist in `wiki/` or `curriculum/`.
The repository uses the equivalent term `post-mvp` instead. It is not an isolated typo:

- `wiki/` contains **40** `post-mvp` occurrences on **39** lines, including **33** bracketed
  `[post-mvp]` tags;
- `curriculum/` contains **2** occurrences on **2** lines, including the active
  `phase: "[post-mvp]"` field on the TOEFL track;
- of the 39 wiki lines, 14 establish or repeat the phase-tag convention, 17 carry active feature
  deferrals, and 8 are historical or state that an older deferral was removed.

The root cause is `wiki/README.md` Principle 4: it explicitly requires target specifications to mark
elements as `[mvp]` or `[post-mvp]`. Therefore deleting individual tags would only treat symptoms.
The governance rule, module template, copied spec headers, active deferrals, and executable curriculum
data must be made consistent with the product decision that these phase tags do not belong in the
specifications.

## Method and reproduction

The review searched case-insensitively for literal and misspelled variants in all Markdown and YAML files:

```powershell
rg -n -i "post[-_ ]?(beta|mvp)|psot[-_ ]?(beta|mvp)" wiki curriculum \
  -g "*.md" -g "*.yaml" -g "*.yml"
```

Count reproduction:

```powershell
@'
from pathlib import Path
import re

patterns = {
    "literal_post_beta": re.compile(r"post[-_ ]?beta", re.I),
    "literal_psot_beta": re.compile(r"psot[-_ ]?beta", re.I),
    "post_mvp": re.compile(r"post[-_ ]?mvp", re.I),
    "tag_post_mvp": re.compile(r"\[post[-_ ]?mvp\]", re.I),
}
for root in (Path("wiki"), Path("curriculum")):
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".yaml", ".yml"}
    ]
    print(root)
    for name, pattern in patterns.items():
        occurrences = []
        for path in files:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                occurrences.extend([(str(path), line_number)] * len(pattern.findall(line)))
        print(name, len(occurrences), "occurrences", len(set(occurrences)), "lines")
'@ | .\.venv\Scripts\python.exe -
```

Observed output:

```text
wiki
literal_post_beta 0 occurrences 0 lines
literal_psot_beta 0 occurrences 0 lines
post_mvp 40 occurrences 39 lines
tag_post_mvp 33 occurrences 33 lines
curriculum
literal_post_beta 0 occurrences 0 lines
literal_psot_beta 0 occurrences 0 lines
post_mvp 2 occurrences 2 lines
tag_post_mvp 1 occurrences 1 lines
```

## Findings

### PM-1 — MAJOR: wiki governance requires the forbidden markers

**Evidence**

- `wiki/README.md:51` says that target specifications mark elements with `[mvp]` / `[post-mvp]`.
- `wiki/modules/_TEMPLATE.md:8,47` repeats that rule in the authoring template.
- The same boilerplate is copied into `wiki/platform/foundation.md:8` and the headers of
  `audit.md`, `adapters.md`, `gates.md`, `curriculum.md`, `evidence.md`, `cli.md`,
  `learning-model.md`, `lessons.md`, `learner.md`, and `control.md`.

**Why this is the root defect**

Authors followed the canonical authoring rule. A cleanup limited to feature lines would regress as soon
as a new spec is created from `_TEMPLATE.md`. It also conflicts with the same constitution's separation
of concerns: target behavior belongs in specs, while current implementation status belongs only in
`wiki/roadmap.md`.

**Required correction**

Record the owner decision in canon, then change Principle 4 and `_TEMPLATE.md` so that specs describe
one product target without beta/MVP phase labels. Remove copied header boilerplate. Current delivery
status must remain in `roadmap.md`; unresolved product choices must remain in `OPEN.md`.

### PM-2 — MAJOR: the active TOEFL track still carries the removed phase

**Evidence**

- `curriculum/tracks.yaml:36-39` defines `toefl-reading-writing` with
  `phase: "[post-mvp]"`.
- `curriculum/README.md:8` says the TOEFL track has `phase: post-mvp`.
- Canon says the opposite: `wiki/modules/curriculum.md:71` says the tag was removed and the track is in
  the product without deferral; `wiki/roadmap.md:16,108` repeats that no curriculum content remains
  post-MVP.

**Runtime relevance**

`src/english_trainer/curriculum/loader.py::load_program` loads whole track dictionaries, and
`snapshot_payload` includes them unchanged in the immutable curriculum policy. The validator currently
ignores `phase`, so the field does not suppress the track, but it still changes the active curriculum
snapshot and its content hash. This is executable data drift, not a documentation-only typo.

**Required correction**

Remove the field from `tracks.yaml` and the stale README claim. Add a curriculum validation invariant
that rejects phase fields/markers so a stale deferral cannot enter a future activated snapshot.

### PM-3 — MAJOR: active target specs still defer product behavior by phase tag

These are current behavioral statements, not history:

| Owner | Location | Deferred behavior |
|---|---:|---|
| glossary | `wiki/glossary.md:55` | untrusted capture of learner turns |
| foundation | `wiki/platform/foundation.md:65` | atomic compound command envelope |
| continuation flow | `wiki/flows/continuation.md:14,88` | session lease |
| evidence | `wiki/modules/evidence.md:62` | untrusted capture of learner turns |
| learning model | `wiki/product/learning-model.md:34` | untrusted capture of learner turns |
| learning model | `wiki/product/learning-model.md:106` | “full placement from the brief” |
| learning model | `wiki/product/learning-model.md:110` | FSRS implementation |
| memory | `wiki/modules/memory.md:31` | Obsidian convenience adapter |
| scheduler | `wiki/modules/scheduler.md:30,63` | FSRS implementation |
| control | `wiki/modules/control.md:125,130` | calibration API and events |
| control | `wiki/modules/control.md:398` | complete calendar availability model |
| OPEN registry | `wiki/OPEN.md:43` | complete calendar availability model |
| resolved decisions | `wiki/OPEN.md:82,92` | untrusted capture and Obsidian adapter |

**Why this is not solved by deleting the token**

Each row needs one of three semantic outcomes:

1. If it is part of the product target, specify it normally without a phase tag; roadmap status says
   whether it is implemented.
2. If the product decision is unresolved, keep one honest OPEN item with an owner and decision boundary,
   without pre-deciding a beta phase.
3. If it is merely a possible implementation (for example FSRS or an Obsidian convenience adapter),
   remove it as a normative promise or retain it as an unphased `MAY` where appropriate.

Otherwise different implementers can still disagree on whether the behavior is required, even after a
mechanical marker cleanup.

### PM-4 — MAJOR: phase markers hide underspecified target behavior

Two lines violate the wiki rule against evasive placeholders independently of the phase-name problem:

- `wiki/platform/foundation.md:65` promises an atomic compound envelope “if needed” but defines no
  triggering condition, envelope, or owner.
- `wiki/product/learning-model.md:106` defers “full placement from the brief” without defining which
  concrete behavior differs from the accepted placement contract.

The spec cannot remain target-state while referring to an unspecified future version. These require an
explicit accept/reject decision or a complete owner contract; simply replacing `[post-mvp]` with another
label would preserve the ambiguity.

### PM-5 — MINOR: historical text will keep string-only checks noisy

Eight wiki lines use `post-mvp` historically or explicitly say an old deferral was removed:

- `wiki/roadmap.md:16,107-109,132`;
- `wiki/modules/curriculum.md:71,193,195`.

They do not defer current behavior. If the desired invariant is “no phase markers in normative text,” a
checker may exclude roadmap history and spec change logs. If the desired invariant is “the token must not
exist anywhere in canon,” rewrite these lines as “previously deferred” / “deferral removed” without
preserving the obsolete label.

### PM-6 — MAJOR: no automated invariant prevents recurrence

There is currently no wiki/curriculum validation rule rejecting forbidden phase markers. The stale TOEFL
field passed validation and entered the snapshot boundary.

**Required correction**

After canon is corrected, add two checks:

1. curriculum validator: reject `phase` on levels/tracks/modules/topics and reject phase-marker strings;
2. architecture/spec check: reject beta/MVP phase tags in normative wiki areas, with an explicit decision
   whether roadmap history is exempt.

The check must cover spelling variants (`post-beta`, `post_beta`, `post beta`, `post-mvp`, `post_mvp`,
`post mvp`, and the observed `psot-*` typo family) case-insensitively.

## Complete classification

| Class | Wiki lines | Meaning |
|---|---:|---|
| Governance/header/template | 14 | the convention itself and copied authoring boilerplate |
| Active behavioral deferral | 17 | current target/API/OPEN statements listed in PM-3 |
| Historical/removal record | 8 | non-normative history listed in PM-5 |
| **Total** | **39** | 40 occurrences because one line contains the term twice |

Outside wiki, the two curriculum lines are both active drift: `tracks.yaml:39` and
`curriculum/README.md:8`.

## Recommended correction order

1. Confirm the invariant in one sentence: target specs contain no beta/MVP phase tags; implementation
   status lives only in roadmap.
2. Fix `wiki/README.md` and `_TEMPLATE.md` first so cleanup cannot regress by convention.
3. Remove the TOEFL `phase` field and stale curriculum README text; add the curriculum validator check.
4. Resolve PM-3 owner by owner, preserving behavior rather than mechanically deleting words.
5. Decide whether history is exempt; then add the zero-regression spec check.
6. Run curriculum validation, all tests, Ruff, formatting, and mypy after the actual fix pass.

## Files changed by this review

- Added only this report: `staging/reviews/2026-07-22-post-mvp-spec-review.md`.
- Existing dirty-tree source and test changes were not modified.
- `wiki/`, `curriculum/`, `src/`, `tests/`, `agent-skills/`, and root `Irregular Verbs.md` were not edited.
