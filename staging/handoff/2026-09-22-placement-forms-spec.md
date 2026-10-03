# Placement forms — authoring and mechanism spec (Д15)

> Date: 2026-09-22. Owner: project owner. Status: binding for the Д15 agents. Decision context: the shipped placement was a 6-item A1 stub (`src/english_trainer/assessments/forms.py`); canon (`wiki/flows/placement.md`, `wiki/modules/assessments.md` §3, `wiki/product/learning-model.md` §6) requires fixed authored versioned forms in `curriculum/assessments`, ≥ 2 forms, ~30–40 minutes, grammar/vocabulary/reading objective + writing by rubric, deterministic seed, ACTIVE ceiling, low-confidence start.

## 1. Files and shape

Forms live in `curriculum/assessments/placement-<name>.yaml`, versioned with the curriculum snapshot (part of the hash), validated at `trainer curriculum validate`/`activate`, loaded by the assessments module (no Python-embedded forms except test fixtures).

```yaml
schema_version: 1
form_version: "placement-en-core-a@1"     # also the deterministic seed
title: "Placement A"
target_minutes: 35
sections: [grammar, vocabulary, reading, writing]
passages:                                   # own text only
  - {passage_id: p-a2-1, cefr: A2, title: "Team update", text: "…90–130 words…"}
items:
  - {item_id: g-a1-01, section: grammar, band: A1, kind: choice, target_ref: grammar.be.identity, dimension: recognition, prompt: "I ___ an engineer on the platform team.", options: ["am", "is", "are", "be"], answer_key: ["am"]}
  - {item_id: g-a2-03, section: grammar, band: A2, kind: cloze, target_ref: grammar.present-perfect.result, dimension: controlled_production, prompt: "We ___ (finish) the migration, so the new dashboard is live.", answer_key: ["have finished", "'ve finished", "have already finished"]}
  - {item_id: r-b1-02, section: reading, band: B1, kind: true_false, passage_id: p-b1-1, target_ref: reading.<topic-id>, dimension: recognition, prompt: "The vendor fixed the issue before the demo.", answer_key: ["false"]}
  - {item_id: w-b1-01, section: writing, band: B1, kind: writing, target_ref: written-production.<topic-id>, dimension: spontaneous_production, prompt: "…", rubric_ref: "rubric:production.spontaneous", min_words: 60, max_words: 120}
```

Item kinds (closed): `choice` (4 options, exactly one correct, `answer_key` = the option text; the learner may answer with the letter a–d or the text), `cloze` (typed; `answer_key` lists every acceptable variant incl. contractions; base form in parentheses when the item tests a verb form), `true_false` (`answer_key` ∈ {"true","false"}; the learner may answer да/нет/yes/no/true/false), `writing` (rubric; `min_words`/`max_words`).

Rules: `item_id` unique per form, pattern `<section-initial>-<band-lowercase>-<nn>`; `section` ∈ core skills; `band` ∈ A1…C1 (C2 not placed); `target_ref` resolves to a topic (grammar/reading/writing) or a LexicalItem (vocabulary); `dimension` ∈ {recognition, controlled_production} for objective items, `spontaneous_production` for writing; reading items reference an existing `passage_id`; no phase markers; American English; own text only; no real people/companies.

## 2. Coverage per form (measurability)

The working level per skill needs ≥ 5 distinct topics of a band (scoring `working_level.min_topics`), so each form tests, per band, **distinct** topics:

| Section | A1 | A2 | B1 | B2 | C1 | Items | Notes |
|---|---|---|---|---|---|---|---|
| grammar | 8 | 8 | 8 | 6 | 5 | 35 | one item per topic, distinct topics within a band; mix `choice`/`cloze`; big-five and core topics first; B2/C1 from tail/core topics of that band |
| vocabulary | 5 | 5 | 5 | 5 | 4 | 24 | `choice` items on CORE/HIGH LexicalItems of that CEFR (words, chunks, phrasal verbs, academic core for B1+); distractors plausible for a Russian speaker |
| reading | – | 1 passage × 3 | 1 × 3 | 1 × 3 | 1 × 3 | 12 | bound to `reading` track topics of the band; questions test gist, detail, inference |
| writing | – | 1 | 1 | – | – | 2 | A2: introduce yourself and your work to a new team (60–90 words); B1: a status/incident message with a request (80–120 words) |

Total ≈ 73 items, ≈ 35 minutes. Form B mirrors form A item-for-item in section/band/kind/dimension and targets the same topics with different prompts (no shared prompts, no shared passages).

## 3. Mechanism (code, Д15)

1. Loader: `curriculum/assessments/*.yaml` → `program["placement_forms"]` (sorted by file); validator rules above; forms enter the snapshot hash. `assessments.forms.select_form` resolves from the active curriculum snapshot (default = the form with the lowest `form_version` that has no exposure history for this learner, else rotation by cooldown per `assessments@1`); the old embedded form becomes a test fixture only.
2. Grading: `choice` accepts letter or text; `cloze` normalized (existing `_normalize_answer`), `true_false` accepts yes/no/да/нет; objective evidence and exposure exactly as today.
3. Writing: `placement answer --input FILE` for the writing section accepts `{"section": "writing", "answers": {...}, "observations": {"w-b1-01": [ ...rubric observations... ]}}`; on submit the engine computes the rubric assessment (`compute_rubric_assessment` with `rubric_step_type: spontaneous_production`, pinned `rubric@1`), records evidence `origin=placement`, `assessment_basis: rubric`, provisional (learning-model §6: a single fragment gives a provisional writing level only). No observations → item recorded non-contributing (as today).
4. Level from placement (`scoring@2`, section `placement`): per skill, the highest band where ≥ `min_topics` distinct topics of that band have **all** their placement items correct; the result is written as `measured_working_level.<skill>` with confidence **`low`** and `basis: placement`; session evidence later raises confidence by the normal rolling rule (per skill). Topics keep their normal knowledge-state rules (a single correct item → LEARNING; ceiling ACTIVE unchanged). Writing level from one fragment = provisional only. Rationale: canon §6 "стартовые оценки по навыкам с пометкой low-confidence"; placement is a designated one-shot measurement, not session evidence. `scoring@1` behaviour unchanged for old pins.
5. `trainer status` shows the per-skill level with `basis` and `confidence`; the tutor briefing carries it (flows/continuation).
6. `tools/check_authoring.py` learns form files (structural check for content authors).

## 4. Presentation (skill `run-placement-assessment` v2)

Items are presented verbatim, section by section, in band order; `choice` shows the four options as a–d; a passage is shown once before its questions; no hints, no explanations, no reformulation; the writing section is presented with its word range; the tutor records rubric observations for writing (span-based, per `rubric@1`), never a verdict; checkpoints after every section; `placement submit` at the end; then `trainer status` is the only source of the level statement. Russian for instructions to the learner, English for items.
