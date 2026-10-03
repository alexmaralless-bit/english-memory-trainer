# The lesson ledger and the `lesson_report@1`

Source of truth: `src/english_trainer/lessons/report.py` (check/commit),
`lessons/brief.py` (`report_contract`), `curriculum/policies/evidence-v2.yaml`
(verdict scale, limits). This file restates them as tutor-facing rules. The
brief's `report_contract` carries the live vocabularies and limits — when it
disagrees with this file, the contract wins.

## The ledger (kept in context during the lesson)

Nothing is sent to the system while the lesson runs. For every item the
learner actually answered, keep one ledger entry in your context as you go:

- the prompt exactly as shown (Russian cue, question, task text);
- the learner's answer — the FIRST answer to that prompt, copied verbatim
  (typos, missing punctuation, capitalisation and all);
- your verdict (`correct` / `partial` / `incorrect`, pedagogy.md "Tutor
  verdict") and the number of hints you gave before the answer;
- for a non-correct verdict, each error: the exact substring of the answer
  that is wrong (`learner_form`), the repaired form (`correction`), the short
  cause;
- the target and dimension the item practised; the `review_id` when the item
  was a due review from `brief.reviews_due`; the round (`block_id`) in a drill.

Also note the new useful units the learner met (lexicon), what you explained
(teaching), and which due reviews you did not reach and why. After a lost
chat, Claude Code resume restores this context; `session resume` only
re-reads the brief — it never holds the ledger.

## Report document

```json
{
  "schema": "lesson_report@1",
  "session_id": "<brief.lesson.session_id>",
  "brief_hash": "<brief.report_contract.brief_hash>",
  "items": [
    {
      "item_id": "i1",
      "target_ref": "grammar.be.identity",
      "dimension": "controlled_production",
      "kind": "production",
      "prompt": "Скажи по-английски: я учитель.",
      "raw_answer": "I am a teacher",
      "verdict": "correct",
      "hints": 0,
      "secondary_targets": [],
      "review_id": null,
      "block_id": null,
      "errors": []
    },
    {
      "item_id": "i2",
      "target_ref": "grammar.be.identity",
      "dimension": "controlled_production",
      "kind": "production",
      "prompt": "Скажи: я учитель и редактор.",
      "raw_answer": "I am a teacher and an editor",
      "verdict": "partial",
      "hints": 0,
      "errors": [
        {
          "learner_form": "a teacher and an editor",
          "correction": "a teacher and editor",
          "cause": "один артикль на одно существительное с двумя определениями",
          "topic_error_ref": null
        }
      ]
    }
  ],
  "blocks": [],
  "reviews_skipped": [{"review_id": "<id>", "reason": "no_time"}],
  "teaching": [{"target_ref": "grammar.be.identity", "summary": "фреймы I am a/an …, I work as …; артикль перед профессией"}],
  "lexicon": [{"surface": "pull an all-nighter", "linked_item_id": null, "note_ru": "не спать всю ночь (чтобы доделать)"}],
  "summary": {"text": "…", "next_focus": "…"}
}
```

Field rules:

- `item_id` — unique within the report (`i1`, `i2`, … in lesson order).
- `target_ref` — a topic or lexical-unit id of the PINNED program (the brief's
  `central_topic.target_ref`, a frame's `frame_ref`, a review's `target_ref`,
  a plan step's `target_ref`). Never invent an id.
- `dimension` — one of `recognition`, `controlled_production`,
  `spontaneous_production`, `transfer`. Recall of a frame from a Russian cue
  is `controlled_production`; free use in a new context is
  `spontaneous_production`; choosing between given options is `recognition`.
- `kind` — descriptive: `recall`, `recognition`, `production`, `review`,
  `drill_item`, `conversation`.
- `prompt` — what the learner saw (a missing prompt is a warning).
- `raw_answer` — verbatim, non-empty, within `report_limits.max_answer_chars`.
- `verdict`, `hints` (non-negative integer).
- `secondary_targets` — optional `[{"target_ref", "dimension"}]` for another
  target the same answer genuinely demonstrates (half credit).
- `review_id` — only for a due review; its `target_ref` AND `dimension` must be
  exactly the review's. One item per review.
- `errors[]` — at most `report_limits.max_errors_per_item`; `learner_form`
  must be a verbatim substring of THIS item's `raw_answer` (the system derives
  the span itself — never send offsets); `topic_error_ref` optional.
- `blocks[]` — drill rounds, see skill `run-drill-block`.
- `reviews_skipped[]` — `{"review_id", "reason"}` with reason `no_time` or
  `learner_declined`.
- `teaching[]`, `lexicon[]`, `summary` — optional but expected; `lexicon`
  `linked_item_id` is a lexical id of the program or `null`.
- No latency, score, level or offset fields exist — do not add any.

## Check → fix → commit

1. Write the report to a temp file (outside the repo, e.g. the scratchpad).
2. `trainer session check-report --file <path> --format json` — read-only.
   Output `lesson_report_check@1`: `valid`, `errors` (report-level:
   `bad_schema`, `session_mismatch`, `too_many_items`), per-item `items[]`
   with `status` `accepted`/`rejected`, `reasons[]` and `effects`
   (`score_ppm`, `contributing`, `duplicate_span`, `review_outcome`),
   `blocks[]`, `reviews` (addressed/skipped/unaddressed), `requirements`,
   `lexicon` statuses, `warnings`, `summary`.
3. Fix every rejection — a single rejected item refuses the whole report:

| Code | Fix |
|---|---|
| `learner_form_not_in_answer` | copy the wrong fragment verbatim from `raw_answer` |
| `unknown_target` | use an id from the brief / pinned program |
| `bad_dimension` | one of the four dimensions (block items share the block's) |
| `empty_answer` | the learner did not answer — drop the item |
| `answer_too_long` | cut to the part that answers the prompt, verbatim |
| `bad_verdict` / `bad_hints` | `correct`/`partial`/`incorrect`; integer ≥ 0 |
| `review_mismatch` | review id not pending, used twice, or target/dimension differ |
| `too_many_errors` | keep the errors that matter most |
| `block_unknown` | declare the block in `blocks[]` with a unique `block_id` |
| `duplicate_item_id` / `bad_item` | unique string ids; lists where lists are due |
| `empty_surface` | a lexicon entry needs its English surface |

   Never "fix" a rejection by changing the learner's answer or the verdict.
4. Warnings do not block, but read them and be honest about them:
   `duplicate_span` (the same answer already earned credit for this target —
   recorded without contribution), `review_unaddressed` (closes
   `INSUFFICIENT_EVIDENCE`), `requirement_unmet`, `brief_changed`,
   `missing_prompt`, `empty_report`. Mention the ones that matter to the
   learner (an unaddressed review) in the wrap-up.
5. `trainer session report --file <path> --provider <id> --format json --idempotency-key <key>`
   writes everything atomically and finishes the session. Re-running with the
   same key and the same file returns the cached result; do not change the
   file under the same key.
6. Summarise from `trainer status --format json` only.
