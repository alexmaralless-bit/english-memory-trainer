# Лексическая система

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: дизайн пользователя 2026-07-19 (Concept Gate, зафиксирован в journal) · концепт Codex по informal-треку (`staging/journal/2026-07-19-codex-curriculum-concept.md`) · [[learning-model]] §3–§4, §7 · все решения [PD-2026-07-19]
> **Роль**: продуктовый контракт словарной системы (roadmap 0.9). Определяет три слоя лексики и их связь со scoring. Формат данных и frequency source — Curriculum Contract (0.3); проекция — Obsidian Vault Contract (0.6); отбор лексикона A1–A2 — работа П.4.

---

## 0. Принцип: сложность индивидуальна

Словарная система — не «список сложных слов». Обычное слово может постоянно вызывать ошибки, а редкое техническое — запомниться сразу. Программа задаёт, **чему учить** (слой 1–2); личная сложность **выводится из evidence** (слой 3), а не назначается заранее.

## 1. Слой 1 — учебный лексикон программы

- **MUST**: curriculum заранее содержит отобранные лексические единицы: слова, устойчивые выражения и chunks, phrasal verbs, неправильные глаголы, рабочую лексику AI/AEC/SaaS.
- **MUST — три раздельные величины** [ревью E-7/F-6]: не смешивать частоту, педагогический приоритет и персональный приоритет:
  - `frequency_band` — **корпусная** частота (из источников данных: `core | high | useful | specialized | incidental`), только corpus statistic;
  - `curriculum_priority_band` — педагогический приоритет в программе: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL` (policy output);
  - `learner_priority` — персональный приоритет ученика; **вычисляется** движком (учитывает личную потребность), не хранится глобальным полем. Формула — 0.4 ([[../OPEN]] OPEN-8).
- **MUST**: каждая единица — сущность `LexicalItem` со стабильным ID. Минимальные поля:

```yaml
id: chunk.follow-up-on
type: chunk               # word | chunk | phrasal-verb | lexeme | informal_chunk | abbreviation | meme_template
title: follow up on
cefr: A2
frequency_band: high      # корпусная частота (source)
curriculum_priority_band: HIGH   # педагогический приоритет
register: neutral
domains: [work, project-management]
meaning_ru: уточнить или вернуться к вопросу
source_refs: [ngsl@1.01]  # ссылки на SourceArtifact (provenance)
examples:
  - I'll follow up on this tomorrow.
```

- Источники данных и лицензии — решены (OPEN-6): CEFR-J + NGSL + wordfreq, build-time режим; схема provenance и notices — [[../OPEN]] OPEN-15, детали — [[../modules/curriculum]] §3.

## 2. Слой 2 — lexemes и формы

- **MUST**: неправильный глагол — один `LexicalItem` типа lexeme с формами, не три отдельные записи:

```yaml
id: lexeme.go
lemma: go
forms:
  base: go
  past: went
  participle: gone
frequency_band: core
```

- **MUST**: `go`, `went`, `gone` не считаются тремя выученными словами — владение привязано к одному lexeme, но движок отдельно видит evidence по каждой форме (умеет ли ученик использовать past, participle).
- **MUST — агрегация форм** [ревью D-7]: у lexeme определены form dimensions и **required set** форм; состояние lexeme детерминированно агрегируется из evidence по формам (знание только `go` не делает lexeme ACTIVE/MASTERED при незнании `went/gone`). Правила required forms и агрегации — [[../OPEN]] OPEN-14.
- **MUST**: страница `[[Irregular Verbs]]` — генерённый обзор, не отдельная копия данных.
- **SHOULD**: активно изучаются частотные глаголы (`core`/`high`); редкие и устаревшие остаются справочными (`INCIDENTAL`), не попадая в повторения без личной потребности.

## 3. Слой 3 — личный словарь ученика

- **MUST**: «выучено» — не boolean. Для каждой отслеживаемой единицы ведётся `LearnerLexicalState`:
  - когда впервые встретилась;
  - в каких сессиях использовалась;
  - значение или конкретный sense (если единица многозначна);
  - recognition и production evidence раздельно;
  - типичные ошибки (связь с observed errors);
  - Mastery, Stability, Retrievability;
  - последняя проверка и следующий review;
  - состояние.
- **MUST**: состояния — та же машина, что у тем ([[learning-model]] §4): попадание в личный словарь = `INTRODUCED`, далее `LEARNING / ACTIVE / MASTERED / REVIEW_DUE / AT_RISK`. Отдельной машины для лексики нет. LexicalItem — LearningTarget наравне с Topic ([[../glossary]]).
- **MUST — enrollment ≠ знание** [ревью D-6]: `INTRODUCED` — это enrollment/tracking (Mastery 0), не доказательство знания. Критерии входа 5–6 ниже (полезность, просьба запомнить) — enrollment-события, дают INTRODUCED, но **не evidence** и сами по себе не двигают состояние выше; критерии 1–4 могут порождать evidence.
- **MUST**: единица попадает в личный словарь, только если выполнен хотя бы один критерий:
  1. была целью упражнения;
  2. ученик её не понял;
  3. допустил значимую ошибку;
  4. агент целенаправленно её объяснил;
  5. выражение отмечено как особенно полезное (enrollment);
  6. ученик попросил её запомнить (enrollment).
- **MUST NOT**: записывать каждое случайно встретившееся слово.
- **MUST**: лексические единицы участвуют в повторениях и re-entry на общих основаниях ([[learning-model]] §7): review-цели манифеста могут указывать на LexicalItem так же, как на тему.

## 3b. Informal-слой (Everyday, Online & Informal English)

Письменный разговорный английский — чаты, форумы, GitHub, Discord, Reddit — полноправная часть лексикона [PD-2026-07-19]. Это не оценка speaking.

- **MUST**: informal-единицы — те же `LexicalItem` с расширенными полями. `volatility` (устойчивость) и `currency` (актуальность) — раздельные поля [ревью A-5/F-7]:

```yaml
id: slang.my-bad
type: informal_chunk        # + abbreviation | meme_template
register: casual            # шкала: formal → neutral → casual → slang → potentially-offensive
usage_policy: safe_to_use   # safe_to_use | context_dependent | recognition_only | avoid
allowed_contexts: [general, work-chat]     # где допустимо употребление
meaning_ru: моя ошибка / виноват
neutral_equivalent: That was my mistake.
communities: [general, work-chat]
frequency_band: high
volatility: stable          # stable | changing
currency: current           # current | dated | obsolete  (для changing)
first_observed_at: 2026-07-19
last_verified_at: 2026-07-19
source_refs: [...]
```

- **MUST — usage_policy у каждой единицы.** Понимать ≠ употреблять: `recognition_only` и `avoid` изучаются только на распознавание и никогда не рекомендуются к production.
- **MUST — assessable dimensions по policy** [ревью H-2]: набор оцениваемых dimensions и `mastery_criteria` зависят от `usage_policy`. Для `recognition_only`/`avoid` production-dimensions не требуются (единица не «застревает» перед MASTERED и scheduler не требует запрещённого production); natural-response проверяется только для разрешённого production. Правила — [[../OPEN]] OPEN-13.
- **MUST — context_dependent имеет enforcement** [ревью H-4]: `context_dependent` задаёт `allowed_contexts`/disallowed; вне разрешённого контекста единица трактуется как `recognition_only` (safe default). `communities` — метаданные, не правило допуска.
- **MUST — currency lifecycle** [ревью D-8/H-5]: для `volatility: changing` обязательны `first_observed_at`, `last_verified_at`, `currency`, источник/сообщество; валидатор проверяет полный набор (не только наличие одного поля). Переходы `current → dated → obsolete`, владелец, TTL/reverification и update-event — [[../OPEN]] OPEN-14. `meme_template` хранит нейтральное объяснение и культурный контекст; «все мемы заранее» собирать не нужно — living layer пополняется из обучения.
- **MUST — stale-safety банка** [ревью H-3]: банк упражнений и placement-формы хранят lexical refs + snapshot usage_policy; при обновлении policy несовместимые items (`safe_to_use → recognition_only/avoid/obsolete`) инвалидируются или ре-валидируются против active version перед повторным использованием в production. Механизм — [[../OPEN]] OPEN-14.
- **MUST**: оценка informal-владения проверяет: понимание значения, распознавание тона (helpful/dismissive/sarcastic/hostile), выбор допустимого контекста, перевод в нейтральный английский, естественный ответ (для разрешённого production), перенос между регистрами.
- **MUST — Informal ↔ CEFR через contribution_scope** [PD-2026-07-19, ревью C-5/H-1]: recognition сленга/мемов **никогда** не в CEFR. Письменное производство в реальном рабочем контексте может давать компонент writing/transfer через `contribution_scope`-тег evidence, с dedup и cap (один source-span — не одновременно в informal-профиль и CEFR сверх cap). Informal-владение ведётся отдельным профилем **Informal Online Competence** с собственной шкалой ([[learning-model]] §5, механизм — [[../OPEN]] OPEN-13).

Каталоги: **stable core** (проектируется заранее) / **living layer** (встреченное в обучении, через maintain-workflow с provenance; rights_basis — [[../OPEN]] OPEN-15) / **learner lexicon** (личный словарь, §3). Источники частот и CEFR-разметки — контракт [[../modules/curriculum]] §3.

## 4. Obsidian-проекция

Генерённые страницы (детали — контракт 0.6):

```text
memory/knowledge/vocabulary/
memory/knowledge/chunks/
memory/knowledge/irregular-verbs.md
memory/current/vocabulary-review.md
```

Страница единицы связана с темами, ошибками и сессиями:

```markdown
# follow up on

- Introduced in [[sessions/2026-07-19-session-001]]
- Related topic: [[topics/work.project-updates]]
- Error: [[errors/missing-preposition-after-follow-up]]
- Next review: [[reviews/2026-07-22]]
```

## 5. Распределение по контрактам

| Что | Куда |
|---|---|
| Формат `LexicalItem`, source provenance/лицензии | Curriculum Contract (0.3) + OPEN-15 |
| `LearnerLexicalState`, scoring, informal-профиль, агрегация форм | 0.4 + OPEN-13/OPEN-14 |
| Фиксация лексики в сессии (vocabulary/chunk observed) | уже в [[../flows/session]] |
| Obsidian-страницы лексики | Obsidian Vault Contract (0.6) |
| Отбор лексикона A1–A2 по категориям | работа П.4 |

## 6. Открытые вопросы

Механизмы зафиксированных выше инвариантов достраиваются в контрактах ([[../OPEN]]):

- **OPEN-13**: Informal Online Competence — шкала, contribution_scope, assessable dimensions по policy → 0.4.
- **OPEN-14**: currency/usage-policy lifecycle, context_dependent enforcement, stale-safety банка, агрегация форм lexeme → curriculum detail / П.3.
- **OPEN-15**: SourceArtifact provenance, CC BY-SA notices, rights_basis living layer → 0.3 / П.4.
- **OPEN-8**: формула learner_priority → 0.4.

## История изменений

- **2026-07-19 (3)**: red-team триаж — разделены frequency_band/curriculum_priority_band/learner_priority (E-7/F-6) и volatility/currency (A-5/F-7); агрегация форм lexeme (D-7); enrollment≠знание (D-6); assessable dimensions по usage_policy (H-2); context_dependent enforcement (H-4); currency lifecycle и полная валидация (D-8/H-5); stale-safety банка (H-3); Informal→CEFR через contribution_scope (C-5). Механизмы → OPEN-13/14/15.
- **2026-07-19 (2)**: добавлен §3b — informal-слой по одобренному концепту Codex.
- **2026-07-19**: создана по дизайну пользователя: три слоя, композитный приоритет, lexeme с формами, не-boolean личный словарь. Все решения [PD-2026-07-19].
