# Модуль: curriculum

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: концепт Codex (одобрен, `staging/journal/2026-07-19-codex-curriculum-concept.md`) · red-team триаж (`staging/journal/2026-07-19-concept-review-triage.md`) · [[../product/learning-model]] §9 · [[../product/lexical-system]] · flows [[../flows/session]], [[../flows/placement]] · лицензии проверены 2026-07-19 ([PD-2026-07-19])
> **Bounded context**: `src/english_trainer/curriculum/`

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — из [[../glossary]]; поведение — полностью inline. Это контракт формата и правил программы (roadmap 0.3); само наполнение — фаза П.

---

## 1. Назначение

Модуль владеет учебной программой: графом can-do тем, треками, уровнями и учебным лексиконом. Отдаёт остальным модулям адресуемые темы, рекомендации («что стоит взять сейчас») и лексикон. Программа — карта, не система замков: модуль никогда ничего не блокирует.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `CurriculumVersion` | иммутабельный версионируемый снимок программы | version, activated_at, changelog |
| `Level` | CEFR-уровень с главным результатом | id (A1…C2), outcome |
| `Track` | сквозной трек через уровни | id, title, from_level |
| `Module` | группа тем уровня вокруг рабочей задачи | id (`a2.2-results-and-experience`), can_do, topics |
| `Topic` | единица изучения | см. формат ниже |
| `LexicalItem` | единица лексикона ([[../product/lexical-system]]) | id, type, `frequency_band`, `curriculum_priority_band`, register, usage_policy, source_refs… |
| `SourceArtifact` | внешний источник данных (provenance) | id, exact_version, url, retrieved_at, sha256, license, attribution, notices |

**Программа — граф can-do умений, не линейный учебник** [PD-2026-07-19]. Каждая тема отвечает на вопрос «что ученик сможет сделать», грамматика привязана к рабочей задаче (Present Perfect ← «сообщить о готовом результате»).

### Формат Topic

```yaml
id: grammar.present-perfect.result
cefr: A2
track: grammar-engine
module: a2.2-results-and-experience
can_do: Report a completed action that matters now
dimensions: [recognition, controlled_production, spontaneous_production, transfer]
advisory_prerequisites:
  strong: [grammar.have-has, grammar.past-participle]   # сильная рекомендация
  soft: [grammar.past-simple]                            # мягкая
lexicon: [chunk.we-have-completed, chunk.we-have-run-into-an-issue]
contexts: [project-update, deployment, aec-model-review]
typical_errors:
  - using Past Simple without a finished-time context
  - incorrect past participle
  - omitting have/has
mastery_criteria: {...}        # по versioned schema из 0.4, критерий на каждую required dimension
explanation_language: ru-allowed   # когда допустим русский
```

- **Единый enum prerequisites — `strong`/`soft`** [ревью A-4]: сила рекомендации, не замок. `hard/soft` из брифа — **superseded**, в текущей schema не используется.
- **`mastery_criteria`** — по versioned schema контракта 0.4 ([[../product/learning-model]] §9, ревью E-1); валидатор (§5) проверяет наличие критерия на каждую required dimension. До 0.4 полноценное авторское наполнение критериев не финализируется (см. roadmap: П.2 зависит от 0.4).

### Треки

| # | Track | С уровня |
|---|---|---|
| 1 | Grammar Engine | A1 |
| 2 | Vocabulary & Chunks | A1 |
| 3 | Reading | A1 |
| 4 | Written Interaction (чат, email, переписка) | A1 |
| 5 | Written Production & Mediation | A1 |
| 6 | US Tech English (AI/AEC/SaaS) | A1 |
| 7 | Everyday, Online & Informal English | A1 |
| 8 | TOEFL Reading & Writing | B1 `[post-mvp]` |

### Каталоги лексикона

- **stable core** — проектируется заранее (П.4) из источников ниже;
- **living layer** — мемы, сленг и форумные единицы, встреченные во время обучения; добавляются через `maintain-english-curriculum` workflow с provenance (`first_observed_at`, источник, `currency`);
- **learner lexicon** — личный словарь; живёт в модуле learner, не здесь.

## 3. Данные и лицензии [PD-2026-07-19]

Источники и режим использования выбраны (OPEN-6 решён). Схема provenance и полнота CC BY-SA notices — [[../OPEN]] OPEN-15.

| Источник | Роль | Лицензия | Обязательства |
|---|---|---|---|
| CEFR-J Vocab/Grammar Profiles A1–B2 (olp-en-cefrj) | CEFR-разметка | free research+commercial (Tono Lab) | цитирование + disclaimer |
| Octanove Vocabulary Profile C1/C2 | CEFR-разметка C1/C2 | **CC BY-SA 4.0** | attribution + license/notices + change-marking + ShareAlike на производное |
| NGSL / NAWL / Business Service List (BSL) | frequency band, рабочая лексика | **CC BY-SA 4.0** | attribution + notices + change-marking + ShareAlike на производное |
| wordfreq (rspeer) | численные частоты (агрегированный корпусный score) | код Apache-2.0, **данные CC BY-SA 4.0** | attribution + notices + change-marking; snapshot ~2021 |

- **MUST — режим build-time** [PD-2026-07-19/Q3, ревью I-1]: частотные данные используются pinned на build-time/этапе отбора; **сырые частотные датасеты в репо не коммитятся**. В репо — только отобранный лексикон с `source_refs`.
- **MUST — CC BY-SA obligations** [rereview I-R1]: отсутствие сырого dataset **само по себе не решает**, является ли распространяемый отобранный лексикон Adapted Material. Для каждого CC BY-SA источника (Octanove C1/C2, NGSL-семейство, wordfreq data) фиксируются author/copyright/license/disclaimer notices, ссылка на материал и лицензию, indication of changes и граница ShareAlike. Полная schema и решение «Adapted Material?» — [[../OPEN]] OPEN-15; **первый publish/import блокируется до закрытия OPEN-15**.
- **MUST — provenance** [ревью I-2/I-3]: каждый импорт фиксирует `SourceArtifact` (exact_version, url, retrieved_at, sha256, license, attribution, notices); каждая импортированная запись несёт `source_refs` + `transformations` (для неизменённой — явное `transformations: [identity]`). Оба поля **проверяются валидатором** (rereview I-R3).
- **Уточнение по wordfreq** [ревью I-5]: wordfreq даёт **агрегированную корпусную частоту** (домены, включая Reddit/Twitter, слиты в один score) — per-domain «присутствие в Reddit/Twitter» из API не запрашивается, а snapshot ~2021 не доказывает текущую currency. Источник informal-currency — отдельно, OPEN-14.
- **MUST**: `ATTRIBUTIONS.md` (или data-license manifest) появляется вместе с первым импортом.
- **MUST NOT**: импортировать данные CEFR-SP (лицензия не указана) и данные OpenVLT (лицензия данных не заявлена; только архитектурный reference).

## 4. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `get_topic(id)` | API | тема с полным содержимым | `[mvp]` |
| `recommendations(learner_state)` | API | темы с флагом `recommended / early` по advisory-графу и уровням | `[mvp]` |
| `lexicon_query(filter)` | API | выборка LexicalItem (frequency_band, curriculum_priority_band, track, usage_policy, currency) | `[mvp]` |
| `get_version(v)` | API | иммутабельный snapshot указанной версии (для replay/pin) | `[mvp]` |
| `validate(version_or_candidate)` | API | валидация **кандидата или версии** до активации (rereview E-R2) | `[mvp]` |
| `activate(version, expected_active)` | API | атомарная активация: требует успешный validate + CAS по expected_active, публикует событие | `[mvp]` |
| `CURRICULUM_VERSION_ACTIVATED` | publishes | активация новой версии (эмитится `activate`) | `[mvp]` |
| `LEXICAL_ITEM_ADDED` | publishes | пополнение living layer | `[mvp]` |

## 5. Поведение

- **MUST**: у каждой темы есть `can_do`; тема без наблюдаемого умения не проходит валидацию.
- **MUST**: граф advisory — модуль выдаёт рекомендации, никогда не запрещает ([[../product/learning-model]] §1, §4).
- **MUST — pinning и не-ретроактивность** [PD-2026-07-19, ревью G-2/G-3]: `CurriculumVersion` иммутабелен. Evidence, session и Session Manifest **pin-ят** версию curriculum (и scoring/scheduler/generation/rubric policy), под которой созданы. Активация новой версии **никогда не ретроактивна**: replay и resume используют pinned-версию, не current active. «Движок работает с активной версией» относится только к формированию *новых* манифестов.
- **MUST — deprecation и replay** [ревью G-3]: изменение ID — только deprecation через append-only alias/migration events с явной семантикой `1:1 | split | merge | retired`; исходная версия сохраняется в snapshot, historical evidence не перепривязывается. Перезапись event log запрещена (append-only). Механизм — [[../OPEN]] OPEN-9.
- **MUST — бессмертие ссылок** [ревью G-5]: стабильный ID бессмертен, если на него ссылается **любой** persistent reference (evidence, manifest, review queue, банк, assessment), не только evidence; tombstones сохраняются; cross-validator проверяет разрешимость ссылок в learner state, манифестах, очереди, банке и assessments.
- **MUST — safety не пинится (safety-overlay)** [PD-2026-07-19, rereview G-R1]: пинятся только scoring/структура/rubric. `production_eligible` (из active usage_policy+currency) проверяется по **active** policy в момент доставки, не по pinned-версии. Прошлое evaluation/replay детерминировано по pinned; но live manifest / review assignment / банк / placement-форма перед доставкой production сверяются с active safety, и ставший `avoid`/`obsolete`/вне-контекста item отменяется/заменяется append-only event с обеими версиями. Scope stale-safety **включает live manifests**, владельцы — [[../OPEN]] OPEN-14 (+0.5 live delivery).
- **MUST — enforcement активации** [ревью E-5]: `validate`/`activate` энфорсят schema, provenance и целостность **независимо от способа правки файла**; невалидная версия не активируется. (Отдельный attestation-протокол в MVP не вводится — осознанный отказ от gate-машинерии, [[README]].)
- **MUST**: изменения программы проходят `maintain-english-curriculum` workflow с последующей валидацией.
- **MUST — `production_eligible` и predicate** [rereview H-R1]: production/scheduler используют вычисляемый `production_eligible`; `obsolete` исключает production и новые assignments. `requires_usage_policy` — predicate по type/register, а не только по «informal-единица»: рискованный `type: word`/register тоже обязан иметь usage_policy.
- **MUST**: валидация ловит: циклы advisory-графа; битые ссылки prerequisites/lexicon/module/track/source_refs; дубли ID; prerequisite с CEFR выше уровня темы; пустые dimensions или отсутствие `mastery_criteria`/`LexicalMasteryProfile` на required dimension; отсутствие can_do; единицу, для которой `requires_usage_policy=true`, без `usage_policy`; `context_dependent` без `allowed_contexts`; `volatility: changing` без полного набора (`first_observed_at`/`last_verified_at`/`currency`/источник); `meme_template` без нейтрального объяснения **или `cultural_context`** (rereview H-R1); импортированную единицу без `source_refs`/SourceArtifact **или без `transformations`** (rereview I-R3); сторонние excerpts в living layer до закрытия OPEN-15 (rereview I-R2).
- **MUST NOT — living layer excerpts** [rereview I-R2]: до закрытия OPEN-15 запрещено хранить сторонние excerpts (текст forum post/example); разрешены source-метаданные, короткая единица и собственный нейтральный парафраз.
- **MUST**: informal-единицы с `usage_policy: avoid`/`recognition_only`/`currency: obsolete` не попадают в production и не рекомендуются — только на понимание; банк/формы/live manifests ре-валидируются против active policy ([[../product/lexical-system]] §3b, [[../OPEN]] OPEN-14).
- **MUST**: TOEFL-трек не порождает тем ниже B1.
- **SHOULD**: каждая тема связана хотя бы с одним рабочим контекстом (AI/AEC/SaaS/переписка/форум).

## 6. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer curriculum validate [--candidate PATH]` | валидация кандидата или активной версии | exit 0 / список ошибок с адресами |
| `trainer curriculum activate --version V --expected-active W` | атомарная активация валидной версии | результат + событие |
| `trainer curriculum show --topic ID --format json` | содержимое темы | Topic JSON |
| `trainer curriculum lexicon --filter ... --format json` | выборка лексикона | список LexicalItem |

## 7. Границы

- **depends on**: kernel (policy registry, IDs), storage
- **events published**: `CURRICULUM_VERSION_ACTIVATED`, `LEXICAL_ITEM_ADDED`
- **consumed by**: scheduler, lessons, assessments, learner, memory (через API рекомендаций/тем/лексикона)

## 8. Открытые вопросы

OPEN-6 решён (источники + build-time режим). Остаточные механизмы, зафиксированные инвариантами выше ([[../OPEN]]):

- **OPEN-9**: version pinning, deterministic replay, deprecation split/merge/retired, бессмертие ссылок → 0.3 (+0.2 CAS/snapshot).
- **OPEN-14**: currency/usage-policy lifecycle, `production_eligible`, safety-overlay для live manifests, stale-safety → П.3 (+0.4/+0.5).
- **OPEN-15**: SourceArtifact schema, CC BY-SA notices/change-marking/ShareAlike, rights_basis living layer; блокирует первый publish/import → 0.3/П.4.

## История изменений

- **2026-07-19 (3)**: rereview — safety-overlay «safety не пинится» + live manifests в scope stale-safety (G-R1); candidate `validate`/`activate` API (E-R2); license-таблица разделена CEFR-J/Octanove + полные CC BY-SA obligations (I-R1); валидатор проверяет `transformations` (I-R3), `cultural_context` и `production_eligible`/`requires_usage_policy` (H-R1); living layer без сторонних excerpts до OPEN-15 (I-R2).
- **2026-07-19 (2)**: red-team триаж — единый enum `strong/soft` (A-4); pinning/не-ретроактивность и deprecation replay (G-2/G-3); бессмертие любого persistent reference (G-5); build-time режим данных (I-1/Q3); SourceArtifact provenance (I-2/I-3); полное имя BSL (I-4); исправлено утверждение о wordfreq Reddit/Twitter (I-5); enforcement активации без attestation (E-5); `mastery_criteria` → 0.4; расширена валидация. Механизмы → OPEN-9/14/15.
- **2026-07-19**: создан по одобренному концепту Codex (can-do граф, 8 треков, формат темы) + решение OPEN-6. Все решения [PD-2026-07-19].
