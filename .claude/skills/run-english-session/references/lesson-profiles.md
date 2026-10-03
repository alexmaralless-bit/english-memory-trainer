# Learner-facing lesson profiles

Profiles describe the learner's experience. They do not replace internal
control modes or step types. Every profile runs in chat from the brief and
closes with one `lesson_report@1` (`lesson-report.md`); the "Report" line of
each profile says what its items usually look like — a guide, not a quota.

## Program lesson

One central new curriculum topic. Announce the route, connect to known
language, explain the mental model, practise with support, require independent
use, and recap. Optional support: a brief warm-up and one related known topic.
Skip the parts the learner demonstrably knows.
Report: recall/recognition/production items on the central topic
(`requirements.central_topic_items`), review items for the warm-up, a
`teaching` entry for what was explained.

## Free conversation

Meaningful conversation on a learner-selected or agreed theme, mostly within
known language. Introduce no more than 1–3 useful new units; each unit the
learner met goes into the report's `lexicon` (enrolment, not evidence of
knowledge). Use focus-plus-batch correction (skill
`coach-english-conversation`).
Report: `kind: "conversation"` items for the learner's substantial turns, the
verbatim turn as `raw_answer`, the focus pattern as `target_ref`.

## Practice

No surprise new grammar. State the target and success criterion, retrieve it
in varied forms, explain errors, and retry.
Report: one item per learner answer on the practised targets.

## Spaced review

Prioritise due/at-risk items. Retrieval comes before restudy; failed retrieval
gets an explanation, retry, and fresh-context use (skill `run-spaced-review`).
Report: one `kind: "review"` item per `brief.reviews_due` entry with its
`review_id`, or a `reviews_skipped` entry with a reason.

## Drill

Frames first, then drill rounds (blocked → interleaved), text
reconstruction, timed writing and a debrief (skill `run-drill-block`).
Report: every round as a `blocks[]` entry with its items (`block_id`);
reconstruction and timed writing as ordinary items. Accuracy only — no
latency.

## Error clinic

Work on one recurring pattern grounded in recorded evidence
(`brief.learner.recent_errors`). Contrast the learner form and target form,
repair the smallest rule, then transfer it.

## Transfer simulation

A real-life role and goal with constraints. Prepare minimally, run the
scenario, debrief choices and errors, then retry the difficult moment with one
condition changed.

## Writing workshop

Name text, audience, and purpose. Analyse a short authored model, draft,
revise with focused feedback, and extract reusable decisions.

## Reading workshop

Name the reading purpose. Predict, read an authored text for meaning, retrieve
evidence and infer language, then summarise.

## Vocabulary lesson

Connect meaning, form, pronunciation, register, and close contrasts. Retrieve
the units in varied contexts and use selected units in an original message.

## Diagnostic

Sample independent performance without teaching the answer. Clarify ambiguous
evidence, report uncertainty honestly, and recommend the next lesson (in the
report's `summary.next_focus`). Levels come only from `trainer status`.
