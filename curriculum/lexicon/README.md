# Stable curriculum lexicon A1–C2 (П.4a–П.4e)

Это курируемый авторский инвентарь `LexicalItem` под can-do темы A1–C2, включая text-only TOEFL Reading/Writing. Он является candidate data-каркасом: стабильные ID и изменения версионируются вместе со snapshot curriculum; активация и pinning выполняются реализацией Curriculum Contract.

## Раскладка и объём

| Файл | Назначение | Единиц |
|---|---|---:|
| `core-a1.yaml` | слова A1 | 50 |
| `core-a2.yaml` | слова A2 | 48 |
| `everyday-words.yaml` | бытовые слова и базовые именные сочетания A1–A2 | 250 |
| `chunks-work-frames.yaml` | рабочие фразы-фреймы A1–A2, сгруппированы по модулям | 116 |
| `lexemes-irregular.yaml` | неправильные глаголы, один lexeme на глагол | 28 |
| `phrasal-verbs.yaml` | базовые phrasal verbs A1–A2 | 18 |
| `phrasal-verbs-everyday.yaml` | разговорные и бытовые phrasal verbs | 82 |
| `idioms-everyday-1.yaml`, `idioms-everyday-2.yaml` | фиксированные идиомы | 120 |
| `informal-core.yaml` | stable-core contractions, casual chunks и abbreviations | 30 |
| `everyday-reactions.yaml` | бытовые разговорные реакции | 61 |
| `slang-stable.yaml` | устойчивый сленг и коллоквиализмы | 35 |
| `word-formation.yaml` | производные слова для трека словообразования | 48 |
| `academic-b1.yaml` | академическое ядро B1 по NAWL | 60 |
| `academic-b2.yaml` | академическое ядро B2 по NAWL | 61 |
| `academic-c1-c2.yaml` | академическое ядро C1–C2 по NAWL | 60 |
| `toefl-reading-writing.yaml` | TOEFL-слова и прозрачные академические фреймы | 45 |
| **Итого** |  | **1112** |

`_suggested-topic-links.yaml` — advisory-предложения «единица → Topic». Это не источник истины: авторитетное поле `topic.lexicon` остаётся владельцем Topic. В П.4e все 226 новых единиц получили advisory-привязку; 144 репрезентативные единицы дополнительно внесены в `topic.lexicon` B1–C2.

## Что такое chunk, а что нет

`chunk` — **рабочий фрейм**: готовая многословная заготовка, которую ученик вставляет в реальное сообщение и дополняет своим содержанием (`we've run into an issue`, `the main advantage is`, `I'll get it done by`).

Грамматический паттерн, у которого **уже есть собственный Topic** с can-do и критериями, chunk'ом не является и в лексиконе не дублируется. В П.4a-bis по этой причине удалены `there is`/`there are`, `have finished`, `better than`, `if ... then ...`, `must have` и `working on`: две записи для одного навыка создали бы два независимых scoring-таргета. Наречные обороты времени (`every day`, `after that`, `at the time`) переведены в `type: word`; `right now` и `by Friday` удалены как покрытые словами `currently` и `deadline`.

После П.4c инвентарь содержит 120 `idiom` и 100 `phrasal-verb`. `idiom` — законченное фиксированное выражение без продуктивного слота; оно не переклассифицируется в `chunk`.

Каждая единица типов `chunk`, `phrasal-verb`, `idiom`, `informal_chunk` имеет `transparency`. Для каждой `opaque` единицы задан `literal_trap_ru`; это описание ошибочного дословного прочтения, которое проверяется в упражнениях на recognition.

## Приоритетные bands

`curriculum_priority_band` — педагогический приоритет, не частота. После П.4e распределение: `CORE` 311 (28.0%), `HIGH` 437 (39.3%), `USEFUL` 250 (22.5%), `SPECIALIZED` 69 (6.2%), `INCIDENTAL` 45 (4.0%). `CORE` удержан в контрактном коридоре 25–32% всего инвентаря; `SPECIALIZED` и `INCIDENTAL` используются для recognition-ориентированных и периферийных единиц.

Корпусный проход П.4b перепроверил эту разметку: ни одна единица `CORE`/`HIGH` не оказалась редкой, но пять лексем были занижены и подняты по частоте (`tell`, `leave`, `bring` → HIGH; `feel`, `buy` → USEFUL). Инвариант: единица с корпусным band `very_high`/`high` не может быть `INCIDENTAL`.

## Авторство и provenance

- Все единицы, русские значения и примеры выписаны для этого проекта; у каждой записи `transformations: [authored]`.
- Единицы, переклассифицированные в П.4a-bis, дополнительно несут `reclassified-from-chunk` в `transformations`.
- Сторонние excerpts не импортировались; чужие таблицы не воспроизводятся.
- Сырые датасеты в каталог не добавляются (build-time режим).

## Корпусные частоты (П.4b, П.4e)

`frequency_score` (Zipf) и `frequency_band` выведены build-time из pinned-артефактов. Манифест — `_provenance.yaml` (id, точная версия, url, retrieved_at, sha256, лицензия, notices + versioned thresholds). Расчёт воспроизводится:

```bash
python tools/enrich_lexicon.py --cache <каталог вне репо> --check
```

Скрипт сверяет sha256 каждого артефакта и отказывается работать при расхождении; `--check` заново выводит каждое значение и падает при дрейфе.

**Покрыто 649 из 1112 единиц (58.4%).** Частоту получают только однословные `word`/`lexeme`/`abbreviation`, если их действительно покрывает pinned-источник. Все 457 единиц типов `chunk`, `phrasal-verb`, `idiom`, `informal_chunk` частоты **не имеют и не получат**: корпус слов не содержит наблюдаемых частот фраз, а композитная оценка по токенам не является частотой. Ещё пять многословных `word` и `abbreviation.tl-dr` не получают выдуманную токенную оценку. Отсутствие поля — честный сигнал, а не пробел; потребители обязаны определить fallback ([[../../wiki/product/lexical-system]] §1, OPEN-22).

Распределение по `frequency_band` среди покрытых: `very_high` 47, `high` 209, `mid` 298, `low` 87, `rare` 8. Членство в NGSL — 304 единицы, в BSL — 171, в NAWL — 195. Списки задают только lemma-family membership и provenance; числовой `frequency_score` по-прежнему приходит исключительно из pinned `wordfreq@3.1.1`.

П.4e не импортирует NAWL целиком. Из закреплённого файла отобрано академическое ядро, которое естественно тренируется в принятых B1–C2/TOEFL-темах; узкопредметные слова остаются материалом для contextual inference. Русские значения и примеры написаны для проекта, таблица источника не воспроизводится.

## Informal stable core

Каждая informal-единица имеет `usage_policy`, `volatility: stable` и `currency: current`; для `context_dependent` задан `allowed_contexts`. В инвентаре 50 единиц с `register: slang`, все они устойчивые и снабжены нейтральным эквивалентом. `meme_template` и living layer здесь отсутствуют.

## Покрытие curriculum

Инвентарь покрывает все **26** модулей A1.1–A2.13: 16 рабочих модулей и 10 бытовых модулей. В каждом бытовом модуле добавлено по 25 базовых слов; CORE/HIGH единицы и тематически применимые идиомы связаны с `everyday-life.*` через advisory-файл. П.4e добавляет покрытие 122 тем B1–C2: в них 510 авторитетных ссылок на 225 разных единиц, а число пустых `lexicon`-списков снизилось с шести до трёх.

## Осознанно отложено

- CEFR-разметка остаётся авторской: CEFR-J и Octanove в П.4b не импортировались. Кросс-проверка авторских CEFR против CEFR-J — отдельная работа.
- Для 82 новых П.4e-единиц пока есть только advisory-привязки; перенос в дополнительные `topic.lexicon` должен следовать из реального lesson-bank usage, а не из требования распределить каждое слово заранее.
- `LexicalMasteryProfile` и `mastery_criteria` — scoring policy 0.4; на `LexicalItem` не авторятся.
- Living layer, изменчивый сленг и meme templates — отдельный maintain-workflow с currency/provenance.
- LearnerLexicalState, evidence по формам lexeme и агрегирование mastery — runtime/scoring, не данные stable core.

## TODO(review)

- CEFR — авторская классификация без корпусной аттестации; нужна человеческая content-проверка перед активацией. `curriculum_priority_band` частично перепроверен корпусом (см. выше), но остаётся педагогическим суждением.
- Точная sense-гранулярность многозначных слов (`issue`, `field`, `run`, `set`) оставлена минимальной под текущие can-do; при П.2 нужно решить, достаточно ли одной единицы или нужны отдельные sense-ID.
- Формат `forms.past` для `lexeme.be` использует список `[was, were]`; контракт это разрешил ([[../../wiki/product/lexical-system]] §2), точная агрегация «знать слот» остаётся за OPEN-14.
- Часть фреймов содержит стяжения (`I'm`, `we're`, `I'll`, `it's`, `doesn't`). Они пересекаются с informal-единицами `informal.contraction-*`; при П.2 нужно решить, считается ли демонстрация фрейма evidence по стяжению.
- `# TODO(review)`: content-review должен проверить границу `casual`/`slang`, авторский CEFR и 14 непрозрачных идиом без подходящего бытового Topic; продуктовые развилки в П.4c не решались.
