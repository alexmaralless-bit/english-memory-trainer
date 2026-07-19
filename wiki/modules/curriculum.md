# Модуль: curriculum

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: концепт Codex (одобрен, `staging/journal/2026-07-19-codex-curriculum-concept.md`) · [[../product/learning-model]] §9 · [[../product/lexical-system]] · flows [[../flows/session]], [[../flows/placement]] · лицензии проверены 2026-07-19 (OPEN-6, [PD-2026-07-19])
> **Bounded context**: `src/english_trainer/curriculum/`

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — из [[../glossary]]; поведение — полностью inline. Это контракт формата и правил программы (roadmap 0.3); само наполнение — фаза П.

---

## 1. Назначение

Модуль владеет учебной программой: графом can-do тем, треками, уровнями и учебным лексиконом. Отдаёт остальным модулям адресуемые темы, рекомендации («что стоит взять сейчас») и лексикон. Программа — карта, не система замков: модуль никогда ничего не блокирует.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `CurriculumVersion` | версионируемый снимок программы | version, activated_at, changelog |
| `Level` | CEFR-уровень с главным результатом | id (A1…C2), outcome |
| `Track` | сквозной трек через уровни | id, title, from_level |
| `Module` | группа тем уровня вокруг рабочей задачи | id (`a2.2-results-and-experience`), can_do, topics |
| `Topic` | единица изучения | см. формат ниже |
| `LexicalItem` | единица лексикона ([[../product/lexical-system]]) | id, type, band, register, usage_policy… |

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
mastery_criteria: {...}        # критерии по dimensions
explanation_language: ru-allowed   # когда допустим русский
```

`advisory_prerequisites.strong/soft` — сила рекомендации, не замок (в learning-model §9 это hard/soft; здесь переименовано в strong/soft, чтобы исключить прочтение «hard = блокирует»).

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

## 3. Данные и лицензии [PD-2026-07-19, закрывает OPEN-6]

| Источник | Роль | Лицензия | Обязательства |
|---|---|---|---|
| CEFR-J Vocabulary/Grammar Profiles (olp-en-cefrj) | CEFR-разметка слов и грамматики | A1–B2: free research+commercial с цитированием (Tono Lab); C1/C2 Octanove: CC BY-SA 4.0 | цитирование в ATTRIBUTIONS |
| NGSL / NAWL / Business SL | core/high frequency band, рабочая лексика | CC BY-SA 4.0 | attribution; производные данные при публикации — CC BY-SA |
| wordfreq (rspeer) | численные частоты; присутствие в Reddit/Twitter для informal | код Apache-2.0, данные CC BY-SA 4.0 | attribution; данные заморожены ~2021 — ок для stable core |

- **MUST**: файл `ATTRIBUTIONS.md` в корне репо с цитированиями появляется вместе с первым импортом данных.
- **MUST NOT**: импортировать данные CEFR-SP (лицензия не указана) и данные OpenVLT (лицензия данных не заявлена; используется только как архитектурный reference).

## 4. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `get_topic(id)` | API | тема с полным содержимым | `[mvp]` |
| `recommendations(learner_state)` | API | темы с флагом `recommended / early` по advisory-графу и уровням | `[mvp]` |
| `lexicon_query(filter)` | API | выборка LexicalItem (band, track, usage_policy, currency) | `[mvp]` |
| `validate()` | API | полная валидация активной версии | `[mvp]` |
| `CURRICULUM_VERSION_ACTIVATED` | publishes | активация новой версии программы | `[mvp]` |
| `LEXICAL_ITEM_ADDED` | publishes | пополнение living layer | `[mvp]` |

## 5. Поведение

- **MUST**: у каждой темы есть `can_do`; тема без наблюдаемого умения не проходит валидацию.
- **MUST**: граф advisory — модуль выдаёт рекомендации, никогда не запрещает ([[../product/learning-model]] §1, §4).
- **MUST**: стабильные ID бессмертны: использованный в evidence ID нельзя изменить или удалить — только deprecation с указанием преемника и миграцией.
- **MUST**: программа версионируется; движок работает с активированной валидной версией; изменения — только через `maintain-english-curriculum` workflow.
- **MUST**: валидация ловит: циклы advisory-графа; битые ссылки prerequisites/lexicon/module/track; дубли ID; prerequisite с CEFR выше уровня темы; пустые dimensions; отсутствие can_do; informal-единицу без `usage_policy`; `meme_template` без нейтрального объяснения или `currency`; импортированную единицу без attribution-меты.
- **MUST**: informal-единицы с `usage_policy: avoid` и `recognition_only` не попадают в production-упражнения и не рекомендуются к употреблению — только на понимание ([[../product/lexical-system]]).
- **MUST**: TOEFL-трек не порождает тем ниже B1.
- **SHOULD**: каждая тема связана хотя бы с одним рабочим контекстом (AI/AEC/SaaS/переписка/форум).

## 6. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer curriculum validate` | валидация активной версии | exit 0 / список ошибок с адресами |
| `trainer curriculum show --topic ID --format json` | содержимое темы | Topic JSON |
| `trainer curriculum lexicon --filter ... --format json` | выборка лексикона | список LexicalItem |

## 7. Границы

- **depends on**: kernel (policy registry, IDs), storage
- **events published**: `CURRICULUM_VERSION_ACTIVATED`, `LEXICAL_ITEM_ADDED`
- **consumed by**: scheduler, lessons, assessments, learner, memory (через API рекомендаций/тем/лексикона)

## 8. Открытые вопросы

Нет новых. OPEN-6 закрыт этим контрактом.

## История изменений

- **2026-07-19**: создан по одобренному концепту Codex (can-do граф, 8 треков, формат темы) + решение OPEN-6 (CEFR-J + NGSL + wordfreq). Все решения [PD-2026-07-19].
