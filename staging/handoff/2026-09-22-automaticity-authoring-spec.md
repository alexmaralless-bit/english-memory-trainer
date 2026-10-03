# Authoring spec — automaticity layer content (frames, article topics, reconstruction texts)

> Date: 2026-09-22. Owner: project owner (Claude session). Status: binding for every content agent in waves 1–4.
> Decisions: `staging/journal/2026-09-22-automaticity-method.md` [PD-2026-09-22]. Concept: `staging/concepts/2026-09-22-automaticity-method-concept.md`.

Every content agent reads this file fully before writing anything.

## 0. Ground rules (all agents)

1. **Own text only.** Every phrase, sentence, text, meaning and note is written for this project. No excerpts from textbooks, websites, corpora, forums or dictionaries. No real people, no real company names (use `the client`, `the vendor`, `our team`, generic product names).
2. **American English** spelling and usage (`color`, `on the weekend`, `in the hospital`).
3. **Never edit files you do not own.** Ownership is stated per task. In particular, content agents never touch `curriculum/lexicon/_suggested-topic-links.yaml`, `curriculum/lexicon/_provenance.yaml`, `curriculum/topics/*.yaml` (only the topics agent), `tests/`, `src/`, `wiki/`, `agent-skills/`.
4. **Validate before finishing**: `python3 tools/check_authoring.py <your file>` must print `OK`. The full pytest is not required for content agents (advisory links are added by the owner's post-pass).
5. No phase markers (`[mvp]`, `post-mvp`) anywhere. No YAML floats.
6. Russian text is used only in `meaning_ru`, `slot_hint_ru`, `note_ru`, `cause_ru`, `summary_ru`. Everything else is English.
7. Quality over count: a frame the learner would never type is worse than a missing one.

## 1. Frames — grammar-carrying chunks (Г1)

A **frame** is a `LexicalItem` of the existing type `chunk` (a multiword template with slots) that carries a grammar target. Frames are what the learner memorizes and produces; the topic keeps the rule.

**File**: one per topic, `curriculum/lexicon/frames-<topic-code>.yaml`, where `<topic-code>` is the topic id without the `grammar.` prefix and with dots replaced by hyphens. Example: `grammar.present-perfect.result` → `curriculum/lexicon/frames-present-perfect-result.yaml`.

File layout (same as existing lexicon files):

```yaml
# Frames for grammar.present-perfect.result (automaticity layer, 2026-09-22). Own text.
lexical_items:
  - {id: chunk.present-perfect-result.ive-already, type: chunk, title: "I've already ___", cefr: A2, curriculum_priority_band: CORE, register: neutral, transparency: transparent, domains: [work, reporting], meaning_ru: "я уже …", frame_of: grammar.present-perfect.result, carries: [tense:present-perfect], slot_hint_ru: "третья форма глагола + объект", examples: ["I've already sent the report to the client.", "I've already restarted the router twice."], contrast: {frame: "I ___ yesterday", note_ru: "есть законченное время (yesterday, last week) → Past Simple"}, trap: {learner_form: "I have already send the report.", correction: "I've already sent the report.", cause_ru: "после have нужна третья форма, не базовая"}, transformations: [authored]}
```

**Fields**

| Field | Rule |
|---|---|
| `id` | `chunk.<topic-code>.<slug>`; slug = lowercase letters, digits, hyphens, derived from the title with apostrophes dropped and `___` removed (`I've already ___` → `ive-already`). Unique inside the file. |
| `type` | always `chunk` |
| `title` | the frame with slots marked `___`; natural contractions (`I've`, `don't`, `we're`); keep articles that the natural phrase has (`the report`, `a ticket`). A frame may have 0–2 slots. |
| `cefr` | the topic's CEFR |
| `curriculum_priority_band` | mix per file: about 30 % `CORE`, 45 % `HIGH`, 25 % `USEFUL`. Never `SPECIALIZED`/`INCIDENTAL` for frames. |
| `register` | `neutral` (default), `casual` or `formal` |
| `transparency` | `transparent` (default) or `semi_opaque`; never `opaque` for a frame |
| `domains` | 1–3 from: work, reporting, planning, troubleshooting, communication, requests, meetings, everyday-life, home, food, travel, health, money, leisure, study, academic, technology, data, organization |
| `meaning_ru` | Russian meaning of the frame, slots as `…` |
| `frame_of` | the topic id |
| `carries` | 1–3 tags from the closed vocabulary in §1.1 |
| `slot_hint_ru` | optional, what goes in the slot |
| `examples` | exactly 2 full sentences, 6–14 words, one work context and one everyday context where natural; the frame appears verbatim (slot filled) |
| `contrast` | optional but expected for tense/aspect and article frames: `{frame, note_ru}` — the nearest competing frame and why it differs |
| `trap` | optional but expected: `{learner_form, correction, cause_ru}` — the tempting wrong form a Russian speaker produces (calque, aspect transfer, dropped article/auxiliary) |
| `transformations` | `[authored]` |

No `frequency_score`, `frequency_band`, `source_refs` (the corpus does not cover phrases).

**How many**: big-five and core topics 20–30 frames; tail topics 12–20. Cover, where the topic allows: affirmative, negative, question, with typical time markers, with an object that needs an article, first and third person, one formal and one casual variant.

**What a good frame is**: a phrase a working adult actually types in chat, email, a ticket or a status update, or says about daily life. It carries the target form in a fixed position (`We haven't ___ yet`, `It was ___ when ___`, `There are ___ in the ___`). It is not a full example sentence with everything filled in, and it is not a bare grammar formula (`have + V3`).

### 1.1 `carries` vocabulary (closed)

Tense/aspect: `tense:present-simple`, `tense:present-continuous`, `tense:past-simple`, `tense:past-continuous`, `tense:present-perfect`, `tense:present-perfect-continuous`, `tense:past-perfect`, `tense:future-will`, `tense:future-going-to`, `tense:future-continuous`, `tense:passive`, `tense:conditional-0`, `tense:conditional-1`, `tense:conditional-2`, `tense:conditional-3`, `tense:reported-speech`, `tense:modal-perfect`.

Articles: `article:indefinite-first-mention`, `article:definite-second-mention`, `article:definite-shared-context`, `article:zero-plural`, `article:zero-uncountable`, `article:fixed-expression`, `article:institutional`, `article:superlative-ordinal`, `article:generic`, `article:proper-noun`, `article:a-an-sound`, `article:of-phrase`.

Structure: `structure:svo-order`, `structure:question-do`, `structure:question-be`, `structure:question-wh`, `structure:negative`, `structure:there-is`, `structure:here-is`, `structure:imperative`, `structure:modal`, `structure:comparative`, `structure:superlative`, `structure:connector`, `structure:relative-clause`, `structure:sequencing`, `structure:time-marker`, `structure:frequency-adverb`, `structure:quantifier`, `structure:preposition-time`, `structure:preposition-place`, `structure:possessive`, `structure:demonstrative`, `structure:inversion`, `structure:cleft`, `structure:participle-clause`, `structure:ellipsis`, `structure:hedging`, `structure:nominalization`, `structure:reference`.

Tag an article only when the frame contains the article in a fixed position (`the report` in `I've already sent the report` is not fixed — the object is a slot; `at the end of the ___` is fixed).

## 2. Article frames (Г2)

**File**: `curriculum/lexicon/frames-articles.yaml`, same entry format as §1, plus `tier: 1 | 2`. Total 120–150 units across the nine article topics below (`frame_of` must be one of these ids). Slugs use the topic-code `articles-<short>`; for the existing topic use `articles-identity`.

- **Tier 1 — fixed expressions learned as wholes** (title has no slot or one trailing slot): `in the morning`, `at night`, `on the weekend`, `at the end of the day`, `once a week`, `a couple of ___`, `a lot of ___`, `have a look`, `take a break`, `go to work`, `at home`, `in the hospital`, `on the other hand`, `the same ___`, `the rest of the ___`, `most of the ___`, `by the way`, `as a rule`, `in a hurry`, `on time` / `in time`, `at the moment`, `for a while`, `the first time`, `the only ___` …
- **Tier 2 — low-scope schemas with slots**: `I'm a ___` (role), `There's a ___ in the ___`, `I opened a ___. The ___ is ___`, `the ___ of the ___`, `one of the ___`, `the ___ we discussed`, `a new ___ / the new ___`, `the ___ team`, `___ (plural, no article) are ___`, `___ (uncountable) is ___` …

| Article topic id | CEFR | Scope |
|---|---|---|
| `grammar.articles.identity` (exists) | A1 | a/an on first mention, roles, a/an by sound |
| `grammar.articles.second-mention` | A1 | a → the on second mention; the when both sides can identify the thing |
| `grammar.articles.zero-plural-uncountable` | A1 | no article with plural and uncountable nouns (data, information, software, tests, feedback) |
| `grammar.articles.fixed-time-expressions` | A1 | in the morning, at night, on Monday, on the weekend, at the end of, once a week, at the moment |
| `grammar.articles.institutional-places` | A2 | go to work / to the office, at home, in the hospital, at school, to the doctor's, in bed, in prison |
| `grammar.articles.the-unique-superlative-ordinal` | A2 | the with superlatives, ordinals, same/only/next/last, unique referents (the sun, the internet, the CEO) |
| `grammar.articles.generic-statements` | B1 | generic reference in technical writing: zero plural (Users need…), a + singular, the + singular |
| `grammar.articles.proper-nouns-geography` | B1 | the US, the Netherlands, the Alps, the Thames vs zero with cities/countries/companies; the EU, NASA |
| `grammar.articles.abstract-and-of-phrases` | B2 | abstract nouns zero vs the; the N of N; academic/TOEFL writing patterns |

## 3. Article topics (В1) and contrasts (Г3) — topics agent only

Author the eight new article topics above as full topic bodies in the format of `grammar.articles.identity` in `curriculum/topics/a1.yaml` (lines 62–124): `title`, `can_do`, `advisory_prerequisites`, `dimensions: [recognition, controlled_production, spontaneous_production, transfer]`, `frequency_tier: core`, `lexicon` (≥ 3 existing item ids that resolve; frames are linked later by the owner), `contexts` (reuse existing context ids), `typical_errors` (3–4, Russian-specific, with the calque named), `examples` (2), `core_points` (3), `contrasts` (**≥ 6 minimal pairs**, `a X / the X / X` in the same context), `scope_limits` (2), `error_patterns` (3 objects: learner_form, correction, explanation), `explanation_language: ru-allowed`, standard `mastery_criteria` (thresholds 70/75/75/75, independent_attempts 2, retention 30 days, 2 confirmations). `memory_insights` only with real, verifiable title+URL; otherwise omit the field.

Register each topic in its module file (`curriculum/modules/<module>.yaml`, `topics:` list) and add the eight ids to `CORE_GRAMMAR_TOPIC_IDS` in `tests/test_curriculum_topic_bodies.py`.

Contrast sets (Г3): make sure these existing topics have **≥ 6** `contrasts` entries as minimal pairs (add, never rewrite existing ones): `grammar.present-perfect.result`, `grammar.present-perfect-past-simple.choice`, `grammar.past-simple.events`, `grammar.present-simple-continuous.choice`, `grammar.past-continuous.incident-context`, `grammar.future-forms.planning`, `grammar.present-perfect.duration`.

`carries` on existing chunks (В2): add `carries: [article:…]` to every existing chunk whose title contains a fixed `a`/`an`/`the` (45 units, mostly `chunks-work-frames.yaml`; find them with `grep -n 'type: chunk' curriculum/lexicon/*.yaml | grep -iE '\b(a|an|the)\b'`). Do not change anything else in those entries.

## 4. Reconstruction texts (Г4)

**Dir**: `curriculum/texts/reconstruction/`, one file per topic named `<topic-id>.yaml`.

```yaml
schema_version: 1
texts:
  - id: text.recon.present-perfect-result.migration-update
    title: "Migration update"
    cefr: A2
    topic: grammar.present-perfect.result
    also_targets: [grammar.articles.second-mention]
    carries: [tense:present-perfect, article:definite-second-mention]
    domain: work
    context: deployment-update
    text: "Quick update on the migration. So far we've moved four of the six tables. ..."
    word_count: 72
    keywords: ["update", "four of six", "two largest - not yet", "export failed Tuesday", "ticket - vendor - escalated", "workaround - staging", "first time - limit", "document - end of week"]
    target_spans: ["we've moved", "haven't been migrated yet", "has already been escalated", "I've just tested", "we've hit"]
    summary_ru: "Апдейт по миграции: что уже перенесли, что нет, что сломалось во вторник."
    transformations: [authored]
```

Rules: two texts per topic (one `work`, one `everyday`; for TOEFL/C-level topics `academic` is allowed instead of everyday). Length by level: A1 50–70 words, A2 60–80, B1 80–110, B2 90–120, C1–C2 110–140. The text is dense in the target form (≥ 5 occurrences) and uses articles correctly and often. `keywords`: 8–12 cues in text order that let the learner rebuild the text without seeing it. `target_spans`: 5–10 exact substrings of `text` (case-sensitive) that carry the target; the checker verifies they occur. `word_count` must equal the whitespace word count. `context` is a short kebab id (reuse topic contexts when possible).

## 5. Checker

`python3 tools/check_authoring.py <file>` validates frames files (§1–2), topic files (§3, structural only) and text files (§4). It prints `OK` or a list of problems. Fix every problem before reporting done.
