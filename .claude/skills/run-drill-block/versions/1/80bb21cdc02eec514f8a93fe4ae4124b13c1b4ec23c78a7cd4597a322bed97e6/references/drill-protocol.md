# Drill block item-authoring rules

Source of truth for the shapes below: `curriculum/policies/generation-v3.yaml`
(`drill_block`, `reconstruction`, `timed_writing` sections) and control 4.3a /
4.6, evidence 4.6, lessons 5. This file restates them as tutor-facing
authoring rules; the engine still validates everything at `exercise rendered`
and `attempt record-block` — nothing here is trusted uncomputed.

## Reading the generation directive

`session peek` / `session next` widen a `drill_block` step's
`generation_directive` with:

- `mode`: `"blocked"` (first exposure of the pattern, round 0 only, no
  contrast) or `"interleaved"` (from the pattern's second exposure onward).
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

A `reconstruction` step's directive carries `text` (the full authored text
object: `id`, `title`, `text`, `keywords`, `target_spans`, `cefr`, `carries`)
or `text_id` alone — if the text itself is missing, resolve it with
`curriculum texts --topic <topic-id> [--domain work|everyday|academic]`.

A `timed_writing` step's directive carries `declared_limit_seconds` and
`expected_targets[]`.

## The five item forms (generation@3 `drill_block.item_forms`)

Every item is one Russian- or English-cued production of a full sentence —
never a bare word, a slot fill, or a translation drill. Pick forms from
`briefing.preferences.preferred_drill_forms` when the learner declared a
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

- **Round 0 is always `blocked`**: every item's `target_ref` is the primary
  target; no item is marked `contrast`; use `ru_to_en_sentence` and
  `frame_recall` off the primary target's `frames[]`.
- **A later round is `interleaved` only when the directive's `mode` is
  `"interleaved"`**: mix in items whose `target_ref` is one of the
  `contrast_targets[]`, marked `contrast: true`, drawn from those targets'
  frames. At least one item of an interleaved round must be a contrast item;
  a blocked round must carry none — the engine rejects either violation.
- Never let a `prompt` contain two or more consecutive words of any
  `answer_key` variant, or the frame's own `title` skeleton with its slot
  filled — that is a leaked answer, not a cue.

## Item and round schema (the `exercise rendered` snapshot)

```
{
  "form": "drill_block",
  "prompt": "<short instruction to the learner, e.g. the round's cue format>",
  "items": [
    {
      "index": 0,                       // 0-based, unique, spans the WHOLE block
      "prompt": "<the Russian or English cue — never the answer>",
      "answer_key": ["I've already sent the report.", "I have already sent the report."],
      "target_ref": "grammar.present-perfect.result",
      "contrast": false                 // true only for a contrast-target item
    }
    // ... exactly round_size items per round, rounds_min*round_size .. rounds_max*round_size total
  ],
  "rounds": [
    {"index": 0, "mode": "blocked", "item_indexes": [0, 1, 2, 3, 4, 5]},
    {"index": 1, "mode": "interleaved", "item_indexes": [6, 7, 8, 9, 10, 11]}
  ]
}
```

`answer_key` is always a list of acceptable variants — contracted and full
forms count as different variants of the same answer, never as two answers.
The block carries no block-level `answer_key`/`rubric_ref`: every item checks
against its own key.

A `reconstruction` snapshot instead carries the chosen text's `text_id`,
`text`, `keywords`, `target_spans`, `cefr`, `carries`, a `rubric_ref` (it is
assessed as a constrained short answer, the `controlled_production` rubric
profile), and, if you add a machine check, `machine_checks: [{"operation":
"required_literal_sequence_all", "parameters": {"authored_sequences": [...]}}]`
whose sequences must be a subset of `target_spans`. The `prompt` must not
contain the text body — it is shown once, on its own, then hidden.

A `timed_writing` snapshot carries `declared_limit_seconds` (the exact number
announced to the learner) and `expected_targets[]`; it is assessed as
spontaneous production.

## Recording the block

`attempt record-block --input FILE` where the file is:

```
{"items": [
  {"index": 0, "raw_answer": "I've already sent the report.", "latency_ms": 4200, "self_repaired": false},
  {"index": 1, "raw_answer": "We haven't tested it yet.", "self_repaired": true}
]}
```

- One record-block call per rendered block — never one `attempt record` per
  item.
- Omit an item entirely if the learner never answered it; do not submit an
  empty `raw_answer`. The engine leaves it out of the accuracy denominator,
  it is not scored as wrong.
- `latency_ms` is optional and trusted-reported: include it only when you can
  read it off real chat timestamps. Never estimate, default, or invent one —
  its only consumer is the `automaticity` axis, and a fabricated number would
  corrupt a measurement the learner cannot see or correct.
- `self_repaired: true` only when the learner produced the correction
  themselves after the flag-and-one-turn hint, without ever seeing the
  correct frame.
- The engine machine-checks every item against the snapshot's own
  `answer_key` and computes the block's `AttemptAssessment`; no separate
  `attempt finalize` call follows a drill block (unlike `reconstruction` and
  `timed_writing`, which are rubric-assessed and need one).

## `feedback_mode: always_explain`

`briefing.preferences.feedback_mode` defaults to `stage_dependent` (the
protocol in pedagogy.md's "Feedback by stage": one-line rule, full "why"
deferred to the debrief). When it is `always_explain`, give the short cause
at the point of correction too — still only after the one self-repair turn,
still without turning the round into a lecture. This preference changes the
explanation protocol only; it never changes how an item or a block is scored
(learner §4a).
