# Лексическая система

> **Status**: current
> **Last updated**: 2026-09-22
> **Sources**: дизайн пользователя 2026-07-19 (Concept Gate, зафиксирован в journal) · концепт Codex по informal-треку (`staging/journal/2026-07-19-codex-curriculum-concept.md`) · [[learning-model]] §3–§4, §7 · все решения [PD-2026-07-19]
> **Роль**: продуктовый контракт словарной системы (roadmap 0.9). Определяет три слоя лексики и их связь со scoring. Формат данных и frequency source — Curriculum Contract (0.3); проекция — Obsidian Vault Contract (0.6); отбор лексикона A1–A2 — работа П.4.

---

## 0. Принцип: сложность индивидуальна

Словарная система — не «список сложных слов». Обычное слово может постоянно вызывать ошибки, а редкое техническое — запомниться сразу. Программа задаёт, **чему учить** (слой 1–2); личная сложность **выводится из evidence** (слой 3), а не назначается заранее.

## 1. Слой 1 — учебный лексикон программы

- **MUST**: curriculum заранее содержит отобранные лексические единицы: слова, устойчивые выражения и chunks, phrasal verbs, идиомы, неправильные глаголы, бытовую и рабочую лексику AI/AEC/SaaS.

### 1a. Ось прозрачности [PD-2026-07-20]

Регистр отвечает на вопрос «уместно ли это здесь», домен — «о чём это», а **прозрачность** — «можно ли понять это по словам». Это независимая ось, и до П.4c её в модели не было: все авторские chunks оказались прозрачными продуктивными заготовками, тогда как в реальной речи ученика подстерегают выражения, дословный перевод которых даёт неверный смысл.

- **MUST — поле `transparency`**: `transparent | semi_opaque | opaque` у каждой многословной единицы (`chunk`, `phrasal-verb`, `idiom`, `informal_chunk`); у однословных допустимо и по умолчанию `transparent`.
  - `transparent` — смысл выводится из слов (`we've completed`, `the delivery date is`);
  - `semi_opaque` — выводится с усилием или частично (`find out`, `back up`, `run into`);
  - `opaque` — не выводится (`put up with`, `off the top of my head`, `call it a day`, `cut corners`).
- **MUST — прозрачность задаёт порядок dimensions**: у `opaque` единицы `recognition` — **обязательный** dimension, а `controlled_production` не может быть required (производить идиому необязательно, понимать — обязательно); у `semi_opaque` required — `recognition`, затем `controlled_production`; у `transparent` производство может требоваться сразу. Разрешение профиля — по `(type, transparency, usage_policy)`.
- **MUST NOT — не смешивать с `usage_policy`**: `usage_policy` отвечает за безопасность и уместность (не прозвучит ли грубо), `transparency` — за декодируемость. `piece of cake` абсолютно безопасно и при этом непрозрачно; `yeah, right` прозрачно по словам и при этом рискованно из-за сарказма. Это разные вопросы, и склейка их повторила бы ошибку, уже исправленную для частоты и приоритета.
- **MUST — тип `idiom`**: фиксированное неразложимое выражение — отдельный `type`, а не `chunk`. `chunk` — это **заготовка со слотом**, которую ученик достраивает своим содержанием; идиома — целое, которое не достраивают. Разные структуры и разные учебные цели.
- **MUST — `literal_trap_ru` у `opaque`**: непрозрачная единица несёт явную запись о том, какой **неверный** дословный смысл она провоцирует (`call it a day` → «не „назвать это днём“»). Это не украшение: именно эта ловушка — учебная цель, и упражнение на узнавание строится как выбор между дословным и настоящим смыслом. Проверяется валидатором.

### 1b. Словообразование — поле `formation` [PD-2026-07-21]

Продуктивные приставки и суффиксы — **порождающий паттерн**: одно правило (`out-` = «превзойти в чём-то») открывает семью слов (`outrun`, `outnumber`, `outperform`). Учить их изолированными единицами — терять рычаг. Паттерны живут в треке `word-formation` (морфология — отдельная ось, не синтаксис и не lexicon-layer).

- **MUST — поле `formation`** [PD-2026-07-21, §5.2-B]: аффиксная единица несёт `formation: {affix, base, affix_type: prefix | suffix}` (`outrun` → `{affix: out-, base: run, affix_type: prefix}`). Поле связывает слово с его паттерном и позволяет движку предъявить порождающее звено: «знаешь `out-` и `run` → вот `outrun`». Однословные без аффиксного строения поля не несут; multi-word единицы — тоже.
- **MUST — паттерн это помощь узнаванию, а не генератор** [PD-2026-07-21]: не всякая база + аффикс даёт реальное слово. `formation` помечает **существующие** единицы и помогает **угадать и узнать** незнакомое, но движок не вправе объявить произвольную комбинацию словом и предъявить её как реальную. Обещать генерацию значило бы учить несуществующим формам.
- **MUST — тема-паттерн и слово это разные targets** [PD-2026-07-21]: «понимаю приставку `out-`» (тема трека `word-formation`) и «знаю слово `outrun`» (LexicalItem) — два разных навыка, не двойной учёт. Знание паттерна не даёт Mastery по слову и наоборот; связь — через evidence.
- **MUST — прозрачность аффикса задаёт форму цели** [PD-2026-07-21, §5.5]: прозрачные аффиксы (`un-`, `re-`) допускают контролируемое производство как цель темы; semi-opaque (`out-`, `over-`, `mis-`) — recognition-first, производство не обязательно. Разрешение — по той же оси `transparency`, что у многословных единиц (§1a).
- **MUST — три раздельные величины** [ревью E-7/F-6, rereview E-R5]: не смешивать частоту, педагогический приоритет и персональный приоритет:
  - `frequency_score` + `frequency_band` — **только** корпусная частота: numeric Zipf/source score + нейтральные bands `very_high | high | mid | low | rare` по versioned thresholds. **Никаких** педагогических/доменных категорий здесь;
  - `curriculum_priority_band` — педагогический приоритет: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL` (сюда ушли utility/domain-категории вроде useful/specialized/incidental);
  - `learner_priority` — персональный приоритет; **вычисляется** движком, не хранится глобально. Формула — [[../OPEN]] OPEN-22 (в 0.4 не написана, см. там).

- **MUST — частота есть не у всех единиц** [П.4b]: `frequency_score`/`frequency_band` проставляются **только** там, где pinned-источник действительно покрывает единицу. Корпус слов не покрывает многословные единицы: `chunk`, `phrasal-verb` и `informal_chunk` частоты **не получают** — это 56% инвентаря. Отсутствие поля — нормальное состояние, а не пробел данных; валидатор не требует частоту и не подставляет значение по умолчанию.
- **MUST — запрет композитных подделок** [П.4b]: нельзя получать частоту многословной единицы, комбинируя частоты её токенов. Проверено на pinned-источнике: такая оценка не зависит от порядка слов (`run into` = `into run`), а бессмысленная цепочка частых слов обгоняет реальное слово средней частоты. Это не наблюдаемая частота фразы, и записывать её в `frequency_score` — фабрикация.
- **MUST — каждый потребитель определяет fallback** [П.4b]: любая policy, читающая `frequency_band` (learner_priority, отбор в повторения, lexicon_query), обязана явно определить поведение при отсутствии поля. Молчаливая трактовка «нет частоты = редкое» запрещена: она вытеснила бы из обучения именно рабочие фреймы, ради которых лексикон и строился.
- **MUST — согласованность с педагогическим приоритетом** [П.4b]: единица с `frequency_band` `very_high`/`high` не может иметь `curriculum_priority_band: INCIDENTAL` (что исключило бы её из повторений). Педагогический приоритет вправе отставать от частоты, но не вправе вычёркивать частотное ядро языка. Проверяется валидатором.

- **MUST**: каждая единица — сущность `LexicalItem` со стабильным ID. Минимальные поля:

Однословная единица, покрытая корпусом:

```yaml
id: word.delivery
type: word                # word | chunk | idiom | phrasal-verb | lexeme | informal_chunk | abbreviation | meme_template
title: delivery
cefr: A2
frequency_score: 4.59     # numeric (Zipf), из pinned-источника
frequency_band: high      # very_high | high | mid | low | rare (по versioned thresholds)
curriculum_priority_band: HIGH   # педагогический приоритет
register: neutral
domains: [work, project-management]
meaning_ru: поставка, выпуск результата
source_refs: [wordfreq@3.1.1, ngsl@1.2]
transformations: [authored, corpus-enriched]   # журнал изменений (rereview I-R3)
examples:
  - The delivery is planned for next week.
```

Многословная единица — **без** частотных полей и без `source_refs`: корпус её не покрывает, подделывать нечем:

```yaml
id: chunk.follow-up-message
type: chunk
title: follow-up message
cefr: A2
curriculum_priority_band: USEFUL
register: neutral
transparency: transparent
domains: [work, communication]
meaning_ru: последующее сообщение
transformations: [authored]
examples:
  - I sent a follow-up message on Tuesday.
```

Непрозрачная единица — дословный перевод даёт неверный смысл, поэтому обязателен `recognition`, а производство необязательно:

```yaml
id: idiom.call-it-a-day
type: idiom
title: call it a day
cefr: A2
curriculum_priority_band: HIGH
register: casual
transparency: opaque
domains: [everyday-life, work]
meaning_ru: закончить на сегодня, свернуть работу
literal_trap_ru: "не «назвать это днём»"
transformations: [authored]
examples:
  - It's almost eight, let's call it a day.
```

- **MUST — mastery-профиль** [rereview E-R3, P0-3]: у каждого LexicalItem (в т.ч. обычного word/chunk) есть versioned `LexicalMasteryProfile` — required dimensions и mastery-критерии по кортежу `(type, transparency, usage_policy)`, разрешимый из curriculum; validator проверяет наличие профиля. Таблица разрешения и precedence — [[../modules/scoring]] §6 (OPEN-13 закрыт).

- Источники данных и лицензии — решены (OPEN-6): CEFR-J + NGSL + wordfreq, build-time режим; правовая позиция, provenance и notices — OPEN-15 закрыт, детали — [[../modules/curriculum]] §3.1–3.2.

### 1c. Фрейм — единица заучивания грамматики [PD-2026-09-22]

Правило объясняет, но заучивается не правило, а фраза. Ученик просит, чтобы артикли, порядок слов и глагольные формы вылетали без припоминания правила в момент письма; такую автоматизацию даёт инвентарь готовых фраз со слотом, а не всё более подробный разбор формы. До этого решения chunks были привязаны к темам как **иллюстрации**; теперь часть из них объявлена тем, что ученик **заучивает и производит**.

- **MUST — фрейм это `chunk`, а не новый тип** [PD-2026-09-22, PD-C]: **Фрейм** — LexicalItem существующего типа `chunk` с двумя новыми полями: `frame_of` (стабильный id темы, чью форму фрейм несёт) и непустой `carries` (теги грамматической нагрузки). Нового `type`, отдельной mastery-таблицы и отдельной оси состояния фрейм не вводит: это тот же chunk — заготовка со слотом, — размеченная как носитель грамматической цели. Введение типа `pattern` потребовало бы второго `LexicalMasteryProfile` и второй ветки во всех потребителях ради разметки, которую выражают два поля.
```yaml
id: chunk.present-perfect-result.ive-already
type: chunk                    # фрейм — это chunk, без нового type
title: "I've already ___"      # слоты помечены ___; 0–2 слота
cefr: A2
curriculum_priority_band: CORE
register: neutral
transparency: transparent      # фрейм никогда не opaque
domains: [work, reporting]
meaning_ru: "я уже …"
frame_of: grammar.present-perfect.result
carries: [tense:present-perfect]
slot_hint_ru: "третья форма глагола + объект"
transformations: [authored]
examples:
  - I've already sent the report to the client.
  - I've already restarted the router twice.
```

- **MUST — `carries` закрыт** [PD-2026-09-22]: 1–3 тега на фрейм из закрытого словаря трёх семейств; незнакомый токен отвергает валидатор ([[../modules/curriculum]] §2c). Пополнение словаря — правка **этой** спеки, как и для `transformations`.

  | Семейство | Теги |
  |---|---|
  | `tense:` | `present-simple`, `present-continuous`, `past-simple`, `past-continuous`, `present-perfect`, `present-perfect-continuous`, `past-perfect`, `future-will`, `future-going-to`, `future-continuous`, `passive`, `conditional-0`, `conditional-1`, `conditional-2`, `conditional-3`, `reported-speech`, `modal-perfect` |
  | `article:` | `indefinite-first-mention`, `definite-second-mention`, `definite-shared-context`, `zero-plural`, `zero-uncountable`, `fixed-expression`, `institutional`, `superlative-ordinal`, `generic`, `proper-noun`, `a-an-sound`, `of-phrase` |
  | `structure:` | `svo-order`, `question-do`, `question-be`, `question-wh`, `negative`, `there-is`, `here-is`, `imperative`, `modal`, `comparative`, `superlative`, `connector`, `relative-clause`, `sequencing`, `time-marker`, `frequency-adverb`, `quantifier`, `preposition-time`, `preposition-place`, `possessive`, `demonstrative`, `inversion`, `cleft`, `participle-clause`, `ellipsis`, `hedging`, `nominalization`, `reference` |

- **MUST — `article:*` только при фиксированной позиции** [PD-2026-09-22]: тег артикля ставится, лишь если артикль стоит во фрейме в **фиксированной** позиции (`at the end of the ___`, `have a look`), а не внутри слота, который ученик заполняет сам (`I've already ___` не несёт `article:*`, хотя типичное заполнение содержит `the report`). Иначе тег перестал бы различать «артикль заучен как часть фразы» и «артикль выбирается заново каждый раз» — а это и есть то самое различие, ради которого ось заведена.
- **MUST — у фрейма нет частотных полей**: фрейм многословен, поэтому `frequency_score`, `frequency_band` и `source_refs` у него отсутствуют по уже действующему правилу §1b («частота есть не у всех единиц»): корпус слов фраз не покрывает, а композитная оценка из токенов запрещена. Отсутствие — норма, не пробел.
- **MUST — артикльный инвентарь в три яруса** [PD-2026-09-22, PD-F]: артикли — главный разрыв русскоязычного ученика, поэтому их фреймы организованы ярусами по убыванию «заучиваемости целиком»:
  1. **ярус 1 — фиксированные обороты, заучиваемые как целое**: `in the morning`, `at night`, `on the weekend`, `at the end of the day`, `once a week`, `have a look`, `go to work`, `on the other hand`, `by the way`, `at the moment`. Слотов нет либо один хвостовой;
  2. **ярус 2 — низкоуровневые схемы со слотами**: `I'm a ___` (роль), `There's a ___ in the ___`, `the ___ of the ___`, `one of the ___`, `a new ___ / the new ___`, `___ (plural, no article) are ___`;
  3. **ярус 3 — дискурсивное правило** (первое упоминание → определённость, общая идентифицируемость): даётся **коротко и последним**, как объяснение уже отработанного, а не как вход в тему.
- **MUST — поле `tier` у артикльного фрейма** [PD-2026-09-22]: фрейм с `frame_of` из артикльной темы несёт `tier: 1 | 2` (ярус 3 — не фреймы, а объяснение темы). Поле обязательно только для артикльных фреймов и проверяется валидатором.
- **MUST — фреймы попадают в личный словарь обычными триггерами**: фрейм становится `tracked` по тем же шести критериям enrollment §3 и планируется в повторения как обычный LexicalItem ([[learning-model]] §7). Отдельной очереди, отдельного scoring и отдельного состояния у фреймов нет — это и есть смысл решения «chunk, а не новый тип».
- **MUST — артикльный ярус повторяется постоянно** [PD-2026-09-22, PD-F]: фреймы артикльных ярусов 1–2 **никогда не покидают** очередь повторений полностью: пройдя базовую лестницу, они переназначаются на последний базовый интервал вместо выбывания (`permanent_interleave`, [[../modules/scheduler]] §3a). Знание артиклей без постоянной практики распадается, и «выучено» для них — состояние, требующее поддержки, а не финал. Ограничение объёма такого яруса в одном занятии — [[../OPEN]] OPEN-38.

## 2. Слой 2 — lexemes и формы

- **MUST**: неправильный глагол — один `LexicalItem` типа lexeme с формами, не три отдельные записи:

```yaml
id: lexeme.go
lemma: go
forms:
  base: go
  past: went          # слот может быть списком: be → past: [was, were]
  participle: gone
frequency_band: very_high
```

- **MUST — слот формы допускает несколько поверхностных форм** [content-review П.4a]: значение слота — одна форма **или список** (`be` → `past: [was, were]`). Валидатор принимает оба вида. «Знать слот» = продемонстрировать **все** перечисленные в нём поверхностные формы, если policy не помечает часть как опциональные; точная агрегация слот→lexeme — [[../OPEN]] OPEN-14.

- **MUST**: `go`, `went`, `gone` не считаются тремя выученными словами — владение привязано к одному lexeme, но движок отдельно видит evidence по каждой форме (умеет ли ученик использовать past, participle).
- **MUST — агрегация форм** [ревью D-7]: у lexeme определены form dimensions и **required set** форм; состояние lexeme детерминированно агрегируется из evidence по формам (знание только `go` не делает lexeme ACTIVE/MASTERED при незнании `went/gone`). Правила required forms и агрегации — [[../OPEN]] OPEN-14.
- **MUST**: страница `[[Irregular Verbs]]` — генерённый обзор, не отдельная копия данных.
- **SHOULD**: активно изучаются частотные глаголы (`core`/`high`); редкие и устаревшие остаются справочными (`INCIDENTAL`), не попадая в повторения без личной потребности.

## 3. Слой 3 — личный словарь ученика

- **MUST**: «выучено» — не boolean. Для каждой отслеживаемой единицы ведётся `LearnerLexicalState`:
  - когда впервые встретилась;
  - в каких сессиях использовалась;
  - значение или конкретный sense (если единица многозначна);
  - recognition и production evidence раздельно;
  - типичные ошибки (связь с observed errors);
  - Mastery, Stability, Retrievability;
  - последняя проверка и следующий review;
  - состояние.
- **MUST**: три оси состояния — те же, что у тем ([[learning-model]] §4, [[../glossary]]): enrollment (`tracked`), knowledge state (`NEW → LEARNING → ACTIVE → MASTERED` + `AT_RISK`), review status (`not_due/due/overdue`). Отдельной машины для лексики нет. LexicalItem — LearningTarget наравне с Topic.
- **MUST — вход даёт только enrollment** [ревью D-6, rereview C-R2]: попадание в личный словарь = `tracked`, knowledge state `NEW`. **Ни один из критериев входа сам по себе не создаёт evidence.** Evidence появляется только при отдельном сохранённом learner response; целенаправленное объяснение единицы агентом (критерий 4) — enrollment, но не доказательство знания.
- **MUST**: единица попадает в личный словарь (enrollment), только если выполнен хотя бы один критерий:
  1. была целью упражнения;
  2. ученик её не понял;
  3. допустил значимую ошибку;
  4. агент целенаправленно её объяснил;
  5. выражение отмечено как особенно полезное;
  6. ученик попросил её запомнить.
- **MUST NOT**: записывать каждое случайно встретившееся слово.
- **MUST**: лексические единицы участвуют в повторениях и re-entry на общих основаниях ([[learning-model]] §7): review-цели манифеста могут указывать на LexicalItem так же, как на тему.

## 3b. Informal-слой (Everyday, Online & Informal English)

Письменный разговорный английский — чаты, форумы, GitHub, Discord, Reddit — полноправная часть лексикона [PD-2026-07-19]. Это не оценка speaking.

- **MUST**: informal-единицы — те же `LexicalItem` с расширенными полями. `volatility` (устойчивость) и `currency` (актуальность) — раздельные поля [ревью A-5/F-7]:

```yaml
id: slang.my-bad
type: informal_chunk        # + abbreviation | meme_template
register: casual            # шкала: formal → neutral → casual → slang → potentially-offensive
usage_policy: safe_to_use   # safe_to_use | context_dependent | recognition_only | avoid
allowed_contexts: [general, work-chat]     # где допустимо употребление
meaning_ru: моя ошибка / виноват
neutral_equivalent: That was my mistake.
communities: [general, work-chat]
frequency_band: high
volatility: stable          # stable | changing
currency: current           # current | dated | obsolete  (для changing)
cultural_context: "..."     # для meme_template — обязателен (rereview H-R1)
first_observed_at: 2026-07-19
last_verified_at: 2026-07-19
source_refs: [...]
```

- **MUST — usage_policy и `requires_usage_policy`** [rereview H-R1]: `requires_usage_policy` — вычисляемый predicate по type/register (не только по флагу «informal-единица»): рискованный `type: word`/register тоже обязан иметь usage_policy. Понимать ≠ употреблять: `recognition_only`/`avoid` — только на распознавание.
- **MUST — `production_eligible`** [rereview H-R1; П.3 PD-2026-07-21]: вычисляемый из active `usage_policy` + active `currency` + active context. `avoid`, `recognition_only`, `obsolete`, `dated` без явного recognition-override, `opaque` как required production и `context_dependent` вне `allowed_contexts` → `production_eligible=false`. Единица с `safe_to_use` + `obsolete` или истёкшим currency review interval не проходит свежую generation/scheduler/bank reuse.
- **MUST — assessable dimensions по policy** [ревью H-2; PD-4 A]: dimensions и `mastery_criteria` зависят от effective policy; для `recognition_only`/`avoid`/`dated`/`obsolete` production не требуется (не «застревает» перед MASTERED). `dated` может появиться только в recognition/historical/register-awareness задачах с явным context-override. Правила профиля — [[../modules/scoring]] §6.
- **MUST — context_dependent enforcement** [ревью H-4]: `context_dependent` задаёт `allowed_contexts`/disallowed; вне разрешённого контекста — `recognition_only` (safe default). `communities` — метаданные, не правило допуска.
- **MUST — currency lifecycle** [ревью D-8/H-5; П.3 PD-3 C]: для `volatility: changing` обязательны `first_observed_at`, `last_verified_at`, `currency`, источник/сообщество; для `meme_template` — ещё `cultural_context`. Валидатор проверяет полный набор. Истёкший review interval не меняет `currency` молча: он приостанавливает production и создаёт review-задачу. `obsolete` ставится явным negative review или повторными пропущенными проверками по versioned policy. Доменное событие: `LEXICAL_CURRENCY_CHANGED`.
- **MUST — safety-overlay, safety не пинится** [PD-2026-07-19, rereview G-R1; П.3]: `production_eligible` всегда проверяется по **active** policy в момент доставки, `EXERCISE_RENDERED`, bank reuse и placement production delivery, а не по pinned-версии. Прошлое evaluation/replay остаётся детерминированным по сохранённым exercise/evidence-снапшотам; unsafe-единицы для будущей доставки/reuse **отменяются или заменяются** append-only event, хранящим обе версии.
- **MUST**: оценка informal-владения проверяет: понимание значения, распознавание тона (helpful/dismissive/sarcastic/hostile), выбор допустимого контекста, перевод в нейтральный английский, естественный ответ (для разрешённого production), перенос между регистрами.
- **MUST — Informal ↔ CEFR через contribution_scope** [PD-2026-07-19, ревью C-5/H-1]: recognition сленга/мемов **никогда** не в CEFR. Письменное производство в реальном рабочем контексте может давать компонент writing/transfer через `contribution_scope`-тег evidence, с dedup и cap (один source-span — не одновременно в informal-профиль и CEFR сверх cap). Informal-владение ведётся отдельным профилем **Informal Online Competence** с собственной шкалой ([[learning-model]] §5, механизм — [[../OPEN]] OPEN-13).

Каталоги: **stable core** (проектируется заранее) / **living layer** (встреченное в обучении, через maintain-workflow с provenance) / **learner lexicon** (личный словарь, §3). Источники частот и CEFR-разметки — контракт [[../modules/curriculum]] §3.

- **MUST — граница living-layer candidate** [П.3, PD-2026-07-21]: сессия может создать только `LivingLexicalCandidate`; это не LexicalItem, не schedulable target и не evidence. Promotion делает только `maintain-english-curriculum` после нормализации, dedup, no-excerpt проверки, назначения usage/currency, авторских примеров с нейтральным парафразом и валидации.
- **MUST — unlinked coverage** [П.3, PD-5 D]: LexicalItem без `topic.lexicon` не является ошибкой. Он может попадать в практику через lexicon-first micro lane по learner request / observed error / due review / CORE-HIGH safe candidate; auto-link candidates проходят maintain-workflow перед активацией.
- **MUST NOT — постоянное правило** [PD-2026-07-20, rereview I-R2; П.3]: living layer **не хранит сторонние excerpts** (текст forum post/example) — мотив ToS площадок и персональные данные. Разрешено: source-метаданные, source pointer/hash, короткая сама единица, авторское context summary и **собственный** нейтральный парафраз. Правовая позиция целиком — [[../modules/curriculum]] §3.1.

## 4. Obsidian-проекция

Генерённые страницы (детали — контракт 0.6):

```text
memory/knowledge/vocabulary/
memory/knowledge/chunks/
memory/knowledge/irregular-verbs.md
memory/current/vocabulary-review.md
```

Страница единицы связана с темами, ошибками и сессиями:

```markdown
# follow up on

- Introduced in [[sessions/2026-07-19-session-001]]
- Related topic: [[topics/work.project-updates]]
- Error: [[errors/missing-preposition-after-follow-up]]
- Next review: [[reviews/2026-07-22]]
```

## 5. Распределение по контрактам

| Что | Куда |
|---|---|
| Формат `LexicalItem`, source provenance/лицензии | Curriculum Contract (0.3) + OPEN-15 |
| `LearnerLexicalState`, scoring, informal-профиль, агрегация форм | 0.4 + OPEN-13/OPEN-14 |
| Фиксация лексики в сессии (vocabulary/chunk observed) | уже в [[../flows/session]] |
| Obsidian-страницы лексики | Obsidian Vault Contract (0.6) |
| Отбор лексикона A1–A2 по категориям | работа П.4 |

## 6. Открытые вопросы

Механизмы зафиксированных выше инвариантов достраиваются в контрактах ([[../OPEN]]):

- ~~OPEN-13~~ **закрыт** в 0.4: Informal Online Competence, `contribution_scope` и assessable dimensions — [[../modules/scoring]] §5–§6.
- ~~OPEN-14~~ **закрыт П.3** [PD-2026-07-21]: currency/usage-policy lifecycle, context_dependent fallback, stale-safety банка/live manifests, `dated` recognition-only и lexeme form-slot handoff — §3b + [[../modules/scoring]] §6.
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция, состав данных и provenance — [[../modules/curriculum]] §3.1–§3.2.
- **OPEN-22**: формула learner_priority (OPEN-8 закрыт только в части CEFR-уровня; формула переоткрыта) → 0.4 scoring.
- **OPEN-38**: нужен ли потолок на число артикльных фреймов постоянного interleaved-яруса в одном занятии (§1c) → [[../modules/control]] после эксплуатации.

## История изменений

- **2026-09-22**: [PD-2026-09-22] добавлен §1c — **фрейм** как единица заучивания грамматики: `chunk` с `frame_of` и закрытым `carries` (PD-C), правило `article:*` только при фиксированной позиции артикля, отсутствие частотных полей у фреймов, три яруса артиклей и поле `tier` (PD-F), enrollment/повторения фреймов на общих основаниях и постоянный interleaved-ярус артикльных фреймов. Заведён OPEN-38.
- **2026-07-21**: патч П.3 фазы 2 [PD-2026-07-21] фиксирует effective `production_eligible`, гибридное currency-старение, `dated` recognition-only, границу living-layer candidate и политику покрытия unlinked-лексикона; OPEN-14 закрыт. OPEN-31 остаётся content-review.
- **2026-07-20 (P0-триаж)**: ранее в этот день добавлены ось `transparency`, тип `idiom`, `literal_trap_ru` и правила покрытия частотой (П.4b/П.4c); здесь — ссылка на OPEN-22 вместо закрытого OPEN-8 (P0-12).
- **2026-07-20**: content-review П.4a — слот формы lexeme допускает список поверхностных форм (`be → past: [was, were]`); «знать слот» = все перечисленные, если policy не пометит опциональными; агрегация слот→lexeme → OPEN-14.
- **2026-07-19 (4)**: rereview — frequency_band только numeric+нейтральные bands (E-R5); generic LexicalMasteryProfile (E-R3); вход даёт только enrollment, объяснение агента ≠ evidence (C-R2); production_eligible + obsolete + requires_usage_policy + cultural_context (H-R1); safety-overlay «safety не пинится» (G-R1); living layer без сторонних excerpts до OPEN-15 (I-R2); transformations в схеме (I-R3); три оси состояния.
- **2026-07-19 (3)**: red-team триаж — разделены frequency_band/curriculum_priority_band/learner_priority (E-7/F-6) и volatility/currency (A-5/F-7); агрегация форм lexeme (D-7); enrollment≠знание (D-6); assessable dimensions по usage_policy (H-2); context_dependent enforcement (H-4); currency lifecycle и полная валидация (D-8/H-5); stale-safety банка (H-3); Informal→CEFR через contribution_scope (C-5). Механизмы → OPEN-13/14/15.
- **2026-07-19 (2)**: добавлен §3b — informal-слой по одобренному концепту Codex.
- **2026-07-19**: создана по дизайну пользователя: три слоя, композитный приоритет, lexeme с формами, не-boolean личный словарь. Все решения [PD-2026-07-19].
