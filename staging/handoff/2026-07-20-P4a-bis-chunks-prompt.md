# Промпт-делегация: П.4a-bis — добор chunks и чистка лексикона

Скопировать целиком в Codex, запущенный в корне репозитория AI_trainer_eng.

---

Ты — автор учебного лексикона. Задача — **исправить состав** уже созданного stable core (`curriculum/lexicon/`) по итогам content-review. Сам формат и качество записей приняты; проблема в **балансе типов**: рабочих фраз-фреймов слишком мало, а часть «chunks» — на самом деле грамматика.

## Контекст

1. **`staging/reviews/2026-07-20-P4a-lexicon-content-review.md`** — content-review с находками. ГЛАВНЫЙ ВХОД.
2. `curriculum/lexicon/*.yaml` + `README.md` — текущий лексикон (204 единицы).
3. `staging/journal/2026-07-19-codex-curriculum-concept.md` — одобренный концепт: в нём **прямо названы** chunks, которых сейчас нет.
4. `wiki/product/lexical-system.md`, `wiki/modules/curriculum.md` §2/§3.1–3.2/§5 — модель и границы (не изменились).
5. `curriculum/topics/a1.yaml`, `a2.yaml` — 91 тема: фреймы отбираются под их can-do.

## Задача 1 — убрать грамматические псевдо-chunks [PD-2026-07-20]

Удалить из `chunk`-типа единицы, которые дублируют существующие Topic'и (грамматика уже покрыта темой с can-do и критериями; дублирование создаёт двойной учёт в scoring):

`there is`, `there are`, `have finished`, `better than`, `if ... then ...`, `must have`, `working on` (дублирует phrasal `work on`).

Пройди весь список chunk и убери **все** подобные грамматические паттерны, не только перечисленные. Наречные обороты времени (`after that`, `right now`, `at the time`, `every day`, `by Friday`) — перевести в `type: word`/коллокации либо удалить, если малополезны.

## Задача 2 — добрать настоящие рабочие фреймы до ~90–120 chunks [PD-2026-07-20]

Целевой ориентир: **5–8 chunks на каждый из 16 модулей A1–A2**. Фрейм — готовая многословная заготовка, которую ученик вставляет в реальное рабочее сообщение.

**Обязательно включить все фразы, названные в концепте** (сейчас их нет ни одной):
`we've completed`, `we've run into an issue`, `I've already checked`, `I'm working on`, `we're testing`, `the main advantage is`, `we should consider`, `I usually start by`, `how often do you…`.

Области покрытия (примеры направления, не готовый список):

- **статус/прогресс**: I'm currently working on…, it's still in review, we're waiting on…, this is blocked by…
- **инциденты/баги**: we ran into…, it stopped working after…, steps to reproduce, expected vs actual, it only happens when…
- **результаты (present perfect, A2.2)**: we've deployed…, we've completed…, I've already checked…, it's been fixed
- **планирование/сроки**: we're planning to…, I'll get it done by…, let's push it to…, that's out of scope
- **требования/варианты**: the main advantage is…, we should consider…, it depends on…, either way
- **коллаборация**: could you take a look at…, just to confirm…, let me know if…, thanks for the update, sorry for the delay
- **чтение/mediation**: in short…, the key point is…, as far as I understand…, it says that…

## Задача 3 — перекалибровать priority bands

Сейчас `CORE` 121 / `HIGH` 76 / `USEFUL` 7, `SPECIALIZED`/`INCIDENTAL` не использованы — band почти не различает приоритет. Перераспредели по всему лексикону так, чтобы `CORE` был действительно ядром (ориентир: CORE ≲ 30–35% единиц), и задействуй нижние bands там, где уместно.

## Задача 4 — дополнить advisory topic-links

Сейчас 60 связей на 204 единицы. Довести покрытие хотя бы для всех новых и всех `CORE`/`HIGH` единиц. Файл `_suggested-topic-links.yaml` остаётся **advisory**, не источник истины.

## Границы (не изменились)

1. **Корпусный проход НЕ делать**: `frequency_score`/`frequency_band`/`source_refs` не проставлять, значения не выдумывать (это П.4b).
2. Примеры — **собственные**; сторонние excerpts запрещены.
3. **НЕ трогать** `curriculum/topics/*`, `curriculum/modules/*`, `wiki/`, `docs/`, корневой `Irregular Verbs.md`. Менять только `curriculum/lexicon/`.
4. `mastery_criteria` / `LexicalMasteryProfile` не создавать; `topic.lexicon` не заполнять (это П.2).
5. Informal-единицы: у всех `usage_policy`; у `context_dependent` — `allowed_contexts`. `meme_template` не создавать.
6. Схема форм lexeme **уточнена**: слот может быть списком (`be → past: [was, were]`) — это теперь легально, приводить к одиночному значению не нужно.
7. Развилки не решать — `# TODO(review)`.

## Самопроверка

- Итог по типам: `chunk` ≈ 90–120; multi-word единицы (chunk + phrasal + informal) составляют **≥ 55%** лексикона.
- Ни одного грамматического паттерна в `type: chunk`.
- Все девять фраз из концепта присутствуют.
- Каждый из 16 модулей A1–A2 имеет ≥5 связанных chunks (по advisory-links).
- ID уникальны, dotted; у всех единиц band/register/meaning_ru/свой пример/`transformations: [authored]`.
- `frequency_*` отсутствуют; topics/modules не изменены.

## Отчёт

`staging/handoff/2026-07-20-P4a-bis-report.md`: что удалено/переклассифицировано (список), что добавлено (список новых chunks по модулям), новое распределение по типам и bands, покрытие модулей chunks, `TODO(review)`.
