# Stable core lexicon A1–A2 (П.4a–П.4c)

Это курируемый авторский инвентарь `LexicalItem` под can-do темы A1–A2. Он является candidate data-каркасом: стабильные ID и изменения версионируются вместе со snapshot curriculum; активация и pinning выполняются реализацией Curriculum Contract.

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
| **Итого** |  | **838** |

`_suggested-topic-links.yaml` — advisory-предложения «единица → Topic» для П.2. Это не источник истины: авторитетное поле `topic.lexicon` остаётся владельцем Topic и в этом проходе не изменялось.

## Что такое chunk, а что нет

`chunk` — **рабочий фрейм**: готовая многословная заготовка, которую ученик вставляет в реальное сообщение и дополняет своим содержанием (`we've run into an issue`, `the main advantage is`, `I'll get it done by`).

Грамматический паттерн, у которого **уже есть собственный Topic** с can-do и критериями, chunk'ом не является и в лексиконе не дублируется. В П.4a-bis по этой причине удалены `there is`/`there are`, `have finished`, `better than`, `if ... then ...`, `must have` и `working on`: две записи для одного навыка создали бы два независимых scoring-таргета. Наречные обороты времени (`every day`, `after that`, `at the time`) переведены в `type: word`; `right now` и `by Friday` удалены как покрытые словами `currently` и `deadline`.

После П.4c инвентарь содержит 120 `idiom` и 100 `phrasal-verb`. `idiom` — законченное фиксированное выражение без продуктивного слота; оно не переклассифицируется в `chunk`.

Каждая единица типов `chunk`, `phrasal-verb`, `idiom`, `informal_chunk` имеет `transparency`. Для каждой `opaque` единицы задан `literal_trap_ru`; это описание ошибочного дословного прочтения, которое проверяется в упражнениях на recognition.

## Приоритетные bands

`curriculum_priority_band` — педагогический приоритет, не частота. После П.4c распределение: `CORE` 210 (25.1%), `HIGH` 316 (37.7%), `USEFUL` 195 (23.3%), `SPECIALIZED` 69 (8.2%), `INCIDENTAL` 48 (5.7%). `CORE` удержан в контрактном коридоре 25–32% всего инвентаря; `SPECIALIZED` и `INCIDENTAL` используются для recognition-ориентированных и периферийных единиц.

Корпусный проход П.4b перепроверил эту разметку: ни одна единица `CORE`/`HIGH` не оказалась редкой, но пять лексем были занижены и подняты по частоте (`tell`, `leave`, `bring` → HIGH; `feel`, `buy` → USEFUL). Инвариант: единица с корпусным band `very_high`/`high` не может быть `INCIDENTAL`.

## Авторство и provenance

- Все единицы, русские значения и примеры выписаны для этого проекта; у каждой записи `transformations: [authored]`.
- Единицы, переклассифицированные в П.4a-bis, дополнительно несут `reclassified-from-chunk` в `transformations`.
- Сторонние excerpts не импортировались; чужие таблицы не воспроизводятся.
- Сырые датасеты в каталог не добавляются (build-time режим).

## Корпусные частоты (П.4b)

`frequency_score` (Zipf) и `frequency_band` выведены build-time из pinned-артефактов. Манифест — `_provenance.yaml` (id, точная версия, url, retrieved_at, sha256, лицензия, notices + versioned thresholds). Расчёт воспроизводится:

```bash
python tools/enrich_lexicon.py --cache <каталог вне репо> --check
```

Скрипт сверяет sha256 каждого артефакта и отказывается работать при расхождении; `--check` заново выводит каждое значение и падает при дрейфе.

**Покрыто 129 из 838 единиц (15%).** П.4c не добавлял частотные поля: новый корпусный проход выполняется отдельно. Частоту получают только однословные `word`/`lexeme`/`abbreviation`, если их действительно покрывает pinned-источник. Все 437 единиц типов `chunk`, `phrasal-verb`, `idiom`, `informal_chunk` частоты **не имеют и не получат**: корпус слов не содержит наблюдаемых частот фраз, а композитная оценка по токенам не является частотой. Отсутствие поля — честный сигнал, а не пробел; потребители обязаны определить fallback ([[../../wiki/product/lexical-system]] §1, OPEN-22).

Распределение по `frequency_band` среди покрытых: `very_high` 38, `high` 60, `mid` 26, `low` 4, `rare` 1. Членство в NGSL — 110 единиц, в BSL — 7.

## Informal stable core

Каждая informal-единица имеет `usage_policy`, `volatility: stable` и `currency: current`; для `context_dependent` задан `allowed_contexts`. В инвентаре 50 единиц с `register: slang`, все они устойчивые и снабжены нейтральным эквивалентом. `meme_template` и living layer здесь отсутствуют.

## Покрытие curriculum

Инвентарь покрывает все **26** модулей A1.1–A2.13: 16 рабочих модулей и 10 бытовых модулей. В каждом бытовом модуле добавлено по 25 базовых слов; CORE/HIGH единицы и тематически применимые идиомы связаны с `everyday-life.*` через advisory-файл. Непрозрачные выражения без подходящего can-do Topic перечислены в handoff П.4c и оставлены П.1c-bis.

## Осознанно отложено

- CEFR-разметка остаётся авторской: CEFR-J и Octanove в П.4b не импортировались. Кросс-проверка авторских CEFR против CEFR-J — отдельная работа.
- Авторитетные `topic.lexicon` links — **→ П.2** после content review advisory-предложений.
- `LexicalMasteryProfile` и `mastery_criteria` — scoring policy 0.4; на `LexicalItem` не авторятся.
- Living layer, изменчивый сленг и meme templates — отдельный maintain-workflow с currency/provenance.
- LearnerLexicalState, evidence по формам lexeme и агрегирование mastery — runtime/scoring, не данные stable core.

## TODO(review)

- CEFR — авторская классификация без корпусной аттестации; нужна человеческая content-проверка перед активацией. `curriculum_priority_band` частично перепроверен корпусом (см. выше), но остаётся педагогическим суждением.
- Точная sense-гранулярность многозначных слов (`issue`, `field`, `run`, `set`) оставлена минимальной под текущие can-do; при П.2 нужно решить, достаточно ли одной единицы или нужны отдельные sense-ID.
- Формат `forms.past` для `lexeme.be` использует список `[was, were]`; контракт это разрешил ([[../../wiki/product/lexical-system]] §2), точная агрегация «знать слот» остаётся за OPEN-14.
- Часть фреймов содержит стяжения (`I'm`, `we're`, `I'll`, `it's`, `doesn't`). Они пересекаются с informal-единицами `informal.contraction-*`; при П.2 нужно решить, считается ли демонстрация фрейма evidence по стяжению.
- `# TODO(review)`: content-review должен проверить границу `casual`/`slang`, авторский CEFR и 14 непрозрачных идиом без подходящего бытового Topic; продуктовые развилки в П.4c не решались.
