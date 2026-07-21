# P.3 phase 2 canon patch proposals

> Date: 2026-07-21.
> Status: proposal only.
> Source concept: `staging/concepts/2026-07-21-P3-generation-concept.md`.
> Accepted PD decisions: PD-1 A, PD-2 A, PD-3 C, PD-4 A, PD-5 D, PD-6 A, PD-7 A.
> Apply rule: copy the `NEW` fragments into `wiki/` only after owner verification.

These patches intentionally do not edit `wiki/`. They describe the canon changes
needed to make `generation@1`, exercise bank lifecycle, and living-layer safety
mechanics normative.

## Summary

| Wiki file | Proposed edits | PD coverage |
|---|---:|---|
| `wiki/modules/curriculum.md` | 6 | PD-3, PD-4, PD-5, PD-6 |
| `wiki/product/lexical-system.md` | 4 | PD-3, PD-4, PD-5, PD-7 |
| `wiki/modules/lessons.md` | 4 | PD-1, PD-2 |
| `wiki/modules/control.md` | 5 | PD-1, PD-3, PD-4, PD-5, PD-6 |
| `wiki/modules/evidence.md` | 4 | PD-1, PD-2 |
| `wiki/modules/scoring.md` | 3 | PD-3, PD-4 |
| `wiki/glossary.md` | 4 | PD-1, PD-2, PD-3, PD-4, PD-5 |
| `wiki/OPEN.md` | 4 | PD-1, PD-2, PD-3, PD-4, PD-5, PD-6, PD-7 |
| `wiki/roadmap.md` | 4 | PD-1, PD-2, PD-3, PD-4, PD-5, PD-6, PD-7 |

`wiki/platform/foundation.md` is not patched: PD-6 uses domain events carried in
the existing kernel event/correction envelope; no foundation business example is
required.

---

## `wiki/modules/curriculum.md`

### Curriculum patch 1 — LexicalItem fields

Concept: C. Living-layer mechanism. PD: PD-3 C, PD-4 A, PD-5 D.

OLD:

```markdown
| `LexicalItem` | единица лексикона ([[../product/lexical-system]]) | id, type, `frequency_band`, `curriculum_priority_band`, register, usage_policy, source_refs… |
```

NEW:

```markdown
| `LexicalItem` | единица лексикона ([[../product/lexical-system]]) | id, type, `frequency_band`, `curriculum_priority_band`, register, usage_policy, allowed_contexts?, volatility, currency, first_observed_at?, last_verified_at?, source_refs…; `production_eligible` вычисляется по active safety, не хранится как канон-истина |
```

### Curriculum patch 2 — living layer mechanics

Concept: C. Living-layer mechanism. PD: PD-3 C, PD-5 D, PD-7 A.

OLD:

```markdown
### Каталоги лексикона

- **stable core** — проектируется заранее (П.4) из источников ниже;
- **living layer** [PD-2026-07-21, supersedes P0-9] — мемы, сленг и форумные единицы, встреченные во время обучения; добавляются через `maintain-english-curriculum` workflow с provenance (`first_observed_at`, источник, `currency`). **В продукте целиком**: workflow-пополнение, currency-lifecycle и авто-устаревание строятся — работа ложится в П.3 вместе с currency/usage-policy lifecycle (OPEN-14). Прежняя отложка «механизм в MVP не строится» снята: у личного тренажёра нет MVP-фазировки контента. Поля `volatility`/`currency`/`first_observed_at` обязательны, как и были; постоянный запрет сторонних excerpts (§3.1) не меняется;
- **learner lexicon** — личный словарь; живёт в модуле learner, не здесь.
```

NEW:

```markdown
### Каталоги лексикона

- **stable core** — проектируется заранее (П.4) из источников ниже;
- **living layer** [PD-2026-07-21, supersedes P0-9] — мемы, сленг, форумные единицы и новые рабочие выражения, встреченные во время обучения. Входной объект — `LivingLexicalCandidate`, а не `LexicalItem`: он создаёт no-evidence candidate с provenance (`candidate_id`, normalized unit text, proposed id/type/register/transparency/usage_policy, `allowed_contexts` при `context_dependent`, `neutral_equivalent`, `meaning_ru`, `literal_trap_ru` при `opaque`, `cultural_context` при `meme_template`, `first_observed_at`, source kind/community, source pointer/hash, authored context summary, session/provider, proposed volatility/currency). Candidate не schedulable и не участвует в mastery до promotion.
- **living-layer activation** [P.3, PD-2026-07-21]: только `maintain-english-curriculum` может превратить candidate в `LexicalItem`: normalize+dedup against stable core/living/aliases/tombstones → no-excerpt check → type/register/transparency/usage_policy assignment → `allowed_contexts` для `context_dependent` → currency/provenance fields для `volatility: changing` → `cultural_context` для `meme_template` → authored examples/neutral paraphrase → validate → activate curriculum version → emit `LEXICAL_ITEM_ADDED`. Acceptance может enroll item в learner lexicon по отдельному trigger, но не создаёт evidence.
- **currency lifecycle** [P.3, PD-2026-07-21]: `currency: current | dated | obsolete`; истёкший review interval автоматически suspend-ит production и создаёт review task; `obsolete` ставится explicit negative review или после repeated missed checks по policy. `dated` — recognition-only по умолчанию, с override только для historical/register-awareness recognition tasks. Постоянный запрет сторонних excerpts (§3.1) не меняется.
- **unlinked lexicon coverage** [P.3, PD-2026-07-21]: отсутствие `topic.lexicon`-ссылки не integrity-error. Unlinked items могут попадать в практику через lexicon-first micro lane (advisory: не более одного growth item за balanced session, кроме maintenance/vocabulary-request) и через auto-link candidates в `maintain-english-curriculum`; плохая topic-ссылка хуже отсутствующей.
- **learner lexicon** — личный словарь; живёт в модуле learner, не здесь.
```

### Curriculum patch 3 — public API and domain events

Concept: C. Living-layer mechanism. PD: PD-3 C, PD-5 D, PD-6 A.

OLD:

```markdown
| `validate(version_or_candidate)` | API | валидация **кандидата или версии** до активации (rereview E-R2) | `[mvp]` |
| `activate(version, expected_active)` | API | атомарная активация: требует успешный validate + CAS по expected_active, публикует событие | `[mvp]` |
| `CURRICULUM_VERSION_ACTIVATED` | publishes | активация новой версии (эмитится `activate`) | `[mvp]` |
| `LEXICAL_ITEM_ADDED` | publishes | пополнение living layer | `[mvp]` [PD-2026-07-21] |
```

NEW:

```markdown
| `validate(version_or_candidate)` | API | валидация **кандидата или версии** до активации (rereview E-R2), включая living-layer no-excerpt/currency/usage fields | `[mvp]` |
| `activate(version, expected_active)` | API | атомарная активация: требует успешный validate + CAS по expected_active, публикует событие | `[mvp]` |
| `record_living_candidate(candidate, idempotency_key)` | API | сохраняет `LivingLexicalCandidate` из сессии; evidence не создаёт | `[mvp]` [P.3] |
| `review_living_candidate(candidate_id, decision, idempotency_key)` | API | `maintain-english-curriculum` принимает/отклоняет candidate; promotion идёт через новую curriculum version | `[mvp]` [P.3] |
| `record_currency_review(item_id, decision, idempotency_key)` | API | фиксирует currency review, меняет active safety через новую версию/overlay | `[mvp]` [P.3] |
| `CURRICULUM_VERSION_ACTIVATED` | publishes | активация новой версии (эмитится `activate`) | `[mvp]` |
| `LIVING_LEXICAL_CANDIDATE_OBSERVED` | publishes | candidate из живой сессии; хранит source pointer/hash и authored summary, не excerpt | `[mvp]` [P.3] |
| `LEXICAL_ITEM_ADDED` | publishes | promotion living-layer candidate в LexicalItem | `[mvp]` [PD-2026-07-21] |
| `LEXICAL_CURRENCY_REVIEW_DUE` | publishes | истёк review interval; production suspended до проверки | `[mvp]` [P.3] |
| `LEXICAL_CURRENCY_CHANGED` | publishes | append-only изменение effective currency/safety с old/new active versions | `[mvp]` [P.3, PD-6 A] |
```

### Curriculum patch 4 — safety, validation, and production eligibility

Concept: A/C. Generation policy and living-layer mechanism. PD: PD-3 C, PD-4 A, PD-6 A.

OLD:

```markdown
- **MUST — safety не пинится (safety-overlay)** [PD-2026-07-19, rereview G-R1]: пинятся только scoring/структура/rubric. `production_eligible` (из active usage_policy+currency) проверяется по **active** policy в момент доставки, не по pinned-версии. Прошлое evaluation/replay детерминировано по pinned; но live manifest / review assignment / банк / placement-форма перед доставкой production сверяются с active safety, и ставший `avoid`/`obsolete`/вне-контекста item отменяется/заменяется append-only event с обеими версиями. Scope stale-safety **включает live manifests**, владельцы — [[../OPEN]] OPEN-14 (+0.5 live delivery).
- **MUST — enforcement активации** [ревью E-5]: `validate`/`activate` энфорсят schema, provenance и целостность **независимо от способа правки файла**; невалидная версия не активируется. (Отдельный attestation-протокол в MVP не вводится — осознанный отказ от gate-машинерии, [[../README]].)
- **MUST**: изменения программы проходят `maintain-english-curriculum` workflow с последующей валидацией.
- **MUST — `production_eligible` и predicate** [rereview H-R1]: production/scheduler используют вычисляемый `production_eligible`; `obsolete` исключает production и новые assignments. `requires_usage_policy` — predicate по type/register, а не только по «informal-единица»: рискованный `type: word`/register тоже обязан иметь usage_policy.
- **MUST**: валидация ловит: циклы advisory-графа; битые ссылки prerequisites/lexicon/module/track/source_refs; дубли ID; prerequisite с CEFR выше уровня темы; пустые dimensions или отсутствие `mastery_criteria`/`LexicalMasteryProfile` на required dimension; отсутствие can_do; тему трека Grammar Engine без `frequency_tier` [PD-2026-07-21]; единицу, для которой `requires_usage_policy=true`, без `usage_policy`; `context_dependent` без `allowed_contexts`; `volatility: changing` без полного набора (`first_observed_at`/`last_verified_at`/`currency`/источник); `meme_template` без нейтрального объяснения **или `cultural_context`** (rereview H-R1); импортированную единицу без `source_refs`/SourceArtifact **или без `transformations`** (rereview I-R3); сторонние excerpts в living layer (постоянное правило).
- **MUST NOT — living layer excerpts** [PD-2026-07-20, rereview I-R2]: **постоянно** запрещено хранить сторонние excerpts (текст forum post/example) — мотив ToS площадок и персональные данные, независимо от лицензий. Разрешены: source-метаданные, короткая сама единица (выражение/сокращение) и **собственный** нейтральный парафраз/объяснение.
- **MUST**: informal-единицы с `usage_policy: avoid`/`recognition_only`/`currency: obsolete` не попадают в production и не рекомендуются — только на понимание; банк/формы/live manifests ре-валидируются против active policy ([[../product/lexical-system]] §3b, [[../OPEN]] OPEN-14).
```

NEW:

```markdown
- **MUST — safety не пинится (safety-overlay)** [PD-2026-07-19, rereview G-R1; P.3 PD-2026-07-21]: пинятся только curriculum/scoring/scheduler/control/generation/rubric snapshots, нужные для deterministic replay. `production_eligible` проверяется по **active** usage/currency policy в момент доставки, `EXERCISE_RENDERED`, bank reuse и placement production delivery, не по pinned-версии. Прошлое evaluation/replay детерминировано по stored exercise/evidence snapshots; later safety changes block future delivery/reuse, not historical assessment.
- **MUST — stale-safety effects** [P.3, PD-3 C, PD-6 A]: live manifest / review assignment / банк / placement-форма перед delivery production сверяются с active safety. Ставший `avoid`/`obsolete`/вне-контекста/expired item отменяется или заменяется append-only domain event (`LIVE_STEP_SAFETY_REJECTED`, `BANK_ITEM_RETIRED`, `LEXICAL_CURRENCY_CHANGED`) с обеими версиями. Expired currency review interval suspend-ит production и создаёт review task; `obsolete` требует explicit negative review или repeated missed checks по policy.
- **MUST — enforcement активации** [ревью E-5]: `validate`/`activate` энфорсят schema, provenance и целостность **независимо от способа правки файла**; невалидная версия не активируется. (Отдельный attestation-протокол в MVP не вводится — осознанный отказ от gate-машинерии, [[../README]].)
- **MUST**: изменения программы и living-layer promotion проходят `maintain-english-curriculum` workflow с последующей валидацией.
- **MUST — `production_eligible` и predicate** [rereview H-R1; P.3 PD-2026-07-21]: production/scheduler/generation используют вычисляемый `production_eligible`; `avoid`, `recognition_only`, `currency: obsolete`, `currency: dated` без explicit recognition override, `opaque` как required production и `context_dependent` вне `allowed_contexts` исключают production и новые assignments. `requires_usage_policy` — predicate по type/register, а не только по «informal-единица»: рискованный `type: word`/register тоже обязан иметь usage_policy.
- **MUST**: валидация ловит: циклы advisory-графа; битые ссылки prerequisites/lexicon/module/track/source_refs; дубли ID; prerequisite с CEFR выше уровня темы; пустые dimensions или отсутствие `mastery_criteria`/`LexicalMasteryProfile` на required dimension; отсутствие can_do; тему трека Grammar Engine без `frequency_tier` [PD-2026-07-21]; единицу, для которой `requires_usage_policy=true`, без `usage_policy`; `context_dependent` без `allowed_contexts`; `volatility: changing` без полного набора (`first_observed_at`/`last_verified_at`/`currency`/источник); expired review interval без production suspension; `meme_template` без нейтрального объяснения **или `cultural_context`** (rereview H-R1); imported item без `source_refs`/SourceArtifact **или без `transformations`** (rereview I-R3); сторонние excerpts в living layer (постоянное правило).
- **MUST NOT — living layer excerpts** [PD-2026-07-20, rereview I-R2; P.3]: **постоянно** запрещено хранить сторонние excerpts (текст forum post/example) — мотив ToS площадок и персональные данные, независимо от лицензий. Разрешены: source-метаданные, source pointer/hash, короткая сама единица (выражение/сокращение), authored context summary и **собственный** нейтральный парафраз/объяснение.
- **MUST**: informal-единицы с `usage_policy: avoid`/`recognition_only`/`currency: dated`/`currency: obsolete` не попадают в required production и не рекомендуются для production. `dated` можно использовать только на recognition/historical/register-awareness tasks с explicit context override. Банк/формы/live manifests ре-валидируются против active policy ([[../product/lexical-system]] §3b).
```

### Curriculum patch 5 — boundary events

Concept: C. Living-layer mechanism. PD: PD-6 A.

OLD:

```markdown
- **events published**: `CURRICULUM_VERSION_ACTIVATED`, `LEXICAL_ITEM_ADDED`
```

NEW:

```markdown
- **events published**: `CURRICULUM_VERSION_ACTIVATED`, `LIVING_LEXICAL_CANDIDATE_OBSERVED`, `LEXICAL_ITEM_ADDED`, `LEXICAL_CURRENCY_REVIEW_DUE`, `LEXICAL_CURRENCY_CHANGED`
```

### Curriculum patch 6 — open question status and changelog

Concept: OPEN closure. PD: PD-1 A through PD-7 A.

OLD:

```markdown
- **OPEN-14**: currency/usage-policy lifecycle, `production_eligible`, safety-overlay для live manifests, stale-safety → П.3 (+0.4/+0.5).
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция (приватное использование + publication trigger), состав данных и provenance-схема — §3.1/§3.2; living-layer rights — постоянное правило.
```

NEW:

```markdown
- ~~OPEN-14~~ **закрыт P.3** [PD-2026-07-21]: currency/usage-policy lifecycle, `production_eligible`, stale-safety для live manifests/bank/placement, living-layer workflow, `dated` recognition-only и lexeme form-slot handoff зафиксированы в §2/§4/§5 и [[../product/lexical-system]] §3b.
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция (приватное использование + publication trigger), состав данных и provenance-схема — §3.1/§3.2; living-layer rights — постоянное правило.
```

Insert this changelog row before the current `2026-07-21 (4)` row:

OLD:

```markdown
## История изменений

- **2026-07-21 (4)**: **`frequency_tier` расширен до трёх значений [PD-2026-07-21]**: `big-five | core | tail`. Находка независимой проверки П.2: бинарный enum вытолкнул фундаментную не-временную грамматику (be, порядок слов, can, императивы, here-is…) в tail = recognition-only, породив противоречие «can_do обещает производство, критериев производства нет» в 17 темах. `core` — частая не-временная грамматика с естественными dimensions и приоритетом наравне с big-five; `tail` сужен до редких глагольных форм (его can_do может описывать целевое умение — производство активируется на B1–B2).
```

NEW:

```markdown
## История изменений

- **2026-07-21 (5)**: **P.3 phase 2 canon patch** [PD-2026-07-21]: living-layer candidate/promotion workflow, hybrid currency aging, `dated` recognition-only, lexicon-first micro lane + auto-link candidates, active-safety hooks and domain lifecycle events added as the implementation contract for `generation@1`; OPEN-14 closed here.
- **2026-07-21 (4)**: **`frequency_tier` расширен до трёх значений [PD-2026-07-21]**: `big-five | core | tail`. Находка независимой проверки П.2: бинарный enum вытолкнул фундаментную не-временную грамматику (be, порядок слов, can, императивы, here-is…) в tail = recognition-only, породив противоречие «can_do обещает производство, критериев производства нет» в 17 темах. `core` — частая не-временная грамматика с естественными dimensions и приоритетом наравне с big-five; `tail` сужен до редких глагольных форм (его can_do может описывать целевое умение — производство активируется на B1–B2).
```

---

## `wiki/product/lexical-system.md`

### Lexical-system patch 1 — production eligibility and currency behavior

Concept: A/C. Safety and living-layer mechanism. PD: PD-3 C, PD-4 A.

OLD:

```markdown
- **MUST — usage_policy и `requires_usage_policy`** [rereview H-R1]: `requires_usage_policy` — вычисляемый predicate по type/register (не только по флагу «informal-единица»): рискованный `type: word`/register тоже обязан иметь usage_policy. Понимать ≠ употреблять: `recognition_only`/`avoid` — только на распознавание.
- **MUST — `production_eligible`** [rereview H-R1]: вычисляемый из active `usage_policy` + `currency`; `avoid`, `recognition_only` **и `obsolete`** → `production_eligible=false`. Единица с `safe_to_use` + `obsolete` не проходит свежую generation/scheduler.
- **MUST — assessable dimensions по policy** [ревью H-2]: dimensions и `mastery_criteria` зависят от `usage_policy`; для `recognition_only`/`avoid`/`obsolete` production не требуется (не «застревает» перед MASTERED). Правила — [[../OPEN]] OPEN-13.
- **MUST — context_dependent enforcement** [ревью H-4]: `context_dependent` задаёт `allowed_contexts`/disallowed; вне разрешённого контекста — `recognition_only` (safe default). `communities` — метаданные, не правило допуска.
- **MUST — currency lifecycle** [ревью D-8/H-5]: для `volatility: changing` обязательны `first_observed_at`, `last_verified_at`, `currency`, источник/сообщество; для `meme_template` — ещё `cultural_context`. Валидатор проверяет полный набор. Переходы `current → dated → obsolete`, владелец, TTL/update-event — [[../OPEN]] OPEN-14.
- **MUST — safety-overlay, safety не пинится** [PD-2026-07-19, rereview G-R1]: `production_eligible` всегда проверяется по **active** policy в момент доставки, а не по pinned-версии. Прошлое evaluation/replay остаётся детерминированным по pinned scoring; но live manifest / review assignment / банк / placement-форма перед доставкой production сверяются с active safety, и ставший `avoid`/`obsolete`/вне-контекста item **отменяется или заменяется** append-only event, хранящим обе версии. Owner механизма — [[../OPEN]] OPEN-14 (+0.5 для live delivery).
```

NEW:

```markdown
- **MUST — usage_policy и `requires_usage_policy`** [rereview H-R1]: `requires_usage_policy` — вычисляемый predicate по type/register (не только по флагу «informal-единица»): рискованный `type: word`/register тоже обязан иметь usage_policy. Понимать ≠ употреблять: `recognition_only`/`avoid` — только на распознавание.
- **MUST — `production_eligible`** [rereview H-R1; P.3 PD-2026-07-21]: вычисляемый из active `usage_policy` + active `currency` + active context. `avoid`, `recognition_only`, `obsolete`, `dated` без explicit recognition override, `opaque` как required production и `context_dependent` вне `allowed_contexts` → `production_eligible=false`. Единица с `safe_to_use` + `obsolete` или expired currency review interval не проходит fresh generation/scheduler/bank reuse.
- **MUST — assessable dimensions по policy** [ревью H-2; PD-4 A]: dimensions и `mastery_criteria` зависят от effective policy; для `recognition_only`/`avoid`/`dated`/`obsolete` production не требуется (не «застревает» перед MASTERED). `dated` может появиться только в recognition/historical/register-awareness tasks с explicit context override. Правила профиля — [[../modules/scoring]] §6.
- **MUST — context_dependent enforcement** [ревью H-4]: `context_dependent` задаёт `allowed_contexts`/disallowed; вне разрешённого контекста — `recognition_only` (safe default). `communities` — метаданные, не правило допуска.
- **MUST — currency lifecycle** [ревью D-8/H-5; P.3 PD-3 C]: для `volatility: changing` обязательны `first_observed_at`, `last_verified_at`, `currency`, источник/сообщество; для `meme_template` — ещё `cultural_context`. Валидатор проверяет полный набор. Expired review interval не меняет `currency` молча: он suspend-ит production и создаёт review task. `obsolete` ставится explicit negative review или repeated missed checks по versioned policy. Domain event: `LEXICAL_CURRENCY_CHANGED`.
- **MUST — safety-overlay, safety не пинится** [PD-2026-07-19, rereview G-R1; P.3]: `production_eligible` всегда проверяется по **active** policy в момент доставки, `EXERCISE_RENDERED`, bank reuse и placement production delivery, а не по pinned-версии. Прошлое evaluation/replay остаётся детерминированным по stored exercise/evidence snapshots; future delivery/reuse unsafe items **отменяется или заменяется** append-only event, хранящим обе версии.
```

### Lexical-system patch 2 — living layer catalog text

Concept: C. Living-layer mechanism. PD: PD-3 C, PD-5 D, PD-7 A.

OLD:

```markdown
Каталоги: **stable core** (проектируется заранее) / **living layer** (встреченное в обучении, через maintain-workflow с provenance) / **learner lexicon** (личный словарь, §3). Источники частот и CEFR-разметки — контракт [[../modules/curriculum]] §3.

- **MUST NOT — постоянное правило** [PD-2026-07-20, rereview I-R2]: living layer **не хранит сторонние excerpts** (текст forum post/example) — мотив ToS площадок и персональные данные. Разрешено: source-метаданные, короткая сама единица и **собственный** нейтральный парафраз. Правовая позиция целиком — [[../modules/curriculum]] §3.1.
```

NEW:

```markdown
Каталоги: **stable core** (проектируется заранее) / **living layer** (встреченное в обучении, через maintain-workflow с provenance) / **learner lexicon** (личный словарь, §3). Источники частот и CEFR-разметки — контракт [[../modules/curriculum]] §3.

- **MUST — living-layer candidate boundary** [P.3, PD-2026-07-21]: сессия может создать только `LivingLexicalCandidate`; это не LexicalItem, не schedulable target и не evidence. Promotion делает только `maintain-english-curriculum` после normalization, dedup, no-excerpt check, usage/currency assignment, authored examples and neutral paraphrase, and validation.
- **MUST — unlinked coverage** [P.3, PD-5 D]: LexicalItem без `topic.lexicon` не является ошибкой. Он может попадать в практику через lexicon-first micro lane по learner request / observed error / due review / CORE-HIGH safe candidate, а auto-link candidates проходят maintain workflow перед activation.
- **MUST NOT — постоянное правило** [PD-2026-07-20, rereview I-R2; P.3]: living layer **не хранит сторонние excerpts** (текст forum post/example) — мотив ToS площадок и персональные данные. Разрешено: source-метаданные, source pointer/hash, короткая сама единица, authored context summary и **собственный** нейтральный парафраз. Правовая позиция целиком — [[../modules/curriculum]] §3.1.
```

### Lexical-system patch 3 — open questions

Concept: OPEN closure. PD: PD-3 C, PD-4 A, PD-5 D.

OLD:

```markdown
- ~~OPEN-13~~ **закрыт** в 0.4: Informal Online Competence, `contribution_scope` и assessable dimensions — [[../modules/scoring]] §5–§6.
- **OPEN-14**: currency/usage-policy lifecycle, context_dependent enforcement, stale-safety банка, агрегация форм lexeme → curriculum detail / П.3.
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция, состав данных и provenance — [[../modules/curriculum]] §3.1–§3.2.
```

NEW:

```markdown
- ~~OPEN-13~~ **закрыт** в 0.4: Informal Online Competence, `contribution_scope` и assessable dimensions — [[../modules/scoring]] §5–§6.
- ~~OPEN-14~~ **закрыт P.3** [PD-2026-07-21]: currency/usage-policy lifecycle, context_dependent fallback, stale-safety банка/live manifests, `dated` recognition-only и lexeme form-slot handoff — §3b + [[../modules/scoring]] §6.
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция, состав данных и provenance — [[../modules/curriculum]] §3.1–§3.2.
```

### Lexical-system patch 4 — changelog

Concept: OPEN closure. PD: PD-3 C, PD-4 A, PD-5 D, PD-7 A.

OLD:

```markdown
## История изменений

- **2026-07-20 (P0-триаж)**: ранее в этот день добавлены ось `transparency`, тип `idiom`, `literal_trap_ru` и правила покрытия частотой (П.4b/П.4c); здесь — ссылка на OPEN-22 вместо закрытого OPEN-8 (P0-12).
```

NEW:

```markdown
## История изменений

- **2026-07-21**: P.3 phase 2 patch [PD-2026-07-21] фиксирует effective `production_eligible`, hybrid currency aging, `dated` recognition-only, living-layer candidate boundary и unlinked-lexicon coverage policy; OPEN-14 closed. OPEN-31 остаётся content-review.
- **2026-07-20 (P0-триаж)**: ранее в этот день добавлены ось `transparency`, тип `idiom`, `literal_trap_ru` и правила покрытия частотой (П.4b/П.4c); здесь — ссылка на OPEN-22 вместо закрытого OPEN-8 (P0-12).
```

---

## `wiki/modules/lessons.md`

### Lessons patch 1 — rendered exercise binding in session manifest text

Concept: A. Delivery pipeline. PD: PD-1 A.

OLD:

```markdown
- **MUST — содержимое**: `session_id`, `provider`, `mode`, `pinned_versions` (curriculum, scoring, scheduler, **control**, generation, rubric), **`required_skills[]`** — пары `{skill_name, version}` — и `session_plan_id` со стартовым снимком `{composition_revision: 1, plan_version: 1}`. Manifest неизменяем; живые `SessionPlan`/`DeliveryLedger` хранятся в session aggregate по этой ссылке ([[control]] §4.2).
```

NEW:

```markdown
- **MUST — содержимое**: `session_id`, `provider`, `mode`, `pinned_versions` (curriculum, scoring, scheduler, **control**, generation, rubric), **`required_skills[]`** — пары `{skill_name, version}` — и `session_plan_id` со стартовым снимком `{composition_revision: 1, plan_version: 1}`. Manifest неизменяем; живые `SessionPlan`/`DeliveryLedger` хранятся в session aggregate по этой ссылке ([[control]] §4.2). Rendered exercise text не входит в Manifest: он фиксируется отдельным `EXERCISE_RENDERED` перед предъявлением learner prompt.
```

### Lessons patch 2 — safety and resume behavior

Concept: A. Delivery pipeline and crash recovery. PD: PD-1 A, PD-3 C, PD-4 A.

OLD:

```markdown
- **MUST — safety не пинится**: манифест закрепляет структуру и scoring, но не safety; `production_eligible` проверяется по active policy при доставке ([[../OPEN]] OPEN-14).
```

NEW:

```markdown
- **MUST — safety не пинится** [P.3]: манифест закрепляет структуру, pinned policies и generation policy, но не safety; `production_eligible` проверяется по active policy при `session next`, bank reuse and `EXERCISE_RENDERED`. `STEP_PRESENTED` without `EXERCISE_RENDERED` is recoverable on `resume`: the same step is returned with the same generation directive. `EXERCISE_RENDERED` without learner attempt is not evidence and becomes reusable only after bank acceptance.
```

### Lessons patch 3 — public API and events

Concept: A/B. Render-before-presentation and bank lifecycle. PD: PD-1 A, PD-2 A.

OLD:

```markdown
| `claim_next_step(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | выдача шага по протоколу [[control]] §4.2 | `[mvp]` |
| `replan(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | новая композиционная ревизия остатка бюджета | `[mvp]` |
| `SESSION_STARTED` / `FINISHED` / `ABANDONED` / `SESSION_STALE_ABANDONED` | publishes | lifecycle-факты | `[mvp]` |
| `ATTEMPT_STATE_CHANGED` | publishes | draft/recorded/assessed | `[mvp]` |
```

NEW:

```markdown
| `claim_next_step(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | выдача шага по протоколу [[control]] §4.2; возвращает bank item или generation directive | `[mvp]` |
| `record_rendered_exercise(session_id, step_id, exercise_instance, idempotency_key)` | API (mutating) | фиксирует immutable rendered exercise snapshot before learner presentation | `[mvp]` [P.3] |
| `replan(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | новая композиционная ревизия остатка бюджета | `[mvp]` |
| `SESSION_STARTED` / `FINISHED` / `ABANDONED` / `SESSION_STALE_ABANDONED` | publishes | lifecycle-факты | `[mvp]` |
| `EXERCISE_RENDERED` | publishes | rendered exercise snapshot tied to `step_id`; source for historical attempts/replay | `[mvp]` [P.3, PD-1 A] |
| `EXERCISE_ACCEPTED` / `EXERCISE_REJECTED` / `EXERCISE_RETIRED` | publishes | exercise bank lifecycle; acceptance only after assessed attempt or maintainer fast-path | `[mvp]` [P.3, PD-2 A] |
| `ATTEMPT_STATE_CHANGED` | publishes | draft/recorded/assessed | `[mvp]` |
```

### Lessons patch 4 — CLI surface

Concept: A. Delivery pipeline. PD: PD-1 A.

OLD:

```markdown
| `trainer attempt record --session ID --step STEP_ID --input FILE [--note "..."]` | фиксация attempt по выданному шагу; `--note` — untrusted-заметка ([[evidence]] §3) |
```

NEW:

```markdown
| `trainer exercise rendered --session ID --step STEP_ID --input FILE --idempotency-key K --format json` | фиксация rendered exercise snapshot before learner prompt; возвращает `exercise_instance_id` |
| `trainer attempt record --session ID --step STEP_ID [--exercise-instance EXERCISE_ID] --input FILE [--note "..."]` | фиксация attempt по выданному шагу; structured tasks reference stored exercise snapshot; `--note` — untrusted-заметка ([[evidence]] §3) |
```

---

## `wiki/modules/control.md`

### Control patch 1 — entity row for PlannedStep

Concept: A/D. Generation directives, bank reuse, lexicon-first lane. PD: PD-1 A, PD-5 D.

OLD:

```markdown
| `PlannedStep` | один шаг занятия — **tagged union по `kind`** (§4.3a) | общие: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?` |
```

NEW:

```markdown
| `PlannedStep` | один шаг занятия — **tagged union по `kind`** (§4.3a) | общие: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?`, `generation_directive?`, `bank_item_id?`, `lexicon_first?` |
```

### Control patch 2 — public event shape

Concept: A/B. Delivery pipeline and bank reuse. PD: PD-1 A, PD-2 A.

OLD:

```markdown
| `STEP_PRESENTED {step_id, session_id, composition_revision, plan_version, review_assignment_id?, targets[]:{target_ref, dimension}, context_id, predicted_retrievability?, presented_at}` | publishes | шаг **фактически выдан**; `targets[]` пуст только у target-less choice | `[mvp]` |
```

NEW:

```markdown
| `STEP_PRESENTED {step_id, session_id, composition_revision, plan_version, review_assignment_id?, targets[]:{target_ref, dimension}, context_id, step_type, generation_directive_hash?, bank_item_id?, predicted_retrievability?, presented_at, active_safety_version}` | publishes | шаг **фактически выдан тьютору**; `targets[]` пуст только у target-less choice; exercise text still requires `EXERCISE_RENDERED` before learner prompt | `[mvp]` |
```

### Control patch 3 — live safety before delivery

Concept: A/C. Active safety and stale-safety. PD: PD-3 C, PD-4 A, PD-6 A.

OLD:

```markdown
- **MUST — live safety перед выдачей** `[mvp]`: в UoW `next` сначала читает active safety-policy, затем выполняет единый условный commit с предикатом `plan_version = expected_plan_version ∧ production_eligible`. Недопустимый шаг не предъявляется, версия и ledger не меняются; ответ — `PRECONDITION_FAILED {reason: safety_changed, current_plan_version, next_action: session.replan}`. Replan затем закрывает выпавший непредъявленный review-assignment как `CANCELLED`, а не outcome.
```

NEW:

```markdown
- **MUST — live safety перед выдачей** `[mvp]` [P.3]: в UoW `next` сначала читает active safety-policy, затем выполняет единый условный commit с предикатом `plan_version = expected_plan_version ∧ production_eligible`. `production_eligible` учитывает active usage_policy, currency, allowed_contexts, `dated` recognition-only default and opaque/recognition-only production ban. Недопустимый шаг не предъявляется, версия и ledger не меняются; response — `PRECONDITION_FAILED {reason: safety_changed, current_plan_version, next_action: session.replan}` and domain event `LIVE_STEP_SAFETY_REJECTED` is emitted where state changes. Replan затем закрывает выпавший непредъявленный review-assignment как `CANCELLED`, а не outcome.
```

### Control patch 4 — PlannedStep common fields

Concept: A. Generation directive and bank item selection. PD: PD-1 A, PD-2 A.

OLD:

```markdown
Общие поля: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?`.
```

NEW:

```markdown
Общие поля: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?`, `generation_directive?`, `bank_item_id?`, `lexicon_first?`.

- **MUST — exercise source is explicit** [P.3]: a delivered step has exactly one of `bank_item_id` or `generation_directive`. A `bank_item_id` means reuse of an accepted, active-safety-revalidated bank item. A `generation_directive` is canonical data for the tutor to render an exercise under pinned `generation@1`; rendered text is persisted separately as `EXERCISE_RENDERED`.
- **MUST — bank item is not evidence** [P.3]: choosing or rendering a bank item does not create evidence. Evidence still requires saved learner response through [[evidence]].
```

### Control patch 5 — canonical pipeline candidates and delivery facts

Concept: D. Unlinked lexical coverage. PD: PD-5 D.

OLD:

```markdown
1. **Кандидаты.** `review` — due/overdue от [[scheduler]] §5. `growth` — рекомендации [[curriculum]], отфильтрованные по `is_first_exposure`. `integration` — пары (новая цель, освоенная цель). `choice` — цели из `goals[]`/личного словаря [[learner]] и рекомендация гейта от [[gates]], если она есть.
```

NEW:

```markdown
1. **Кандидаты.** `review` — due/overdue от [[scheduler]] §5, including LexicalItem review. `growth` — рекомендации [[curriculum]], отфильтрованные по `is_first_exposure`, plus the lexicon-first micro lane from `generation@1` for learner-requested / observed-error / due-review / CORE-HIGH safe unlinked LexicalItems (advisory: at most one growth item per balanced session unless maintenance or explicit vocabulary practice). `integration` — пары (новая цель, освоенная цель). `choice` — цели из `goals[]`/личного словаря [[learner]] и рекомендация гейта от [[gates]], если она есть.
```

OLD:

```markdown
- **MUST — цели и `context_id` в факте доставки** `[mvp]` [R-5]: `STEP_PRESENTED.targets[]` перечисляет все пары `(target_ref, dimension)` шага, включая обе роли integration, а `context_id` идентифицирует смысловой контекст (домен + тип задания). Reducer обновляет saturation для каждой пары; `review_assignment_id` обязателен для kind=review и делает разрешимой корреляцию §4.10.
```

NEW:

```markdown
- **MUST — цели, `context_id` и exercise source в факте доставки** `[mvp]` [R-5; P.3]: `STEP_PRESENTED.targets[]` перечисляет все пары `(target_ref, dimension)` шага, включая обе роли integration, а `context_id` идентифицирует смысловой контекст (домен + тип задания). Event also records `step_type`, `active_safety_version`, and exactly one of `bank_item_id` or `generation_directive_hash`. Reducer обновляет saturation для каждой пары; `review_assignment_id` обязателен для kind=review и делает разрешимой корреляцию §4.10.
```

---

## `wiki/modules/evidence.md`

### Evidence patch 1 — Attempt entity

Concept: A. Stored exercise snapshot before attempt. PD: PD-1 A.

OLD:

```markdown
| `Attempt` | одна попытка ученика | id, **`step_id`** (выданный шаг, [RR2-3]), target, dimension, mode, raw_answer, span, hints, draft/finalized |
```

NEW:

```markdown
| `Attempt` | одна попытка ученика | id, **`step_id`** (выданный шаг, [RR2-3]), `exercise_instance_id?` (для structured/generated tasks), target, dimension, mode, raw_answer, span, hints, draft/finalized |
```

### Evidence patch 2 — record_attempt API

Concept: A. Attempt references rendered exercise. PD: PD-1 A.

OLD:

```markdown
| `record_attempt(step_id, raw_answer, observations, hints)` | API | фиксация попытки **по выданному шагу**; target/dimension/mode и `origin` движок берёт из `PlannedStep`, клиент их не задаёт [RR2-3] | `[mvp]` |
```

NEW:

```markdown
| `record_attempt(step_id, exercise_instance_id?, raw_answer, observations, hints)` | API | фиксация попытки **по выданному шагу**; for structured/generated tasks validates stored `EXERCISE_RENDERED`; target/dimension/mode и `origin` движок берёт из `PlannedStep`, клиент их не задаёт [RR2-3] | `[mvp]` |
```

### Evidence patch 3 — observation/distractor links

Concept: A. Typical errors as distractors. PD: PD-1 A.

OLD:

```markdown
- **MUST — observation schema**: наблюдение ссылается на конкретный `rubric_criterion` и `span/error` в raw_answer, не булев флаг `criterion_satisfied`. Разделены machine-checkable часть (проверяется кодом) и subjective (под cap/trust); observation, не подтверждаемая raw_answer, **отклоняется** (единственная ветка, см. ниже).
```

NEW:

```markdown
- **MUST — observation schema**: наблюдение ссылается на конкретный `rubric_criterion` and/or `distractor_error_ref` и `span/error` в raw_answer, не булев флаг `criterion_satisfied`. Разделены machine-checkable часть (проверяется кодом) и subjective (под cap/trust); observation, не подтверждаемая raw_answer или stored exercise snapshot, **отклоняется** (единственная ветка, см. ниже).
```

### Evidence patch 4 — attempt validation against exercise snapshot

Concept: A/B. Rendered exercise and flawed generated exercises. PD: PD-1 A, PD-2 A.

OLD:

```markdown
- **MUST — attempt ссылается на выданный шаг** [RR2-3]: `record_attempt` принимает `step_id` шага с зафиксированным `STEP_PRESENTED` в указанной активной сессии; ссылка валидируется. Уже выданный шаг остаётся допустимым после replan, даже если его `composition_revision` больше не текущая: replan сохраняет предъявленные шаги и их assignments. Отсюда движок выводит target, dimension, mode и `origin` — клиент их не передаёт.
```

NEW:

```markdown
- **MUST — attempt ссылается на выданный шаг и rendered snapshot** [RR2-3; P.3]: `record_attempt` принимает `step_id` шага с зафиксированным `STEP_PRESENTED` в указанной активной сессии; ссылка валидируется. Для structured/generated tasks он также принимает и валидирует `exercise_instance_id` с зафиксированным `EXERCISE_RENDERED`, совпадающим с `step_id`, targets, dimensions and content hash. Уже выданный шаг остаётся допустимым после replan, даже если его `composition_revision` больше не текущая: replan сохраняет предъявленные шаги и их assignments. Отсюда движок выводит target, dimension, mode и `origin` — клиент их не передаёт.
- **MUST — flawed generated exercise handling** [P.3, PD-2 A]: ambiguous answer key, unsafe production requirement, dangling refs, borrowed text, or prompt fault rejects bank admission and can make the attempt non-contributing with audit reason; it never creates silent positive evidence. Bank acceptance requires an assessed attempt or explicit maintainer fast-path.
```

---

## `wiki/modules/scoring.md`

### Scoring patch 1 — LexicalMasteryProfile effective safety

Concept: A/C. Opaque and dated production rules. PD: PD-3 C, PD-4 A.

OLD:

```markdown
- **MUST — разрешение по трём осям** [P0-3]: у каждого LexicalItem versioned `LexicalMasteryProfile`; lookup **тотален** по кортежу `(type, transparency, usage_policy)` ([[../product/lexical-system]] §1a). Прежний lookup по `type`/`usage_policy` не учитывал ось прозрачности и оставлял mastery непрозрачных единиц неопределённой.
- **MUST — precedence: ограничение сильнее разрешения** [P0-3]: `recognition` требуется всегда. `controlled_production` попадает в required, **только если разрешают обе** оси — и `transparency`, и `usage_policy`. Конфликт разрешается в сторону запрета, а не разрешения.

| | `usage_policy` разрешает production (`safe_to_use`, разрешённый `context_dependent`) | `usage_policy` запрещает (`recognition_only`, `avoid`, `obsolete`) |
|---|---|---|
| `transparent` | recognition + controlled_production | только recognition |
| `semi_opaque` | recognition → затем controlled_production | только recognition |
| `opaque` | **только recognition** (production не required никогда) | только recognition |
```

NEW:

```markdown
- **MUST — разрешение по effective safety profile** [P0-3; P.3 PD-2026-07-21]: у каждого LexicalItem versioned `LexicalMasteryProfile`; lookup **тотален** по кортежу `(type, transparency, effective_usage_policy)`, где `effective_usage_policy` выводится из active usage_policy + active currency + context. Прежний lookup по `type`/`usage_policy` не учитывал ось прозрачности и оставлял mastery непрозрачных единиц неопределённой.
- **MUST — precedence: ограничение сильнее разрешения** [P0-3; PD-4 A]: `recognition` требуется всегда. `controlled_production` попадает в required, **только если разрешают все** оси — transparency, usage_policy, currency and context. `dated` is recognition-only by default; `obsolete`, `avoid`, `recognition_only`, `opaque` required production and `context_dependent` outside allowed context forbid production. Конфликт разрешается в сторону запрета, а не разрешения.

| | effective safety permits production (`safe_to_use`, allowed `context_dependent`, `currency: current`) | effective safety forbids production (`recognition_only`, `avoid`, `dated`, `obsolete`, disallowed context) |
|---|---|---|
| `transparent` | recognition + controlled_production | только recognition |
| `semi_opaque` | recognition → затем controlled_production | только recognition |
| `opaque` | **только recognition** (production не required никогда) | только recognition |
```

### Scoring patch 2 — lexeme form-slot evidence handoff

Concept: A/C. Lexeme form aggregation. PD: PD-3 C.

OLD:

```markdown
- **MUST**: lexeme агрегирует состояние из required forms детерминированно.
```

NEW:

```markdown
- **MUST**: lexeme агрегирует состояние из required forms детерминированно. Evidence from generated exercises records the tested `form_slot` (`base`, `past`, `participle` or policy-declared slot); scoring consumes form-slot evidence, not prompt text, so replay is deterministic.
```

### Scoring patch 3 — consumed events

Concept: A/B. Exercise snapshot is audit input, not scoring source. PD: PD-1 A, PD-2 A.

OLD:

```markdown
- **events consumed**: `EVIDENCE_ADDED`, `REVIEW_OUTCOME`; `REVIEW_ASSIGNMENT_CANCELLED` — terminal no-op, переход состояния и дельты не вычисляются.
```

NEW:

```markdown
- **events consumed**: `EVIDENCE_ADDED`, `REVIEW_OUTCOME`; `REVIEW_ASSIGNMENT_CANCELLED` — terminal no-op, переход состояния и дельты не вычисляются. `EXERCISE_RENDERED`/bank lifecycle events are audit/admissibility context only and do not change scores without `EVIDENCE_ADDED`.
```

---

## `wiki/glossary.md`

### Glossary patch 1 — session/exercise terms

Concept: A/B. Rendered exercise and bank lifecycle. PD: PD-1 A, PD-2 A.

OLD:

```markdown
- **STEP_PRESENTED** — факт выдачи шага **тьютору**, то есть граница наблюдаемости движка; не утверждает, что ученик увидел экран. Отличается от `SESSION_COMPOSED` (намерение): непредъявленный шаг мог выпасть при replan ([[modules/control]] §4.6).
```

NEW:

```markdown
- **STEP_PRESENTED** — факт выдачи шага **тьютору**, то есть граница наблюдаемости движка; не утверждает, что ученик увидел экран. Отличается от `SESSION_COMPOSED` (намерение): непредъявленный шаг мог выпасть при replan ([[modules/control]] §4.6). Exercise text is not implied by this event; generated/selected content is persisted separately.
- **EXERCISE_RENDERED** — immutable event that stores the authored exercise snapshot before the tutor presents the learner prompt: `step_id`, `exercise_instance_id`, content hash, targets, dimensions, context, lexicon refs, answer key or rubric ref, generation/rubric/curriculum versions and active safety version.
- **ExerciseInstance** — one rendered exercise snapshot tied to a `PlannedStep`. It can support the current attempt immediately, but is not reusable until bank admission accepts it.
- **ExerciseBankItem** — reusable accepted exercise instance with provenance, dedup key, safety revalidation, use history and append-only lifecycle `generated → accepted/rejected → retired`.
```

### Glossary patch 2 — production_eligible

Concept: A/C. Safety predicates. PD: PD-3 C, PD-4 A.

OLD:

```markdown
- **production_eligible** — вычисляемый признак «можно ли предъявлять как production сейчас» из active `usage_policy` + `currency` (`avoid`/`recognition_only`/`obsolete` → false). Всегда по active policy, не пинится (safety-overlay, [[OPEN]] OPEN-14).
```

NEW:

```markdown
- **production_eligible** — вычисляемый признак «можно ли предъявлять как production сейчас» из active `usage_policy` + `currency` + context + transparency (`avoid`/`recognition_only`/`obsolete`/`dated` без explicit recognition override/`context_dependent` вне allowed_contexts/`opaque` as required production → false). Всегда по active policy, не пинится (safety-overlay).
```

### Glossary patch 3 — currency and generation policy

Concept: A/C. Generation policy and currency lifecycle. PD: PD-3 C, PD-4 A.

OLD:

```markdown
- **currency** — актуальность изменчивой единицы: `current` / `dated` / `obsolete`, с датами наблюдения/проверки и владельцем reverification ([[OPEN]] OPEN-14).
```

NEW:

```markdown
- **currency** — актуальность изменчивой единицы: `current` / `dated` / `obsolete`, с датами наблюдения/проверки и владельцем reverification. Expired review interval suspends production and opens a review task; `dated` is recognition-only by default; `obsolete` blocks new production/review assignments.
- **generation_policy** — versioned policy snapshot, pinned in Session Manifest, that defines allowed exercise schemas, step-type forms, distractor rules, bank admission/reuse rules, dedup keys and safety predicates for generated lesson exercises.
- **stale-safety** — active-safety revalidation before delivery/reuse/rendering; if active usage/currency now forbids a production step, the step or bank item is cancelled/replaced/retired append-only instead of being silently delivered.
```

### Glossary patch 4 — living layer

Concept: C/D. Living layer and unlinked lexicon. PD: PD-5 D.

OLD:

```markdown
- **Stable core / living layer** — каталоги лексикона: спроектированный заранее / пополняемый из обучения (мемы, сленг) с provenance.
```

NEW:

```markdown
- **Stable core / living layer** — каталоги лексикона: спроектированный заранее / пополняемый из обучения (мемы, сленг, новые рабочие выражения) с provenance.
- **LivingLexicalCandidate** — no-evidence candidate captured from a session with normalized unit, proposed metadata, source pointer/hash and authored summary. It is not a LexicalItem and not schedulable until accepted by `maintain-english-curriculum`.
- **lexicon-first micro lane** — small scheduling lane for LexicalItems without topic refs, used for learner-requested, observed-error, due-review and CORE/HIGH safe items; advisory cap lives in generation policy.
```

---

## `wiki/modules/OPEN.md`

The actual file is `wiki/OPEN.md`; section title kept explicit here for routing.

### OPEN patch 1 — owner matrix

Concept: OPEN closure. PD: PD-1 A through PD-6 A.

OLD:

```markdown
| Currency/usage-policy lifecycle, production_eligible, safety-overlay для live manifest, exercise-bank lifecycle | **П.3 policies** (+ 0.4 для scoring-части) |
```

NEW:

```markdown
| Currency/usage-policy lifecycle, production_eligible, safety-overlay для live manifest, exercise-bank lifecycle, generation policy payload and living-layer candidate mechanics | **П.3 policies** (+ 0.4 для scoring-части, + 0.5/0.12 для delivery integration) |
```

### OPEN patch 2 — remove OPEN-14/OPEN-16 from open table

Concept: OPEN closure. PD: PD-1 A through PD-6 A.

OLD:

```markdown
| OPEN-14 | Currency и usage-policy lifecycle; `context_dependent`; агрегация форм lexeme. **Safety-overlay** (rereview G-R1/H-R1): вычисляемый `production_eligible` из active usage_policy+currency (`obsolete` исключает production); live manifest/review assignment проверяются active safety при доставке, несовместимое отменяется/заменяется append-only event с обеими версиями; `requires_usage_policy` predicate по type/register; `cultural_context` в validator | ревью D-7/D-8/H-3/H-4/H-5/H-6, G-R1/H-R1 | П.3 (+0.4 scoring, +0.5 live delivery) |
| OPEN-16 | Lifecycle банка упражнений: `generated → accepted/rejected`, acceptance criteria, promotion/invalidation, dedup, provenance | ревью E-4 | П.3 |
```

NEW:

```markdown
```

### OPEN patch 3 — add resolved rows after accepted P.3 concept row

Concept: OPEN closure. PD: PD-1 A through PD-6 A.

OLD:

```markdown
| — | **П.3 generation-концепт принят** (7 развилок): `EXERCISE_RENDERED` **до** показа ученику; приём в банк — после оценённой попытки (maintainer fast-path); currency — гибрид (просрочка авто-приостанавливает production + review-задача, obsolete не автоматом); `dated` — recognition-only с явным override; покрытие 591 непривязанной единицы — lexicon-first микро-полоса + авто-линк кандидаты через workflow; доменные safety-события внутри generic-конверта ядра; OPEN-31 остаётся content-review. Канон-правки — фаза 2 (патчи через верификацию владельца) | [PD-2026-07-21], `staging/concepts/2026-07-21-P3-generation-concept.md` |
```

NEW:

```markdown
| — | **П.3 generation-концепт принят** (7 развилок): `EXERCISE_RENDERED` **до** показа ученику; приём в банк — после оценённой попытки (maintainer fast-path); currency — гибрид (просрочка авто-приостанавливает production + review-задача, obsolete не автоматом); `dated` — recognition-only с явным override; покрытие 591 непривязанной единицы — lexicon-first микро-полоса + авто-линк кандидаты через workflow; доменные safety-события внутри generic-конверта ядра; OPEN-31 остаётся content-review. Канон-правки — фаза 2 (патчи через верификацию владельца) | [PD-2026-07-21], `staging/concepts/2026-07-21-P3-generation-concept.md` |
| OPEN-14 | **Закрыт P.3**: usage/currency lifecycle, active `production_eligible`, context-dependent fallback, stale-safety for live manifests/bank/placement, hybrid aging, `dated` recognition-only, no-excerpt living layer, `requires_usage_policy`, `cultural_context`, and lexeme form-slot handoff are specified in curriculum/lexical/scoring/control/lessons patches plus `generation@1` policy payload | [PD-2026-07-21], `staging/handoff/2026-07-21-P3-canon-patches.md`, `curriculum/policies/generation-v1.yaml` |
| OPEN-16 | **Закрыт P.3**: exercise bank lifecycle is `generated → accepted/rejected → retired`; admission requires assessed attempt or maintainer fast-path; invalidation, dedup key, provenance, active-safety revalidation and crash/retry semantics are specified in lessons/control/evidence patches plus `generation@1` policy payload | [PD-2026-07-21], `staging/handoff/2026-07-21-P3-canon-patches.md`, `curriculum/policies/generation-v1.yaml` |
```

### OPEN patch 4 — changelog

Concept: OPEN closure. PD: PD-1 A through PD-7 A.

OLD:

```markdown
## История изменений

- **2026-07-21 (31)**: **0.12 разблокирован.** Пятый прогон (независимое подтверждение) — `PASS`, 0 находок; все находки 4-го прогона сняты, 4 сквозных сценария собираются, канон не менялся. OPEN-30 закрыт. **Фаза 0 завершена — все 12 контрактов приняты; вертикальный срез разблокирован.**
```

NEW:

```markdown
## История изменений

- **2026-07-21 (32)**: P.3 phase 2 proposal prepared: `generation@1` policy payload, exact canon patch proposals, living-layer lifecycle, exercise bank lifecycle and active-safety delivery rules. After owner applies patches, OPEN-14/OPEN-16 move to resolved; OPEN-31 remains content-review by PD-7.
- **2026-07-21 (31)**: **0.12 разблокирован.** Пятый прогон (независимое подтверждение) — `PASS`, 0 находок; все находки 4-го прогона сняты, 4 сквозных сценария собираются. OPEN-30 закрыт. **Фаза 0 завершена — все 12 контрактов приняты; вертикальный срез разблокирован.**
```

---

## `wiki/roadmap.md`

### Roadmap patch 1 — current-state counters and critical path

Concept: phase 2 completion. PD: PD-1 A through PD-7 A.

OLD:

```markdown
| Открытых вопросов | **16**; решённых — 46 |
| Прогонов red-team ревью | **13** (8 по контрактам + 5 по kernel-коду); 0.12 подтверждён (PASS); **kernel-цикл закрыт**: находки 5-го прогона чинил Codex, подтвердил Claude — роли разведены |
| Программа | **155 тем · 35 модулей · 10 треков**; TOEFL-трек и living layer — в продукте, `[post-mvp]`-контента не осталось [PD-2026-07-21] |
| Лексикон | **838 единиц** (П.4c сдан): 120 идиом, 100 phrasal verbs, разметка прозрачности по всему |
| Исполняемое | **kernel** (1–8) + **storage** (1.3) + **curriculum** (2.1: loader/валидатор/активация — первый бизнес-модуль; программа 155/838 активируется живьём) + CLI из 8 команд; **198 тестов**, ruff + mypy strict чисты |
| Ближайшее по критическому пути | П.3 фаза 1 (концепт у Codex) · 2.2 (сессия end-to-end — ждёт П.3) · П.4d · content-review П.4c |
```

NEW:

```markdown
| Открытых вопросов | **14**; решённых — 48 |
| Прогонов red-team ревью | **13** (8 по контрактам + 5 по kernel-коду); 0.12 подтверждён (PASS); **kernel-цикл закрыт**: находки 5-го прогона чинил Codex, подтвердил Claude — роли разведены |
| Программа | **155 тем · 35 модулей · 10 треков**; TOEFL-трек и living layer — в продукте, `[post-mvp]`-контента не осталось [PD-2026-07-21] |
| Лексикон | **838 единиц** (П.4c сдан): 120 идиом, 100 phrasal verbs, разметка прозрачности по всему |
| Policies | `generation@1` payload proposed in `curriculum/policies/generation-v1.yaml`; canon patch proposals in `staging/handoff/2026-07-21-P3-canon-patches.md` |
| Исполняемое | **kernel** (1–8) + **storage** (1.3) + **curriculum** (2.1: loader/валидатор/активация — первый бизнес-модуль; программа 155/838 активируется живьём) + CLI из 8 команд; **198 тестов**, ruff + mypy strict чисты |
| Ближайшее по критическому пути | 2.2 (сессия end-to-end — использует P.3 policy proposals after owner verification) · П.4d · content-review П.4c |
```

### Roadmap patch 2 — 0.3 dependencies

Concept: OPEN closure. PD: PD-3 C, PD-5 D.

OLD:

```markdown
| 0.3 | Curriculum Contract | `wiki/modules/curriculum.md` | done-with-open | can-do граф, **9 треков** (добавлен `everyday-life`); остаточные OPEN-9/14 (OPEN-15 закрыт) |
```

NEW:

```markdown
| 0.3 | Curriculum Contract | `wiki/modules/curriculum.md` | done-with-open | can-do граф, **10 треков** (`everyday-life`, `word-formation`, TOEFL in product); OPEN-14 closed by P.3; остаточный OPEN-9 (OPEN-15 закрыт) |
```

### Roadmap patch 3 — 0.9 dependencies

Concept: OPEN closure. PD: PD-3 C, PD-4 A, PD-5 D.

OLD:

```markdown
| 0.9 | Lexical System Requirements | `wiki/product/lexical-system.md` | done-with-open | дизайн пользователя + ось `transparency`/`idiom`; остаточные OPEN-14/22 (OPEN-13/15 закрыты) |
```

NEW:

```markdown
| 0.9 | Lexical System Requirements | `wiki/product/lexical-system.md` | done-with-open | дизайн пользователя + ось `transparency`/`idiom`; OPEN-14 closed by P.3; остаточный OPEN-22 (OPEN-13/15 закрыты) |
```

### Roadmap patch 4 — P.3 row and changelog

Concept: phase 2 done. PD: PD-1 A through PD-7 A.

OLD:

```markdown
| П.3 | Policies генерации уроков + lifecycle банка + **living-layer механизм** [PD-2026-07-21] | **in-progress** | **Фаза 1 принята**: концепт Codex прошёл независимую проверку (противоречий с каноном нет), все 7 развилок решены пользователем [PD-2026-07-21] — см. OPEN.md и approval-блок концепта. **Фаза 2 у Codex**: канон-патчи как предложения (применение через верификацию) + авторинг `generation-v1` policy-данных. Движковая реализация (EXERCISE_RENDERED, банк, living-layer события) — с 2.2. **Закрывает OPEN-14/OPEN-16** |
```

NEW:

```markdown
| П.3 | Policies генерации уроков + lifecycle банка + **living-layer механизм** [PD-2026-07-21] | done-with-owner-verification | **Фаза 1 принята**: концепт Codex прошёл независимую проверку. **Фаза 2 сдана Codex**: `generation@1` policy payload authored in `curriculum/policies/generation-v1.yaml`; exact canon patch proposals prepared in `staging/handoff/2026-07-21-P3-canon-patches.md`; P2 handoff tier mismatch superseded by append-only postscript. Owner verification/application pending. Движковая реализация (`EXERCISE_RENDERED`, банк, living-layer события) — с 2.2. **Закрывает OPEN-14/OPEN-16 after owner applies patches** |
```

Insert this changelog row before the current `2026-07-21 (65)` row:

OLD:

```markdown
## История изменений

- **2026-07-21 (65)**: **П.3 фаза 1 принята [PD-2026-07-21] — все 7 развилок решены.** Концепт Codex (`staging/concepts/2026-07-21-P3-generation-concept.md`) прошёл независимую проверку Claude: инварианты легли на канон (safety не пинится, opaque вне обязательного производства, вечный запрет чужих текстов, replay читает сохранённое упражнение, пустой банк не блокирует, числа advisory), пайплайн корректно встроен в принятый протокол сессии, карты закрытия OPEN-14/OPEN-16 попунктны. Решения: `EXERCISE_RENDERED` до показа (PD-1 A); банк-приём после оценённой попытки (PD-2 A); currency-гибрид — авто-suspend production + review-задача, obsolete не автоматом (PD-3 C); `dated` recognition-only с override (PD-4 A); покрытие непривязанного лексикона — микро-полоса + авто-линк (PD-5 D); доменные safety-события в generic-конверте (PD-6 A); OPEN-31 — content-review (PD-7 A). Фаза 2 у Codex: канон-патчи как предложения + `generation-v1` policy-данные; движковая реализация — с 2.2.
```

NEW:

```markdown
## История изменений

- **2026-07-21 (66)**: **П.3 фаза 2 сдана Codex**: authored `curriculum/policies/generation-v1.yaml` (`generation@1` payload), `curriculum/policies/README.md`, exact canon patch proposals and handoff report. Patches implement PD-1..PD-7 as proposals only; wiki application waits for owner verification. P2 handoff got append-only postscript for `big-five | core | tail` sync.
- **2026-07-21 (65)**: **П.3 фаза 1 принята [PD-2026-07-21] — все 7 развилок решены.** Концепт Codex (`staging/concepts/2026-07-21-P3-generation-concept.md`) прошёл независимую проверку Claude: инварианты легли на канон (safety не пинится, opaque вне обязательного производства, вечный запрет чужих текстов, replay читает сохранённое упражнение, пустой банк не блокирует, числа advisory), пайплайн корректно встроен в принятый протокол сессии, карты закрытия OPEN-14/OPEN-16 попунктны. Решения: `EXERCISE_RENDERED` до показа (PD-1 A); банк-приём после оценённой попытки (PD-2 A); currency-гибрид — авто-suspend production + review-задача, obsolete не автоматом (PD-3 C); `dated` recognition-only с override (PD-4 A); покрытие непривязанного лексикона — микро-полоса + авто-линк (PD-5 D); доменные safety-события в generic-конверте (PD-6 A); OPEN-31 — content-review (PD-7 A). Фаза 2 у Codex: канон-патчи как предложения + `generation-v1` policy-данные; движковая реализация — с 2.2.
```
