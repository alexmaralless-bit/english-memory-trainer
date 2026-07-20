# Red-team ревью контракта 0.12 Learning Control

Дата: 2026-07-20  
Предмет: `wiki/modules/control.md` и его стыки с принятым каноном.  
Метод: только документы; факты о будущей реализации не предполагаются.

## Резюме

Вердикт — **FAIL**: найдено 5 BLOCKER, 10 MAJOR, 1 MINOR и 2 QUESTION.

Топ-5:

1. `SessionBudget` не образует исполнимого разбиения: для `important/normal/maintenance` review нет корзины, `integration` и `learner_choice` пересекают оси «новое/review», а формулы долей и правила переполнения не определены.
2. Жизненный цикл композиции противоречив: `compose_session` публикует событие, но `session next` нормативно read-only; при этом `session start` не вызывает control и Session Manifest не несёт control-policy/revision композиции.
3. Control-policy требуется пинить, но такой policy нет ни в kernel policy registry, ни в Session Manifest. Replay/resume под прежней политикой невыполним.
4. `UrgencyClass` не является тотальным классификатором: точное правило есть только для `critical`, остальные классы заданы стрелками; один из stake-сигналов отсутствует у `Topic`, хотя `LearningTarget = Topic | LexicalItem`.
5. OPEN-27 утверждает, что числовые дефолты и диапазоны существуют, но собственных значений 0.12 в каноне нет. Это отсутствие исполнимой policy, а не отсутствие калибровки.

## BLOCKER

### CTRL-1. Бюджет не задаёт ни полное разбиение шагов, ни проверяемые доли — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: «`buckets{critical_review, growth, integration, learner_choice}`»; §4.2: «`critical_review`, `growth` (новый материал), `integration` (новое поверх старого), `learner_choice`. У повторений есть **максимальная** доля, у нового материала — **минимальная**»; §4.1: «доля нового материала не опускается ниже `new_material_min_share`».

**Почему дефект:** в бюджете нет корзины для принятых в сессию review классов `important`, `normal` и `maintenance`. Одновременно `integration` по определению содержит и новое, и старое, а `learner_choice` может содержать любой тип: корзины не являются взаимоисключающими и из них нельзя однозначно вычислить `review_share` и `new_material_rate`. Не определены `sum(buckets) = total_minutes`, запрет двойного учёта, поведение шага, который не помещается целиком, округление, минимальная допустимая длительность и конфликт `new_material_min_share` с `review_max_share`. Не определено и само «новое»: `knowledge_state=NEW` не подходит, потому что объяснение/предъявление не является evidence и цель может оставаться NEW после нескольких показов. Две реализации законно соберут разные занятия и обе объявят инварианты выполненными.

**Предлагаемая правка:** задать одну нормативную модель: либо непересекающиеся admission-корзины, покрывающие каждый шаг ровно один раз, плюс независимые labels `is_new`/`is_review`, либо явную матрицу пересечений. Определить формулы обеих долей, session-level критерий first exposure, порядок allocation/backfill, rounding и поведение для неразрешимого бюджета.

### CTRL-2. Не определён атомарный жизненный цикл `compose_session`; он конфликтует с read-only `session next` — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §3: «`compose_session(session_id)` … собирает набор шагов» и «`SESSION_COMPOSED` … состав занятия с бюджетом и trace»; там же: «алгоритм выбора следующего шага — `compose_session` здесь». `wiki/modules/cli.md`, §5: «`trainer session next` … Мутирует: **нет**»; §4.4: «команды, помеченные `mutating: false`, не изменяют состояние даже косвенно». `wiki/modules/lessons.md`, §5: «`start(duration?, provider)` … создаёт сессию + Session Manifest»; `wiki/flows/session.md`, сценарий: `session start` сразу возвращает Manifest с review-целями и рекомендациями.

**Почему дефект:** если `session next` вызывает `compose_session`, read-only команда публикует событие и сохраняет trace. Если композиция выполняется при `session start`, ни lessons API, ни Manifest, ни межмодульная UoW этого не требуют. Не определены момент композиции, idempotency key, допустимое число `SESSION_COMPOSED` на сессию, revision/recomposition после evidence или сигнала, связь `decision_id ↔ step_id` и поведение при crash между стартом и композицией. Поэтому закрытие владельца `session next` пока номинальное: вызываемый протокол отсутствует.

**Предлагаемая правка:** выбрать один lifecycle. Например: lessons в UoW старта вызывает control, пинит policy, сохраняет `composition_revision=1` и Manifest; `session next` только читает следующий сохранённый шаг. Либо сделать `session next/replan` мутирующей идемпотентной командой с CAS, revision и событием. В обоих вариантах определить schema `SESSION_COMPOSED`, step/decision IDs, replan triggers и crash recovery.

### CTRL-3. Control-policy нельзя pin/replay по действующему kernel-контракту — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.1: «изменение политики пинится и действует вперёд; replay идёт по pinned-версии»; §4.6: trace содержит «pinned-версии политик». `wiki/platform/foundation.md`, §3.6: «реестр … policy (`curriculum`, `scoring`, `scheduler`, `generation`, `rubric`)». `wiki/modules/lessons.md`, §4b: `pinned_versions` содержит «curriculum, scoring, scheduler, generation, rubric».

**Почему дефект:** версии composition/admission/saturation/availability policy не имеют registry key, retention rule и места в Session Manifest. После активации новых параметров resume или recomputation той же сессии может выбрать другой шаг; `PinnedPolicyUnavailable` для control недостижим, потому что pin никогда не создан. `DecisionTrace` с абстрактным `pinned_policy_versions{}` не исправляет отсутствие источника и момента захвата версии.

**Предлагаемая правка:** добавить именованную `control_policy` в foundation registry и Session Manifest, описать её immutable snapshot/retention и синхронный resolve до commit. Зафиксировать, какая active safety-version использована для live exclusion/replacement, не превращая safety-overlay в pinned policy.

### CTRL-4. `classify(targets)` не является тотальной детерминированной функцией — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.3: «`critical` требует риска И ставки» с полной таблицей; затем «Риск без ставки → `important`/`normal`; ставка без риска → `maintenance`» и «`important` → `normal` → `maintenance` (формально due, прогноз успеха высок) → `deferrable`». Там же stake: «`curriculum_priority_band` ∈ {CORE, HIGH}». `wiki/glossary.md`: «`LearningTarget` … `Topic | LexicalItem`». `wiki/modules/curriculum.md`, §2: `curriculum_priority_band` перечислен у `LexicalItem`, но отсутствует в schema `Topic`.

**Почему дефект:** точные взаимоисключающие predicates и precedence определены только для `critical`. «Риск без ставки» всё ещё оставляет два результата; «ставка без риска → maintenance» конфликтует с последующим требованием, что maintenance формально due; `normal` не имеет правила вообще; `deferrable` пересекается с maintenance. Не задан candidate universe: только due backlog или все targets. Для Topic один из нормативных stake-сигналов не существует; «prerequisite нескольких ближайших тем» не определяет `нескольких` и зависит от ещё не выбранного growth-набора. Фраза «внутри класса не более четырёх величин» не называет эти величины. Одинаковый вход не гарантирует одинаковый класс и порядок.

**Предлагаемая правка:** дать тотальную ordered decision table для каждого допустимого сочетания risk/stake/due/saturation/relevance с единственным результатом и явным fallback. Определить stake для обоих вариантов LearningTarget, источник/порог «ближайших тем», candidate universe и точный tuple внутри каждого класса.

### CTRL-5. OPEN-27 смешивает «не откалибровано» с «не существует» — BLOCKER

**Файл и раздел → точная цитата:** `wiki/OPEN.md`, OPEN-27: «Реализацию не блокируют (**все имеют дефолт и диапазон**)»; `wiki/modules/control.md`, §7: «числовые дефолты всех параметров … авторские и не откалиброваны»; §4.7 показывает только чужой пример `scheduler.target_recall default: 0.90`.

**Почему дефект:** в каноне и данных нет ни одного конкретного default/range для `new_material_min_share`, `review_max_share`, `critical_floor`, `starvation_cap` или `expected_minutes_by_step_type`. Также не названы параметры и значения для saturation windows, diversity quotas, observed-divergence, starvation growth и alert thresholds. Поиск по канону находит только имена, не значения. Реализация должна либо выдумать продуктовые числа, либо не сможет классифицировать и заполнить бюджет. Это та же принципиальная граница, уже пойманная в 0.4: калибровку можно отложить, исполнимую структуру и конкретную policy-version — нельзя.

**Предлагаемая правка:** создать versioned control-policy с полным закрытым schema и конкретными авторскими defaults для каждой ветки; каталог должен ссылаться на неё. OPEN-27 оставить только про эмпирическую калибровку этих уже существующих значений и честно перечислить весь набор параметров.

## MAJOR

### CTRL-6. Для saturation и части метрик нет наблюдаемого факта реального предъявления — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.4: saturation использует «число предъявлений в окне, серия независимых успехов, однообразие контекстов, давность последней проверки на transfer»; §6 consumed events: только `REVIEW_SCHEDULED`, `OVERDUE_AT_RISK_TRIGGERED`, `STATE_TRANSITION`, `SESSION_STARTED`/`FINISHED`. `wiki/modules/evidence.md`, §3 публикует `ATTEMPT_RECORDED`/`EVIDENCE_ADDED`/`REVIEW_OUTCOME`; `wiki/modules/control.md` их не потребляет.

**Почему дефект:** `SESSION_COMPOSED` — план, не факт доставки. В abandoned или перепланированной сессии выбранный шаг мог не показываться; считать его exposure нельзя. И наоборот, успешность, independence и context находятся в evidence, события которого отсутствуют во входном контракте control. Нельзя корректно rebuild-ить `SaturationState`, calibration error и familiar-vs-new-context gap.

**Предлагаемая правка:** определить единственный факт delivery (`STEP_PRESENTED`/`ITEM_EXPOSED`) с stable exposure/step ID и добавить необходимые evidence/outcome events либо публичный event-sourced read API. Зафиксировать distinction planned/issued/completed и reducer/checkpoint для SaturationState.

### CTRL-7. Обещанная защита от бесконечного откладывания логически не обеспечена — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.2: «От бесконечного откладывания защищает §4.4»; §4.4: priority растёт, но «Рост ограничен `starvation_cap`: периферийная единица не должна обгонять базовый навык».

**Почему дефект:** capped bonus не даёт upper bound ожидания. При постоянном притоке целей выше cap периферийная цель может проигрывать бесконечно; critical overflow при этом нормативно всегда возвращается в backlog. Контракт утверждает гарантию, которой механизм не предоставляет.

**Предлагаемая правка:** либо убрать обещание защиты и назвать starvation telemetry без fairness guarantee, либо добавить проверяемую fairness-политику: резерв, максимальное системное откладывание, escalation/learner choice или явное признание infeasible backlog.

### CTRL-8. `STARTED → FINISHED` не измеряет фактическое учебное время — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.2: «длительность сессии целиком движку известна (`STARTED`/`FINISHED`)» и используется против суммы expected minutes; §4.5: движок наблюдает «длительность сессии». `wiki/modules/lessons.md`, §2: сессия может оставаться `IN_PROGRESS`, возобновляться после потери чата и стать stale только через `stale_session_days` (default 7).

**Почему дефект:** разность timestamp'ов включает сон, работу, потерю чата и паузы между агентами. Это wall-clock span, а не active learning time. Подстройка `expected_minutes_by_step_type` по такому сигналу систематически испортит таблицу и нарушает собственную «границу наблюдаемости» control.

**Предлагаемая правка:** не считать elapsed session span фактической длительностью. Использовать planned duration и completion/abandon signals либо ввести наблюдаемые active segments; явный self-report длительности хранить с provenance как self-report, а не engine-observed fact.

### CTRL-9. LearnerControlSignal не способен выразить собственные виды сигналов — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: `LearnerControlSignal` имеет только «`kind`, `target_id?`, `created_at`»; §4.5 перечисляет `not_relevant_now`, `snooze`, `prefer_different_context` и availability correction.

**Почему дефект:** `snooze` не содержит `until`/duration, `prefer_different_context` — желаемого/исключённого контекста, `not_relevant_now` — срока или способа отмены. Нет precedence, expiry, semantic dedup и lifecycle proposal→accept/reject для коррекции availability. Разные реализации будут трактовать один сохранённый сигнал как постоянный, одноразовый или с произвольным TTL.

**Предлагаемая правка:** сделать discriminated union payload по `kind`, задать обязательные поля, expiry/cancel/supersede, precedence и idempotency identity каждого сигнала.

### CTRL-10. «Провал пробы лишь снимает гипотезу» противоречит обычному scoring — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.1: «неуспех пробы не штрафует» и «он лишь снимает гипотезу»; там же: «не понижает состояние сверх обычных правил». `wiki/modules/scoring.md`, §3: подтверждённый `REGRESSION` переводит `ACTIVE → LEARNING`, `MASTERED → ACTIVE`.

**Почему дефект:** «обычные правила» могут понизить состояние, поэтому одновременно истинными не являются «лишь снимает гипотезу» и «обычные последствия». В evidence нет origin/mode `control_probe`, который позволил бы scoring отличить добровольно запрошенную усложнённую пробу от проверки на ожидаемом уровне. Не определён consumer `PROBE_REQUESTED`, выбор difficulty/context, бюджет и dedup проб.

**Предлагаемая правка:** выбрать семантику. Если probe неотрицательный diagnostic challenge — зафиксировать отдельный origin/mode и scoring cap/no-negative rule. Если это обычное evidence — убрать «лишь»/«не штрафует» и объяснить, что провал может дать REGRESSION. Описать consumer и lifecycle запроса.

### CTRL-11. Availability не выражает обещанные календарные ограничения, а специальные modes недостижимы — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: declared profile — только `sessions_per_week, typical_minutes`; §4.5 обосновывает гибрид тем, что чисто выведенная модель «не знает о запланированном перерыве» и обещает перенос «на ближайшее занятие». §2 допускает `maintenance`/`re_entry` только «по явному выбору». `wiki/modules/lessons.md`, §5: `start(duration?, provider)` не принимает mode; CLI `session start` также его не имеет.

**Почему дефект:** одинаковые `3 sessions/week` описывают и занятия через день, и три занятия подряд; профиль не знает next availability, weekdays или blackout, поэтому не может знать «ближайшее занятие» и запланированный перерыв. При этом нет команды/API, которым ученик явно выбирает `maintenance` или `re_entry`; нормативное исключение из new-min недостижимо.

**Предлагаемая правка:** добавить минимальную календарную форму (`next_available_at`/cadence + exceptions) либо сузить обещание до статистического rate. Добавить mode в `session start`/отдельную идемпотентную команду и определить precedence между `--duration`, declared typical, observed и policy default.

### CTRL-12. Детерминизм композиции заканчивается до фактического выбора набора и порядка — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.3: «внутри класса не более четырёх величин, затем детерминированный tie-break»; §4.4: «квоты разнообразия» и чередование modes; §4.2: budget в expected minutes.

**Почему дефект:** не названы четыре величины, порядок их сравнения, алгоритм packing/backfill, единица/precision минут, rounding, порядок применения diversity constraints и определение «почти одинаковых» единиц. Даже после тотального classifier два детерминированных алгоритма — greedy и best-fit — выберут разные наборы из тех же кандидатов; порядок применения quotas даст разные step sequences.

**Предлагаемая правка:** зафиксировать canonical selection pipeline: classify → total sort → deterministic admission/packing → quota repair/backfill → final sequence, с точными ключами, integer seconds или Decimal-контекстом и tie-break на каждом шаге.

### CTRL-13. Минимальные метрики названы, но не определены как `PolicyMetric` — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.8: «метрика — сущность `PolicyMetric` с формулой, окном и списком наблюдаемых параметров»; затем только список имён и аварии: «`review_share` устойчиво у максимума», «`new_material_rate` близок к нулю несколько занятий подряд».

**Почему дефект:** для перечисленных MVP MUST отсутствуют formula/window/observes: calibration error может быть Brier, log-loss или binning; success label и момент прогноза не заданы; `backlog age`, `lapse`, familiar/new context не имеют cohort semantics. «Устойчиво», «близок» и «несколько» — скрытые tunables без строк каталога. Нельзя реализовать одинаковые метрики и CI-проверить аварии.

**Предлагаемая правка:** дать versioned registry rows для каждой обязательной метрики: input events/fields, cohort, formula, missing-data rule, window, Decimal/rounding и alert enter/exit thresholds.

### CTRL-14. Межмодульная граница learner/control не отражена в dependencies и API входа — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §3 говорит о «композиции curriculum + scheduler + learner», §4.5 использует `learner_relevance`, но §6 `depends on` не содержит learner. `wiki/modules/learner.md`, §4: `goals[]` и linked personal lexicon «повышают `learner_relevance` в control».

**Почему дефект:** owner-спека learner объявляет вход планирования, а control не объявляет dependency, событие или snapshot, по которому его читает. При архитектурном allowlist это либо запрещённый import, либо прямое чтение чужой таблицы. Кроме того, Gate contract говорит, что решение, когда предлагать gate, принадлежит control (`gates.md` §6), но control не имеет такого результата в composition schema.

**Предлагаемая правка:** добавить явный learner API/snapshot во вход `compose_session`, pin/capture нужных значений в `SESSION_COMPOSED`, обновить dependency. Определить, входит ли gate recommendation в planned-step union, либо убрать назначение владельца у gates.

### CTRL-15. OPEN/roadmap объявляют закрытым то, что контракт ещё не специфицировал — MAJOR

**Файл и раздел → точная цитата:** `wiki/roadmap.md`, 0.12: `done-with-open`, «остаточный OPEN-27»; `wiki/OPEN.md`, owner matrix: «Композиция `session next` — закрыто»; `wiki/modules/control.md`, §7 перечисляет только OPEN-26/27/14.

**Почему дефект:** CTRL-1…CTRL-4 и CTRL-6 — не численная калибровка, а schema/lifecycle/event/pinning semantics. У них нет carrier row, acceptance condition и зависимости реализации. Статус `done-with-open` с единственным численным долгом создаёт ложную разблокировку вертикального среза.

**Предлагаемая правка:** после триажа либо исправить контракт и соседей, либо завести отдельные OPEN с владельцами и зависимостями; до снятия BLOCKER не считать owner/protocol `session next` закрытым.

## MINOR

### CTRL-16. Новые сущности 0.12 не заведены в нормативный glossary — MINOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2 вводит `SessionBudget`, `UrgencyClass`, `SaturationState`, `AvailabilityProfile`, `LearnerControlSignal`, `DecisionTrace`, `TunableParameter`, `PolicyMetric`. `wiki/README.md`, правило 2/правила ведения: «Словарь … определяется в одном месте» и «Новый термин/сущность/состояние сначала вводится в glossary».

**Почему дефект:** поиск по `wiki/glossary.md` не находит ни одного из этих имён. Их смысл сейчас локальный, а `DecisionTrace`, availability и urgency уже используются соседями/CLI.

**Предлагаемая правка:** добавить короткие единственные определения публичных сущностей/enum в glossary; детали поведения оставить в control.

## QUESTION

### CTRL-Q1. Должна ли система ограничивать приток нового по прогнозируемому review debt? — QUESTION

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.2: critical overflow всегда переносится, protected new share не занимается; §4.8: долговая спираль только вызывает сообщение.

**Почему вопрос:** при постоянной доступности ученика и фиксированной доле нового система может создавать будущий review debt быстрее, чем обслуживает. Текущий контракт ограничивает спам внутри одной сессии, но не стабилизирует систему между сессиями. Это продуктовая развилка: автоматически снижать admission нового, только предлагать maintenance/увеличение времени или сознательно допускать растущий backlog.

**Предлагаемая правка:** принять [PD] и определить хотя бы одну измеримую capacity/debt метрику и обязательную реакцию. Не менять интервалы забывания ради удобства.

### CTRL-Q2. Кто применяет калибровку параметра чужой policy? — QUESTION

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.7: «значения живут в pinned policy у своего владельца»; §3/§5: control публикует `CALIBRATION_APPLIED` и владеет `trainer calibration … apply`.

**Почему вопрос:** применение `scheduler.target_recall` или scoring threshold означает создание/активацию новой policy версии у scheduler/scoring. Неясно, имеет ли control право мутировать чужой aggregate, делегирует ли owner API или только фиксирует подтверждение. Самостоятельное применение создало бы второго владельца policy.

**Предлагаемая правка:** оставить control владельцем proposal/confirmation workflow, а activation делегировать owner API с CAS и owner event; либо принять другое явное owner-решение. Связать события correlation/causation и одну UoW там, где требуется атомарность.

## Проверено, ок

- `due` корректно объявлен кандидатом, а не правом на место в сессии; overdue backlog не превращён в блокировку новых тем.
- Availability и learner signals явно запрещено использовать как evidence или прямой вход scoring; граница знания сохранена.
- Safety-overlay использует active policy, а не pinned safety; это согласуется с curriculum/foundation.
- Ограничение автономии калибровки до propose-confirm разумно и не создаёт скрытого online-learning при `n=1`.
- Owner-матрица правильно относит budget/admission/saturation/telemetry к бизнес-модулю control, а не к platform/kernel.
- Исправленный scheduler tuple начинается с риска утраты и имеет `target_id + dimension_id` как стабильный tie-break; 0.12 не вернул прежний `overdue_days-first`.
- Решение не делать hard prerequisites и не занимать protected new share critical backlog соответствует принятым [PD]; находки выше требуют сделать эту политику исполнимой, а не отменить её.

## Вердикт

**FAIL** — в `wiki/modules/control.md` есть BLOCKER уровня schema/lifecycle/pinning. Контракт нельзя считать готовым к реализации только с OPEN-27 про калибровку: сначала нужны исполнимый бюджет, тотальный classifier, атомарный протокол композиции и control-policy pinning.
