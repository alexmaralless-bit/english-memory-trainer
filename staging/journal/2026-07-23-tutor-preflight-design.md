# Tutor preflight: observed failure and design discussion

Date: 2026-07-23

## Context

During a live system test, an agent resumed an existing session and presented a
free-conversation prompt without explaining the format, topic, or purpose. The
learner had expected continuation of article practice. A subsequent replan
proposed a new `do`-question topic without first establishing the learner's
history or obtaining consent to introduce it. The session was explicitly
abandoned through the engine; no learning result was claimed.

## Design direction under discussion

The control engine remains the source of truth for state and recommendations,
but the AI tutor must act as a transparent personal teacher. Before any
learner-facing exercise it should disclose the session mode and topic, give a
short pedagogical bridge (purpose, context, and examples where useful), and
treat the learner's current message as live instructional context. An engine
proposal is not sufficient authority to silently introduce an unfamiliar topic.

Candidate implementation: a Markdown-maintained tutor preflight policy,
explicitly invoked by session/orchestration, teaching, and conversation skills;
with tests covering disclosure, learner-intent precedence, unknown-topic
clarification, and explanation before new material. This is not yet a product
decision or canon.

## Expanded pedagogical direction under discussion

The learner asks for a full, interesting lesson rather than an unintroduced
sequence of prompts. For a new topic (and when useful for review), the tutor
should provide a compact teaching arc: topic title; scope and reason for the
step; an intuitive explanation; several authored examples and contrasts;
typical errors and their causes; guided practice; then independent practice
and feedback. A short, accurate etymological, phonetic, or historical note is
encouraged when it makes the rule easier to remember. It must be framed as
explanation rather than invented certainty, remain appropriate to the learner,
and be sourced from approved authored curriculum content rather than improvised
as a factual claim.

Examples proposed by the learner: the historical relation of the indefinite
article to "one"; the sound-based `a`/`an` contrast; and English plural ending
pronunciation (`/s/`, `/z/`, `/ɪz/`) as a useful phonetic pattern. Exact
historical wording and examples need curriculum review before becoming teaching
content.

## Open questions

- Exact policy scope: a shared base skill, a Markdown policy read by every
  teaching skill, or both.
- Which learner preferences should be persisted as profile data rather than
  only applied within the current turn.
- Whether "new material" always requires consent, or whether disclosure plus
  an easy opt-out is sufficient for short introductions.

## Terminology preference

Learner-facing language must say **"система"** (or a natural equivalent), not
"движок". "Движок" is an internal engineering term and belongs only in
developer-facing specifications and diagnostics.

## Approved product decision and implementation

The learner approved implementation on 2026-07-23 [PD-2026-07-23].

- Ten lesson profiles are distinct presentation strategies over one evidence
  model: program, free conversation, practice, spaced review, error clinic,
  transfer simulation, writing, reading, vocabulary, and diagnostic.
- A read-only LessonProposal announces title, profile, duration, central topic,
  reason, agenda, and language envelope. A direct learner request is consent;
  a system recommendation requires confirmation. A proposal hash detects a
  stale start.
- Program lessons introduce at most one central new topic. Ten to nineteen
  minutes is a micro lesson; twenty or more is a full lesson.
- Learner-facing explanations are persisted as TeachingSegments before they
  are shown. Sourced historical, phonetic, or etymological notes are optional;
  unavailable research is skipped rather than invented.
- Free conversation primarily uses known language and admits one to three
  explained new units. A changed request becomes a `lesson_request` signal and
  affects an active session only through replan.
- Curriculum remains a dynamic lesson source, not a catalog of pre-generated
  scripts. Three foundational A1 topics received richer teaching anchors; all
  topics receive a deterministic learner-facing title.
- The pedagogy rules live in editable Markdown references inside canonical
  skill packages. Exact archived versions remain resolvable by
  `(name, version, content_hash)`.
- Background lesson prefetch was not implemented. It may be reconsidered only
  after latency has been measured for at least 30 learner-facing steps.

Canonical specifications were updated in the glossary, learning model,
curriculum, control, lessons, adapters, audit, CLI, session/continuation flows,
and roadmap. Implementation uses `generation@2`, `control@2`, and
`obligations@2` while retaining v1 resolution for existing sessions.

Validation and rollout completed against the local installation:

- 518 tests passed; Ruff, format check, and strict mypy were clean.
- Curriculum validation reported 275 topics, 1142 lexical items, no warnings
  and no errors.
- Canonical skills were synchronized recursively and the final drift check was
  clean.
- Curriculum version `curriculum@2026-07-23-tutor-pedagogy-v2` was activated
  over `2026-07-22`; activation registered both v1 and v2 policy payloads.
- A read-only live proposal for `grammar.articles.identity` returned the full
  LessonProposal and correctly classified the target as known from learner
  evidence. No learning session was opened by this rollout check.
