# P.5 concept: `rubric@1` for open-response assessment

> Status: concept proposal; no product decision in this document is accepted yet.
> Date: 2026-07-22.
> Canon status: this file is not canon. No `wiki/`, `src/`, `tests/`, or curriculum content is changed.
> Decision gate: phase-2 authoring starts only after the owner explicitly chooses every PD fork below.

## 1. Purpose and boundaries

`rubric@1` is the versioned data contract by which the engine turns a saved open learner response and admissible
observations into an `AttemptAssessment`. It covers open controlled production, spontaneous production, transfer,
writing, and free conversation in the text-only product scope.

The policy does not ask an agent for a ready score. The agent remains a trusted reporter of `raw_answer` and concrete
observations; the engine validates those observations, resolves the pinned rubric, computes criterion results, and derives
`score_ppm`. Only an engine-produced assessment may create `EVIDENCE_ADDED`.

`rubric@1` does not:

- define topic mastery thresholds or required dimensions; those belong to pinned `Topic.mastery_criteria`;
- compute a terminal `ReviewOutcome`; an `AttemptAssessment` remains a per-attempt fact;
- replace `scoring@1`, its `rubric_cap`, session cap, independence rules, or state-transition rules;
- generate exercise text, model answers, or distractors; that remains `generation@1`;
- assign a TOEFL score or reproduce a proprietary external rubric;
- add listening or speaking modalities;
- make historical assessment follow the currently active policy.

All criterion labels, descriptors, examples, and feedback authored in phase 2 must be original project text. No external
rubric wording or third-party excerpt may enter the policy, exercise bank, events, or reports.

## 2. Existing contract and implementation boundary

The concept relies on the following already accepted behavior:

1. `generation@1` allows rubric observations for open classifications and requires `rubric_ref` for open constrained,
   spontaneous, and transfer exercise schemas.
2. `EXERCISE_RENDERED` stores exactly one of `answer_key` or `rubric_ref`, plus the content hash and pinned rubric version,
   before the learner sees a structured exercise.
3. `record_attempt` derives target, dimension, mode, and origin from saved session facts. It stores `raw_answer`, the semantic
   span hash, observations, exercise reference, and pinned versions. The client does not supply classification facts.
4. Objective answers are assessed immediately. Open answers currently remain `recorded`; their observations are stored but
   are not yet interpreted or validated.
5. The scoring fold already distinguishes `assessment_basis != objective_check` and applies `rubric_cap`. It currently gates
   positive gain on `correct` and does not use `score_ppm` as a graded multiplier. If PD-2 chooses graduated levels, the 2.3
   consumer must explicitly consume the engine-produced `score_ppm`; otherwise a graduated rubric would be collapsed back
   to a Boolean and its apparent precision would be false.
6. A rubric-derived assessment may not promote knowledge state by itself. Rubric/informal promotion requires evidence from
   at least two independent sessions, where independence is derived from prompt, context, and interval rather than session ID.

The phase-2 payload is data. Validation, observation processing, atomic attempt settlement, and scoring consumption remain
owner work in 2.3 and must be implemented against the accepted payload rather than inferred from prose.

## 3. Non-negotiable invariants

These requirements come from the current evidence, scoring, learning-model, and generation contracts rather than from the
open PD choices.

1. **Engine classification only.** Agent input MUST NOT contain `criterion_satisfied`, a criterion level, a criterion score,
   `score_ppm`, `correct`, `ReviewOutcome`, or a mastery delta.
2. **Concrete observation.** Each subjective observation MUST identify a concrete rubric criterion, an allowed atomic
   finding code, and an exact span or error in the saved `raw_answer`. A finding about an absence may anchor to the whole
   answer, but it may not omit the answer reference.
3. **One rejection branch.** An observation unsupported by the raw answer, the stored rendered exercise, or the pinned policy
   is `rejected` with a stable audit reason and contributes nothing. There is no “flagged but counted” path.
4. **Machine/subjective separation.** Machine checks are executed by code from a closed operation set. Subjective findings
   are reported under the accepted trust model and remain subject to rubric/informal caps. A subjective claim cannot override
   a contradictory machine result.
5. **Pinned resolution.** Historical assessment resolves the exact rubric policy version pinned by the session/exercise. A
   missing pinned version is `PinnedPolicyUnavailable`; there is no fallback to the active version or another profile.
6. **Deterministic arithmetic.** Decision values use integers or decimal strings only. Criterion aggregation uses the pinned
   scoring Decimal context (precision 28, `ROUND_HALF_EVEN`) or an exactly equivalent integer algorithm. IEEE floats are
   forbidden.
7. **Deterministic order.** Criteria and observations are processed by stable IDs, not YAML insertion order, provider order,
   hash iteration order, or localized display text.
8. **Captured result.** Accepted and rejected observations, machine-check results, criterion results, `score_ppm`, rubric ref,
   pinned rubric version, and calculation inputs are captured in the assessment event. Scoring replay consumes the captured
   fact in event sequence order and never asks an agent to reassess history.
9. **Atomic settlement.** Transition of an open attempt out of `recorded` and any resulting `EVIDENCE_ADDED` commit in one
   Unit of Work. A crash may leave a recoverable recorded attempt or a complete settlement. A contributing assessment never
   exists without its evidence, evidence never exists for a pending attempt, and an explicitly non-contributing settlement
   records why no `EVIDENCE_ADDED` was emitted.
10. **Semantic identity remains authoritative.** Rubric evaluation does not mint a second evidence fact from the same source
    span for the same target/dimension. Repeated assessment is idempotent by attempt and assessment fingerprint.
11. **Mastery ownership.** A rubric interprets the quality of one response. It MUST NOT override required dimensions,
    `active_threshold`, retention requirements, mode weights, `rubric_cap`, or state transitions.
12. **Rubric basis cannot evade the cap.** An open response assessed through a rubric remains `assessment_basis: rubric` even
    if some or all of its individual criteria are machine-checkable.
13. **No negative mastery from one miss.** A low rubric score may yield no positive gain. Mastery reduction still requires a
    confirmed `REGRESSION` through the scoring contract.
14. **No target, no mastery evidence.** A targetless conversational turn may be stored and assessed for audit, but it cannot
    create contributing evidence until a target/dimension is derived from a saved step or assignment.
15. **Own text only.** Policy descriptors, feedback, example observations, and any model material are original project text.

## 4. Proposed `rubric@1` payload shape

This is a conceptual shape, not phase-2 YAML. Exact fields depend on the PD decisions.

### 4.1 Header and deterministic contract

The payload should contain:

- `policy_id: "rubric@1"`;
- `schema_version`;
- `status: "accepted"` only after owner approval;
- the decision record containing all accepted PD choices;
- `canonical_encoding: "kernel.canonical_json_v1"`;
- an integer/string-only numeric rule and the fixed rounding rule;
- `own_text_rule`;
- stable assessment algorithm and normalization algorithm identifiers.

### 4.2 Criterion catalog

A reusable criterion definition should declare:

- stable `criterion_id` and authored description;
- `kind: machine | subjective | mixed`;
- allowed dimensions and task families;
- allowed atomic finding codes;
- machine-check operation and parameter schema, where applicable;
- deterministic rules mapping accepted findings and machine results to a level value;
- stable audit and learner-feedback keys;
- whether the criterion is required when selected by a profile.

Finding codes describe inspectable facts, for example `target_surface_present`, `required_claim_missing`,
`reason_supports_claim`, `reference_is_ambiguous`, or `register_mismatch_at_span`. They do not say “pass”, “satisfied”,
“level 2”, or “score 700000”. The policy owns the mapping from a set of findings to a criterion result.

### 4.3 Rubric profiles

A rubric profile should declare:

- stable `profile_id`;
- allowed dimensions, step types, and task families;
- its selected criterion IDs;
- one integer weight per selected criterion;
- fixed applicability rules evaluated from the saved exercise before the answer is scored;
- completeness requirements;
- error bindings and criterion-local severity effects;
- a deterministic calculation rule;
- optional feedback ordering that does not affect the score.

The criterion set applicable to a rendered exercise must be fixed before assessment and included in the rendered content
hash or an equally immutable rubric-input snapshot. A missing observation must never make the engine silently remove a
criterion and renormalize the remaining weights.

Candidate task-family profiles, subject to PD-1, are:

- `production.controlled`;
- `production.spontaneous`;
- `conversation.free`;
- `transfer.open`;
- `writing.short-response`;
- `writing.correspondence`;
- `writing.academic-argument`;
- `writing.academic-source-integration`.

These are project assessment profiles, not external exam score rubrics. Shared criteria such as target control, clarity, task
fulfilment, organization, and register should be defined once and reused where their evidence semantics are genuinely the
same.

### 4.4 Default map and namespace

The policy should contain a total, validated default map for only the step/dimension combinations that are allowed to omit an
explicit ref. Every resolved default is materialized as a concrete `rubric_ref` in the stored exercise or assessment fact.
There is no runtime “best match” search.

### 4.5 Typical-error catalog and bindings

Current topic `typical_errors` values are authored strings rather than objects with stable IDs. A list index is not a stable
reference: insertion or reordering would silently retarget old observations. Without changing topic bodies, a stable ref can
be derived from the pinned topic ID and the full canonical hash of the NFC-normalized exact error text:

```text
topic-error:<topic_id>#sha256:<64-lowercase-hex>
```

The digest is `sha256(kernel.canonical_json_v1({topic_id, typical_error: NFC(text)}))`, not a hash of an ambiguous
concatenated string.

The rendered exercise should capture the resolved ref and authored error text or its hash. A later curriculum version that
changes the text creates a new ref; the old ref remains resolvable through the pinned curriculum version.

Rubric policy should bind an error ref or error family to:

- one policy-owned severity;
- exactly one score-bearing criterion, preventing accidental double subtraction;
- zero or more diagnostic criteria for feedback only;
- allowed machine matcher IDs or subjective finding codes;
- a deterministic criterion-level effect.

The agent reports the observed error ref and span. It does not choose severity or penalty.

## 5. Observation contract

### 5.1 Subjective input

Recommended observation shape:

```yaml
rubric_criterion_ref: "rubric:writing.academic-argument#criterion:claim-support"
finding_code: "reason_supports_claim"
span_ref:
  start_utf8: 18
  end_utf8: 74
  span_hash: "sha256:..."
topic_error_ref: null
distractor_error_ref: null
```

Offsets are proposed as a half-open range over the exact UTF-8 bytes of saved `raw_answer`; the engine verifies boundaries,
hash, non-empty content, and ownership by that attempt. This avoids provider-dependent UTF-16/code-point indexing. For an
absence finding, the policy may require a whole-answer span plus the relevant rendered requirement. An error ref may
supplement, but never replace, `rubric_criterion_ref` and the raw-answer anchor.

The engine rejects an observation when any of these holds:

- the criterion/profile/ref does not resolve under the pinned rubric;
- the finding code is not allowed for the criterion;
- the span is outside the exact saved answer, is empty when not allowed, or its hash differs;
- an error ref does not resolve under the pinned curriculum or rendered distractor snapshot;
- a finding requires exercise context that is absent from `EXERCISE_RENDERED`;
- the same finding/span/error occurrence is duplicated;
- it contradicts an authoritative machine result;
- it targets a criterion not applicable to this exercise.

Stable rejection codes, rather than free-form exception text, should be stored for replay and audit.

### 5.2 Engine-produced machine observations

Machine checks should emit the same normalized result form, but with `reported_by: engine` and the operation/configuration
hash. The agent cannot supply or override these records. Machine checks execute over exact saved inputs only:
`raw_answer`, rendered prompt/configuration, pinned target surfaces, and stored rubric inputs.

### 5.3 Consistency and aggregation

The engine canonicalizes accepted observations by:

```text
criterion_ref asc
finding_code asc
start_utf8 asc
end_utf8 asc
error_ref asc
```

It then deduplicates identical occurrences, applies machine precedence, maps the remaining fact set through the criterion's
pinned rule, and records both accepted and rejected dispositions. Subjective observations remain auditable separately from
machine facts even when both affect one mixed criterion.

## 6. Deterministic machine-check boundary

The recommended v1 boundary is a closed enum of small operations, each with a versioned algorithm and schema:

- `nonempty_after_trim`;
- `unicode_scalar_count_between`;
- `token_count_between` using one named NFC tokenizer algorithm;
- `paragraph_count_between` after canonical CRLF/LF normalization;
- `required_literal_sequence_any`;
- `required_literal_sequence_all`;
- `forbidden_literal_sequence_none`;
- `required_target_surface_any`, using surface variants resolved from pinned curriculum and captured at render;
- `required_section_label_sequence`, only when the rendered prompt explicitly requires those authored labels.

Literal operations declare whether they use exact NFC comparison or NFC + casefold + whitespace collapse. A matcher is data,
not an arbitrary regex or executable expression. The exact matcher inputs and algorithm ID become part of the rendered
rubric-input snapshot.

“Forbidden calque” is machine-checkable only when the policy/rendered exercise supplies an exact authored surface sequence.
The engine cannot deterministically infer a semantic calque from arbitrary prose. The following remain subjective in v1:

- grammatical correctness beyond declared literal/target-form checks;
- semantic relevance, factual support, and source synthesis;
- coherence, naturalness, style, register, and pragmatic appropriacy;
- whether an argument is convincing;
- general plagiarism or third-party-source detection;
- vocabulary range and paraphrase quality beyond declared surface matches.

Length and structure checks are task-compliance signals, not proxies for language quality. Passing them alone must not award a
high holistic writing score.

## 7. Assessment pipeline and crash behavior

### 7.1 Resolution and render

1. Session start pins rubric policy version alongside curriculum/scoring/generation versions.
2. For a rendered open exercise, the engine resolves the explicit or allowed default `rubric_ref` against that pinned version.
3. It validates profile compatibility with the saved step's dimension/type, resolves fixed applicability and machine-check
   inputs, and stores the concrete ref, pinned version, and rubric-input hash in `EXERCISE_RENDERED` before presentation.
4. An unknown ref, incompatible profile, or missing pinned policy prevents render. It never falls back to active rubric.

For an unrendered `free_conversation` turn, the pinned default is resolved during assessment from the saved step type and
dimension, then materialized in the assessment event. No target/dimension means no contributing evidence.

### 7.2 Attempt assessment

1. Load the recorded attempt, saved step, optional rendered exercise, and pinned rubric.
2. Revalidate the attempt/exercise relation and semantic identity.
3. Resolve the exact criterion set and execute all machine checks in stable order.
4. Validate and disposition subjective observations.
5. Apply the completeness rule selected in PD-7.
6. Compute criterion levels and `score_ppm` under the pinned algorithm.
7. In one Unit of Work, update the attempt disposition and append assessment/audit events plus `EVIDENCE_ADDED` when the
   attempt is admissible and targeted.

The atomic write captures at least:

- `attempt_id`, session, step, exercise instance, target/dimension, mode, origin, and semantic span hash;
- resolved `rubric_ref`, pinned rubric version, rubric-input/configuration hash, and algorithm ID;
- sorted accepted and rejected observations with stable reasons;
- machine-check results;
- per-criterion weight, level, level PPM, and calculation trace;
- final integer `score_ppm` and `assessment_basis: rubric`;
- hints and engine-derived independence inputs;
- full `CreditAllocation[]` and selection basis.

An assessment retry with the same attempt and calculation fingerprint is idempotent. A retry that would produce a different
assessment is a conflict or explicit correction, never a silent overwrite. Policy activation after render cannot change the
historical result.

### 7.3 Scoring boundary

The rubric engine produces response quality in `score_ppm`; scoring owns its mastery effect. Under the recommended graduated
scale, scoring should use:

```text
quality = Decimal(score_ppm) / Decimal(1000000)
positive_delta = base_delta * mode_weight * hint_independence * quality
```

Then the existing per-session cap, rubric cap, origin rules, and monotonicity rules apply. Zero quality adds no mastery;
negative mastery still requires confirmed regression. The rubric policy must not contain a topic `active_threshold` or decide
a state transition.

Whether an assessment is strong enough to contribute to a later `CONFIRMED` outcome is a scoring/review policy question, not
an agent-supplied Boolean. If the event retains a compatibility `correct` field, the engine must derive it from an accepted
pinned rule; clients never send it and scoring must not use it to discard the graduated quality factor.

## 8. Suggested criterion mechanics by response family

This section illustrates semantics; it does not pre-accept profile granularity or numeric calibration.

| Response family | Candidate criteria | Typical evidence |
|---|---|---|
| Open controlled production | target-form control, required meaning, task compliance, local intelligibility | declared target surface, transformation relation, concrete form/error spans |
| Spontaneous production | target use in a new sentence, meaning clarity, contextual fit, independence from prompt wording | target-use span, relevant clause, context mismatch or prompt-copy finding |
| Free conversation | relevance to the turn, intelligibility, spontaneous target use, register fit | learner-turn spans tied to a saved target/assignment |
| Open transfer | preserved target meaning, adaptation to new context, register/context fit | source/new-context relation and concrete rewritten spans |
| Short writing/correspondence | task fulfilment, organization, language control, lexical appropriacy, register | request/response spans, linking spans, local errors |
| Academic argument | claim, development, organization, language control, academic register | claim span, reason/evidence relations, paragraph links, error spans |
| Academic source integration | source-role accuracy, synthesis, attribution boundaries, organization, language control | spans mapped to saved authored source facts and response claims |

The integrated profile must assess only against project-authored source material saved in the exercise snapshot. It must not
store or evaluate third-party excerpts.

## 9. PD forks requiring owner approval

No recommendation below is a decision until the owner explicitly approves it.

### PD-1: Rubric granularity

**Option A — one universal profile per dimension.**

- Benefits: smallest payload and simplest defaulting.
- Costs: `spontaneous_production` in a chat and source-integrated academic writing would share criteria that do not describe
  the same evidence; weights become vague compromises.

**Option B — independent profile for every track and step type.**

- Benefits: exact task fit.
- Costs: duplicated criteria, inconsistent wording and weights, large calibration surface, and profile explosion as B1-C2
  topics grow.

**Option C — shared criterion catalog plus task-family profiles, with a track-specific profile only when evidence semantics
materially differ.**

- Benefits: reusable definitions with real specialization for conversation, correspondence, academic argument, and source
  integration; avoids both universal vagueness and per-topic duplication.
- Costs: requires profile composition/validation and an explicit `rubric_ref` for specialized tasks.

**Recommendation: Option C.** Specialize by response family, not by individual topic. Source integration is materially
different from chat; target-form control is reusable across many profiles.

### PD-2: Criterion scale and `score_ppm`

**Option A — binary criterion results.**

- Benefits: directly matches the current scoring fold's `correct` gate and is easy to explain.
- Costs: loses meaningful partial performance in writing and spontaneous production; a nearly adequate response and an empty
  failure collapse to the same result.

**Option B — uniform four-level criterion scale.**

- Levels are policy-owned integers `0 | 1 | 2 | 3` mapped to integer PPM values such as
  `0, 333333, 666667, 1000000`.
- Profile weights are positive integer units and should sum to a validator-enforced constant such as `10000`.
- Calculation is:

```text
numerator = sum(weight_units_i * level_ppm_i for criterion_i in canonical_order)
score_ppm = ROUND_HALF_EVEN(numerator / sum(weight_units_i)) to an integer
```

- Benefits: real partial credit with one total, deterministic formula.
- Costs: criterion rules must define observable distinctions between four levels; the scoring consumer must apply
  `score_ppm` as a quality factor rather than collapse it to `correct`.

**Option C — criterion-specific arbitrary level counts.**

- Benefits: maximum author flexibility.
- Costs: hard to validate, compare, explain, and calibrate; encourages invented precision.

**Recommendation: Option B.** Four levels are enough to distinguish absent, limited, adequate, and strong evidence without
pretending to continuous linguistic precision. Exact level descriptors and weights are calibration data; any proposed
numbers are advisory until accepted in a versioned payload.

### PD-3: Machine-checkable operation set

**Option A — closed versioned opcode list.**

- Includes only deterministic checks listed in §6.
- Benefits: replayable, testable, and safe; every operation has an exact input schema.
- Costs: grammar, semantics, and most style judgments remain subjective.

**Option B — policy-provided regex/expression DSL.**

- Benefits: content authors can add checks without engine releases.
- Costs: regex flavor/runtime drift, pathological patterns, ambiguous token semantics, and a much larger validator surface.

**Option C — ask the model to run “machine” checks.**

- Benefits: broad language coverage.
- Costs: not machine-checkable, not deterministic, and violates the engine-classification boundary.

**Recommendation: Option A.** Extend the enum through new policy/engine versions only when a check has a precise deterministic
contract. Exact authored forbidden-calque strings are allowed; semantic calque detection is not.

### PD-4: `typical_errors`, severity, and score effect

**Option A — diagnostic links only.**

- Benefits: no double penalties.
- Costs: the scoring contract's error-severity input remains unused.

**Option B — subtract one global penalty per observed error.**

- Benefits: simple arithmetic.
- Costs: one error may already lower a criterion level, so a second global subtraction double-counts it; long answers are
  mechanically punished for having more observable spans.

**Option C — policy-owned severity with one criterion-local score effect.**

- Each stable topic-error binding declares `minor | major | blocking` and exactly one score-bearing criterion.
- The error changes that criterion's finding set, level, or ceiling; it is not subtracted again globally.
- Agent input contains only error ref and span.
- Benefits: severity affects quality without double deduction; replay is deterministic and topic errors remain traceable.
- Costs: phase-2 authoring must bind errors carefully. Current string-only errors require the content-addressed ref described
  in §4.5.

**Recommendation: Option C.** Severity belongs to policy/content, never to the reporting agent. Use diagnostic-only links for
additional criteria.

### PD-5: `rubric_ref` namespace and version resolution

**Option A — versionless internal ref plus external policy pin.**

- Profile: `rubric:<profile_id>`.
- Criterion: `rubric:<profile_id>#criterion:<criterion_id>`.
- `pinned_rubric_version` supplies the policy version.
- Benefits: one source of version truth; activation cannot create conflicting embedded/pinned versions.
- Costs: every assessment must carry and validate the external pin.

**Option B — embed version in every ref, for example `rubric:<profile_id>@1`.**

- Benefits: a ref looks self-contained.
- Costs: duplicates session/event pinning and creates a conflict branch when embedded and pinned versions differ.

**Option C — free-form refs interpreted by the agent.**

- Benefits: no schema work.
- Costs: dangling refs and non-replayable interpretation.

**Recommendation: Option A.** Resolve at render against the session-pinned rubric, store the concrete ref and pin, and resolve
the same pinned version at assessment. Missing pinned content fails closed with no active/alias fallback.

### PD-6: Default rubric when an exercise omits `rubric_ref`

**Option A — one universal open-response fallback.**

- Benefits: no open attempt remains pending because a ref was omitted.
- Costs: silently scores academic writing as conversation or controlled production as generic prose.

**Option B — exact `(step_type, dimension)` default table, materialized before scoring.**

- Proposed entries include `free_conversation + spontaneous_production -> rubric:conversation.free`,
  `controlled_production + controlled_production -> rubric:production.controlled`, and
  `spontaneous_production + spontaneous_production -> rubric:production.spontaneous`.
- Specialized writing/source-integration exercises still require an explicit profile because step type alone cannot identify
  their evidence semantics.
- Missing exact mapping is a render/assessment error, not a broad fallback.
- Benefits: safe recovery for genuinely generic tasks without hidden best-match behavior.
- Costs: the table must be total for every omission the generator permits.

**Option C — no defaults; every open task must carry an explicit ref.**

- Benefits: maximum explicitness.
- Costs: free conversation without an exercise snapshot has nowhere to store a ref before the attempt; one omission can keep
  session finish blocked.

**Recommendation: Option B.** Defaults are resolution rules, not implicit scoring. Store the chosen ref in
`EXERCISE_RENDERED` when one exists and in the assessment fact for unrendered conversation.

### PD-7: Missing or rejected required observations

**Option A — treat missing criterion evidence as level zero.**

- Benefits: every attempt receives a score.
- Costs: transport/reporting failure becomes a false learner failure and may later contribute to regression.

**Option B — omit uncovered criteria and renormalize weights.**

- Benefits: produces a score from partial observations.
- Costs: missing weak areas inflate the result; two identical answers can score differently depending on reporter coverage.

**Option C — no score without complete required coverage; settle an explicitly finalized incomplete attempt as
`insufficient_evidence`, non-contributing.**

- Invalid observations are still individually `rejected` with reasons.
- Before finalization, the attempt may remain `recorded` so the reporter can supply corrected spans.
- On explicit finalization with incomplete coverage, the engine stores the audit and settles the attempt without
  `EVIDENCE_ADDED`; it does not invent zero and does not block finish forever.
- Benefits: separates learner performance from assessment failure and preserves the finish invariant.
- Costs: needs a clear finalize/retry boundary in 2.3.

**Recommendation: Option C.** Missing assessor evidence is not evidence of learner failure. Completeness must be computed by
the engine from required criteria, not asserted by the agent.

## 10. Recommended decisions as one coherent package

The recommended set is:

```text
PD-1 C
PD-2 B
PD-3 A
PD-4 C
PD-5 A
PD-6 B
PD-7 C
```

Together these choices yield a compositional but bounded policy: concrete task-family profiles reuse stable criteria; agents
report spans and atomic findings; a closed machine layer checks only what code can prove; the engine maps all accepted facts
to uniform graduated levels and integer PPM; missing assessment coverage never becomes a false low score.

## 11. Phase-2 artifacts after approval

No item in this section is authorized until all PD forks are approved.

### Direct artifact

`curriculum/policies/rubric-v1.yaml` should contain the accepted header, criterion catalog, profiles, machine opcode schemas,
typical-error severity bindings, namespace/resolution rules, default table, completeness behavior, and calculation algorithm.
All decision numbers must be integers or decimal strings; YAML floats are forbidden. Registration/consumption hooks remain
owner implementation work.

### Proposed canon patches only

Phase 2 should provide copy-applicable OLD → NEW proposals, not edit canon directly, for:

- `wiki/modules/evidence.md`: exact observation fields, UTF-8 span validation, accepted/rejected disposition, completeness,
  attempt settlement, assessment event capture, and idempotency;
- `wiki/modules/scoring.md`: graduated `score_ppm` consumption, rubric basis/cap, and the boundary between response quality and
  topic mastery criteria;
- `wiki/product/learning-model.md`: atomic finding codes as trusted observations rather than agent-supplied levels;
- `wiki/modules/lessons.md`: pinned rubric resolution and concrete ref/rubric-input capture in `EXERCISE_RENDERED`, including
  unrendered free conversation;
- `wiki/modules/curriculum.md`: validation of stable typical-error references only if the accepted design requires more than
  content-addressed refs;
- `wiki/glossary.md`: `rubric_policy`, `rubric_profile`, `rubric_criterion_ref`, machine finding, and subjective finding;
- `wiki/OPEN.md`: resolution status only after the contract and payload are accepted and the engine consumer is scheduled;
- `wiki/roadmap.md`: P.5 state and the concrete dependency into 2.3;
- `wiki/platform/foundation.md`: only if a policy-registry example is genuinely necessary; no rubric business rule belongs
  in the kernel.

### Owner implementation dependencies

The accepted payload will require 2.3 to:

- register/activate policy kind `rubric` and ensure Session Manifest pinning is non-null;
- validate and resolve refs at render/assessment with no active fallback;
- capture rubric inputs needed by machine checks in the rendered snapshot/content hash;
- validate observations and run machine checks;
- settle attempt status and emit assessment/evidence atomically;
- apply graded `score_ppm` under scoring caps if PD-2 B is accepted;
- expose stable audit reasons without accepting client-computed classification.

## 12. Acceptance checks for the future payload and consumer

After phase 2 and owner integration, reproducible validation should prove:

1. YAML parses and contains no float values at any depth.
2. Every profile criterion resolves; every weight is a positive integer; every profile has a deterministic non-zero total.
3. Every allowed finding code resolves to one criterion rule; every machine opcode is from the closed set.
4. Every default key is unique and every default profile is compatible with its step/dimension pair.
5. Unknown, retired, or unavailable pinned rubric versions never fall back to active.
6. Agent-supplied score/level/satisfied fields are rejected.
7. Invalid span/hash/error refs produce only rejected observations and zero contribution.
8. Observation input order and process hash seed do not change criterion trace or `score_ppm`.
9. Crash at any point of assessment leaves either a recorded attempt or a complete atomic assessment/evidence pair.
10. Retrying the same assessment is idempotent; a different result requires an explicit correction path.
11. Machine/subjective mixed assessments remain rubric-basis and obey `rubric_cap`.
12. Missing required observation coverage follows the accepted PD-7 behavior and never silently renormalizes.
13. One rubric assessment cannot promote knowledge state; independent-session requirements remain enforced downstream.
14. No criterion, descriptor, example, or test fixture contains borrowed external text.
