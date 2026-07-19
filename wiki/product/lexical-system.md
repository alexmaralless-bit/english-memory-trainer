# Лексическая система

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: дизайн пользователя 2026-07-19 (Concept Gate, зафиксирован в journal) · [[learning-model]] §3–§4, §7 · все решения [PD-2026-07-19]
> **Роль**: продуктовый контракт словарной системы (roadmap 0.9). Определяет три слоя лексики и их связь со scoring. Формат данных и frequency source — Curriculum Contract (0.3); проекция — Obsidian Vault Contract (0.6); отбор лексикона A1–A2 — работа П.4.

---

## 0. Принцип: сложность индивидуальна

Словарная система — не «список сложных слов». Обычное слово может постоянно вызывать ошибки, а редкое техническое — запомниться сразу. Программа задаёт, **чему учить** (слой 1–2); личная сложность **выводится из evidence** (слой 3), а не назначается заранее.

## 1. Слой 1 — учебный лексикон программы

- **MUST**: curriculum заранее содержит отобранные лексические единицы: слова, устойчивые выражения и chunks, phrasal verbs, неправильные глаголы, рабочую лексику AI/AEC/SaaS.
- **MUST**: приоритет единицы определяется композицией факторов, не одной частотностью:
  общая частотность + коммуникативная полезность + применимость в работе + соответствие CEFR + продуктивность выражения + личная потребность ученика.
- **MUST**: категории приоритета: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL`.
- **MUST**: каждая единица — сущность `LexicalItem` со стабильным ID. Минимальные поля:

```yaml
id: chunk.follow-up-on
type: chunk            # word | chunk | phrasal-verb | lexeme | ...
title: follow up on
cefr: A2
frequency_band: high   # core | high | useful | specialized | incidental
register: neutral
domains: [work, project-management]
meaning_ru: уточнить или вернуться к вопросу
examples:
  - I'll follow up on this tomorrow.
```

- Точный frequency source и лицензирование словарных данных — **OPEN-6**, решается в Curriculum Contract (0.3).

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
- **MUST**: состояния — та же машина, что у тем ([[learning-model]] §4): попадание в личный словарь = `INTRODUCED`, далее `LEARNING / ACTIVE / MASTERED / REVIEW_DUE / AT_RISK`. Отдельной машины для лексики нет.
- **MUST**: единица попадает в личный словарь, только если выполнен хотя бы один критерий:
  1. была целью упражнения;
  2. ученик её не понял;
  3. допустил значимую ошибку;
  4. агент целенаправленно её объяснил;
  5. выражение отмечено как особенно полезное;
  6. ученик попросил её запомнить.
- **MUST NOT**: записывать каждое случайно встретившееся слово.
- **MUST**: лексические единицы участвуют в повторениях и re-entry на общих основаниях ([[learning-model]] §7): review-цели манифеста могут указывать на LexicalItem так же, как на тему.

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
| Формат `LexicalItem`, frequency source, лицензии (OPEN-6) | Curriculum Contract (0.3) |
| `LearnerLexicalState`, scoring и повторения лексики | Evidence, Scoring & Review Contract (0.4) |
| Фиксация лексики в сессии (vocabulary/chunk observed) | уже в [[../flows/session]] |
| Obsidian-страницы лексики | Obsidian Vault Contract (0.6) |
| Отбор лексикона A1–A2 по категориям | работа П.4 |

## 6. Открытые вопросы

- **OPEN-6**: frequency source и лицензирование лексических данных → блокирует финализацию 0.3 и отбор П.4. Единый реестр — [[../OPEN]].

## История изменений

- **2026-07-19**: создана по дизайну пользователя: три слоя, композитный приоритет с категориями, lexeme с формами, не-boolean личный словарь с критериями входа. Все решения [PD-2026-07-19].
