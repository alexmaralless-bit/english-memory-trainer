# Промпт-делегация: П.4c — лексикон быта и непрозрачных выражений

Скопировать целиком в Codex, запущенный в корне репозитория AI_trainer_eng.

---

Ты — автор учебного лексикона. Задача — самый большой контентный проход проекта: добрать **бытовую лексику и выражения, которые нельзя перевести дословно**. Лексикон вырастет с 290 до ~800 единиц.

## Зачем именно это

Ученик — IT-специалист, которому английский нужен не только для работы. Его формулировка цели: *«бытовые устойчивые выражения очень важны… я не должен тупить, переводя дословно»*.

Замер после П.4b показал, почему этого сейчас нет: `register: casual` — 24 единицы из 290, бытовой лексики **ноль**, сленга **ноль**, а из 18 phrasal verbs все рабочие и почти все прозрачные (`log in`, `fill in`, `set up`). Ни `put up with`, ни `figure out`, ни `come up with`.

## Контекст (прочитать до начала)

1. **`wiki/product/lexical-system.md` §1a** — ось прозрачности. ГЛАВНЫЙ ВХОД: что такое `opaque`, зачем `literal_trap_ru`, почему `idiom` отдельный тип.
2. `curriculum/lexicon/README.md` + `*.yaml` — текущие 290 единиц и формат.
3. `curriculum/lexicon/_provenance.yaml` — почему у многословных единиц нет частот.
4. `curriculum/topics/a1.yaml`, `a2.yaml` — 136 тем; новые бытовые лежат в модулях `a1.9`–`a1.13` и `a2.9`–`a2.13`.
5. `wiki/modules/curriculum.md` §3.2 — закрытый словарь `transformations`, правила валидации.

## Задача 1 — phrasal verbs: 18 → ~100

Добрать разговорные и непрозрачные: `put up with`, `come up with`, `figure out`, `run out of`, `look forward to`, `get over`, `pull off`, `hang out`, `catch up`, `mess up`, `screw up`, `freak out`, `chill out`, `show up`, `turn out`, `give up`, `bring up`, `work out`, `end up`, `take off`, `get along`, `look after`, `put off`, `call off`, `break down`, `run late`.

## Задача 2 — идиомы: 0 → ~120, **новый тип `idiom`**

Фиксированные неразложимые выражения: `call it a day`, `no big deal`, `off the top of my head`, `keep an eye on`, `cut corners`, `piece of cake`, `hit the road`, `get the hang of`, `touch base`, `on the same page`, `under the weather`, `a heads-up`, `for the time being`, `on the fly`, `make ends meet`, `bite the bullet`, `once in a blue moon`.

**`idiom` — не `chunk`.** Chunk это заготовка со слотом, которую ученик достраивает (`the main advantage is …`); идиома — целое, которое не достраивают.

## Задача 3 — бытовые разговорные реакции: 0 → ~70

`how's it going`, `what's up`, `never mind`, `no way`, `you kidding`, `I'm good`, `same here`, `not really`, `sounds like a plan`, `my pleasure`, `no rush`, `take care`, `catch you later`, `that works`, `up to you`, `I'd rather`, `kind of`, `I guess so`.

## Задача 4 — устойчивый сленг: 0 → ~50

Только **устойчивое**, не хайповое: `gonna`, `wanna`, `gotta`, `kinda`, `sorta`, `stuff`, `guys`, `cool`, `weird`, `awesome`, `broke` (без денег), `ripped off`, `hang out`, `chill`, `a bunch of`, `pretty` (в значении «довольно»).

`meme_template` **не создавать** — самая скоропортящаяся категория, в MVP не строится.

## Задача 5 — бытовые слова: ~0 → ~250

По десяти бытовым модулям: люди и близкие · дом и распорядок · еда и заведения · перемещения и покупки · small talk · здоровье · деньги и сервисы · поездки и жильё · досуг и медиа · бытовые проблемы.

## Задача 6 — КРИТИЧНО: разметить `transparency` по ВСЕМУ лексикону

Не только новые единицы. **Все** многословные (`chunk`, `phrasal-verb`, `idiom`, `informal_chunk`) получают поле:

- `transparent` — смысл выводится из слов (`we've completed`, `the delivery date is`);
- `semi_opaque` — выводится с усилием (`find out`, `back up`, `run into`);
- `opaque` — не выводится (`put up with`, `call it a day`).

**У каждой `opaque` обязателен `literal_trap_ru`** — запись о том, какой **неверный** дословный смысл она провоцирует. Это учебная цель, а не украшение.

```yaml
- {id: idiom.call-it-a-day, type: idiom, title: "call it a day", cefr: A2,
   curriculum_priority_band: HIGH, register: casual, transparency: opaque,
   domains: [everyday-life, work], meaning_ru: "закончить на сегодня, свернуть работу",
   literal_trap_ru: "не «назвать это днём»",
   examples: ["It's almost eight, let's call it a day."], transformations: [authored]}
```

У однословных `transparency` не обязателен (по умолчанию `transparent`).

## Задача 7 — advisory topic-links

Связать новые единицы с бытовыми темами (`everyday-life.*` в модулях `a1.9`–`a2.13`). Покрыть **все** новые единицы band `CORE`/`HIGH` и все новые `chunk`/`idiom`.

Файл `_suggested-topic-links.yaml` остаётся advisory, `topic.lexicon` не заполнять.

Часть непрозрачных единиц не найдёт подходящей темы: тем «понимание не-дословных выражений» ещё нет, они появятся в П.1c-bis. Такие оставить без связи и перечислить в отчёте — их подхватит следующий проход.

## Задача 8 — перекалибровать bands

Сейчас `CORE` 85 из 290 (29%). После добора до ~800 удержать `CORE` в коридоре **25–32%** по всему инвентарю, а не только по новым единицам. Задействовать `SPECIALIZED` и `INCIDENTAL`.

## Границы

1. **Частотные поля НЕ проставлять вообще.** Ни `frequency_score`, ни `frequency_band`, ни `source_refs`. Корпусный проход выполняется отдельно инструментом `tools/enrich_lexicon.py` по pinned-артефактам — руками эти значения не пишутся никогда.
2. **Многословным единицам частоты не положены** даже после прогона инструмента: корпус слов не измеряет фразы ([[_provenance]] `coverage_policy`).
3. `transformations` — **закрытый словарь**: `identity`, `authored`, `corpus-enriched`, `lemma-form-sum`, `reclassified-from-chunk`. Новых токенов не вводить.
4. Примеры — **собственные**; сторонние excerpts запрещены.
5. Informal-единицы: у всех `usage_policy`; у `context_dependent` — `allowed_contexts`. Поля `volatility` и `currency` заполнять (механизм living layer не строится, но поля остаются).
6. **НЕ трогать**: `curriculum/topics/*`, `curriculum/modules/*`, `wiki/`, `docs/`, `tools/`, `tests/`, `pyproject.toml`, корневой `Irregular Verbs.md`. Менять только `curriculum/lexicon/`.
7. `mastery_criteria` и `LexicalMasteryProfile` не создавать.
8. Развилки не решать — `# TODO(review)`.

## Самопроверка

- Всего ~800 единиц; `idiom` ≈ 120, `phrasal-verb` ≈ 100.
- **У каждой многословной единицы есть `transparency`**; у каждой `opaque` есть `literal_trap_ru`.
- `CORE` в коридоре 25–32% по всему инвентарю.
- ID уникальны, dotted, стабильные; старые ID не переименованы.
- Ни одного `frequency_*` и `source_refs` у новых единиц.
- `transformations` только из закрытого словаря.
- YAML парсится; `curriculum/topics` и `curriculum/modules` не изменены.
- `pytest` проходит **или** падает только на проверке покрытия модулей chunks (её константу обновит ревьювер).

## Отчёт

`staging/handoff/2026-07-21-P4c-report.md`: сколько добавлено по типам и по модулям · распределение `transparency` (сколько transparent / semi_opaque / opaque) · распределение bands до и после · список непрозрачных единиц, оставшихся без темы (для П.1c-bis) · `TODO(review)`.
