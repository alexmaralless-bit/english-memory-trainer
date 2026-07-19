# Семантический red-team review концепта

Дата: 2026-07-19

Предмет: шесть current-спек English Memory Trainer

Метод: проверка канона против `wiki/README.md`, `docs/design-direction.md`, брифа, glossary/OPEN/roadmap и provenance. Расхождения с нижестоящими источниками, явно принятые через `[PD-2026-07-19]`, дефектами не считались.

## 1. Резюме: топ-5

1. **Backend не является фактическим владельцем оценки.** Flow разрешает агенту передать готовую `классификацию` review, а evidence не имеет правил семантической уникальности. Агент может отправлять `CONFIRMED/PROGRESS`, переиспользовать один ответ с новыми idempotency keys и накручивать Mastery, CEFR, Informal Online Competence и XP. Это `BLOCKER`.
2. **`ABANDONED` — обход evidence-ограничений.** Брошенная сессия запускает тот же scoring, но не обязана выполнять finish-postconditions. Можно сохранять только успехи, бросать сессию перед неудачами и формально получать «разные сессии» для rubric-повторяемости. Это `BLOCKER`.
3. **Replay не привязан к неизменяемой curriculum.** Session Manifest и evidence не pin-ят curriculum/scoring/policy versions; deprecation описана без семантики replay, split/merge и orphan review targets. Активация версии посреди сессии способна изменить прошлый результат. Это `BLOCKER`.
4. **State machines неполны и местами неверны.** Успешный review переводит `MASTERED → REVIEW_DUE → ACTIVE`; не определены переходы для части outcomes, time-driven переход противоречит evidence-only правилу, а lexeme не агрегирует состояния форм. Это `BLOCKER` для scoring-контракта.
5. **Не выбран лицензионно значимый режим использования `wordfreq`.** Спека объявляет импорт и корневой `ATTRIBUTIONS.md`, но не решает, будет ли это runtime query или распространяемый derivative и как notices останутся связаны с данными; upstream отдельно предупреждает о проблеме CSV-экспорта. До решения П.4 имеет `BLOCKER`.

## 2. Находки A–J

## A. Внутренние противоречия — НАХОДКИ

### A-1. Два владельца review-классификации — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Сценарий»: `A->>T: review result {review_id, классификация}`; там же, «Правила сценария»: «агент меняет scores, состояния тем или расписание — только записывает факты»; «Выведенные контракты»: evidence отвечает за «классификацию review-результатов».

**Почему дефект:** диаграмма делает итоговую оценку клиентским вводом, тогда как текст запрещает агенту оценочное управление и отдаёт классификацию backend. `PROGRESS/CONFIRMED` влияет на scoring и scheduler, поэтому это не косметическая двусмысленность.

**Предлагаемая правка:** агент передаёт raw answer, контекст, hints и rubric observations; движок сам вычисляет и возвращает classification по versioned policy.

### A-2. Уровень после отказа от placement появляется без evidence — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §5: «уровень меняет только движок по накопленному evidence тем соответствующего уровня»; `wiki/flows/placement.md`, «Сценарий»: `placement decline --self-assessment A2` и «консервативный старт: уровни very-low-confidence».

**Почему дефект:** самооценка не является evidence, но записывается в ту же сущность «уровни». Низкая confidence не устраняет нарушение инварианта и позволяет влиять на рекомендации без измерения.

**Предлагаемая правка:** хранить `self_reported_level` отдельно; working level до первого допустимого evidence считать unknown/provisional и не смешивать с измеренным уровнем.

### A-3. OPEN-6 одновременно открыт и закрыт — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §1: «Точный frequency source и лицензирование словарных данных — **OPEN-6**, решается в Curriculum Contract (0.3)»; §6: «**OPEN-6**: frequency source и лицензирование лексических данных → блокирует финализацию 0.3 и отбор П.4»; `wiki/modules/curriculum.md`, §8: «OPEN-6 закрыт этим контрактом».

**Почему дефект:** две current-спеки задают противоположный статус зависимости. `wiki/OPEN.md` помещает OPEN-6 в решённые, а `wiki/roadmap.md` одновременно пишет «OPEN-6 закрыт» для 0.3 и «OPEN-6 открыт» для 0.9.

**Предлагаемая правка:** синхронизировать lexical-system/roadmap с реестром; из-за I-1 открыть отдельный вопрос о допустимом режиме импорта.

### A-4. Каноническая Topic schema имеет два enum prerequisites — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §9: «advisory prerequisites (hard/soft — как сила рекомендации, не замок)»; `wiki/modules/curriculum.md`, §2: «`advisory_prerequisites.strong/soft`» и «в learning-model §9 это hard/soft; здесь переименовано в strong/soft».

**Почему дефект:** явное признание rename не создаёт совместимость. Автор программы, validator и потребители могут реализовать разные ключи.

**Предлагаемая правка:** оставить один schema enum (`strong/soft`); старые имена обозначить только как superseded, не как current contract.

### A-5. LexicalItem schema расходится по именам и значениям — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §1/§3b: `frequency_band: high`, `currency: stable`; `wiki/modules/curriculum.md`, §2/§4: ключевое поле `band`, фильтры «band, track, usage_policy, currency»; lexical-system далее требует `currency: current / dated / obsolete`.

**Почему дефект:** один и тот же объект валиден по одному фрагменту канона и невалиден по другому. `stable` также отсутствует в объявленном enum.

**Предлагаемая правка:** утвердить единое имя поля и разделить `volatility: stable/changing` от `currency: current/dated/obsolete`.

### A-6. XP для ABANDONED одновременно обещан и не назначен — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §8: «XP начисляется за практику: выполненные задания, evidence, закрытые повторения, re-entry блоки»; `wiki/flows/session.md`, «Состояния сессии»: `ABANDONED` «сохраняет и учитывает всё зафиксированное»; таблица контрактов: learner делает «начисление XP, обновление streak на finish».

**Почему дефект:** replay одной ABANDONED-сессии может законно дать разные XP/streak в двух реализациях.

**Предлагаемая правка:** определить eligibility и exactly-once award для обоих terminal states.

### A-7. Один writing rubric в placement конфликтует с запретом одной оценки двигать уровень — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §3: «одна оценка агента не меняет состояние темы и не двигает уровень»; §6: «writing — короткий фрагмент по rubric»; `wiki/flows/placement.md`: после scoring возвращаются «уровни по навыкам + confidence».

**Почему дефект:** неясно, является ли provisional writing estimate продуктовым исключением или writing должен остаться unknown до повторения.

**Предлагаемая правка:** пользователь должен выбрать явное исключение только для low-confidence estimate либо минимум два независимых writing items.

## B. Замки-безбилетники — ЧИСТО

Скрытых учебных замков, противоречащих `[PD-2026-07-19]`, не найдено. Подозрительные места проверены отдельно:

- finish-postconditions блокируют только нечестное терминальное закрытие; пропущенный review можно закрыть `INSUFFICIENT_EVIDENCE`;
- конфликт active session оставляет ученику выбор `resume` или `abandon_and_start`;
- placement, re-entry и CEFR gate допускают отказ без штрафа;
- prerequisites, overdue backlog и флаг `early` явно рекомендательные;
- `recognition_only/avoid` ограничивают небезопасное production, а не доступ к изучению;
- отсутствие TOEFL-тем ниже B1 — граница контента трека, не learner lock.

## C. Дыры evidence-модели — НАХОДКИ

### C-1. Агент может назначить себе успешный review outcome — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Сценарий»: `review result {review_id, классификация}`.

**Почему дефект / атака:** агент отправляет `CONFIRMED` или `PROGRESS` для слабого ответа. Такой payload не нарушает ни одного MUST; server-side derivation или admissibility check не требуются.

**Предлагаемая правка:** запретить client-supplied итоговую classification; принимать только проверяемые наблюдения и вычислять outcome в движке.

### C-2. ABANDONED позволяет cherry-picking и обход two-session/cap — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Состояния сессии»: «закрытие брошенной сессии запускает тот же пересчёт scoring»; «Решения этого flow»: finish требует финализировать attempts и дать исход каждой review-цели.

**Почему дефект / атака:** агент записывает лёгкий успех, не записывает/не завершает сложную цель и делает abandon. Положительное evidence считается без finish-postconditions. Два быстрых abandon формально дают «две разные сессии» для rubric repeatability; per-session cap только ограничивает одну итерацию.

**Предлагаемая правка:** terminalization ABANDONED должна закрывать все pending records явными outcomes и иметь правила eligibility/independence; «разная сессия» не должна сама по себе доказывать повторяемость.

### C-3. Idempotency не запрещает семантический replay — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §3: evidence содержит «idempotency key»; скрытое подтверждение фиксируется «через CLI с цитатой»; §3: rubric-repeatability — «минимум в двух разных сессиях».

**Почему дефект / атака:** один raw answer, одна цитата или одно тривиальное generated exercise записываются повторно с новыми keys и session IDs. Один span можно одновременно зачесть множеству тем/dimensions. Все MUST соблюдены, Mastery растёт.

**Предлагаемая правка:** ввести immutable `attempt_id`, `source_message_id`/span hash, item exposure ID, semantic uniqueness, multi-credit allocation и независимость по новому prompt/context/интервалу.

### C-4. CEFR можно поднять узкой выборкой лёгких тем — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §5: уровень меняется «по накопленному evidence тем соответствующего уровня».

**Почему дефект / атака:** ученик выполняет только несколько самых лёгких тем уровня и избегает слабых областей. Нет MUST для curriculum coverage, representative sampling, числа независимых тем и обязательной ширины dimensions. Ограничение общего уровня относительно weakest core не помогает, если слабость не измерена.

**Предлагаемая правка:** определить coverage matrix, минимумы по темам/dimensions, confidence floor и правило unknown-as-unknown, а не как отсутствующая слабость.

### C-5. Informal evidence может обойти запрет повышения CEFR — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §5: informal «не повышает CEFR-уровни напрямую», но evidence «может засчитываться в writing и transfer»; `wiki/modules/curriculum.md`, §2: любой Topic имеет `cefr`; informal track начинается с A1.

**Почему дефект / атака:** у Topic, LexicalItem и evidence нет машинного признака, разделяющего `informal_only`, core Writing/Transfer и dual evidence. Агент размечает короткий ответ как writing/transfer по нескольким CEFR-темам и одновременно поднимает Informal Online Competence. Слово «напрямую» не задаёт запрет.

**Предлагаемая правка:** добавить `contribution_scope`, раздельные evidence-компоненты, dedup и cap; informal recognition по умолчанию не участвует в CEFR.

### C-6. Две фиксированные placement-формы можно выучить — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §6: «минимум две формы теста»; `wiki/flows/placement.md`: повторный placement — «только по явному запросу ученика».

**Почему дефект / атака:** ученик запоминает обе формы и запрашивает повторные прохождения. Objective ответы остаются формально валидным evidence без exposure/cooldown policy.

**Предлагаемая правка:** хранить exposure history; вводить rotation/cooldown и понижать либо обнулять вес повторно увиденных items.

### C-7. XP и re-entry можно фармить — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §8: «XP начисляется за практику: выполненные задания, evidence, закрытые повторения, re-entry блоки»; §7: «результат re-entry обновляет Retrievability и план повторений».

**Почему дефект / атака:** бесконечные простые задания, duplicate evidence или повторно созданный лёгкий re-entry дают XP и могут повышать Retrievability. Нет award-once, source ID, eligibility outcome или session/day cap.

**Предлагаемая правка:** XP ledger с уникальным source event; versioned re-entry assignment/trigger epoch; caps и допустимые outcomes.

### C-8. Session notes могут обойти границу authoritative state — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/continuation.md`, «Решения этого flow»: заметка может описывать «о чём говорили, на чём остановились»; «Состав tutor briefing»: briefing включает «итог + session notes».

**Почему дефект / атака:** агент пишет «ученик уверенно освоил X». Текущие MUST не дают note прямого пути в scoring, но следующий агент получает note внутри того же briefing, может принять её за state и пропустить нужную практику. Не задана trust boundary между вычисленным state и свободным текстом агента.

**Предлагаемая правка:** маркировать notes как untrusted, non-evidence data, экранировать их в briefing и запретить автоматическую интерпретацию как состояние.

## D. Целостность state machines — НАХОДКИ

### D-1. Успешный review демотирует MASTERED — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §4: `MASTERED --> REVIEW_DUE: подошёл интервал`; `REVIEW_DUE --> ACTIVE: CONFIRMED`.

**Почему дефект:** подтверждение сохранённого знания всегда теряет `MASTERED`. После первого due review устойчивое состояние больше не восстанавливается напрямую.

**Предлагаемая правка:** сохранять prior steady state либо добавить `REVIEW_DUE → MASTERED: CONFIRMED` для цели, пришедшей из MASTERED.

### D-2. Outcome enum не покрыт transition table — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §3: `PROGRESS / CONFIRMED / REGRESSION / RECOVERED / INSUFFICIENT_EVIDENCE`; диаграмма §4 использует только часть этих outcomes.

**Почему дефект:** не определены `PROGRESS`/`INSUFFICIENT_EVIDENCE`, regression из LEARNING/ACTIVE до due, confirmed/recovered из иных состояний и необходимые self-loops. Реализации разойдутся.

**Предлагаемая правка:** полная таблица `(current state, trigger/outcome) → next state`, включая no-op/error.

### D-3. Time-driven AT_RISK противоречит evidence-only переходам — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §4: `REVIEW_DUE --> AT_RISK: просрочено / REGRESSION`; далее: «переходы выполняет только движок по evidence».

**Почему дефект:** просрочка возникает от часов, не от evidence. Неясно, это knowledge state или scheduler status и кто инициирует переход.

**Предлагаемая правка:** вынести due/overdue в scheduling status либо явно разрешить clock event и versioned policy.

### D-4. `STARTED → ABANDONED` отсутствует — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Состояния сессии»: `STARTED → IN_PROGRESS → FINISHED | ABANDONED`; «Сценарий»: незавершённую сессию можно закрыть через `session start --abandon-active`.

**Почему дефект:** только что созданная STARTED-сессия уже active, но abandon для неё недостижим по диаграмме. Неясен и finish сессии только с отказами, где нет первой attempt-фиксации.

**Предлагаемая правка:** определить terminal transitions из STARTED или событие, которое гарантированно переводит её в IN_PROGRESS перед closure.

### D-5. У ABANDONED нет самостоятельной команды и terminal semantics — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, таблица CLI: `trainer session start/resume/finish`; abandon существует только как `start --abandon-active`.

**Почему дефект:** сессию нельзя штатно бросить без старта новой; не определены repeated abandon, finish/resume terminal session и инициатор перехода.

**Предлагаемая правка:** добавить idempotent `session abandon` с pre/postconditions и стабильными terminal responses.

### D-6. Tracking ошибочно является knowledge transition — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §3: «попадание в личный словарь = INTRODUCED»; критерии включают «выражение отмечено как особенно полезное» и «ученик попросил её запомнить»; `learning-model.md`, §4: переходы идут «по evidence».

**Почему дефект:** просьба отслеживать не доказывает знакомства или знания, но меняет общую knowledge machine.

**Предлагаемая правка:** отделить enrollment/tracking status от knowledge state либо определить non-scoring exposure event для INTRODUCED.

### D-7. Одна machine lexeme не агрегирует evidence форм — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §2: «движок отдельно видит evidence по каждой форме»; §3: у единицы одна общая машина состояний.

**Почему дефект:** знание `go` может сделать lexeme ACTIVE/MASTERED при незнании `went/gone`; правила required forms и агрегации отсутствуют.

**Предлагаемая правка:** определить form dimensions, required set и детерминированную агрегацию item state.

### D-8. Currency не имеет lifecycle — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §3b: `last_verified_at`, `currency: current / dated / obsolete`; `wiki/modules/curriculum.md`, §4 публикует только `LEXICAL_ITEM_ADDED`.

**Почему дефект:** нет переходов, инициатора, revalidation срока, update event и последствий `dated/obsolete`. Состояния объявлены, но недостижимы/неоперациональны.

**Предлагаемая правка:** определить currency lifecycle, владельца workflow, события и влияние на generation/review/bank.

### D-9. Placement может сразу выдать MASTERED — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/flows/placement.md`, «Решения»: проверенные единицы получают состояния «`INTRODUCED`/`LEARNING`/…»; `learning-model.md`: MASTERED требует «mastery-критерии + retention».

**Почему дефект:** многоточие не задаёт максимальное стартовое состояние. Одна 30–40-минутная диагностика не демонстрирует retention во времени.

**Предлагаемая правка:** решить и зафиксировать placement ceiling; без отдельного retention evidence запретить MASTERED.

## E. Невыполнимые или пустые MUST — НАХОДКИ

### E-1. `mastery_criteria` — пустой placeholder ключевого MUST — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §9: тема MUST иметь «required dimensions и критерии освоения по каждой»; `wiki/modules/curriculum.md`, §2: `mastery_criteria: {...}`; validator §5 не проверяет наличие/валидность этих критериев.

**Почему дефект:** по schema нельзя написать или проверить curriculum. Roadmap допускает П.2 до 0.4, хотя именно 0.4 должен определить scoring semantics.

**Предлагаемая правка:** определить versioned criteria schema до П.2 либо сделать П.2 зависимым от 0.4; валидировать критерии каждой required dimension.

### E-2. Finish требует summary до того, как сам его создаёт — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Решения»: «summary создан»; «Правила»: finish отклоняется, если «нет summary»; диаграмма: после `session finish` движок возвращает `summary`.

**Почему дефект:** postcondition циклична. Не определены автор, schema и момент summary; также нет lifecycle/команды «финализировать attempt», хотя это обязательное условие.

**Предлагаемая правка:** определить Attempt state machine/API; выбрать engine-generated summary после commit либо явный `summary_draft` как вход atomic finish.

### E-3. Confidence «3–5 сессий» недетерминирован — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §6: «движок повышает confidence по evidence первых 3–5 сессий»; `wiki/flows/placement.md`, «Правила сценария»: «движок повышает confidence и корректирует уровни автоматически».

**Почему дефект:** не определены конец окна, coverage, снижение confidence и учёт ABANDONED/пустых сессий. Одинаковый event log допускает разные решения «после 3» и «после 5».

**Предлагаемая правка:** versioned confidence policy; явно включить её в OPEN-1 или отдельный OPEN.

### E-4. «Удачное упражнение» не проверяемо — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §9: «удачное сгенерированное упражнение сохраняется».

**Почему дефект:** нет acceptance rubric, владельца решения, promotion event, dedup и invalidation. Любое упражнение можно назвать удачным, выполнив MUST.

**Предлагаемая правка:** состояния `generated → accepted/rejected`, versioned acceptance criteria и provenance; иначе понизить до SHOULD.

### E-5. `maintain-english-curriculum` — непроверяемый enforcement — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §5: «изменения — только через `maintain-english-curriculum` workflow».

**Почему дефект:** workflow не имеет контракта входов, проверок, результата или attestation. Нельзя вручную доказать, каким путём изменился файл.

**Предлагаемая правка:** специфицировать workflow и сделать activation проверяющей source provenance, schema и validation result независимо от способа редактирования.

### E-6. XP MUST не имеет единицы и exactly-once механизма — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §8: «XP начисляется за практику: выполненные задания, evidence, закрытые повторения, re-entry блоки».

**Почему дефект:** «выполнено» и «закрыто» не определены; один event может подходить сразу под несколько оснований. Caps и unique source отсутствуют.

**Предлагаемая правка:** versioned XP policy и immutable award event с уникальным source ID.

### E-7. Глобальный frequency band зависит от конкретного ученика — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §1: «общая частотность + коммуникативная полезность + применимость в работе + соответствие CEFR + продуктивность выражения + личная потребность ученика»; пример сохраняет `frequency_band: high`.

**Почему дефект:** learner-specific фактор нельзя детерминированно записать в глобальное поле. Смешаны corpus frequency, curriculum priority и scheduler priority.

**Предлагаемая правка:** разделить эти три значения и версионировать формулу персонального приоритета.

### E-8. «Максимально консервативные» рекомендации пусты — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/placement.md`, «Правила сценария»: «рекомендации при `very-low-confidence` максимально консервативны».

**Почему дефект:** нет наблюдаемого свойства, которое отличает допустимую рекомендацию от недопустимой; MUST нельзя проверить.

**Предлагаемая правка:** определить fallback range, exploration rate и запрет трактовать unknown как mastered.

### E-9. Placement «~30–40 минут» как MUST — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §6: «**MUST** `[mvp]`: короткий текстовый placement ~30–40 минут».

**Почему дефект:** время зависит от ученика; знак `~` не задаёт проверяемой границы.

**Предлагаемая правка:** выбрать time-box/число items либо сделать это SHOULD с целевой медианой.

## F. Глоссарий-дрейф — НАХОДКИ

### F-1. Season XP сохраняет отменённые штрафы — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/glossary.md`, «Метрики»: «Season XP — дисциплина: выполненные планы, бонусы, штрафы»; `wiki/product/learning-model.md`, §8: «Штрафов и списаний XP нет».

**Почему дефект:** определение термина противоречит принятому PD и current spec.

**Предлагаемая правка:** определить единый `XP` без штрафов; Season XP либо удалить, либо отдельно определить только как период агрегации.

### F-2. Состояния и outcomes перечислены, но не определены — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/glossary.md`, «Review»: «результат классифицируется как `PROGRESS / CONFIRMED / REGRESSION / RECOVERED / INSUFFICIENT_EVIDENCE`»; `wiki/product/learning-model.md`, §4 использует `NEW`, `INTRODUCED`, `LEARNING`, `ACTIVE`, `MASTERED`, `REVIEW_DUE`, `AT_RISK`.

**Почему дефект:** нарушён принцип README «термин определяется здесь один раз»; классификаторы не имеют общего смысла enum values.

**Предлагаемая правка:** дать нормативные определения каждого knowledge state и outcome; переходы оставить в learning-model.

### F-3. Skill dimension имеет два schema имени — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/glossary.md`: `spontaneous written production`; `wiki/product/learning-model.md` и `wiki/modules/curriculum.md`: `spontaneous_production`.

**Почему дефект:** display label смешан с exact enum ID.

**Предлагаемая правка:** в glossary перечислить точные machine IDs и отдельно human labels.

### F-4. Mastery/Review определены только для Topic, но применены к LexicalItem — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/glossary.md`: «Mastery — качество владения темой», «Review — повторение темы»; `wiki/product/lexical-system.md`, §3: LexicalItem имеет Mastery/Stability/Retrievability и review.

**Почему дефект:** глоссарий исключает половину target types.

**Предлагаемая правка:** ввести `LearningTarget = Topic | LexicalItem` либо нормативные lexical-определения.

### F-5. Критические сущности используются без определения — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Решения этого flow»: «каждый записанный attempt финализирован», «каждая review-цель манифеста имеет явный исход», «summary создан»; `wiki/product/learning-model.md`, §5/§6: «самого слабого core-навыка», «общий working estimate», `confidence`.

**Почему дефект:** это не просто синонимы Attempt/Review: у них отдельные lifecycle и scoring consequences, но glossary их не фиксирует.

**Предлагаемая правка:** определить ReviewAssignment/ReviewTarget, Attempt finalization, Session Summary, Confidence, Working Level и core skill.

### F-6. Frequency и педагогический priority названы одним термином — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §1: «общая частотность + коммуникативная полезность + применимость в работе + соответствие CEFR + продуктивность выражения + личная потребность ученика» и `frequency_band: high`; `wiki/glossary.md`: «Приоритет — категории `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL`».

**Почему дефект:** corpus statistic и policy output становятся неразличимы.

**Предлагаемая правка:** отдельные `corpus_frequency`/`frequency_band`, `curriculum_priority_band`, `learner_priority`.

### F-7. Currency enum расходится с примером — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`: `currency: stable`, затем `currency: current / dated / obsolete`; `wiki/glossary.md` содержит только второй набор.

**Почему дефект:** канонический пример не проходит каноническую схему.

**Предлагаемая правка:** разделить volatility и currency либо утвердить единый enum с правилами применимости.

### F-8. Локально введённые curriculum-сущности отсутствуют в glossary — `MINOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §2 вводит `CurriculumVersion`, `Level`, `Module`; `wiki/README.md`: «Новый термин/сущность/состояние сначала вводится в glossary».

**Почему дефект:** локальная таблица объясняет поля, но нарушает единую точку терминологии.

**Предлагаемая правка:** добавить краткие определения в glossary, не дублируя module schema.

## G. Пропущенные сценарии — НАХОДКИ

### G-1. Placement не имеет lifecycle, resume и checkpoint — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/placement.md`, диаграмма: внутри `loop по секциям` многократно вызывается `placement submit`; audit знает `PLACEMENT_STARTED / SUBMITTED / SCORED / DECLINED`.

**Почему дефект:** после обрыва чата неизвестно, сохранена ли секция, можно ли resume, является ли каждый submit terminal и когда scoring допустим. Повторная отправка может пересчитать результат.

**Предлагаемая правка:** state machine `STARTED → IN_PROGRESS → SUBMITTED → SCORED | ABANDONED`, incremental answer/checkpoint API, resume/expiry и один terminal submit.

### G-2. Live session не pin-ит активную curriculum/policy — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §5: «движок работает с активированной валидной версией»; `wiki/flows/session.md`, «Сценарий»: `Session Manifest {re-entry?, review-цели[review_id], рекомендации тем, required_skills}`; `wiki/product/learning-model.md`, §3: evidence содержит «версия rubric (если применялась)».

**Почему дефект:** activation при `IN_PROGRESS` меняет criteria, refs и recommendations на resume и replay. Одинаковые события получают другой результат.

**Предлагаемая правка:** pin curriculum, scoring, scheduler, generation-policy и rubric snapshots в session/placement/evidence; новая версия действует только для явно определённой границы.

### G-3. Deprecation несовместима с deterministic replay — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §5: «только deprecation с указанием преемника и миграцией»; `wiki/product/learning-model.md`, §4: «scoring детерминирован и воспроизводим replay'ем событий».

**Почему дефект:** не определено, replay использует старое definition или successor, что происходит при split/merge/retired без преемника и перепривязывается ли historical evidence. Перезапись event log нарушит append-only; lookup current successor меняет прошлое.

**Предлагаемая правка:** immutable curriculum snapshots; event с исходной version; append-only alias/migration events и явная policy 1:1/split/merge/retired.

### G-4. Terminal ABANDONED не закрывает pending review/re-entry — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, «Решения этого flow»: к finish «каждая review-цель манифеста имеет явный исход»; «Состояния сессии»: `ABANDONED` запускает scoring «без полного summary»; `wiki/flows/continuation.md` рассматривает только «resume брошенной IN_PROGRESS сессии».

**Почему дефект:** обязательное закрытие целей определено для finish и для продолжения всё ещё IN_PROGRESS-сессии, но не для terminal ABANDONED. При abandon во время re-entry или review нет partial/interrupted outcome, правила переноса цели и следующей рекомендации.

**Предлагаемая правка:** abandon атомарно закрывает pending цели как `INSUFFICIENT_EVIDENCE(reason=abandoned)` и создаёт новые scheduler assignments либо явно переносит их с новыми IDs; re-entry получает собственный outcome.

### G-5. Review target может осиротеть до появления evidence — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §5 запрещает удалить только ID, «использованный в evidence»; `wiki/flows/session.md` хранит review-цели в Manifest до выполнения.

**Почему дефект:** persisted manifest/review queue/placement form уже ссылается на ID, но deletion guard ещё не действует. Activation может оставить неразрешимую цель.

**Предлагаемая правка:** бессмертие для любого persistent reference; cross-validator проверяет learner state, manifests, queue, bank и assessments; tombstones сохраняются.

### G-6. ABANDONED пересчитывает не все производные — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`: ABANDONED запускает «тот же пересчёт scoring»; таблица назначает scheduler, XP/streak и memory обновление только «на finish».

**Почему дефект:** новый manifest после `start --abandon-active` может строиться на обновлённом score, но старой review queue/briefing/projection.

**Предлагаемая правка:** единая atomic terminalization transaction для FINISHED/ABANDONED с явно перечисленными различиями.

### G-7. Idempotency semantics не определены для mutations — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`: evidence имеет `idempotency key`; `wiki/flows/continuation.md`: «idempotency keys защищают от дублей».

**Почему дефект:** нет scope, same-key/different-payload поведения и cached response; требования не покрывают review, placement submit, finish и compound `start --abandon-active`. Потерянный ответ и retry с новым key могут бросить уже новую сессию.

**Предлагаемая правка:** общий CommandEnvelope; scoped unique key + payload hash; identical retry возвращает прежний результат, mismatch — стабильную ошибку.

### G-8. Два агента обходят idempotency разными keys — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/continuation.md`, «Решения этого flow»: «Lease/блокировки сессий в MVP не вводятся» и «idempotency keys защищают от дублей».

**Почему дефект:** два агента могут одновременно resume и отправить разные outcomes одной review-цели. Transport idempotency не решает semantic conflict. Это реалистично именно при заявленной сменяемости Codex/Claude.

**Предлагаемая правка:** без lease использовать optimistic session revision, unique terminal outcome per assignment и append-only correction protocol.

### G-9. Crash между attempt и review оставляет непочинимый record — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/flows/session.md`, диаграмма последовательно вызывает `attempt record` и `review result`; finish отвергает «нефинализированный attempt».

**Почему дефект:** resume показывает attempts, но ни state machine, ни finalize/recover command не определены.

**Предлагаемая правка:** atomic attempt+review command либо явная Attempt machine и idempotent finalize/recover.

### G-10. Streak и интервалы не имеют календаря ученика — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §7: интервалы заданы в «днях»; §8: streak — «подряд идущих дней с практикой».

**Почему дефект:** UTC instant не определяет learner-day; не решены DST, смена зоны и практика в 23:59/00:01. Для review «день» может означать elapsed 24h, для streak — local date.

**Предлагаемая правка:** решить правило: UTC instants + IANA timezone; отдельно elapsed review durations и local-calendar streak dates, включая смену зоны.

## H. Informal-слой — НАХОДКИ

### H-1. Informal Online Competence не отделена от CEFR машинно — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §5: «не повышает CEFR-уровни напрямую» и «может засчитываться в writing и transfer»; `wiki/product/lexical-system.md`, §3b повторяет оба правила.

**Почему дефект:** нет scope/dimensions/coverage/cap отдельного профиля. Один evidence можно засчитать informal, writing, transfer и CEFR-темам; placement-item также создаёт обычное evidence. Запрет не исполним.

**Предлагаемая правка:** отдельный measurement contract Informal Online Competence; `contribution_scope`, component-level evidence и правила dedup/cap.

### H-2. `recognition_only` несовместим с общей lexical mastery — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §3: «recognition и production evidence раздельно» и «состояния — та же машина, что у тем»; §3b: `recognition_only`/`avoid` — «только на распознавание», но оценка проверяет «естественный ответ, перенос между регистрами».

**Почему дефект:** нет policy-specific required dimensions. Единица либо навсегда застрянет до MASTERED, либо scheduler потребует запрещённое production.

**Предлагаемая правка:** `assessable_dimensions`/`mastery_criteria` по usage policy; natural response только для разрешённого production.

### H-3. Старое упражнение обходит новый usage_policy — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/learning-model.md`, §9: банк сохраняет «версия policy» и «переиспользуется»; `wiki/modules/curriculum.md`, §5: `avoid`/`recognition_only` «не попадают в production-упражнения»; placement-формы фиксированы.

**Почему дефект:** банк не обязан хранить lexical refs/safety snapshot и не обязан повторно валидироваться. Item, созданный при `safe_to_use`, продолжит production после перехода в `recognition_only/avoid/obsolete`; то же возможно в placement.

**Предлагаемая правка:** lexical refs + safety snapshot; runtime cross-validation банка/manifests/assessment с active version; policy update инвалидирует несовместимые items.

### H-4. `context_dependent` не имеет enforcement semantics — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §3b: `usage_policy: ... context_dependent ...`; ограничения далее заданы только для `recognition_only` и `avoid`.

**Почему дефект:** агент может рекомендовать такую единицу в любом work/community/audience контексте, не нарушив MUST. `communities` — metadata, не правило допуска.

**Предлагаемая правка:** allowed/disallowed contexts, audience/register constraints и safe default: при несовпадении — recognition-only.

### H-5. Currency validator проверяет только наличие одного поля — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/product/lexical-system.md`, §3b требует `first_observed_at`, `last_verified_at`, currency и «источник/сообщество»; `wiki/modules/curriculum.md`, §5 валидирует только «`meme_template` без нейтрального объяснения или `currency`».

**Почему дефект:** item без дат, источника и community проходит обязательную validation; пример дополнительно использует недопустимое `stable`.

**Предлагаемая правка:** единая schema и validation полного provenance/currency набора.

### H-6. Никто не отвечает за актуальность мемов — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §2: living layer «добавляются через `maintain-english-curriculum` workflow»; §4 публикует `LEXICAL_ITEM_ADDED`.

**Почему дефект:** описано только добавление. Не решены owner, cadence/TTL, evidence для reverification, переходы `current → dated → obsolete` и последствия для reviews/production.

**Предлагаемая правка:** отдельный OPEN о владельце, TTL по типам, update event и поведении stale items.

## I. Данные и лицензии — НАХОДКИ

### I-1. Режим использования `wordfreq` не выбран до импорта — `BLOCKER`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §3: `wordfreq` даёт «численные частоты»; «файл `ATTRIBUTIONS.md` в корне репо с цитированиями появляется вместе с первым импортом данных».

**Почему дефект:** спека не предписывает CSV и потому ещё не нарушает лицензию, но слово «импорт» не выбирает между pinned runtime/build-time use и распространяемым производным dataset. Для наиболее очевидного CSV-экспорта upstream прямо пишет: “No. The CSV format does not have any space for attribution or license information…”. Корневой `ATTRIBUTIONS.md` сам по себе не определяет, как notices останутся связаны с производным артефактом. См. [wordfreq README, license/export section](https://github.com/rspeer/wordfreq#can-i-convert-wordfreq-to-a-more-convenient-form-for-my-purposes-like-a-csv-file).

**Предлагаемая правка:** до П.4 выбрать режим: pinned runtime/build-time query без массового экспорта либо отдельно спроектированный redistributable derivative с provenance/license рядом с данными и юридической проверкой.

### I-2. CC BY-SA сведена к citation/ATTRIBUTIONS — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §3: «attribution; производные данные при публикации — CC BY-SA» и «файл `ATTRIBUTIONS.md` в корне репо с цитированиями появляется вместе с первым импортом данных».

**Почему дефект:** контракт не фиксирует author/copyright/license/disclaimer notices, ссылку на материал и лицензию, indication of changes и ShareAlike boundary для производной curriculum. Эти элементы нужны для воспроизводимой реализации условий; см. [CC BY-SA 4.0 §3](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en#s3a).

**Предлагаемая правка:** data-license manifest, граница лицензируемого dataset, notices, transformations и license text рядом с распространяемым артефактом.

### I-3. Source provenance не воспроизводима — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §5: validator ловит «импортированную единицу без attribution-меты»; schema этой меты отсутствует.

**Почему дефект:** не pin-ятся exact versions/artifacts/checksums NGSL, NAWL, BSL, CEFR-J и wordfreq; одна запись может иметь несколько источников с разными условиями. Импорт невозможно повторить или проаудировать.

**Предлагаемая правка:** `SourceArtifact {id, exact_version, url, retrieved_at, sha256, license, attribution, notices}` и `source_refs + transformations` на каждой записи.

### I-4. `Business SL`/`BSL` — неоднозначное имя источника — `MINOR`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`: `Business SL`; `wiki/OPEN.md`: `BSL`.

**Почему дефект:** без полного имени/версии импортёр может выбрать другой список.

**Предлагаемая правка:** везде `Business Service List (BSL), exact version`.

### I-5. Роль Reddit/Twitter в `wordfreq` неоднозначна — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §3: «численные частоты; присутствие в Reddit/Twitter для informal».

**Почему дефект:** фраза может означать только наличие Reddit/Twitter среди upstream corpora либо обещать queryable per-domain presence. Документированный API агрегирует домены в общий score; это вывод из [описания API и источников upstream](https://github.com/rspeer/wordfreq#usage). Snapshot около 2021 года в любом случае не доказывает текущую currency.

**Предлагаемая правка:** решить и записать роль: только stable-core aggregate frequency либо отдельный разрешённый источник/human verification для forum presence и currency.

### I-6. Provenance living layer не является правом копирования — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/modules/curriculum.md`, §2: «living layer — мемы, сленг и форумные единицы, встреченные во время обучения; добавляются через `maintain-english-curriculum` workflow с provenance»; §5 требует ловить «импортированную единицу без attribution-меты».

**Почему дефект:** URL и attribution не задают rights basis для текста forum post/example и не решают ToS/личные данные.

**Предлагаемая правка:** решить, хранится ли только короткая единица + собственный paraphrase или допустимы excerpts; задать `rights_basis`, source kind, quote limit и quarantine.

## J. Полнота OPEN — НАХОДКИ

### J-1. Единый реестр уже не един — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/OPEN.md`, §Открытые содержит только OPEN-1/2/3; §Решённые содержит OPEN-6; `wiki/product/lexical-system.md`, §6: «**OPEN-6**: frequency source и лицензирование лексических данных → блокирует финализацию 0.3 и отбор П.4».

**Почему дефект:** текущие документы не позволяют определить реальный gate П.4/0.3. Это прямое нарушение конституции OPEN.

**Предлагаемая правка:** синхронизировать статус OPEN-6 и завести отдельный unresolved license/import вопрос, а не возвращать молча старую формулировку.

### J-2. Найденные unresolved вопросы отсутствуют в OPEN — `MAJOR`

**Файл и раздел → точная цитата:** `wiki/OPEN.md`, вводное правило: «Продуктовые развилки и нерешённые вопросы»; в открытой таблице есть только scoring formula, Obsidian structure и integration.

**Почему дефект:** ни одна из следующих независимых развилок/неполных контрактов не зарегистрирована:

1. ownership classification, semantic dedup, evidence independence/multi-credit и CEFR coverage;
2. ABANDONED eligibility, pending outcomes, re-entry interruption и terminalization derivatives;
3. Attempt lifecycle и ownership/schema summary;
4. pinning curriculum/policies, deprecation replay, split/merge и orphan refs;
5. placement lifecycle/resume/reuse/cooldown и статус self-assessment;
6. confidence policy и placement ceiling;
7. mutation idempotency и optimistic concurrency двух агентов;
8. learner timezone/day semantics;
9. Informal Online Competence scale, CEFR contribution scope и safety enforcement;
10. `context_dependent` и currency owner/TTL/update;
11. wordfreq usage mode, CC BY-SA boundary, source pinning и living-layer rights;
12. exercise-bank promotion/invalidation;
13. XP exactly-once и определения Learning Score/Tutor Compliance Score.

**Предлагаемая правка:** добавить отдельные OPEN rows с блокируемыми контрактами; численные части можно связать с OPEN-1, но не прятать там семантические решения.

### J-3. Граница OPEN-1 не определена — `QUESTION`

**Файл и раздел → точная цитата:** `wiki/OPEN.md`: «OPEN-1 | Точная scoring-формула и thresholds»; `wiki/product/learning-model.md` использует также Learning Score, Tutor Compliance Score, confidence и Informal Online Competence без формул/шкал.

**Почему дефект:** неясно, покрывает ли OPEN-1 только Mastery/Retrievability или все агрегаты. Молчание позволит объявить метрики реализованными с произвольной семантикой.

**Предлагаемая правка:** пользователь должен определить scope OPEN-1 либо разделить scoring, confidence, informal и compliance на отдельные вопросы.

## 3. Вердикт по шести документам

| Документ | Вердикт | Основание |
|---|---|---|
| `wiki/product/learning-model.md` | **FAIL** | BLOCKER: semantic replay/coverage (C-3/C-4), неверная topic machine (D-1), пустой mastery contract (E-1) |
| `wiki/product/lexical-system.md` | **FAIL** | BLOCKER: Informal↔CEFR boundary отсутствует (C-5/H-1); дополнительно неполная lexical machine |
| `wiki/modules/curriculum.md` | **FAIL** | BLOCKER: version/deprecation replay (G-2/G-3), невыбранный wordfreq usage/distribution mode (I-1) |
| `wiki/flows/session.md` | **FAIL** | BLOCKER: client classification (A-1/C-1), ABANDONED exploit (C-2/G-4), circular finish (E-2) |
| `wiki/flows/continuation.md` | **PASS-with-findings** | Нет локального BLOCKER; MAJOR: untrusted notes и concurrent agents не покрыты idempotency (C-8/G-8) |
| `wiki/flows/placement.md` | **FAIL** | BLOCKER: отсутствует placement lifecycle/recovery/idempotent terminal submit (G-1) |

`FAIL` означает запрет строить зависимый контракт/код до снятия хотя бы указанных BLOCKER; это не требование перепроектировать архитектуру.

## 4. Проверено, ок

- Приоритет источников соблюдён: расхождения брифа с current wiki, помеченные `[PD-2026-07-19]`, не записаны как дефекты.
- Text-only MVP последовательно исключает listening/speaking; informal chat не маскируется под speaking.
- Prerequisites, gates, overdue backlog, re-entry и placement остаются рекомендациями, а не learner locks.
- Обычный обрыв учебной session после уже записанного attempt частично покрыт incremental recording + resume; дефект относится к промежутку до записи, раздельному attempt/review и placement.
- Намерение ограничить rubric contribution cap-ом и повторяемостью согласовано между learning-model и placement; дефект — в admissibility/independence, а не в отсутствии самого cap.
- `ABANDONED` явно сохраняет уже записанное evidence; дефект — отсутствие completeness/eligibility и согласованной terminalization.
- Objective placement sections отданы коду, writing — versioned rubric; generated placement items запрещены.
- Stable IDs, уже использованные в evidence, нельзя физически удалить; дефект — ссылки до evidence и replay semantics deprecation.
- `avoid/recognition_only` одинаково запрещены для production в lexical-system и curriculum; дефект — stale bank/assessment и policy-specific mastery.
- Stable core / living layer / learner lexicon согласованы по владению данными.
- Условия CEFR-J A1–B2 и отдельная CC BY-SA лицензия Octanove C1/C2 подтверждаются [primary repository](https://github.com/openlanguageprofiles/olp-en-cefrj#terms-of-use); CC BY-SA для [NGSL](https://www.newgeneralservicelist.com/new-general-service-list), [NAWL](https://www.newgeneralservicelist.com/new-academic-word-list) и [BSL](https://www.newgeneralservicelist.com/business-service-list) также подтверждена.
- Формулировка «Apache-2.0 code / CC BY-SA data / snapshot ~2021» для wordfreq в целом соответствует [upstream](https://github.com/rspeer/wordfreq#license); дефект — способ импорта, полнота notices и заявленный per-domain signal.
- Импортированных dataset-файлов в checkout не найдено; отсутствие `ATTRIBUTIONS.md` сейчас не нарушает условие «вместе с первым импортом».
- Obsidian vault последовательно остаётся projection, а не scoring source.
