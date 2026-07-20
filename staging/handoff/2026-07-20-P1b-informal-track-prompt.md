# Промпт-делегация: П.1b — расширение informal-трека в каркасе

Скопировать целиком в Codex, запущенный в корне репозитория AI_trainer_eng.

---

Ты — автор учебной программы. Задача — **точечный патч** уже принятого каркаса (`curriculum/`): расширить недопредставленный трек `everyday-online-informal` для A1–A2. Content-review показал: сейчас в треке 2 темы против концепта, где он заметно богаче. Всё остальное в каркасе трогать не нужно.

## Контекст

1. `curriculum/README.md` и `curriculum/topics/a1.yaml`, `a2.yaml` — текущий каркас (85 тем; в informal-треке только `everyday-online-informal.basic-chat-response` (A1, модуль a1.5) и `everyday-online-informal.casual-neutral-request` (A2, модуль a2.6)).
2. `staging/journal/2026-07-19-codex-curriculum-concept.md` — одобренный концепт, раздел **Everyday, Online & Informal English** (шесть слоёв) и «Распределение по уровням».
3. `wiki/modules/curriculum.md` — формат Topic и правила валидации.
4. `wiki/product/lexical-system.md` §3b — informal-слой, `usage_policy`, регистр.
5. `staging/reviews/2026-07-20-P1-content-review.md` — находка C-2 (что именно недостаёт).

## Что добавить

Темы трека `everyday-online-informal` для A1–A2, по концепту:

- **A1** (модули по смыслу, напр. a1.1/a1.4/a1.5): contractions в переписке; базовые casual-ответы/подтверждения (Sounds good, No worries, My bad).
- **A2** (напр. a2.6/a2.7/a2.8): распространённые сокращения (IMO/FYI/TL;DR/AFAIK); простые форумные ответы (ответ в ветке, уточняющий вопрос, краткий ответ без грубости); **распознавание тона** (helpful / dismissive / sarcastic / hostile); переключение casual ↔ neutral.

Ориентир — 4–7 новых тем суммарно; не раздувай.

## Ограничения (важно)

1. **Только topic-skeleton**, как в П.1: `id`, `cefr`, `track: everyday-online-informal`, `module`, однострочный `can_do`, `advisory_prerequisites` (`strong`/`soft`). **Ничего больше.**
2. **НЕ добавлять**: `mastery_criteria`, `topic.lexicon`, LexicalItem/лексикон, `usage_policy` на темах, `typical_errors`, examples, числа. Лексикон — П.4 (после OPEN-15); тела тем — П.2.
3. **Vocabulary & Chunks остаётся без тем** — это принятое решение [PD-2026-07-20]: лексика живёт в лексиконе, не в topic'ах. Не создавай vocab-темы.
4. Новые темы **вписываются в существующие модули** (менять список `topics:` соответствующих module-файлов). Новых модулей не создавать.
5. Prerequisites — только на существующие темы, `strong`/`soft`, без циклов, CEFR prerequisite не выше темы. Опирайся на уже существующие informal/written-interaction темы.
6. Менять только файлы под `curriculum/`. `wiki/`, `docs/`, остальной `staging/` — не трогать. Пустой `Irregular Verbs.md` в корне не трогать.
7. Продуктовые развилки не решай — помечай `# TODO(review)`.

## Самопроверка

- Все новые id уникальны, dotted, резолвятся; module-файлы обновлены согласованно.
- Нет циклов; CEFR-инверсий нет; только strong/soft.
- Нет запрещённых полей (п.2).
- Пересчитай итог: сколько тем стало всего, сколько в informal-треке.

## Отчёт

Сохрани в `staging/handoff/2026-07-20-P1b-informal-track-report.md`: что добавлено (список id с модулями), новые счётчики (всего тем / informal), самопроверка, `TODO(review)`-домыслы.
