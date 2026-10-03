# Drill block authoring and reporting rules

Source of truth for the drill shapes: `curriculum/policies/generation-v3.yaml`
(`drill_block`, `reconstruction`, `timed_writing` sections); for the report:
`src/english_trainer/lessons/report.py` and evidence@2. This file restates
them as tutor-facing rules. The lesson runs in chat from the brief; nothing
is sent to the system until the one report at the end [PD-2026-09-23].

## Reading the brief

Each `drill_block` / `reconstruction` / `timed_writing` step of the brief's
advisory `plan.steps[]` carries a `material` object (the authored material
the round is built from). For a `drill_block` step:

- `mode`: `"blocked"` (first exposure of the pattern, no contrast) or
  `"interleaved"` (from the pattern's second exposure onward).
- `round_size` — items per round (learner preference, default 6).
- `rounds` — how many rounds this block runs (2–3).
- `primary_target` — `{target_ref, dimension, role: "target"}`, the one
  pattern this block drills.
- `contrast_targets[]` — 0, or 2–4 entries `{target_ref, dimension, role:
  "contrast"}`, present only when `mode` is `"interleaved"`.
- `frames[]` — the authored `chunk` frames of the primary target (`role:
  "target"`) and, when interleaved, of each contrast target (`role:
  "contrast"`). Each frame carries `frame_ref`, `title` (slots marked `___`),
  `meaning_ru`, `slot_hint_ru`, `examples[]`, optional `contrast`/`trap`, and
  `carries[]`.

`central_topic` carries the same frames and, for a drill, the
`reconstruction_text` (`id`, `title`, `text`, `keywords`, `target_spans`,
`cefr`, `carries`). If it is missing, read one with
`curriculum texts --topic <topic-id> [--domain work|everyday|academic]`
before the lesson starts. The plan is advice: if the learner already owns
the pattern, shorten round 1 and go interleaved sooner.

## The five item forms (generation@3 `drill_block.item_forms`)

Every item is one Russian- or English-cued production of a full sentence —
never a bare word, a slot fill, or a translation drill. Pick forms from
`learner.preferences.preferred_drill_forms` when the learner declared a
subset; otherwise any of the five is admissible, and a round should not use
only one form throughout.

| Form | Cue | What the learner produces |
|---|---|---|
| `ru_to_en_sentence` | a Russian line (meaning/situation) | one full English sentence (~8–12 words) built from scratch |
| `frame_recall` | the meaning/situation in Russian, naming no English words | the whole frame verbatim, slot filled — deleting only an article would drill the article, not the frame |
| `cue_to_sentence` | English keywords only | one full sentence supplying the grammar the keywords do not show |
| `transformation` | a full sentence in a competing pattern, plus a changed condition (e.g. a finished-time marker) | the same sentence rebuilt in the target pattern |
| `minimal_pair` | a context that fits one of two competing frames | a full sentence choosing the correct member (a/the/zero, Past Simple/Present Perfect, …) |

`transformation` and `minimal_pair` only make sense once a contrast exists —
use them in interleaved rounds, against a `contrast_targets[]` entry.

## Building a round

- **Round 1 is `blocked`**: every item targets the primary target; use
  `ru_to_en_sentence` and `frame_recall` off the primary target's frames.
- **A later round is `interleaved`** when the pattern has a contrast: mix in
  items whose target is one of the `contrast_targets[]`, drawn from those
  targets' frames; at least one contrast item per interleaved round.
- Never let a cue contain two or more consecutive words of the expected
  answer, or the frame's own `title` skeleton with its slot filled — that is
  a leaked answer, not a cue.
- Keep your own answer key in mind (contracted and full forms are variants of
  one answer); it never appears in chat before the learner answers.

## Pacing (learner feedback, 2026-09-22 — binding)

- One item per message: never list a round's items at once; show one, wait
  for the learner's answer, then show the next.
- No system calls between items or rounds. Every item, answer and verdict
  stays in the tutor's context (the ledger) until the report.
- Response time is not measured [PD-2026-09-23]: never estimate latency.

## Verdicts inside a round

pedagogy.md "Tutor verdict" applies per item. The round's `raw_answer` is the
learner's FIRST answer to the cue; a self-repair after the flag adds a hint
and caps the item at `partial`. The block's own outcome is computed by the
system from the items: accuracy = correct items / credited items against a
fixed threshold — `partial` counts as not correct for block accuracy, so do
not inflate it to pass a round.

## Reporting the drill

Each round is one block:

```json
"blocks": [
  {"block_id": "b1", "target_ref": "grammar.present-perfect.result", "mode": "blocked"},
  {"block_id": "b2", "target_ref": "grammar.present-perfect.result", "mode": "interleaved"}
],
"items": [
  {"item_id": "b1-1", "block_id": "b1", "target_ref": "grammar.present-perfect.result",
   "dimension": "controlled_production", "kind": "drill_item",
   "prompt": "Скажи: я уже отправил отчёт.", "raw_answer": "I've already sent the report.",
   "verdict": "correct", "hints": 0, "errors": []},
  {"item_id": "b2-3", "block_id": "b2", "target_ref": "grammar.past-simple.finished-time",
   "dimension": "controlled_production", "kind": "drill_item",
   "prompt": "Скажи: вчера я отправил отчёт.", "raw_answer": "Yesterday I have sent the report.",
   "verdict": "incorrect", "hints": 0,
   "errors": [{"learner_form": "have sent", "correction": "sent",
               "cause": "yesterday — законченное время, нужен Past Simple"}]}
]
```

- `block_id` unique; `target_ref` = the round's primary target; `mode`
  `blocked` or `interleaved`. An optional block `dimension` defaults to the
  items'; all items of a block share ONE dimension.
- A contrast item keeps its own contrast `target_ref`; it is credited within
  the block against the primary target.
- Only answered items; an unanswered cue is simply absent (not `incorrect`).
- A round delivered as a due review names the review: `"review_id"` on the
  block (or the same `review_id` on its items) — the review's target and
  dimension must equal the block's.
- `secondary_targets` are ignored inside a block (a warning).
- Reconstruction and timed writing are ordinary items outside `blocks`:
  reconstruction `controlled_production` (kind `production`, prompt = the
  keywords shown), timed writing `spontaneous_production` (prompt = the task
  and the announced limit). Their errors quote verbatim fragments of the
  learner's text; name the missed `target_spans` in the debrief.

## `feedback_mode: always_explain`

`learner.preferences.feedback_mode` defaults to `stage_dependent` (the
protocol in pedagogy.md "Feedback by stage": one-line rule, full "why"
deferred to the debrief). When it is `always_explain`, give the short cause
at the point of correction too — still only after the one self-repair turn,
still without turning the round into a lecture. This preference changes the
explanation protocol only; it never changes a verdict.
