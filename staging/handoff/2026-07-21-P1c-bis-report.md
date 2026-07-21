# Отчёт П.1c-bis — темы не-дословного понимания

Дата: 2026-07-21 · Исполнитель: Claude (не делегировано — Codex занят ревью 0.12) · Вход: `staging/reviews/2026-07-20-P1c-everyday-life-review.md`, промпт `staging/handoff/2026-07-20-P1c-bis-prompt.md`

## Итог

Добавлено **10 тем** и **2 модуля**. Каркас: 136 → **146 тем**, 30 → **32 модуля**. Все 14 непрозрачных идиом, оставшихся без темы после П.4c, получили дом. **Сирот-opaque больше нет.**

## Что двигало этот проход

Content-review П.1c нашёл дыру в главном приоритете ученика: *«не тупить, переводя дословно»*. Контракт под это ввёл ось `transparency`, тип `idiom` и `literal_trap_ru`, а П.4c дал 155 непрозрачных единиц. Но **ни одна из 136 тем не делала не-дословное понимание учебной целью** — все бытовые can-do продуктивные, а контракт запрещает требовать производство `opaque`-единиц. Планировщику нечего было ставить в расписание для идиом.

## Ключевое решение: трек `reading`, а не новый

Темы понимания положены в существующий трек `reading`, а не в новый трек и не в `everyday-life`. Причина — по `core_skill_map` ([[../../wiki/modules/scoring]] §4) `reading` + `recognition` строит навык **Reading**, а «понять, не переводя буквально» и есть recognition-скилл чтения. Заводить новый трек под кросс-доменный навык (идиома не принадлежит домену) значило бы смешать скилл с доменом — та же ошибка, что уже распутывалась для частоты/приоритета. Прецедент есть: `everyday-online-informal.tone-recognition` — тоже recognition-тема.

Одна тема — `written-production.paraphrase-expression` — в треке `written-production-mediation`: перефразировать идиому нейтральным английским это **медиация смысла**, а не производство идиомы, и её дом рядом с существующей `written-production.paraphrase-summary`.

## Новые модули и темы

### a1.14 — Understanding everyday expressions (трек reading, A1)

| Тема | can-do |
|---|---|
| `reading.everyday-phrasal-verbs` | Recognize the everyday meaning of a common phrasal verb when its parts do not add up (put up with, figure out). |
| `reading.common-idioms` | Recognize a very common fixed expression and tell its real meaning apart from the word-for-word reading. |
| `reading.casual-reactions` | Understand short casual reactions in a chat (no way, never mind, fair enough) and what the writer actually means. |
| `reading.everyday-notice` | Find the key information in a short everyday notice, sign, or label. |
| `reading.household-instructions` | Follow short written instructions for a household item or service. |

### a2.14 — Non-literal meaning and reading (треки reading + written-production-mediation, A2)

| Тема | can-do |
|---|---|
| `reading.idioms-in-context` | Work out the meaning of a less common idiom from the surrounding context instead of translating it literally. |
| `reading.stable-slang` | Recognize common stable slang in casual writing and state its neutral meaning. |
| `reading.personal-message` | Understand the main point and tone of a short personal message or review. |
| `reading.short-news-item` | Get the main facts from a short everyday news item or announcement. |
| `written-production.paraphrase-expression` | Restate an everyday idiom or phrasal verb in plain neutral English, showing its meaning is understood. |

**Все can-do — узнавание, различение, медиация. Ни один не требует производить идиому.** Различение буквального и настоящего смысла вписано прямо в формулировки («tell its real meaning apart from the word-for-word reading», «instead of translating it literally»).

## Задача 2 — бытовое чтение

Выполнена внутри тех же тем: `reading.everyday-notice`, `reading.household-instructions`, `reading.personal-message`, `reading.short-news-item` — объявление/вывеска, инструкция к бытовому прибору, личное сообщение/отзыв, короткая новость. Трек `reading` вырос с 4 до 13 тем.

## Замыкание цели: 14 сирот привязаны

`_suggested-topic-links.yaml` дополнен: все 14 непрозрачных идиом без темы (`all of a sudden`, `beats me`, `from scratch`, `in a nutshell`, …) связаны с `reading.idioms-in-context`. Это единственное касание `curriculum/lexicon/` в проходе — оно и есть завершающий шаг: без него новые темы существовали бы, а идиомы к ним не привязаны. Файл остаётся advisory, `topic.lexicon` не заполнялся.

## Проверка (независимый скрипт)

| Критерий | Результат |
|---|---|
| Новых тем | 10; всего 146 ✓ |
| Новых модулей | 2; всего 32 ✓ |
| Новых тем `grammar-engine` | **0** ✓ |
| can-do требует производства идиом | **нет** ✓ |
| У каждой темы `can_do`, module существует, тема в списке модуля | ✓ |
| Висячие prerequisites | нет ✓ |
| CEFR-инверсии | нет ✓ |
| Циклы в advisory-графе | нет ✓ |
| Дубликаты ID | нет ✓ |
| opaque-единиц без темы | **0** (было 14) ✓ |
| Висячие ссылки в advisory-links | нет ✓ |
| `wiki/`, `tracks.yaml`, `levels.yaml`, `curriculum/README.md`, `tests/` | не изменялись ✓ |
| Существующие 136 тем и 30 модулей | побайтово ✓ |
| `pytest` | 11 passed ✓ |

## TODO(review)

- Трек `reading` теперь несёт и рабочее (документация, тикеты), и бытовое чтение, и понимание идиом. При росте B1+ стоит решить, не разделить ли comprehension от literal reading.
- `written-production.paraphrase-expression` — единственная production-тема, работающая с идиомами. Её dimension — производство **нейтрального перефраза**, не идиомы; при П.2 явно зафиксировать это в `mastery_criteria`, чтобы её не спутали с производством непрозрачной единицы.
- 141 непрозрачная единица уже была связана П.4c с бытовыми темами (домен), 14 — теперь с comprehension-темой (скилл). При П.2 решить, какая связь авторитетна для `topic.lexicon`: у идиомы законны обе, но у разных dimension.
- Slang recognition (`reading.stable-slang`) положен в `reading`, а не в `everyday-online-informal`: сленг не только онлайновый. Content-review должен подтвердить.
