# П.1b: расширение Everyday, Online & Informal English (A1–A2)

## Что добавлено

Добавлены шесть topic-skeletons; существующие модули обновлены так, чтобы их `topics` и `tracks` оставались согласованными.

| Topic ID | CEFR | Module |
|---|---|---|
| `everyday-online-informal.written-contractions` | A1 | `a1.4-work-in-progress` |
| `everyday-online-informal.casual-acknowledgements` | A1 | `a1.5-requests-and-clarification` |
| `everyday-online-informal.common-abbreviations` | A2 | `a2.6-collaboration` |
| `everyday-online-informal.casual-neutral-rephrasing` | A2 | `a2.6-collaboration` |
| `everyday-online-informal.tone-recognition` | A2 | `a2.7-reading-and-mediation` |
| `everyday-online-informal.forum-thread-reply` | A2 | `a2.7-reading-and-mediation` |

Все добавления содержат только поля skeleton: `id`, `cefr`, `track`, `module`, однострочный `can_do` и `advisory_prerequisites`.

## Счётчики

- Всего Topic: **91** (было 85).
- Topic в `everyday-online-informal`: **8** (было 2).
- Advisory-рёбра во всём графе: **117 strong**, **22 soft**.
- Максимальная глубина цепочки prerequisites: **11**.

## Самопроверка

Пройдено:

- все ID уникальны, dotted и резолвятся;
- все новые темы перечислены в соответствующих module-файлах, а новые треки добавлены в `tracks` модулей A1.4 и A2.7;
- все prerequisites существуют, используют только `strong`/`soft` и не имеют CEFR выше зависимой темы;
- граф prerequisites ацикличен;
- в новых темах отсутствуют запрещённые поля: `mastery_criteria`, `lexicon`, `usage_policy`, богатое тело и численные параметры;
- не создавались новые модули, Topic Vocabulary & Chunks или лексические единицы.

Проблем не найдено.

## TODO(review) и допущения

- `# TODO(review)`: выбор A1.4 для written contractions и A2.7 для tone/forum topics — минимальная авторская привязка к существующим рабочим модулям; концепт не задаёт точные module boundaries для этих тем.
- `# TODO(review)`: тема `casual-neutral-rephrasing` добавлена в A2 по прямому заданию этого патча. В одобренном концепте переключение casual ↔ neutral также названо в B1-распределении; следует подтвердить, что A2 задаёт базовый вариант, а B1 остаётся последующим расширением, а не дублирующей границей.
