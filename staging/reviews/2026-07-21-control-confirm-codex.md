# Подтверждающее red-team ревью 0.12

Дата: 2026-07-21  
Предмет: четвёртый прогон `wiki/modules/control.md` и нормативных стыков с `cli`, `lessons`, `evidence`, `scoring`, `scheduler`, glossary, OPEN и session-flow.  
Метод: только документы; проверка исполнимыми контрпримерами. Числовая калибровка значений `control_policy@1` не оценивалась (OPEN-27).

## 1. Вердикт

**FAIL — 3 BLOCKER / 7 MAJOR / 1 MINOR / 0 QUESTION.**

Системный BLOCKER RR2-1 про противоположную семантику `session next` снят: mutating delivery и read-only peek теперь согласованы во всех перечисленных владельцах и во flow. Однако блок 0.12 снять нельзя:

1. опубликованный `control_policy@1` не проходит собственный MUST дискретной достижимости: validator требует `floor ≥ min(step)`, а следующие строки пытаются разрешить ровно этот случай через overshoot, не меняя predicate validator;
2. сценарий `too_easy → probe-step` не имеет единственного допустимого пути вставки `PlannedStep{kind: probe}` в активную revision: `record_signal` не принимает session/revision, а изменение плана разрешено только явным `replan`.
3. control/evidence закрывают replan как `CANCELLED`, который прямо «не ReviewOutcome», тогда как owner finish в lessons требует, чтобы **каждый** ReviewAssignment имел ReviewOutcome; один формально верный finish принимает отмену, другой навсегда видит непустой pending-set.

Кроме того, четыре прежних системных рассинхрона всё ещё существуют в соседних спеках: learner/tutor boundary, второй `record_attempt` без `step_id`, `INSUFFICIENT_EVIDENCE(reason=replanned)` в lessons и CLI/API без `expected_revision` для mutating next.

## 2. Статус RR2-1…RR2-14

| Finding | Статус | Проверка у владельца и в соседних файлах |
|---|---|---|
| **RR2-1 — `session next`** | **снята** | `cli.md` §5: «`session next` … **да** … атомарно помечает предъявленным и публикует `STEP_PRESENTED`»; `lessons.md` §4b: «`session next` **мутирующая**»; glossary SessionPlan: «`session next` **выдаёт** шаг … read-only `session peek`»; owner-матрица `OPEN.md`: «`next` мутирующая … `peek` read-only»; `flows/session.md` явно содержит `peek → next → STEP_PRESENTED → attempt record --step → replan`. Две добросовестные реализации больше не получают противоположные эффекты команды. |
| **RR2-2 — boundary `STEP_PRESENTED`** | **снята частично** | `control.md` §4.6 честно выбирает tutor boundary: «шаг **выдан тьютору**»; flow подтверждает порядок: сначала `STEP_PRESENTED`, затем `A->>L: … по этому шагу`. Но glossary всё ещё говорит противоположное: «`STEP_PRESENTED` — факт фактической выдачи шага **ученику**». Реализация проекции exposure по glossary формально утверждает ненаблюдаемый факт. |
| **RR2-3 — probe provenance** | **снята частично** | Исправленный путь есть: `evidence.md` §3: «`record_attempt(step_id, …)` … target/dimension/mode и `origin` движок берёт из `PlannedStep`»; §4.5 и `scoring.md` §4b имеют одинаковый enum `session \| placement \| re_entry \| control_probe`; CLI не принимает origin. Но в той же публичной таблице evidence остался второй MVP API: «`record_attempt(target, dimension, mode, raw_answer, observations, hints)`». Его область и отношение к plan-backed attempt не ограничены. Один исполнитель запрещает этот overload для session, другой принимает его без `step_id`; оба следуют таблице. |
| **RR2-4 — replan cancellation** | **снята частично; BLOCKER** | `evidence.md` §4.3 требует `CANCELLED(reason=replanned)` и говорит, что это не ReviewOutcome; `scheduler.md` §3: «`CANCELLED` — не исход … retry не назначается». Но owner сессии остался старым: `lessons.md` §4b — «получает `INSUFFICIENT_EVIDENCE(reason=replanned)`», а §4 требует: «все ReviewAssignment имеют ReviewOutcome». Control/evidence path с `CANCELLED` формально не удовлетворяет этому finish-postcondition. |
| **RR2-5 — matrix и дискретность** | **снята частично; BLOCKER** | Матрица `kind → step_type` появилась, и все её значения разрешаются в `expected_seconds_by_step_type`. Сосед `lessons.md` §4b действительно сохраняет «`session_plan` с `composition_revision`», то есть должен получить валидный plan. Но `control.md` §3 одновременно требует: «валидатор проверяет: пол корзины ≥ минимальной стоимости» и «первый шаг корзины помещается, даже если его стоимость больше зарезервированной ёмкости». При 1800 с balanced integration-floor = 270 с < 420 с, choice-floor = 180 с < 300 с. Первая формулировка отвергает default policy, вторая разрешает сборку. Это две формально верные реализации и отсутствие активируемого единственного контракта. |
| **RR2-6 — ledger/revisions** | **снята частично** | Появились `DeliveryLedger`, остаток `total − presented`, переходы `CONSUMED → PLANNED/DISCARDED`; glossary отдельно определяет `SessionBudget` как «распределение времени … по четырём корзинам», то есть plan/fact концептуально разведены. Но далее `control.md` §4.2 требует проверять доли по `presented + planned`, а §4.3a говорит: «`planned_review_share` считается по текущей ревизии» и «инварианты состава … проверяются на **плане**». Дополнительно §4.3 использует несуществующее после rename поле `sum(allocated)`. Накопительный и revision-local checks остаются двумя нормативными источниками одной проверки. |
| **RR2-7 — CAS выдачи** | **снята частично** | Таблица исходов `next↔next` и `next↔replan` появилась. Но публичный API всё ещё объявлен как `claim_next_step(session_id, idempotency_key)` без требуемого ниже `expected_revision`; `lessons.md` §6 и `flows/session.md` вызывают next также без expected revision. Более того, заявленный CAS ключуется `composition_revision`, а успешный next её не меняет: next может закоммитить claim, после чего replan с прежней revision всё ещё проходит CAS. Поэтому обещанный исход «проигравший получает CONFLICT» из указанного CAS не выводится. |
| **RR2-8 — fairness bound** | **снята частично** | Admission теперь назван честно: control обещает, что цель «попадает в резерв», а соседний flow допускает `STARTED → ABANDONED`, поэтому presentation безусловно не обещается. Но формула всё ещё дословно `|eligible| / reserved_steps_per_session`, не `ceil(...)`; `deferral_count` всё ещё растёт «когда цель была кандидатом **ревизии**», без cap «не более раза за session composition epoch». Два replans могут состарить цель на три «занятия» внутри одной сессии. |
| **RR2-9 — signal expiry/effects** | **не снята; часть даёт BLOCKER** | Glossary фиксирует: «`too_easy` порождает пробу». В owner-таблице control session-based сигналы всё ещё имеют `expires_at = +N сессий`, а следующий MUST запрещает это и требует `expires_after_session_seq`. Entity §2 перечисляет только `expires_at?`. Кроме того, `record_signal(signal)` не принимает session/revision, «переплан только явной командой», но `too_easy` якобы создаёт «соответствующий `PlannedStep{kind: probe}`». Не задано, в какую revision и в какой UoW вставляется шаг, нужен ли replan и когда применяется сигнал. |
| **RR2-10 — availability dimensions** | **не снята** | Сосед `lessons.md` публикует терминальные `FINISHED/ABANDONED`, из которых observed можно считать. Но control по-прежнему определяет `sessions_per_week` как «число терминализованных сессий за `divergence_window_sessions` последних календарных **недель**», хотя policy-поле измерено в sessions. Для 12 сессий за шесть недель одна реализация получает 12, другая нормирует до 2/week. Влияние на состав также остаётся свободным: «повышает долю critical … понижает growth до пола» без величины, no-data и перераспределения. |
| **RR2-11 — fact metrics/correlation** | **снята** | Метрики используют `ledger.presented.* / ledger.presented_seconds`; аварии — только `presented_*` и balanced. `evidence.md` §4.3 подтверждает, что `CANCELLED` не является outcome и не входит в метрики. Связь задана однозначно: последний выданный шаг конкретного `review_assignment_id` ↔ terminal outcome; nearest-rank для p90 определён. |
| **RR2-12 — integer decision contract** | **снята частично** | YAML-пороги classification/availability переведены в целые ppm; `scoring.md` §2.1 задаёт Decimal precision 28 + `ROUND_HALF_EVEN`, а control требует перевод Retrievability в ppm тем же округлением. Однако availability вычисляет `divergence = abs(...) / max(...)` и сравнивает с tolerance без `divergence_ppm` и правила округления. На границе 300000 ppm exact-rational, Decimal и округлённый integer paths могут принять разные решения. |
| **RR2-13 — saturation key/staleness** | **снята** | Entity ключуется `(target_ref, dimension)`; predicate явно `per-dimension` и читает `transfer_check_staleness_days`. Сосед `evidence.md` хранит target и dimension в Attempt/Evidence, поэтому reducer имеет разрешимый ключ. Старого cross-dimension смешения больше нет. |
| **RR2-14 — free conversation** | **снята** | Control §4.4: «Свободный разговор — безусловный кандидат `choice` … доступен всегда». Соседний session-flow ведёт «разговор … по плану, но формулировки свободны». При пустых goals/personal vocabulary choice больше не получает `NO_CHOICE_CANDIDATE`. |

Итого по последнему набору: **4 сняты полностью, 8 сняты частично, 2 не сняты**.

## 3. Новые дефекты и регрессии после правок

### B-1. Validator дискретной достижимости противоречит разрешённому overshoot — BLOCKER

**Контрпример:** default balanced, `total_seconds = 1800`.

- `integration_min = floor(1800 × 1500 / 10000) = 270`, минимальный разрешённый integration step = `integration_task` 420;
- `choice_min = floor(1800 × 1000 / 10000) = 180`, минимальный разрешённый choice step = `free_conversation` 300.

MUST validator из §3 отвергает policy по обоим полам. Следующий MUST разрешает первому неделимому шагу превысить reserve, но не заменяет predicate validator. Та же проблема есть у maintenance: choice reserve 180 < 300. Это не OPEN-27 и не спор о величине констант; это два противоположных правила валидности одних данных.

### B-2. `too_easy` не имеет транзакционного пути в активный SessionPlan — BLOCKER

`record_signal(signal)` не принимает `session_id`, `expected_revision` или idempotency key активного plan. §4.2 утверждает: «переплан только явной командой». §4.7 одновременно требует создать `PlannedStep{kind: probe}` и расходовать сигнал «в момент создания probe-шага». Возможны минимум три формально допустимых поведения: скрыто мутировать текущий plan, ждать явного replan или ждать следующей session composition. Только первое даёт немедленный шаг, но нарушает exclusive replan; остальные не собирают требуемый сценарий без неописанного действия.

### B-3. `CANCELLED` закрывает assignment в evidence, но не удовлетворяет owner-postcondition finish — BLOCKER

`evidence.md` объявляет `CANCELLED` терминальной отменой и отдельно подчёркивает: «не является ReviewOutcome». `lessons.md` §4 требует для FINISHED: «все ReviewAssignment имеют ReviewOutcome», а §4b всё ещё создаёт `INSUFFICIENT_EVIDENCE(reason=replanned)`. Реализация по control/evidence получает закрытый assignment без ReviewOutcome; реализация буквального lessons.finish считает postcondition невыполненным. Поэтому именно требуемый сценарий «replan убрал review → finish не заблокирован» системно не доказан.

### M-1. Tutor/learner boundary снова расходится с glossary — MAJOR

Owner считает exposure при выдаче тьютору; glossary утверждает выдачу ученику. Crash после commit до сообщения ученику в одной реализации считается exposure, в другой — нет. Это влияет на `is_first_exposure`, saturation и reset `deferral_count`.

### M-2. Evidence публикует два несовместимых MVP-входа `record_attempt` — MAJOR

Один требует выданный `step_id` и engine-derived origin, второй принимает target/dimension/mode напрямую. Нет discriminant «placement-only» или запрета использовать старую форму в session. Provenance probe поэтому снова можно реализовать двумя способами.

### M-3. SessionBudget и DeliveryLedger разведены как сущности, но не как invariant source — MAJOR

§4.2 проверяет `review_max`/полы по accumulated `presented + planned`; §4.3a — по current revision plan. После одного review-first replan один исполнитель удержит cumulative cap, второй даст каждой revision собственный cap. Ссылка на `allocated` после перехода schema к `planned` усиливает неоднозначность.

### M-4. Обещанный CAS-исход `next↔replan` не следует из указанного version key — MAJOR

Next не увеличивает `composition_revision`. Поэтому после claim rev=1 replan с expected rev=1 всё ещё удовлетворяет CAS. Чтобы гарантировать один loser с `CONFLICT`, нужен delivery/version token или явное правило сериализации, меняющее precondition; ни API, ни CLI его не объявляют.

### M-5. Fairness всё ещё считается по revision и без `ceil` — MAJOR

При `|eligible|=2`, reserve=3 формула даёт 2/3 занятия вместо одного. Два replans одной сессии увеличивают deferral несколько раз, хотя bound измерен занятиями. Это меняет порядок резервирования при одинаковом event log.

### M-6. Signal schema и signal transformations нетотальны — MAJOR

Помимо противоположных expiry fields, не определены точные transformations для «need_more_practice повышает частоту» и «too_repetitive понижает класс»: на сколько классов, до/после risk-classifier и когда это вступает в силу. Две реализации законно строят разные планы.

### M-7. Availability остаётся размерностно и численно недоопределённой — MAJOR

`divergence_window_sessions` используется как число календарных недель; sessions/week не нормируется. Решение сравнивает division-result с ppm threshold без conversion/rounding rule. Re-entry adjustment не задаёт delta basis points и no-data. Это один непрерывный decision-path, а не калибровка значения.

### N-1. После вставок остались битые/устаревшие ссылки на разделы — MINOR

- `control.md` Public API: availability ведёт на несуществующий **§4.11**, фактический алгоритм — §4.7a;
- `control.md` entity `LearnerControlSignal` ведёт на **§4.6**, фактически union — §4.7;
- `cli.md` `trainer why` ведёт на control **§4.6**, фактически trace — §4.8;
- glossary `AvailabilityProfile` ведёт на control **§4.5**, фактически — §4.7a;
- `scheduler.md` §5 говорит, что классы control находятся в **§4.3**, фактически — §4.5.

## 4. Сквозная исполнимость

| Сценарий | Результат | Исполнимый разбор |
|---|---|---|
| **1. Первая сессия, 30 мин, нет learned integration-role** | **НЕ СОБРАЛСЯ** | Intended pipeline понятен: growth-кандидаты; integration получает `NO_INTEGRATION_CANDIDATE`; free conversation гарантирует choice; пустого plan быть не должно. Но default policy до composition отвергается собственным validator: integration 270 < 420 и choice 180 < 300. Если применить overshoot, план собирается; если применить validator буквально — start падает. Единственного разрешённого результата нет. |
| **2. Maintenance, `growth_min=0`** | **НЕ СОБРАЛСЯ** | Отсутствие growth само по себе обработано корректно. Но при 30 мин `choice_min=180` с минимальным choice step 300 снова нарушает MUST validator. Overshoot и validator дают противоположные решения активации policy. |
| **3. `too_easy → probe → attempt`** | **НЕ СОБРАЛСЯ** | Matrix, `step_id`, enum origin и no-negative после появления шага согласованы. Не определено главное: какой command/UoW/revision помещает probe в активный plan. `record_signal` не имеет session/revision, а implicit plan mutation запрещена правилом explicit replan. Дополнительно evidence оставляет старый overload attempt без `step_id`. |
| **4. Replan середины сессии, выпавший review, затем finish** | **НЕ СОБРАЛСЯ** | Evidence говорит, что `CANCELLED` закрывает pending-set, но одновременно подчёркивает, что это не ReviewOutcome. Owner `lessons.finish` требует ReviewOutcome у каждого assignment, а owner §4b продолжает использовать `INSUFFICIENT_EVIDENCE`. По одной нормативной ветке finish проходит, по другой отклоняется; единственного postcondition нет. |

По заданному правилу достаточно одного несобираемого сценария для BLOCKER; здесь однозначно не собирается ни один из четырёх.

## 5. Проверено, ок

- `session next`/peek и session-flow наконец синхронизированы системно.
- Композиция и start находятся в одной UoW; control policy пинится в Session Manifest.
- `kind → step_type` покрывает каждый kind, и все step types имеют `expected_seconds`.
- Free conversation — безусловный choice candidate; отсутствие integration-пар имеет явный waiver.
- `CANCELLED` в evidence и scheduler тотально определён: не ReviewOutcome, без state transition и retry. Другие `INSUFFICIENT_EVIDENCE.reason` не повисают — scheduler применяет общий hold + `retry_days`.
- Метрики здоровья читают фактический `DeliveryLedger`, а не `SESSION_COMPOSED`; calibration correlation и percentile определены.
- Classification/availability policy fields больше не записаны YAML-float; thresholds представлены integer ppm.
- `SaturationState` ключуется `(target, dimension)`, а transfer staleness участвует в predicate.
- `meme_template`/OPEN-31 и числовая калибровка OPEN-27 не использовались как дефекты.

## 6. Можно ли снимать `blocked`

**Нет. `wiki/roadmap.md` 0.12 должен остаться `blocked`; перевод в `done-with-open` и разблокировка вертикального среза не подтверждены.**

Минимальный системный gate следующего подтверждения:

1. свести discrete-feasibility validator и overshoot к одному predicate, который принимает или отклоняет default policy однозначно;
2. определить транзакционный protocol `too_easy → active revision probe`;
3. синхронизировать glossary boundary, evidence API и lessons replan disposition;
4. сделать CAS token next/replan реально изменяемым и передаваемым через API/CLI;
5. исправить fairness `ceil`/session epoch, signal expiry и availability dimensions/rounding;
6. устранить cumulative-vs-revision-local правило проверки долей.

Канон в этом прогоне не редактировался.
