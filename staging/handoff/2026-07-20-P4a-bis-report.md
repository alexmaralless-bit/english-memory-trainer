# Отчёт П.4a-bis — добор рабочих фреймов и чистка лексикона

Дата: 2026-07-20 · Исполнитель: Claude · Вход: `staging/reviews/2026-07-20-P4a-lexicon-content-review.md`, решения [PD-2026-07-20]

## Итог

Лексикон вырос с **204 → 290** единиц. Chunks: **33 → 116**. Изменялся только `curriculum/lexicon/`.

## 1. Что удалено

Грамматические паттерны, у которых уже есть собственный Topic с can-do и критериями (дублирование создало бы два независимых scoring-таргета на один навык):

| Удалённая единица | Покрывающая тема |
|---|---|
| `chunk.there-is` | `grammar.there-is-are.systems` |
| `chunk.there-are` | `grammar.there-is-are.systems` |
| `chunk.have-finished` | `grammar.present-perfect.result` |
| `chunk.better-than` | `grammar.comparatives.options` |
| `chunk.if-then` | `grammar.first-conditional.troubleshooting` |
| `chunk.must-have` | `grammar.modals.requirements` |
| `chunk.working-on` | `phrasal-verb.work-on` (лексический дубль) |

Полный проход по всем 33 chunks выполнен; других грамматических паттернов не осталось.

Удалены как малополезные и покрытые словами:

- `chunk.right-now` → покрыт `word.currently`;
- `chunk.by-friday` → это слот-шаблон, а не единица; покрыт `word.deadline` и фреймами `I'll get it done by`, `by the end of the week`.

## 2. Что переклассифицировано

Наречные обороты времени переведены в `type: word` с пометкой `transformations: [authored, reclassified-from-chunk]`:

- `chunk.every-day` → `word.every-day` (HIGH)
- `chunk.after-that` → `word.after-that` (USEFUL)
- `chunk.at-the-time` → `word.at-the-time` (USEFUL)

ID изменились вместе с типом (префикс — часть ID). Единицы ещё не активированы и не пиннились, поэтому переименование безопасно; после активации потребовалась бы миграция.

## 3. Что добавлено — 95 новых рабочих фреймов

Все chunks вынесены в новый файл `chunks-work-frames.yaml`, сгруппированы комментариями по модулям. Прежние 21 подлинных фрейма сохранили свои ID.

**Все девять фраз, названных в одобренном концепте, присутствуют** — в том числе `chunk.we-have-completed` и `chunk.we-have-run-into-an-issue`, на которые ссылается канонический пример Topic в Curriculum Contract §2.

| Модуль | Всего | Новых | Новые фреймы |
|---|---:|---:|---|
| a1.1 identity-and-role | 7 | 4 | I work in the … team · I'm part of · I report to · My main task is |
| a1.2 daily-work | 7 | 7 | **I usually start by** · **How often do you …?** · On a typical day · first thing in the morning · at the end of the day · once a week · I spend most of my time |
| a1.3 systems-objects-and-data | 7 | 7 | This field contains · Each record has · it's stored in · You can find it under · The value should be · in the shared folder · by default |
| a1.4 work-in-progress | 8 | 6 | **I'm working on** · **we're testing** · it's still in review · we're waiting on · this is blocked by · I'm almost done with |
| a1.5 requests-and-clarification | 7 | 4 | just to confirm · Do you mean …? · I'm not sure I understand · Could you send me |
| a1.6 past-work | 7 | 6 | The first thing I did was · it stopped working after · it worked fine until · we fixed it by · it turned out that · we couldn't reproduce it |
| a1.7 plans-and-next-steps | 7 | 6 | we're planning to · I'll get it done by · by the end of the week · I'll let you know once · let's push it to · that's the plan for now |
| a1.8 integrated-work-scenario | 7 | 7 | Here's a short update · The open items are · handing this over to · Everything you need is in · please take it from here · no action needed · let me know if anything is unclear |
| a2.1 events-and-incidents | 7 | 7 | **we've run into an issue** · we ran into · The issue started at · it only happens when · steps to reproduce · users are affected · no data was lost |
| a2.2 results-and-experience | 7 | 6 | **we've completed** · **I've already checked** · we've deployed · it's been fixed · we haven't had any issues since · I have experience with |
| a2.3 planning-and-delivery | 7 | 6 | The delivery date is · we're aiming for · that's out of scope · we may need more time · ahead of schedule · behind schedule |
| a2.4 requirements-and-options | 7 | 7 | **the main advantage is** · **we should consider** · the downside is · it depends on · The main requirement is · in terms of · either way |
| a2.5 processes-and-troubleshooting | 7 | 7 | The root cause was · The usual process is to · make sure that · try this first · if that doesn't help · as a workaround · the same thing happened before |
| a2.6 collaboration | 9 | 4 | Could you take a look at · Thanks for the update · Sorry for the delay · Does that work for you? |
| a2.7 reading-and-mediation | 8 | 6 | The key point is · in short · To summarize · as far as I understand · it says that · in other words |
| a2.8 integrated-project-update | 7 | 5 | Overall, the project is · The main risk is · Next week we'll focus on · actual result · no blockers at the moment |

**Полужирным** — фразы, прямо названные в концепте.

## 4. Новое распределение по типам

| Тип | Было | Стало |
|---|---:|---:|
| `chunk` | 33 | **116** |
| `word` | 95 | 98 |
| `lexeme` | 28 | 28 |
| `informal_chunk` | 23 | 23 |
| `phrasal-verb` | 18 | 18 |
| `abbreviation` | 7 | 7 |
| **Итого** | **204** | **290** |

Многословные единицы (chunk + phrasal-verb + informal_chunk + многословные `word`): **160 = 55.2%** (было ~34%). С учётом abbreviations, разворачивающихся во фразы, — 57.6%. Соотношение перевёрнуто в пользу фразовых заготовок, как требует цель «автоматизм построения фраз».

## 5. Новое распределение по bands

| Band | Было | Стало | Доля |
|---|---:|---:|---:|
| `CORE` | 121 (59%) | **85** | 29.3% |
| `HIGH` | 76 | 135 | 46.6% |
| `USEFUL` | 7 | 56 | 19.3% |
| `SPECIALIZED` | 0 | 10 | 3.4% |
| `INCIDENTAL` | 0 | 4 | 1.4% |

`CORE` уложен в целевой коридор ≲30–35%. `SPECIALIZED` отдан узкодоменным единицам (`timeline`, `milestone`, `observed`, `paraphrase`, `handoff`, `steps to reproduce`, `users are affected`, `roll back`, два маркера деэскалации). `INCIDENTAL` — справочным (`buy`, `feel`, `IMHO`, `Yeah, right`).

## 6. Advisory topic-links

`_suggested-topic-links.yaml`: **60 → 254** строки, 339 пар «единица → тема», сгруппированы по модулям.

- Покрыты **все 116 chunks** и **все 220 единиц band CORE/HIGH** любого типа.
- Единицы `USEFUL` и ниже сознательно оставлены без связей, кроме предложенных ещё в П.4a.
- Файл остаётся `authority: advisory-only`; `topic.lexicon` не заполнялся.

## 7. Самопроверка

| Критерий | Результат |
|---|---|
| `chunk` в диапазоне 90–120 | 116 ✓ |
| Multi-word ≥ 55% | 55.2% ✓ |
| Грамматических паттернов в `type: chunk` | нет ✓ |
| Все девять фраз из концепта | присутствуют ✓ |
| ≥5 chunks на каждый из 16 модулей A1–A2 | минимум 7 ✓ |
| Дубликаты ID | нет ✓ |
| Обязательные поля (band/register/meaning_ru/пример/transformations) | у всех 290 ✓ |
| `frequency_*` / `source_refs` | отсутствуют ✓ |
| Висячие ссылки в advisory-links | нет ✓ |
| `curriculum/topics`, `curriculum/modules`, `wiki/`, `docs/`, `Irregular Verbs.md` | не изменялись ✓ |
| YAML парсится | все файлы ✓ |

## 8. Границы: что не делалось

- **Корпусный проход не выполнялся** (П.4b). `frequency_score`, `frequency_band`, `source_refs`, `SourceArtifact` отсутствуют; значения не выдумывались.
- Примеры авторские; сторонние excerpts не использовались.
- `mastery_criteria` / `LexicalMasteryProfile` не создавались; `topic.lexicon` не заполнялся (П.2).
- `meme_template` и living layer не создавались.

## 9. TODO(review)

1. **Словарь `transformations` не зафиксирован контрактом.** Токен `reclassified-from-chunk` введён здесь как запись журнала изменений; валидатор Curriculum Contract должен его признать либо предложить другой механизм.
2. **Стяжения внутри фреймов.** Многие новые фреймы содержат `I'm`, `we're`, `I'll`, `it's`, `doesn't`, которые одновременно существуют как `informal.contraction-*`. П.2 должен решить, засчитывается ли демонстрация фрейма как evidence по стяжению, иначе снова возникнет двойной учёт — того же класса, что и удалённые псевдо-chunks.
3. **CEFR и bands** остаются авторской педагогической классификацией без корпусной аттестации; человеческая content-проверка нужна до активации.
4. **Sense-гранулярность** многозначных (`issue`, `field`, `run`, `set`) оставлена минимальной.
5. **Переименование ID** трёх переклассифицированных единиц безопасно только потому, что лексикон ещё не активирован и не пиннился. Механизм переименования после активации контрактом не описан.
