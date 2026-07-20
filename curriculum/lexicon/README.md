# Stable core lexicon A1–A2 (П.4a)

Это курируемый авторский инвентарь `LexicalItem` под can-do темы A1–A2. Он является candidate data-каркасом: стабильные ID и изменения версионируются вместе со snapshot curriculum; активация и pinning выполняются реализацией Curriculum Contract.

## Раскладка и объём

| Файл | Назначение | Единиц |
|---|---|---:|
| `core-a1.yaml` | базовые слова и chunks A1 | 64 |
| `core-a2.yaml` | базовые слова и chunks A2 | 64 |
| `lexemes-irregular.yaml` | неправильные глаголы, один lexeme на глагол | 28 |
| `phrasal-verbs.yaml` | базовые phrasal verbs A1–A2 | 18 |
| `informal-core.yaml` | stable-core contractions, casual chunks и abbreviations | 30 |
| **Итого** |  | **204** |

`_suggested-topic-links.yaml` — advisory-предложения «единица → Topic» для П.2. Это не источник истины: авторитетное поле `topic.lexicon` остаётся владельцем Topic и в этом проходе не изменялось.

## Авторство и provenance

- Все единицы, русские значения и примеры выписаны для этого проекта; у каждой записи `transformations: [authored]`.
- Сторонние списки и excerpts не импортировались; `source_refs` и `SourceArtifact` поэтому отсутствуют.
- Корпусный проход **не выполнен**. Поля `frequency_score` и `frequency_band` намеренно отсутствуют: без pinned CEFR-J / NGSL / wordfreq artifact и воспроизводимого build-time расчёта их нельзя назначать экспертно «на глаз».
- Сырые датасеты в каталог не добавлялись.

## Informal stable core

Каждая запись `informal-core.yaml` имеет `usage_policy`, `neutral_equivalent`, `volatility: stable` и `currency: current`. Для `context_dependent` задан `allowed_contexts`; саркастический маркер `informal.yeah-right` имеет `recognition_only`. `meme_template` и living layer здесь отсутствуют.

## Покрытие curriculum

Инвентарь покрывает все **16** существующих модулей A1.1–A2.8: identity/role, routines, systems/data, current status, requests, past work, plans, A1 capstone, incidents, results, delivery, requirements, troubleshooting, collaboration, reading/mediation и A2 capstone. В репозитории 20 module-файлов всего; оставшиеся четыре — B1–C2 sketches и не входят в A1–A2 scope П.4a.

## Осознанно отложено

- Build-time корпусный enrichment (`frequency_score`, собственные `frequency_band`, `SourceArtifact`, `source_refs`, notices) — **→ П.4b** после получения и pinning точных версий источников.
- Авторитетные `topic.lexicon` links — **→ П.2** после content review advisory-предложений.
- `LexicalMasteryProfile` и `mastery_criteria` — scoring policy 0.4; на `LexicalItem` не авторятся.
- Living layer, изменчивый сленг и meme templates — отдельный maintain-workflow с currency/provenance.
- LearnerLexicalState, evidence по формам lexeme и агрегирование mastery — runtime/scoring, не данные stable core.

## TODO(review)

- CEFR и `curriculum_priority_band` в П.4a — авторская педагогическая классификация без корпусной аттестации; нужна человеческая content-проверка перед активацией.
- Точная sense-гранулярность многозначных слов (`issue`, `field`, `run`, `set`) оставлена минимальной под текущие can-do; при П.2 нужно решить, достаточно ли одной единицы или нужны отдельные sense-ID.
- Формат `forms.past` для `lexeme.be` использует список `[was, were]`; schema агрегации форм должна подтвердить поддержку нескольких обязательных вариантов.
- В формулировке задачи упомянуты «20 модулей A1–A2», но текущий curriculum содержит 16 модулей A1–A2 и четыре B1–C2 sketches. Покрытие проверено для 16 модулей в заявленном уровне scope.
