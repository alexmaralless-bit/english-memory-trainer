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
- **MUST — три раздельные величины** [ревью E-7/F-6, rereview E-R5]: не смешивать частоту, педагогический приоритет и персональный приоритет:
  - `frequency_score` + `frequency_band` — **только** корпусная частота: numeric Zipf/source score + нейтральные bands `very_high | high | mid | low | rare` по versioned thresholds. **Никаких** педагогических/доменных категорий здесь;
  - `curriculum_priority_band` — педагогический приоритет: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL` (сюда ушли utility/domain-категории вроде useful/specialized/incidental);
  - `learner_priority` — персональный приоритет; **вычисляется** движком, не хранится глобально. Формула — 0.4 ([[../OPEN]] OPEN-8).
- **MUST**: каждая единица — сущность `LexicalItem` со стабильным ID. Минимальные поля:

```yaml
id: chunk.follow-up-on
type: chunk               # word | chunk | phrasal-verb | lexeme | informal_chunk | abbreviation | meme_template
title: follow up on
cefr: A2
frequency_score: 4.2      # numeric (Zipf/source)
frequency_band: mid       # very_high | high | mid | low | rare (по versioned thresholds)
curriculum_priority_band: HIGH   # педагогический приоритет
register: neutral
domains: [work, project-management]
meaning_ru: уточнить или вернуться к вопросу
source_refs: [ngsl@1.01]
transformations: [identity]   # журнал изменений при импорте (rereview I-R3)
examples:
  - I'll follow up on this tomorrow.
```

- **MUST — mastery-профиль** [rereview E-R3]: у каждого LexicalItem (в т.ч. обычного word/chunk) есть versioned `LexicalMasteryProfile` — required dimensions и mastery-критерии по type/usage_policy, разрешимый из curriculum; validator проверяет наличие профиля. Схема — 0.4 ([[../OPEN]] OPEN-13).

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
frequency_band: very_high
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
- **MUST**: три оси состояния — те же, что у тем ([[learning-model]] §4, [[../glossary]]): enrollment (`tracked`), knowledge state (`NEW → LEARNING → ACTIVE → MASTERED` + `AT_RISK`), review status (`not_due/due/overdue`). Отдельной машины для лексики нет. LexicalItem — LearningTarget наравне с Topic.
- **MUST — вход даёт только enrollment** [ревью D-6, rereview C-R2]: попадание в личный словарь = `tracked`, knowledge state `NEW`. **Ни один из критериев входа сам по себе не создаёт evidence.** Evidence появляется только при отдельном сохранённом learner response; целенаправленное объяснение единицы агентом (критерий 4) — enrollment, но не доказательство знания.
- **MUST**: единица попадает в личный словарь (enrollment), только если выполнен хотя бы один критерий:
  1. была целью упражнения;
  2. ученик её не понял;
  3. допустил значимую ошибку;
  4. агент целенаправленно её объяснил;
  5. выражение отмечено как особенно полезное;
  6. ученик попросил её запомнить.
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
cultural_context: "..."     # для meme_template — обязателен (rereview H-R1)
first_observed_at: 2026-07-19
last_verified_at: 2026-07-19
source_refs: [...]
```

- **MUST — usage_policy и `requires_usage_policy`** [rereview H-R1]: `requires_usage_policy` — вычисляемый predicate по type/register (не только по флагу «informal-единица»): рискованный `type: word`/register тоже обязан иметь usage_policy. Понимать ≠ употреблять: `recognition_only`/`avoid` — только на распознавание.
- **MUST — `production_eligible`** [rereview H-R1]: вычисляемый из active `usage_policy` + `currency`; `avoid`, `recognition_only` **и `obsolete`** → `production_eligible=false`. Единица с `safe_to_use` + `obsolete` не проходит свежую generation/scheduler.
- **MUST — assessable dimensions по policy** [ревью H-2]: dimensions и `mastery_criteria` зависят от `usage_policy`; для `recognition_only`/`avoid`/`obsolete` production не требуется (не «застревает» перед MASTERED). Правила — [[../OPEN]] OPEN-13.
- **MUST — context_dependent enforcement** [ревью H-4]: `context_dependent` задаёт `allowed_contexts`/disallowed; вне разрешённого контекста — `recognition_only` (safe default). `communities` — метаданные, не правило допуска.
- **MUST — currency lifecycle** [ревью D-8/H-5]: для `volatility: changing` обязательны `first_observed_at`, `last_verified_at`, `currency`, источник/сообщество; для `meme_template` — ещё `cultural_context`. Валидатор проверяет полный набор. Переходы `current → dated → obsolete`, владелец, TTL/update-event — [[../OPEN]] OPEN-14.
- **MUST — safety-overlay, safety не пинится** [PD-2026-07-19, rereview G-R1]: `production_eligible` всегда проверяется по **active** policy в момент доставки, а не по pinned-версии. Прошлое evaluation/replay остаётся детерминированным по pinned scoring; но live manifest / review assignment / банк / placement-форма перед доставкой production сверяются с active safety, и ставший `avoid`/`obsolete`/вне-контекста item **отменяется или заменяется** append-only event, хранящим обе версии. Owner механизма — [[../OPEN]] OPEN-14 (+0.5 для live delivery).
- **MUST**: оценка informal-владения проверяет: понимание значения, распознавание тона (helpful/dismissive/sarcastic/hostile), выбор допустимого контекста, перевод в нейтральный английский, естественный ответ (для разрешённого production), перенос между регистрами.
- **MUST — Informal ↔ CEFR через contribution_scope** [PD-2026-07-19, ревью C-5/H-1]: recognition сленга/мемов **никогда** не в CEFR. Письменное производство в реальном рабочем контексте может давать компонент writing/transfer через `contribution_scope`-тег evidence, с dedup и cap (один source-span — не одновременно в informal-профиль и CEFR сверх cap). Informal-владение ведётся отдельным профилем **Informal Online Competence** с собственной шкалой ([[learning-model]] §5, механизм — [[../OPEN]] OPEN-13).

Каталоги: **stable core** (проектируется заранее) / **living layer** (встреченное в обучении, через maintain-workflow с provenance) / **learner lexicon** (личный словарь, §3). Источники частот и CEFR-разметки — контракт [[../modules/curriculum]] §3.

- **MUST NOT — до закрытия OPEN-15** [rereview I-R2]: living layer **не хранит сторонние excerpts** (текст forum post/example) — provenance URL не даёт права копирования. Разрешено: source-метаданные, короткая единица и собственный нейтральный парафраз. Право на excerpts (`rights_basis`) решается в [[../OPEN]] OPEN-15.

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

- **2026-07-19 (4)**: rereview — frequency_band только numeric+нейтральные bands (E-R5); generic LexicalMasteryProfile (E-R3); вход даёт только enrollment, объяснение агента ≠ evidence (C-R2); production_eligible + obsolete + requires_usage_policy + cultural_context (H-R1); safety-overlay «safety не пинится» (G-R1); living layer без сторонних excerpts до OPEN-15 (I-R2); transformations в схеме (I-R3); три оси состояния.
- **2026-07-19 (3)**: red-team триаж — разделены frequency_band/curriculum_priority_band/learner_priority (E-7/F-6) и volatility/currency (A-5/F-7); агрегация форм lexeme (D-7); enrollment≠знание (D-6); assessable dimensions по usage_policy (H-2); context_dependent enforcement (H-4); currency lifecycle и полная валидация (D-8/H-5); stale-safety банка (H-3); Informal→CEFR через contribution_scope (C-5). Механизмы → OPEN-13/14/15.
- **2026-07-19 (2)**: добавлен §3b — informal-слой по одобренному концепту Codex.
- **2026-07-19**: создана по дизайну пользователя: три слоя, композитный приоритет, lexeme с формами, не-boolean личный словарь. Все решения [PD-2026-07-19].
