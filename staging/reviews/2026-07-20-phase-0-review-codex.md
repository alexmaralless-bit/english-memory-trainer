# Сквозное red-team ревью спек фазы 0

**Дата:** 2026-07-20  
**Роль:** внешний семантический ревьювер  
**Объект:** нормативные контракты `0.1–0.9`, их flows, `wiki/glossary.md`, `wiki/OPEN.md`, `wiki/roadmap.md` и принципы `wiki/README.md`  
**Не проверялось:** реализация и факты о коде. Файлы канона не изменялись.

## Итог

**Вердикт по фазе 0: `FAIL`.** Найдены 4 `BLOCKER`, 7 `MAJOR`, 3 `MINOR` и 3 `QUESTION`.

Фаза не даёт однозначной и достижимой цели для вертикального среза: терминальный ReviewOutcome нельзя записать через единственную agent-facing границу; state machine одновременно задаёт и отрицает вход в `AT_RISK` по `REGRESSION`; новый обязательный параметр `transparency` отсутствует у владельца lexical scoring; три объявленных MVP-модуля не имеют собственных контрактов и owner-строк.

### Топ-5

1. **P0-1, BLOCKER:** `AT_RISK` от подтверждённого `REGRESSION` заявлен, но тотальная таблица переводит `ACTIVE → LEARNING` и `MASTERED → ACTIVE`; ветви входа в `AT_RISK` нет.
2. **P0-2, BLOCKER:** `FINISHED` требует закрытых ReviewAssignment, но CLI не предоставляет `close_review`; одновременно evidence ошибочно говорит, что `finish` сам закрывает pending.
3. **P0-3, BLOCKER:** lexical contract и glossary требуют профиль по `(type, transparency, usage_policy)`, а scoring — только по `type/usage_policy`; mastery непрозрачных единиц не определена.
4. **P0-4, BLOCKER:** `learner`, `audit`, `gates` объявлены отдельными MVP-модулями и владельцами команд, но их спек и owner-строк нет.
5. **P0-7, MAJOR:** memory обещает полный rebuild из event-store, хотя часть отображаемых сущностей foundation классифицирует как SQLite-authoritative и не rebuildable из событий.

## BLOCKER

### P0-1 — в state machine отсутствует заявленный переход `REGRESSION → AT_RISK`

**Файлы и разделы:** `wiki/modules/scoring.md` §3; `wiki/product/learning-model.md` §4; `wiki/glossary.md` «Knowledge state».

**Точные цитаты:**

> `ACTIVE | ... | REGRESSION(подтв.) → LEARNING`  
> `MASTERED | ... | REGRESSION(подтв.) → ACTIVE`  
> — `wiki/modules/scoring.md` §3, строки 39–45

> «`AT_RISK` возникает от подтверждённого REGRESSION или от события `OVERDUE_AT_RISK_TRIGGERED`»  
> — `wiki/modules/scoring.md` §3, строка 49

> `ACTIVE --> LEARNING: REGRESSION (подтверждён)`  
> `MASTERED --> ACTIVE: REGRESSION (подтверждён)`  
> — `wiki/product/learning-model.md` §4, строки 73–74

> «`AT_RISK` — подтверждённый REGRESSION или просрочка вышла за порог. Лёгкий/неподтверждённый regression опускает в `LEARNING`»  
> — `wiki/glossary.md`, строка 38

**Почему это дефект:** таблица объявлена тотальной, но не содержит ни одной regression-ветки в `AT_RISK`. При этом outcome enum содержит только один `REGRESSION`: поля, разделяющего «лёгкий» и «подтверждённый», нет. Один и тот же факт имеет два несовместимых нормативных результата. Replay не может выбрать переход без скрытой логики вне контракта.

**Предлагаемая правка:** оформить продуктовую развилку: либо `AT_RISK` возникает только из overdue-события и ссылки на regression удаляются, либо в outcome/policy вводится проверяемая разновидность regression и для неё добавляются явные строки тотальной таблицы. Синхронно обновить learning model и glossary.

**Severity:** `BLOCKER`.

### P0-2 — ReviewAssignment нельзя штатно закрыть через CLI; `finish` описан взаимоисключающе

**Файлы и разделы:** `wiki/modules/evidence.md` §§3, 4.3; `wiki/modules/lessons.md` §§4, 6; `wiki/modules/cli.md` §5; `wiki/flows/session.md`.

**Точные цитаты:**

> «`close_review(review_id)` — вычисление единственного ReviewOutcome»  
> — `wiki/modules/evidence.md` §3, строка 36

> «терминализация сессии — finish/abandon закрывает все pending цели»  
> — `wiki/modules/evidence.md` §4.3, строка 63

> «FINISHED требует пустой pending-set ... Иначе finish отклоняется ... (это не авто-закрытие)»  
> — `wiki/modules/lessons.md` §4, строка 46

> CLI обучения содержит `attempt record` и `review due`, но не содержит `review close`/эквивалента  
> — `wiki/modules/cli.md` §5, строки 112–121

> «каждая review-цель к моменту finish имеет исход»  
> — `wiki/flows/session.md`, строка 82

**Почему это дефект:** CLI объявлен единственным agent-facing входом. Для due-review агент может записать attempts, но не может вызвать единственный явный trigger терминального ReviewOutcome. `finish` не спасает: owner-спека lessons прямо запрещает auto-close при `FINISHED`, тогда как evidence утверждает обратное. Сессия с ReviewAssignment может оказаться штатно незавершаемой; поведение реализации будет зависеть от того, какую спеку прочитал автор.

**Предлагаемая правка:** добавить в CLI и owner-спеки идемпотентную команду явного закрытия review (с session/review revision и engine-computed outcome). В evidence заменить «finish/abandon закрывает все pending» на согласованное правило: `finish` требует предварительно закрытого набора, `abandon` преобразует pending в `INSUFFICIENT_EVIDENCE`, если именно это принятое поведение.

**Severity:** `BLOCKER`.

### P0-3 — обязательная ось `transparency` не входит в scoring-профиль

**Файлы и разделы:** `wiki/product/lexical-system.md` §1a; `wiki/modules/curriculum.md` §§2, 5; `wiki/modules/scoring.md` §6; `wiki/glossary.md`.

**Точные цитаты:**

> «Разрешение профиля — по `(type, transparency, usage_policy)`»  
> — `wiki/product/lexical-system.md` §1a, строка 26

> «`opaque`: recognition — обязательный dimension, а controlled_production не может быть required»  
> — там же

> «Профиль разрешается по `(type, transparency, usage_policy)`»  
> — `wiki/modules/curriculum.md` §2, строка 103

> «LexicalMasteryProfile ... по `type`/`usage_policy`»  
> — `wiki/modules/scoring.md` §6, строка 113

**Почему это дефект:** scoring — владелец lexical mastery-profile по owner-матрице, но не определяет новую ось и precedence между `transparency` и `usage_policy`. Для `opaque + safe_to_use` curriculum запрещает required production, тогда как scoring добавляет production для `safe_to_use`. Валидатор и reducer могут принять разные профили; П.4c создаёт сущности, для которых переходы mastery не определены. В OPEN нет строки, честно откладывающей эту интеграцию.

**Предлагаемая правка:** сделать lookup/schema scoring тотальной по `(type, transparency, usage_policy)`, зафиксировать precedence ограничений (в частности, `opaque` и restrictive usage policy) и добавить validator/replay fixtures для всех конфликтных комбинаций.

**Severity:** `BLOCKER`.

### P0-4 — у MVP-команд и бизнес-правил отсутствуют контракты владельцев

**Файлы и разделы:** `wiki/README.md` принципы 2, 3, 5; `docs/design-direction.md` §4; `wiki/modules/cli.md` §5; `wiki/flows/continuation.md`; `wiki/OPEN.md` owner-матрица.

**Точные цитаты:**

> «Один модуль = одна спека `wiki/modules/<name>.md` ... modules: ... gates, ... learner, ... audit, storage»  
> — `wiki/README.md`, строки 38–42

> «Flow не владеет поведением — полное правило живёт в спеке модуля»  
> — `wiki/README.md`, строка 55

> `trainer status | learner`; `trainer gate begin | submit | evaluate | gates`; `trainer audit session | audit`  
> — `wiki/modules/cli.md` §5, строки 108, 121, 137

> continuation возлагает briefing на `learner`, а `AGENT_ATTACHED` — на `audit`  
> — `wiki/flows/continuation.md`, строки 77–81

**Почему это дефект:** файлов `wiki/modules/learner.md`, `audit.md`, `gates.md` нет; owner-матрица в OPEN также не назначает владельцев этим компонентам. При этом команды не помечены `[post-mvp]`, а lessons/scoring/memory зависят от briefing, XP/streak, audit obligations и gate pages. Не определены API, события, lifecycle, таблицы и инварианты. CLI здесь создаёт бизнес-контракт вместо владельца, что прямо запрещено конституцией. Дополнительно `trainer session next` объявлен за lessons, но отсутствует в public API lessons и не имеет алгоритма/владельца композиции curriculum+scheduler+learner.

**Предлагаемая правка:** продуктовая развилка: либо добавить named contracts и строки roadmap/owner-матрицы для `learner`, `audit`, `gates` (и определить владельца `session next`) до реализации вертикального среза, либо снять соответствующие команды и зависимости из MVP, пометив их `[post-mvp]`.

**Severity:** `BLOCKER`.

## MAJOR

### P0-5 — continuation требует notes и `AGENT_ATTACHED`, которых нет в API/событиях владельцев

**Файлы и разделы:** `wiki/flows/continuation.md` сценарии и derived contracts; `wiki/modules/evidence.md` §3; `wiki/modules/lessons.md` §5; `wiki/modules/cli.md` §5.

**Точная цитата:**

> «каждое подключение ... фиксируется событием `AGENT_ATTACHED`»; «session note при любой фиксации (`--note`)»; evidence обязан принимать/возвращать notes  
> — `wiki/flows/continuation.md`, строки 68–80

> Evidence API: `record_attempt`, `finalize_attempt/recover`, `close_review`, `record_observed`; published events не содержат notes  
> — `wiki/modules/evidence.md`, строки 34–38

> Lessons публикует `SESSION_STARTED / FINISHED / ABANDONED / SESSION_STALE_ABANDONED` и `ATTEMPT_STATE_CHANGED`, но не `AGENT_ATTACHED`  
> — `wiki/modules/lessons.md`, строки 64–71

**Почему это дефект:** flow сформулировал обязательства, но они не перенесены в module contracts, вопреки flow-first. Нет payload/schema notes, команды/флага, события подключения и его owner. Tutor Compliance и audit смены агентов не получают заявленного входа.

**Предлагаемая правка:** определить owner `AGENT_ATTACHED` и session notes, добавить их API/command/event schemas и trust boundary в соответствующие module contracts; затем сослаться на них из flow.

**Severity:** `MAJOR`.

### P0-6 — placement decline отсутствует в общем CLI и не имеет per-skill payload

**Файлы и разделы:** `wiki/flows/placement.md`; `wiki/modules/assessments.md` §§2, 4, 5; `wiki/modules/cli.md` §5; `wiki/glossary.md`.

**Точные цитаты:**

> `placement decline --self-assessment A2`  
> — `wiki/flows/placement.md`, строка 64

> «self_reported_level ... замещается измерением по каждому навыку»  
> — `wiki/flows/placement.md`, строка 76

> Assessments API/CLI содержит `decline(self_assessment?)` / `decline --self-assessment X`  
> — `wiki/modules/assessments.md`, строки 49, 60

> Общая CLI-поверхность перечисляет только `start | answer | submit | resume | abandon`  
> — `wiki/modules/cli.md`, строка 127

**Почему это дефект:** command registry, по которому валидируются skills, не содержит принятую MVP-команду. Кроме того, пример принимает один CEFR scalar, а канон требует per-skill state; не определено, означает ли `A2` broadcast, либо payload должен содержать четыре значения. Две реализации могут записать разные provisional estimates из одной команды.

**Предлагаемая правка:** добавить `placement decline` в CLI registry и зафиксировать versioned input schema для per-skill self-report. Если scalar broadcast допустим, это отдельное продуктово фиксируемое правило, а не догадка реализации.

**Severity:** `MAJOR`.

### P0-7 — memory обещает rebuild из источника, который не является источником части отображаемого состояния

**Файлы и разделы:** `wiki/platform/foundation.md` §2; `wiki/modules/memory.md` §§4–5; `wiki/glossary.md` Snapshot.

**Точные цитаты:**

> «сессии, Attempt-lifecycle, review-очереди, exposure-очередь/cooldown, черновики — SQLite-authoritative; события ... для аудита, не источник истины»  
> — `wiki/platform/foundation.md` §2, строка 23

> Memory строит `sessions/...`, `reviews/...`, `gates/...`, `plans/...`  
> — `wiki/modules/memory.md` §4, строки 47–56

> «Проекция полностью восстановима из event-store»  
> — `wiki/modules/memory.md` §5, строка 67

> «операционное состояние не rebuildable из событий, поэтому бэкапится»  
> — `wiki/glossary.md`, Snapshot, строка 113

**Почему это дефект:** полный rebuild memory требует полных сессионных/очередных/плановых данных, но foundation не обещает capture-complete события для operational aggregates и прямо запрещает считать их event-sourced. Snapshot может восстановить authoritative SQLite, но это другой протокол, не «rebuild из event-store». После частичной потери/миграции проекция может отличаться от authoritative operational state.

**Предлагаемая правка:** нормативно перечислить источник каждой memory page. Для operational pages — render из authoritative SQLite/snapshot; для event-sourced — replay event-store. Либо потребовать capture-complete projection events и зарегистрировать их в boundary manifest, не объявляя их бизнес-источником истины.

**Severity:** `MAJOR`.

### P0-8 — Curriculum Contract не содержит принятого трека `everyday-life`

**Файлы и разделы:** `wiki/modules/curriculum.md` §2; `wiki/OPEN.md` resolved decisions; `wiki/roadmap.md` 0.3; `wiki/modules/scoring.md` §4.

**Точные цитаты:**

> Таблица Curriculum перечисляет 8 треков и не содержит `everyday-life`  
> — `wiki/modules/curriculum.md`, строки 55–66

> «Трек `everyday-life` заведён отдельно ... паритет бытового и рабочего пласта»  
> — `wiki/OPEN.md`, resolved decisions, строки 58–59

> Scoring уже включает `everyday-life` в core-skill map  
> — `wiki/modules/scoring.md`, строка 91

> Roadmap 0.3: «can-do граф, 8 треков»  
> — `wiki/roadmap.md`, строка 18

**Почему это дефект:** accepted enum в данных/scoring содержит девятый трек, а его schema-owner — нет. Валидатор может отвергнуть канонические данные или потребовать неописанное расширение enum. Work-only формулировки `Module` и SHOULD «каждая тема связана с рабочим контекстом» также противоречат принятому паритету бытового домена.

**Предлагаемая правка:** добавить `everyday-life` в нормативную таблицу Track, обновить количество треков и заменить work-only требования на рабочий **или бытовой** can-do/context там, где правило относится ко всей программе.

**Severity:** `MAJOR`.

### P0-9 — living-layer workflow одновременно MVP и «не строится в MVP»

**Файлы и разделы:** `wiki/OPEN.md` resolved decisions; `wiki/modules/curriculum.md` §§2, 4; `wiki/product/lexical-system.md` §3b.

**Точные цитаты:**

> «Living layer в MVP не строится ... maintain-workflow и авто-устаревание откладываются»  
> — `wiki/OPEN.md`, строка 61

> «living layer ... добавляются через `maintain-english-curriculum` workflow»  
> — `wiki/modules/curriculum.md`, строка 73

> `LEXICAL_ITEM_ADDED | ... | пополнение living layer | [mvp]`  
> — `wiki/modules/curriculum.md`, строка 121

**Почему это дефект:** accepted PD откладывает именно механизм, но contract сохраняет механизм и событие с `[mvp]`. Реализация не может понять, обязана ли она строить authoring/lifecycle pipeline в текущем срезе. Поля stable data и постоянный запрет excerpts можно оставить без MVP workflow — сейчас это не разделено.

**Предлагаемая правка:** пометить maintain workflow/event/lifecycle `[post-mvp]`, сохранив data fields и validator legal constraints в target contract; либо отменить resolved PD отдельным решением.

**Severity:** `MAJOR`.

### P0-10 — верхний learning/evidence контракт допускает ветку, которую owner исключил

**Файлы и разделы:** `wiki/product/learning-model.md` §3; `wiki/modules/evidence.md` §4.1.

**Точные цитаты:**

> «observation, не подтверждаемая raw answer, отклоняется или помечается»  
> — `wiki/product/learning-model.md`, строка 33; та же фраза осталась в `wiki/modules/evidence.md`, строка 44

> «→ `rejected` ... Единственная ветка; “помечается” без участия в scoring исключено»  
> — `wiki/modules/evidence.md`, строка 53

**Почему это дефект:** одно и то же owner-содержание в evidence содержит общий MUST с двумя ветками и ниже более точный MUST с одной. Product contract также сохраняет удалённую ветку. Клиент/schema может добавить состояние `flagged`, которого reducer не принимает, или учитывать его иначе.

**Предлагаемая правка:** в обоих верхних утверждениях заменить развилку на единственную принятую семантику `rejected` + audit reason.

**Severity:** `MAJOR`.

### P0-11 — adapters переиспользует закрытые exit codes с другой семантикой

**Файлы и разделы:** `wiki/modules/cli.md` §4.2; `wiki/modules/adapters.md` §5.

**Точные цитаты:**

> `3 INVALID_INPUT` — «вход не прошёл schema/доменную валидацию»; `5 CONFLICT` — CAS/действие уже выполнено; «CONFLICT означает повтори с актуальным состоянием»  
> — `wiki/modules/cli.md`, строки 66–78

> `skills validate`: «`3` при невалидности, `5` при drift»  
> — `wiki/modules/adapters.md`, строка 97

**Почему это дефект:** drift канонической и производной копии — не CAS-конфликт и не лечится повтором validate; требуемое действие — `skills sync`. Невалидная структура уже существующего skill также не обязательно является невалидным command input. Закрытый набор codes заявлен как средство выбора next action, но здесь один code получает несовместимое recovery-поведение.

**Предлагаемая правка:** определить единое отображение диагностических нарушений на closed codes и `next_action`; при необходимости добавить отдельный code правкой CLI contract, а не локально переопределять 3/5.

**Severity:** `MAJOR`.

## MINOR

### P0-12 — roadmap и «Открытые вопросы» ссылаются на уже закрытые вопросы

**Файлы и разделы:** `wiki/roadmap.md` строки 18, 24; `wiki/product/lexical-system.md` §6; `wiki/modules/curriculum.md` §8; `wiki/modules/scoring.md` §10; `wiki/OPEN.md`.

**Точная цитата:**

> 0.3: «остаточные OPEN-9/14/15»; 0.9: «остаточные OPEN-13/14/15»  
> — `wiki/roadmap.md`, строки 18, 24

> `OPEN-13` закрывается scoring §10; `OPEN-15` зачёркнут как закрытый в самих curriculum/lexical specs; `learner_priority` переоткрыт как `OPEN-22`, но lexical §6 всё ещё пишет `OPEN-8`  
> — соответствующие разделы

**Почему это дефект:** статус фазы и единый реестр расходятся. Это не меняет доменную семантику напрямую, но ломает dependency tracking и может заставить повторно решать закрытую задачу либо пропустить OPEN-22.

**Предлагаемая правка:** синхронизировать roadmap и секции open questions с текущим `OPEN.md`: 0.3 — OPEN-9/14; 0.9 — OPEN-14/22, если именно они остаются; закрытые вопросы перенести только в history.

**Severity:** `MINOR`.

### P0-13 — метаданные изменений не отражают правки 2026-07-20

**Файлы и разделы:** headers/history `wiki/modules/curriculum.md`, `wiki/product/lexical-system.md`.

**Точная цитата:**

> `Last updated: 2026-07-19`  
> — headers этих двух файлов

При этом curriculum/lexical содержат `[PD-2026-07-20]`; история lexical не фиксирует добавление `transparency`/`idiom`/новый mastery tuple, а curriculum — `everyday-life` вообще не внесён.

**Почему это дефект:** по header/history невозможно установить, какая редакция включает поздние PD и прошла ли она review. Это особенно опасно сейчас: именно поздняя ось transparency породила P0-3 после принятия 0.4.

**Предлагаемая правка:** после семантического триажа обновить `Last updated` и добавить отдельные history entries с перечислением новых контрактных полей/треков.

**Severity:** `MINOR`.

### P0-14 — glossary сохраняет старую ссылку на формат working level

**Файлы и разделы:** `wiki/glossary.md` Working level; `wiki/modules/scoring.md` §4; `wiki/OPEN.md` resolved OPEN-8.

**Точная цитата:**

> «ordinal/sublevel-представление — OPEN-8»  
> — `wiki/glossary.md`, строка 65

**Почему это дефект:** OPEN-8 уже закрыт решением про целые CEFR bands, а формулировка `sublevel` выглядит как сохранённый вариант «полступеней». Термин определён не в той финальной форме, которую применяет scoring.

**Предлагаемая правка:** определить Working level прямо как отдельные целые CEFR bands по навыкам + общий conservative result и убрать ссылку на закрытую развилку.

**Severity:** `MINOR`.

## QUESTION

### P0-Q1 — когда именно проверяется разрешимость required skill?

**Файлы и разделы:** `wiki/modules/lessons.md` §4b; `wiki/modules/adapters.md` §§3, 6.

**Точные цитаты:**

> «`start` падает, если затребованная версия skill неразрешима»  
> — `wiki/modules/lessons.md`, строка 59

> adapters имеет API `resolve(skill, version)`, но также «consumes `SESSION_STARTED` — для проверки, что затребованные skills разрешимы»  
> — `wiki/modules/adapters.md`, строки 45, 104

**Вопрос:** является ли `resolve` синхронной precondition до commit, а `SESSION_STARTED` — только постфактум audit? Если проверка выполняется лишь по событию, она происходит после создания сессии и нарушает MUST lessons.

**Предлагаемая правка:** зафиксировать порядок: preflight resolve всех required versions → UoW start → `SESSION_STARTED`; post-commit consumer может только контролировать уже обеспеченный invariant.

**Severity:** `QUESTION`.

### P0-Q2 — `REVIEW_DUE` является фактом, notification или производной?

**Файлы и разделы:** `wiki/modules/scheduler.md` §§3, 6; `wiki/platform/foundation.md` §2.

**Точные цитаты:**

> «`due` когда `now ≥ next_review_at`»  
> — `wiki/modules/scheduler.md`, строка 31

> «events published: `REVIEW_SCHEDULED`, `REVIEW_DUE`, ...»  
> — `wiki/modules/scheduler.md`, строка 55

**Вопрос:** если due — вычисляемый operational status от Clock, при каком crossing и с каким idempotency key публикуется `REVIEW_DUE`? Должны ли consumers восстанавливать статус из события или вычислять его из schedule? Сейчас можно получить два источника/две задержки.

**Предлагаемая правка:** объявить `REVIEW_DUE` либо идемпотентным notification с epoch/boundary и запретом использовать как truth, либо удалить его и оставить `REVIEW_SCHEDULED` + Clock-derived query.

**Severity:** `QUESTION`.

### P0-Q3 — Tutor Compliance измеряет audit-факт или самоотчёт агента?

**Файлы и разделы:** `wiki/modules/scoring.md` §5; `wiki/modules/adapters.md` §§3, 4.5.

**Точные цитаты:**

> «каждое obligation берётся из audit-события»  
> — `wiki/modules/scoring.md`, строка 107

> «`SKILL_STARTED/COMPLETED/FAILED` сообщает агент ... годятся для Tutor Compliance»  
> — `wiki/modules/adapters.md`, строка 49

**Вопрос:** obligation «required-skill вызван нужной версии» считается выполненным по untrusted self-report или по наблюдаемому CLI/adapter invocation? В первом случае агент оценивает собственное соблюдение и может породить `SKILL_COMPLETED` без эффектов; во втором отсутствует спецификация trusted observation boundary.

**Предлагаемая правка:** явно назвать trust level метрики и алгоритм корреляции `required_skills` с наблюдаемыми событиями/эффектами. Если self-report допустим, не называть его проверенным audit-фактом.

**Severity:** `QUESTION`.

## Вердикт по контрактам

| Контракт | Вердикт | Главные причины |
|---|---|---|
| 0.1 Learning Model | `FAIL` | P0-1; P0-10 |
| 0.2 Foundation | `PASS-with-findings` | собственные ранее принятые OPEN честно зарегистрированы; boundary расходится с 0.6 (P0-7) |
| 0.3 Curriculum | `PASS-with-findings` | P0-8, P0-9, P0-12/13 |
| 0.4 Evidence/Scoring/Scheduler | `FAIL` | P0-1, P0-3; P0-2/10; Q2/Q3 |
| 0.5 Lessons/Assessments | `FAIL` | P0-2; P0-6; Q1 |
| 0.6 Memory | `PASS-with-findings` | P0-7 |
| 0.7 CLI/Adapters | `FAIL` | P0-2, P0-4; P0-5/6/11; Q1/Q3 |
| 0.8 Flows | `FAIL` | derived contracts не предоставлены owners: P0-2, P0-4/5/6 |
| 0.9 Lexical System | `FAIL` | P0-3; P0-9; P0-12/13 |

`FAIL` здесь означает наличие `BLOCKER` в самом контракте или в обязательном стыке, без которого его MVP-flow не исполним. `PASS-with-findings` не означает отсутствие правок, только отсутствие blocker в данном артефакте.

## Проверено, ок

- **Event-store atomicity:** authoritative event log теперь SQLite append-only table, а JSONL — derived export; это согласовано с одной ACID UoW и не повторяет прежний filesystem/SQLite split-brain.
- **Known kernel debt честно открыт:** OPEN-19/20/21 покрывают atomicity implementation, canonical determinism и outbox/rebuild protocol; эти строки сами по себе не считались дефектами `done-with-open`.
- **Safety-overlay:** pinned policy используется для replay, active safety — для live delivery; curriculum, lessons, CLI, adapters и flows в этом принципе согласованы.
- **Placement exposure:** применённый вес захватывается в evidence event; replay не перечитывает изменившуюся operational exposure queue.
- **CAS и uniqueness:** kernel предоставляет multi-aggregate CAS, а business uniqueness одного ReviewOutcome закреплена за lessons; owner-граница выдержана.
- **Scheduler ordering:** due-list имеет полный canonical tuple с `target_id` и `dimension_id`; порядок SQLite не протекает в выбор.
- **Numeric determinism:** scoring задаёт Decimal context/rounding и отделяет schema version от policy version.
- **OPEN references:** не найдено номера `OPEN-*`, полностью отсутствующего в `wiki/OPEN.md`; проблема P0-12 — не dangling ID, а устаревший статус/владелец.
- **Файловые проекции:** post-commit outbox, inbox/dedup, applied offset и isolate-and-swap rebuild согласованы на уровне механизма; P0-7 касается только состава источников для operational pages.

## Рекомендуемый порядок триажа

1. Решить продуктовую семантику `REGRESSION`/`AT_RISK` и синхронизировать 0.1/0.4/glossary.
2. Закрыть executable review lifecycle: explicit close command + единое finish/abandon rule.
3. Довести `LexicalMasteryProfile` до нового tuple с transparency до П.4c/П.2.
4. Решить судьбу отсутствующих `learner/audit/gates` contracts и MVP-команд.
5. После снятия blockers исправить MAJOR-стыки и повторить сквозной replay/CLI review; затем обновить roadmap/history.
