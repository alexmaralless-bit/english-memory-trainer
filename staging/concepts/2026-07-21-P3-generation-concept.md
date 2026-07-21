# P.3 concept: generation policies, exercise bank lifecycle, living layer

> Phase: concept only.
> Date: 2026-07-21.
> Scope: design for OPEN-14 and OPEN-16.
> Canon status: this file is not canon. `wiki/`, `src/`, `tests/`, `curriculum/`, `agent-skills/` are not changed in this phase.
> **APPROVED [PD-2026-07-21]**: user accepted all recommendations after independent
> review by Claude (no canon contradictions found). Decisions: PD-1 → A
> (EXERCISE_RENDERED before presentation), PD-2 → A (bank admission after an
> assessed attempt, maintainer fast path), PD-3 → C (hybrid currency aging),
> PD-4 → A (dated = recognition-only with explicit override), PD-5 → D (hybrid
> lexicon-first micro lane + auto-link candidates), PD-6 → A (domain event types
> inside the generic envelope), PD-7 → A (OPEN-31 stays content-review).
> Phase 2: canon edits go as PATCH PROPOSALS verified and applied by the owner.

## Input Notes

- Current `curriculum/topics/a1.yaml` + `a2.yaml` contain 153 A1-A2 topics, all with P.2 bodies.
- Current grammar contract uses `frequency_tier: big-five | core | tail`. The P.2 handoff report still records the earlier
  two-tier snapshot (`big-five | tail`); phase 2 should sync the report/test wording if that document stays referenced.
- Current lexicon contains 838 items. A1-A2 topic bodies reference 247 distinct items; 591 are not directly referenced.
- Exercise generation must fit into the accepted session protocol: `SessionPlan` is created at `session start`;
  `session next` is a mutating delivery step and publishes `STEP_PRESENTED`; `Attempt` evidence is recorded by `step_id`.

## Invariants

These are the non-negotiable rules that the future `generation@1` policy must enforce.

1. Generation creates exercises, not knowledge. Evidence appears only after a saved learner response and engine assessment.
2. Every exercise is tied to a `PlannedStep` and its `(target_ref, dimension)` data. No free-floating scored exercise.
3. Exercise text is persisted once shown to the tutor. Replay reads the stored exercise instance and its hash; it never
   asks an LLM to regenerate historical content.
4. Safety is not pinned. `production_eligible` is computed from the active usage/currency policy at delivery and bank reuse.
5. A production step must not require production of any item whose active profile forbids production. This includes:
   `opaque`, `recognition_only`, `avoid`, `obsolete`, and `context_dependent` outside allowed contexts.
6. Opaque units may appear in recognition and neutral-paraphrase tasks, never in required controlled or spontaneous production.
7. Living-layer excerpts are permanently forbidden. Store the short unit, metadata, source pointers/hashes, and authored
   neutral paraphrase, not third-party posts, comments, emails, tickets, or forum text.
8. Typical errors are used as controlled traps: distractors, negative rubric checks, and feedback reasons. They are not copied
   as learner evidence unless the learner actually makes the error in a saved response.
9. All generated examples, prompts, distractors, answers, and explanations are authored for the project. No borrowed text.
10. Bank reuse is opportunistic. An empty bank never blocks a session.
11. Acceptance into the bank is explicit and append-only. A generated exercise is not reusable merely because it was produced.
12. Retirement never deletes history. Retired items remain resolvable for past sessions, evidence, and replay.
13. Numeric defaults below are advisory calibration only. They must become versioned policy values before implementation.

## A. Generation Policy: `generation@1`

### Policy Payload

`generation@1` should be a versioned policy registered in the kernel policy registry and pinned in the Session Manifest.
It should carry:

- supported dimensions and allowed `step_type` shapes;
- exercise schemas per dimension;
- distractor construction rules;
- safety predicates and the active-safety fields to record at delivery;
- bank reuse/admission constraints;
- deterministic ordering keys when multiple valid exercise candidates exist;
- advisory intensity weights by `frequency_tier`;
- own-text and no-excerpt constraints;
- minimum metadata for evidence and audit.

The policy should not contain scoring thresholds that belong to topics or scoring. It describes how to produce admissible
exercise instances from curriculum input.

### Delivery Pipeline

Recommended shape:

1. `control.compose_session` plans only the step target/dimension/context, not full exercise text.
2. `session next` rechecks active safety before publishing `STEP_PRESENTED`.
3. The returned step is either linked to a revalidated bank item or carries a generation directive.
4. The tutor agent renders the exercise under `generation@1`.
5. Before asking the learner, the agent records the rendered exercise as `EXERCISE_RENDERED` with:
   `step_id`, `exercise_instance_id`, content hash, target refs, dimensions, context id, lexicon refs, answer key or rubric ref,
   `generation_policy_version`, pinned curriculum/rubric versions, and `active_safety_version`.
6. `trainer attempt record` references `step_id` and, for structured tasks, `exercise_instance_id`.
7. After assessment, bank admission evaluates the exercise and emits `EXERCISE_ACCEPTED` or `EXERCISE_REJECTED`.

Crash recovery:

- `STEP_PRESENTED` without `EXERCISE_RENDERED` is recoverable on `resume`: the same step returns with the same directive.
- `EXERCISE_RENDERED` without learner attempt is not evidence and can be reused only if later accepted by policy.
- A crash during bank admission leaves the item in `generated`; retry is idempotent by `exercise_instance_id`.
- A learner response to an already presented step is assessed against the stored exercise snapshot. Later safety changes block
  future delivery/reuse, not the historical attempt.

### Dimension Mechanics

| Dimension | Exercise shapes | Evidence generated |
|---|---|---|
| `recognition` | multiple choice meaning/form; cloze recognition; sentence classification; match expression to neutral paraphrase; tone/register classification | objective `recognition_check` where possible; selected distractor becomes `ERROR_OBSERVED` candidate tied to the relevant `typical_errors` item |
| `controlled_production` | fill a slot; transform a sentence; guided reply; reorder words; produce one or two constrained sentences | objective check for closed items, rubric observation for open but constrained answers; `hints` and acceptable variants stored |
| `spontaneous_production` | short free reply, mini-chat turn, status update, or role-context prompt without showing the target form directly | rubric evidence only when the response contains an assessable span; no span means no contributing evidence or `INSUFFICIENT_EVIDENCE` on review close |
| `transfer` | same target in a new domain/context; combine new target with learned target; paraphrase in a different register | `transfer_task` or `integration_task`; context id must differ from recent exposures for independence to count |

Special cases:

- `word-formation` tasks may ask the learner to infer an existing word from `formation`, but must never invent a fake word as
  if it were real.
- `lexeme` tasks should target explicit form slots (`base`, `past`, `participle`) and record which slot was tested.
- Informal/casual items may ask for neutral paraphrase and context selection even when production is unsafe.
- `free_conversation` can generate hidden observations, but only saved spans become evidence.

### Typical Errors as Distractors

For recognition:

- each distractor should correspond to exactly one `typical_errors` entry where practical;
- distractors must be plausible for a Russian-speaking learner, not random nonsense;
- literal-translation traps for opaque items use `literal_trap_ru` as the authoring guide, but the displayed text is authored
  for the exercise;
- distractors store `distractor_error_ref` so feedback and `ERROR_OBSERVED` can name the root error.

For production:

- `typical_errors` become rubric checks and feedback messages;
- the prompt should elicit the target without telling the learner exactly which form to use in spontaneous tasks;
- a learner's real wrong answer can inform future generator rules only through an observed error kind, not by copying the
  raw answer into reusable bank content.

### Frequency Tier Intensity

Current canon has three tiers:

- `big-five`: high repetition and production intensity; all required dimensions are trained through production and transfer.
- `core`: high priority for frequent non-tense grammar; required dimensions follow the topic can-do, often full production.
- `tail`: present at A1-A2 mainly for recognition and transfer; production is not required unless a later topic makes it
  explicit.

Advisory calibration for `generation@1`:

| Tier | Candidate weight | Suggested mix |
|---|---:|---|
| `big-five` | 10000 | recognition warm-up, then controlled, spontaneous, and transfer in the same or adjacent sessions |
| `core` | 8500 | full-dimension practice when topic requires it, with fewer same-session repeats than big-five |
| `tail` | 3500 | recognition and transfer checks, mostly in reading/mediation contexts |

These numbers are advisory calibration. The policy should use integer weights and leave empirical tuning to later versions.
Frequency affects ordering and intensity only. It must not delete a target, change topic dimensions, or override
`mastery_criteria`.

## B. Exercise Bank Lifecycle

### Entities

`ExerciseInstance` is the generated artifact for one step:

- `exercise_instance_id`
- `step_id`
- `status: generated | accepted | rejected | retired`
- `content_hash`
- authored prompt, expected answer or rubric, distractors, feedback keys
- target refs, dimensions, `context_id`, lexicon refs
- provenance: session id, provider, generated_at, pinned curriculum/generation/rubric/scoring policy versions,
  active safety version at render, source topic examples used as inspiration

`ExerciseUse` is each delivery/reuse:

- `exercise_instance_id`
- `session_id`
- `step_id`
- `presented_at`
- active safety version at delivery
- outcome link if review closes

### State Machine

```text
generated -> accepted
generated -> rejected
accepted  -> retired
```

`generated`:

- created from a delivered step and stored with content hash;
- not reusable yet;
- can still support the current attempt if it passes immediate validation.

`accepted`:

- schema-valid;
- target/dimension/lexicon refs resolve;
- no unsafe production requirement under active safety;
- answer key or rubric is sufficient to create admissible evidence;
- no third-party excerpt;
- not a near duplicate of an accepted item for the same target/dimension/context unless it adds a distinct transfer context.

`rejected`:

- ambiguous answer key, dangling refs, unsafe production, borrowed text, poor fit to the planned dimension, or repeated learner
  confusion caused by prompt wording rather than the target skill.

`retired`:

- active safety now forbids reuse;
- target or lexicon item is retired/deprecated beyond 1:1 alias;
- policy version marks schema incompatible;
- duplicate has a better accepted replacement;
- quality metrics cross a threshold. Advisory calibration: retire after 3 independent prompt-fault flags or 2 explicit
  maintainer rejections.

### Dedup and Reuse

Canonical dedup key:

```text
target_refs + dimensions + step_type + context_family + normalized_prompt_skeleton + answer_key_hash + sorted_lexicon_refs
```

Reuse rules:

- choose only `accepted` and not `retired`;
- revalidate against active safety at delivery;
- prefer items whose context supports independence from recent exposures;
- do not use the same bank item to satisfy independent attempts unless the policy explicitly treats the context as changed;
- record every reuse as `ExerciseUse` tied to the session step.

Crash-safety:

- all bank state transitions are events in the authoritative store;
- no external file is authoritative;
- generated/accepted/rejected/retired transitions are idempotent by stable IDs;
- a crash between generated content and acceptance leaves `generated`, not a half-accepted bank item.

## C. Living-Layer Mechanism

### Candidate Capture

During a session, the agent may propose a living-layer candidate when the learner asks about a phrase, fails to understand it,
or the phrase is useful enough to explain. Capture creates no mastery evidence.

Candidate fields:

- `candidate_id`
- normalized unit text and proposed ID
- proposed type/register/transparency
- proposed `usage_policy`, `allowed_contexts`, `neutral_equivalent`
- `meaning_ru`
- `literal_trap_ru` if opaque
- `cultural_context` if `meme_template`
- `first_observed_at` as UTC
- `source_kind` and community
- source pointer metadata or source hash, never the third-party excerpt
- authored context summary
- session id and provider
- proposed `volatility` and `currency`

The candidate is not a `LexicalItem` yet and cannot be scheduled as curriculum content.

### Acceptance Workflow

Only `maintain-english-curriculum` can promote a candidate:

1. normalize and dedup against stable core, living layer, aliases, and tombstones;
2. verify no third-party excerpt is stored;
3. assign type/register/transparency and `usage_policy`;
4. require `allowed_contexts` for `context_dependent`;
5. require `first_observed_at`, `last_verified_at`, `currency`, source metadata for `volatility: changing`;
6. require `cultural_context` for `meme_template`;
7. generate authored examples and neutral paraphrase;
8. validate the candidate;
9. activate through curriculum versioning and emit `LEXICAL_ITEM_ADDED`.

Acceptance adds a curriculum item and may enroll it in the learner lexicon if an enrollment trigger is present. It does not
create evidence of mastery.

### Currency Lifecycle

Recommended lifecycle fields for changing items:

- `first_observed_at`
- `last_verified_at`
- `currency: current | dated | obsolete`
- `volatility: stable | changing`
- `currency_review_after_days` (advisory calibration)
- `source_kind`, `communities`, `neutral_equivalent`

Advisory calibration:

| Item class | Review interval |
|---|---:|
| `meme_template` / highly volatile slang | 30 days |
| changing informal chunks / abbreviations | 90 days |
| stable slang / idioms | 180 days |
| neutral work chunks | 365 days |

Stale-safety rule:

- if `last_verified_at + review_interval < now`, production is suspended by the active safety overlay;
- if an item is marked `dated`, generation treats it as recognition-only unless a policy explicitly asks for historical or
  register-awareness recognition;
- if an item is marked `obsolete`, no new production or review assignments are created, and accepted bank items containing it
  are retired for future delivery.

Obsolete triggers:

- maintainer marks the item obsolete in the maintain workflow;
- repeated currency checks fail;
- learner or maintainer marks the phrase as no longer acceptable in its allowed contexts;
- active usage policy changes the item to `avoid` or removes all allowed contexts.

The append-only event must store both the old effective safety version and the new active safety version so stale-safety
changes are auditable.

## D. Policy for the 591 Unlinked Lexical Items

The 591 unlinked items are not a data-integrity error. They are a coverage policy choice.

### Option 1: Topic-first only

Only items referenced by `topic.lexicon` are eligible for planned topic exercises. Unlinked items enter practice only if the
learner asks about them, makes an error, or they are deliberately added to personal lexicon.

Trade-offs:

- Pro: lessons stay can-do coherent and do not become flashcards;
- Pro: no artificial topic links;
- Con: many valid CORE/HIGH items may never be practiced;
- Con: weak coverage for phrasal verbs, reactions, and idioms that were added after topic bodies.

### Option 2: Lexicon-first micro lane

LexicalItems become first-class growth/review candidates using their `LexicalMasteryProfile`, domains, CEFR, and learner
relevance, even without topic refs.

Trade-offs:

- Pro: covers the full lexicon and personal vocabulary;
- Pro: works well for retention checks and living-layer items;
- Con: can create disconnected flashcard practice;
- Con: needs OPEN-22 learner-priority behavior for missing `frequency_band`.

### Option 3: Auto-link candidates through maintain workflow

A deterministic linker proposes topic refs for unlinked items by CEFR, domains, examples, type, register, and context. The
links are candidates; activation still goes through `maintain-english-curriculum`.

Trade-offs:

- Pro: preserves topic context while expanding coverage;
- Pro: catches obvious unlinked CORE/HIGH items;
- Con: needs human/content review to avoid unnatural links;
- Con: slower than direct lexicon-first scheduling.

Recommendation: hybrid Option 2 + Option 3.

- Use a small lexicon-first lane for learner-requested, observed-error, due-review, and CORE/HIGH safety-safe items.
- Use auto-link candidates to improve topic coverage over time.
- Do not force all 591 items into `topic.lexicon`; a bad link is worse than an unlinked item.

Advisory calibration: reserve at most one lexicon-first growth item per balanced session, unless the session mode is
maintenance or the learner explicitly asks for vocabulary practice.

## PD Forks

### PD-1: When is generated content persisted?

Option A: Persist rendered exercise before tutor presents it, via `EXERCISE_RENDERED`.

- Pro: exact prompt/answers are auditable before learner response;
- Pro: attempts can reference an immutable exercise instance;
- Con: adds one API call between `session next` and learner interaction.

Option B: Persist exercise only together with `attempt record`.

- Pro: fewer protocol steps;
- Con: crash after presenting but before attempt loses the exercise text;
- Con: harder to audit no-excerpt and safety rules for unanswered items.

Recommendation: Option A.

### PD-2: Bank admission timing

Option A: Accept only after at least one assessed attempt or explicit maintainer approval.

- Pro: avoids promoting plausible but broken prompts;
- Con: fewer reusable items early.

Option B: Accept immediately after schema/safety validation.

- Pro: bank grows faster;
- Con: ambiguous prompts enter reuse before being tested.

Recommendation: Option A, with explicit maintainer approval as a fast path.

### PD-3: Currency aging behavior

Option A: Soft stale-safety only. Expired `last_verified_at` suspends production, but `currency` changes only by review.

- Pro: low false-positive risk;
- Con: less automatic cleanup.

Option B: Hard auto-aging. Current becomes dated, then obsolete by fixed timeouts.

- Pro: fully automatic;
- Con: can retire still-useful language silently.

Option C: Hybrid. Expiry auto-suspends production and opens a review task; repeated missed checks or explicit negative review
marks obsolete.

- Pro: protects delivery immediately and avoids silent false obsolescence;
- Con: needs a small review queue.

Recommendation: Option C.

### PD-4: `dated` production eligibility

Option A: `dated` is recognition-only by default.

- Pro: avoids teaching stale phrasing as something to say;
- Con: may be too strict for harmless old idioms.

Option B: `dated` can still be produced if `usage_policy` is safe.

- Pro: less conservative;
- Con: weakens the point of currency lifecycle.

Recommendation: Option A, with explicit context override only for "recognize older usage" tasks.

### PD-5: Unlinked lexicon coverage

Option A: topic-first only.
Option B: lexicon-first micro lane.
Option C: auto-link candidates.
Option D: hybrid micro lane + auto-link candidates.

Recommendation: Option D.

### PD-6: Safety correction event naming

Option A: use domain-specific events: `LIVE_STEP_SAFETY_REJECTED`, `BANK_ITEM_RETIRED`, `LEXICAL_CURRENCY_CHANGED`.

- Pro: clear owner boundaries;
- Con: more event types.

Option B: use generic correction envelope only.

- Pro: fewer event types;
- Con: domain intent becomes harder to inspect.

Recommendation: Option A, carried inside the generic correction/event envelope where kernel requires it.

### PD-7: OPEN-31 boundary

Option A: P.3 only defines safety/lifecycle mechanics; CEFR/register cleanup of idioms/slang remains content-review.

- Pro: keeps P.3 focused on policy machinery;
- Con: some questionable items remain until content review.

Option B: P.3 also reclassifies idiom CEFR/register.

- Pro: resolves more immediately;
- Con: violates the phase-1 no-curriculum-edit scope.

Recommendation: Option A. P.3 touches OPEN-31 only by making unsafe or stale production impossible.

## OPEN Closure Map

### OPEN-14

- Currency lifecycle: covered by candidate fields, review intervals, stale-safety computation, and currency change events.
- Usage-policy lifecycle: covered by active `production_eligible`, `context_dependent` enforcement, and avoid/obsolete handling.
- `production_eligible`: computed at delivery/reuse from active safety, never trusted from pinned manifests or bank snapshots.
- Live manifest stale-safety: `session next` rejects or requires replan if active safety no longer allows the next production step.
- Bank stale-safety: accepted items are revalidated before reuse; unsafe items are retired append-only.
- Living manifest/review assignment replacement: unsafe unpresented review steps are cancelled or replaced through replan, not
  silently delivered.
- `requires_usage_policy`: phase 2 must codify the predicate by type/register and require it in validation.
- `context_dependent`: outside allowed contexts, the item is recognition-only.
- `cultural_context`: required for `meme_template` candidates before activation.
- Lexeme form aggregation: generation records form slots tested; final scoring aggregation remains owned by scoring.

### OPEN-16

- Lifecycle: `generated -> accepted/rejected -> retired`.
- Acceptance criteria: schema, safety, refs, answer key/rubric, no-excerpt, target fit, dedup.
- Promotion: accepted only after assessed use or maintainer approval.
- Invalidation: active safety, target retirement, schema incompatibility, quality flags, duplicate replacement.
- Dedup: canonical key over targets, dimensions, step type, context family, prompt skeleton, answer key, and lexicon refs.
- Provenance: session, step, policy versions, provider, content hash, active safety version.

## Phase 2 Canon Edits Needed

No canon edits are made in phase 1. If the PD forks above are approved, phase 2 should update:

- `wiki/modules/curriculum.md`: living-layer candidate/activation schema, exact `requires_usage_policy` predicate, currency
  validation rules, and stale-safety hooks.
- `wiki/product/lexical-system.md`: effective `production_eligible` formula, `dated` behavior, context-dependent fallback,
  and living-layer lifecycle fields.
- `wiki/modules/lessons.md`: exercise instance binding in the session protocol, likely `EXERCISE_RENDERED` before learner
  attempt, and resume behavior for rendered/unrendered presented steps.
- `wiki/modules/control.md`: how `PlannedStep` exposes generation directives or bank item selection, and how active safety
  rejection maps to replan/cancel.
- `wiki/modules/evidence.md`: attempt references to `exercise_instance_id`, distractor/rubric observation links, and handling
  of flawed generated exercises.
- `wiki/modules/scoring.md`: lexical form-slot evidence consumption and any scoring no-op rules for cancelled unsafe steps.
- `wiki/platform/foundation.md`: only if new event families need policy-registry examples or correction-envelope examples;
  kernel mechanics should not gain business rules.
- `wiki/glossary.md`: define `ExerciseInstance`, `ExerciseBankItem`, `production_eligible`, `stale-safety`, and
  `generation_policy`.
- `wiki/OPEN.md`: move OPEN-14/OPEN-16 to resolved after implementation contract review, not merely after this concept.
- `wiki/roadmap.md`: mark P.3 phase state and dependencies after acceptance.

Non-canon follow-up:

- `staging/handoff/2026-07-21-P2-report.md` records the earlier two-tier grammar snapshot. Current canon/data use
  `big-five | core | tail`; update or supersede that handoff note if future reviewers keep using it.
