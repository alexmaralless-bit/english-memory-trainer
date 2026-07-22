# Модуль: memory (Obsidian Vault)

> **Status**: current
> **Last updated**: 2026-07-22
> **Sources**: `docs/design-direction.md` §4 · [[../platform/foundation]] §3.7–§3.8 (outbox, rebuild, drift) · [[../product/lexical-system]] §4 · [[../flows/continuation]] · бриф §5.4 · Concept Gate 0.6 2026-07-20 (3 развилки, [PD-2026-07-20]) · контракт 0.6
> **Bounded context**: `src/english_trainer/memory/`

> Спека — **target**. Термины — [[../glossary]]. Закрывает OPEN-2 и OPEN-3.

---

## 1. Назначение

Модуль генерирует **читаемую связанную проекцию** состояния ученика в Obsidian-вольт: страницы тем, сессий, ошибок, лексики, повторений + сводные дашборды. Проекция — **для человека**. Она **никогда** не источник scoring и не источник восстановления состояния агентом ([[../flows/continuation]]: агент берёт tutor briefing из движка).

## 2. Две зоны [PD-2026-07-20, OPEN-2]

| Зона | Владелец | Правило |
|---|---|---|
| `memory/` | **движок** | Полностью генерируется и перезаписывается. Руками не редактируется — правки будут затёрты при regenerate/rebuild. |
| `notes/` | **ученик** | Движок **никогда** сюда не пишет и не читает как состояние. Личные заметки, свои связи, черновики. |

- **MUST**: движок пишет только в `memory/`; запись в `notes/` запрещена (архитектурный чек).
- **MUST**: `memory check` (drift) проверяет **только** `memory/`; содержимое `notes/` не сверяется и не влияет на состояние.
- **MUST**: ссылки `[[...]]` из `notes/` в генерённые страницы поддерживаются — граф Obsidian работает через обе зоны. Обратные ссылки движок не создаёт.
- **SHOULD** (операционное): в настройках Obsidian «место для новых заметок» указать `notes/` — иначе клик по несуществующему wikilink создаёт пустой файл в корне (уже наблюдалось: пустой `Irregular Verbs.md` в корне репозитория; настоящая страница — `memory/knowledge/irregular-verbs.md`).

## 3. Интеграция — обычные файлы [PD-2026-07-20, OPEN-3]

- **MUST**: движок пишет **обычный markdown** в папку; Obsidian просто открывает её как vault. Никакой зависимости от Obsidian CLI или плагина — приложение остаётся local-first и переживает любое обновление Obsidian.
- **MAY**: адаптер поверх (авто-открытие, команды) — необязательное удобство, не часть контракта.
- **MUST**: файлы детерминированы — стабильный порядок строк/списков, идемпотентный вывод (повторный render без изменений состояния не меняет байты).

## 4. Структура [PD-2026-07-20]

Страница на сущность (граф) + сводные дашборды (чтение):

```text
memory/
├── current/                     ← дашборды
│   ├── learner-profile.md
│   ├── current-level.md         ← measured_working_level по навыкам + confidence
│   ├── next-session.md          ← план следующей сессии
│   ├── roadmap-progress.md      ← прогресс по программе
│   ├── recurring-errors.md
│   └── vocabulary-review.md     ← что скоро повторять
├── topics/<topic-id>.md
├── sessions/YYYY/YYYY-MM-DD-<session-id>.md
├── errors/<error-id>.md
├── knowledge/
│   ├── vocabulary/<item-id>.md
│   ├── chunks/<item-id>.md
│   └── irregular-verbs.md       ← генерённый обзор lexeme-форм
├── reviews/YYYY-MM-DD.md        ← что назначено на дату
├── gates/<gate-id>.md
└── plans/<session-id>.md
```

Узлы графа — Topic, Session, Error, Vocabulary, Chunk, Gate, Review, Plan (design-direction §4). Страница единицы связана с темами, ошибками и сессиями ([[../product/lexical-system]] §4).

- **MUST — frontmatter**: каждая генерённая страница несёт frontmatter с `generated: true`, идентификаторами источника (`source_ids`), `pinned_versions` и меткой «не редактировать». Это делает drift-проверку и rebuild механическими, а не археологическими.
- **MUST**: имена файлов детерминированы из стабильных ID; переименование сущности следует правилам deprecation ([[curriculum]] §5).

## 5. Обновление, rebuild и drift

- **MUST**: проекция обновляется **post-commit через outbox** ([[../platform/foundation]] §3.7) — не внутри ACID-транзакции. Сбой записи файлов не откатывает authoritative commit.
- **MUST**: доставка идемпотентна и упорядочена (per-consumer offset, applied-offset); полный **rebuild** — isolate-and-swap до high-water mark, затем ordered catch-up (реализовано kernel 1.2; OPEN-21 закрыт).
- **MUST — источник страницы объявлен, rebuild гибридный** [P0-7]: состояние в системе гибридное ([[../platform/foundation]] §2), поэтому «rebuild из event-store» верно не для всех страниц:

| Страницы | Источник | Протокол восстановления |
|---|---|---|
| topics, errors, vocabulary, chunks, gates-исходы, прогресс | event-sourced learning state | replay event-store |
| sessions, reviews-очередь, plans, exposure/cooldown, черновики | **SQLite-authoritative** operational state | render из authoritative SQLite (при утрате — из snapshot) |

  Утверждение «проекция полностью восстановима из event-store» было неверным: foundation прямо запрещает считать operational state event-sourced и не обещает capture-complete событий для него. Потеря `memory/` по-прежнему не теряет данных — но восстановление идёт двумя протоколами, а не одним.
- **MUST — drift-проверка сверяет с объявленным источником** [P0-7]: страница сверяется с тем источником, который указан в таблице выше и продублирован в её `source_ids`; сверять operational-страницу с event-store бессмысленно.
- **MUST — drift**: `trainer memory check` сверяет `memory/` с authoritative state и **завершается ошибкой** при расхождении (после catch-up; отставание в пределах offset — не ошибка, а pending, как с JSONL-export, foundation §2.1).

## 6. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `render(scope?)` | API | инкрементальное обновление затронутых страниц |
| `rebuild()` | API | **гибридный** пересбор по page-source manifest (§5): event-sourced страницы — replay с isolate-and-swap до high-water mark; operational — render из authoritative SQLite/snapshot в согласованной точке |
| `check()` | API | drift-проверка generated-зоны |
| `PROJECTION_UPDATED` | publishes | факт обновления проекции |

## 7. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer memory render` | обновить проекцию |
| `trainer memory rebuild` | полный пересбор из событий |
| `trainer memory check` | drift: расхождение → ошибка |

## 8. Границы

- **depends on**: kernel (outbox, projection framework, offsets), scoring/learner (состояние, уровни, агрегаты), evidence (ошибки/лексика), scheduler (что повторять), curriculum (темы/лексикон), lessons (сессии).
- **events published**: `PROJECTION_UPDATED`.
- **consumed by**: человек (Obsidian). **Не** consumed движком или агентом как источник состояния.

## 9. Открытые вопросы

Закрывает **OPEN-2** и **OPEN-3**; механика доставки/rebuild реализована в kernel 1.2 и закрыла OPEN-21.

## История изменений

- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). Obsidian-адаптер — MAY без фазы.
- **2026-07-20**: создан (контракт 0.6). Две зоны `memory/` (generated) и `notes/` (ученик), обычные файлы без зависимости от Obsidian CLI/плагина, структура «страница на сущность + дашборды» — [PD-2026-07-20]. Post-commit через outbox, rebuild из event-store, drift только в generated-зоне. Закрывает OPEN-2/OPEN-3.
