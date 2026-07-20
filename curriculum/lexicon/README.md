# Stable core lexicon A1–A2 (П.4a + П.4a-bis)

Это курируемый авторский инвентарь `LexicalItem` под can-do темы A1–A2. Он является candidate data-каркасом: стабильные ID и изменения версионируются вместе со snapshot curriculum; активация и pinning выполняются реализацией Curriculum Contract.

## Раскладка и объём

| Файл | Назначение | Единиц |
|---|---|---:|
| `core-a1.yaml` | слова A1 | 50 |
| `core-a2.yaml` | слова A2 | 48 |
| `chunks-work-frames.yaml` | рабочие фразы-фреймы A1–A2, сгруппированы по модулям | 116 |
| `lexemes-irregular.yaml` | неправильные глаголы, один lexeme на глагол | 28 |
| `phrasal-verbs.yaml` | базовые phrasal verbs A1–A2 | 18 |
| `informal-core.yaml` | stable-core contractions, casual chunks и abbreviations | 30 |
| **Итого** |  | **290** |

`_suggested-topic-links.yaml` — advisory-предложения «единица → Topic» для П.2. Это не источник истины: авторитетное поле `topic.lexicon` остаётся владельцем Topic и в этом проходе не изменялось.

## Что такое chunk, а что нет

`chunk` — **рабочий фрейм**: готовая многословная заготовка, которую ученик вставляет в реальное сообщение и дополняет своим содержанием (`we've run into an issue`, `the main advantage is`, `I'll get it done by`).

Грамматический паттерн, у которого **уже есть собственный Topic** с can-do и критериями, chunk'ом не является и в лексиконе не дублируется. В П.4a-bis по этой причине удалены `there is`/`there are`, `have finished`, `better than`, `if ... then ...`, `must have` и `working on`: две записи для одного навыка создали бы два независимых scoring-таргета. Наречные обороты времени (`every day`, `after that`, `at the time`) переведены в `type: word`; `right now` и `by Friday` удалены как покрытые словами `currently` и `deadline`.

Соотношение типов подчинено продуктовой цели «довести построение фраз до автоматизма»: многословные единицы (chunk + phrasal-verb + informal_chunk + многословные words) составляют 55% инвентаря.

## Приоритетные bands

`curriculum_priority_band` — педагогический приоритет, не частота. Текущее распределение: `CORE` 85 (29%), `HIGH` 135 (47%), `USEFUL` 56 (19%), `SPECIALIZED` 10 (3%), `INCIDENTAL` 4 (1%). `CORE` зарезервирован за ядром, которое должно производиться автоматически; `SPECIALIZED` — за узкодоменными единицами (incident-management, QA, procurement); `INCIDENTAL` — за справочными.

## Авторство и provenance

- Все единицы, русские значения и примеры выписаны для этого проекта; у каждой записи `transformations: [authored]`.
- Единицы, переклассифицированные в П.4a-bis, дополнительно несут `reclassified-from-chunk` в `transformations`.
- Сторонние списки и excerpts не импортировались; `source_refs` и `SourceArtifact` поэтому отсутствуют.
- Корпусный проход **не выполнен**. Поля `frequency_score` и `frequency_band` намеренно отсутствуют: без pinned CEFR-J / NGSL / wordfreq artifact и воспроизводимого build-time расчёта их нельзя назначать экспертно «на глаз».
- Сырые датасеты в каталог не добавлялись.

## Informal stable core

Каждая запись `informal-core.yaml` имеет `usage_policy`, `neutral_equivalent`, `volatility: stable` и `currency: current`. Для `context_dependent` задан `allowed_contexts`; саркастический маркер `informal.yeah-right` имеет `recognition_only`. `meme_template` и living layer здесь отсутствуют.

## Покрытие curriculum

Инвентарь покрывает все **16** существующих модулей A1.1–A2.8: identity/role, routines, systems/data, current status, requests, past work, plans, A1 capstone, incidents, results, delivery, requirements, troubleshooting, collaboration, reading/mediation и A2 capstone. У каждого модуля не менее семи связанных рабочих фреймов. В репозитории 20 module-файлов всего; оставшиеся четыре — B1–C2 sketches и не входят в A1–A2 scope П.4.

## Осознанно отложено

- Build-time корпусный enrichment (`frequency_score`, собственные `frequency_band`, `SourceArtifact`, `source_refs`, notices) — **→ П.4b** после получения и pinning точных версий источников.
- Авторитетные `topic.lexicon` links — **→ П.2** после content review advisory-предложений.
- `LexicalMasteryProfile` и `mastery_criteria` — scoring policy 0.4; на `LexicalItem` не авторятся.
- Living layer, изменчивый сленг и meme templates — отдельный maintain-workflow с currency/provenance.
- LearnerLexicalState, evidence по формам lexeme и агрегирование mastery — runtime/scoring, не данные stable core.

## TODO(review)

- CEFR и `curriculum_priority_band` — авторская педагогическая классификация без корпусной аттестации; нужна человеческая content-проверка перед активацией.
- Словарь значений `transformations` контрактом не зафиксирован; токен `reclassified-from-chunk` введён в П.4a-bis как запись журнала изменений и должен быть подтверждён валидатором Curriculum Contract.
- Точная sense-гранулярность многозначных слов (`issue`, `field`, `run`, `set`) оставлена минимальной под текущие can-do; при П.2 нужно решить, достаточно ли одной единицы или нужны отдельные sense-ID.
- Формат `forms.past` для `lexeme.be` использует список `[was, were]`; контракт это разрешил ([[../../wiki/product/lexical-system]] §2), точная агрегация «знать слот» остаётся за OPEN-14.
- Часть фреймов содержит стяжения (`I'm`, `we're`, `I'll`, `it's`, `doesn't`). Они пересекаются с informal-единицами `informal.contraction-*`; при П.2 нужно решить, считается ли демонстрация фрейма evidence по стяжению.
- Единицы band `USEFUL` и ниже сознательно оставлены без advisory topic-links, кроме тех, что были предложены в П.4a.
