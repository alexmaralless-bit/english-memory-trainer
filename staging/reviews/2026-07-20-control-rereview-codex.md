# Повторное red-team ревью 0.12 после `4135f33`

Дата: 2026-07-20  
Предмет: revised `wiki/modules/control.md` и изменённые стыки с lessons/CLI/evidence/scoring/foundation.  
Метод: только документы; проверялись не намерения, а исполнимые контрпримеры.

## Резюме

Переписывание существенное: control-policy теперь существует, pinning проведён через kernel и Manifest, classifier стал синтаксически тотальным, glossary заполнен, решения по debt/calibration ownership зафиксированы. Но утверждение «все 5 BLOCKER сняты» преждевременно.

Вердикт — **FAIL**: 3 BLOCKER и 12 MAJOR.

Топ-5:

1. `STEP_PRESENTED` не имеет вызываемой мутации: `session next` read-only, отдельной операции present/claim нет. Следующий «непредъявленный» шаг никогда не становится предъявленным.
2. `control_policy@1` не тотальна по собственным допустимым состояниям: первый balanced-сеанс не имеет integration-кандидата, а `maintenance/re_entry` всё равно проходят pipeline с обязательным growth floor.
3. `PlannedStep` не может представить ни ReviewAssignment (`review_id`, dimension, criteria), ни integration-пару; replan не определяет судьбу удалённых pending assignments и может сделать `finish` незавершаемым.
4. Saturation поставлен выше риска: три любых показа, включая три провала, переводят цель в `deferrable`; recurring error при высокой Retrievability становится `maintenance` раньше проверки risk.
5. Probe exception пока либо недостижим, либо подделываем: нет engine-issued `probe_id`/связи attempt→request, а no-negative запрещает только REGRESSION/state drop, но не отрицательную дельту Mastery/Stability/schedule.

## Статус исходных находок

| Исходная находка | Статус после `4135f33` | Комментарий |
|---|---|---|
| CTRL-1 budget/partition | **частично, BLOCKER остаётся** | корзины названы взаимоисключающими, но mode/candidate/discrete feasibility и schema integration не закрыты (R-2/R-3) |
| CTRL-2 composition lifecycle | **частично, BLOCKER остаётся** | start+compose UoW исправлен, но delivery event недостижим и replan не закрывает assignments (R-1/R-3) |
| CTRL-3 policy pinning | **снята** | `control` есть в registry и Session Manifest |
| CTRL-4 total classifier | **снята структурно** | пять правил дают класс, но порядок правил и `stake_rank` создают новые дефекты (R-4) |
| CTRL-5 executable defaults | **снята по values** | конкретные значения есть; каталог ranges всё ещё представлен одной строкой (R-10) |
| CTRL-6 saturation inputs | **частично** | добавлен delivery fact, но payload/event names не позволяют собрать projection (R-5) |
| CTRL-7 starvation | **частично** | reserve введён, заявленная upper bound всё ещё не доказана (R-6) |
| CTRL-8 wall-clock duration | **снята** | ложная калибровка по STARTED→FINISHED удалена |
| CTRL-9 signals | **частично** | union есть, но тип expiry и межвидовой precedence не определены (R-11) |
| CTRL-10 probe | **частично** | origin добавлен, но provenance и полная no-negative semantics отсутствуют (R-7) |
| CTRL-11 availability/modes | **частично** | mode стал достижим через CLI, но его budget semantics и availability behavior отсутствуют (R-2/R-9) |
| CTRL-12 deterministic pipeline | **частично** | first-fit появился, но sort key и numeric type не тотальны (R-4/R-12) |
| CTRL-13 metrics | **частично** | таблица появилась, но прогноз/labels/alerts расходятся с lifecycle (R-8) |
| CTRL-14 dependencies | **частично** | learner/gates добавлены, evidence dependency и реальные owner-event names пропущены (R-5) |
| CTRL-15 OPEN/roadmap | **не снята** | roadmap снова объявил отсутствие BLOCKER до rereview (R-15) |
| CTRL-16 glossary | **снята** | новые сущности зарегистрированы |
| CTRL-Q1 review debt | **решена [PD]** | сообщать и предлагать выбор, автоматически intake не снижать |
| CTRL-Q2 foreign policy activation | **решена [PD]** | control подтверждает, owner активирует своей CAS-командой |

## BLOCKER

### R-1. `STEP_PRESENTED` невозможно породить, не нарушив read-only `session next` — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.2: «`session next` остаётся read-only … возвращает следующий непредъявленный шаг … ничего не публикует»; §4.6: «`STEP_PRESENTED` … публикуется, когда шаг фактически выдан ученику». `wiki/modules/cli.md`, §5 содержит `session next` и `session replan`, но не содержит present/claim/ack command.

**Почему дефект:** выдача шага пользователю — именно переход из «непредъявлен» в «предъявлен». Read-only `next` не может записать событие, а отдельного API/command нет. Поэтому повторный `next` обязан вернуть тот же шаг; `is_first_exposure`, saturation, starvation и `CONSUMED` никогда не изменятся. Если событие тайно пишет `next`, нарушается нормативный запрет CLI §4.4 и пропадает обязательный idempotency-key мутирующей команды.

**Предлагаемая правка:** замкнуть delivery protocol. Наиболее crash-safe вариант — мутирующий идемпотентный `session next/issue`, который атомарно claim-ит шаг, пишет `STEP_PRESENTED` и возвращает cached response при retry. Если `next` принципиально read-only — добавить явную mutating operation `present(step_id, expected_revision)` и описать окно crash/duplicate между показом агентом и ack.

### R-2. Конкретная `control_policy@1` не исполнима для допустимых modes и состояний ученика — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §3: `growth_min: 0.25`, `integration_min: 0.15`, `choice_min: 0.10`, `min_total_minutes: 10`; §4.4: candidates integration — «пары (новая цель, освоенная цель)», затем безусловно «Заполнение полов … `growth → integration → choice`»; §2: `maintenance/re_entry` допускают занятие без нового материала; единственный отказ — `BUDGET_TOO_SMALL` при duration < 10 минут.

**Почему дефект:** у ученика перед первой сессией нет освоенной цели, следовательно integration-кандидатов по нормативному определению нет, но default balanced pipeline требует заполнить `integration_min`. После исчерпания first-exposure целей аналогично невозможно заполнить `growth_min`. Для `maintenance/re_entry` algorithm всё равно выполняет шаг 5 и заполняет growth floor, поэтому разрешённый review-only режим фактически не определён. Наконец, проверка выполнимости учитывает только сумму долей, а не дискретную стоимость доступных step types и наличие кандидатов; `total_seconds ≥ 600` само по себе план не гарантирует.

**Предлагаемая правка:** задать отдельные shares/waivers для каждого mode; определить deterministic fallback/error для пустой корзины (`NO_GROWTH_CANDIDATE`, `NO_INTEGRATION_CANDIDATE`) и кто предлагает сменить mode. Validator policy должен проверять feasibility не только algebra shares, но и indivisible step costs; либо floors определить как reserved capacity, а не обязательную фактическую загрузку — с отдельной метрикой.

### R-3. `SessionPlan` не представляет обязательные review/integration данные, а replan не закрывает pending work — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: `PlannedStep {step_id, bucket, target_ref?, step_type, expected_seconds, is_first_exposure, urgency_class?, decision_id}`; §4.3: integration требует «одновременно новую и ранее изученную цель»; §4.2: replan создаёт новую revision и «не отменяет уже предъявленные шаги». `wiki/modules/scheduler.md`, §5: ReviewAssignment содержит `review_id, target, dimension, режим, критерии, pinned versions`. `wiki/modules/lessons.md`, §4: `finish` требует ReviewOutcome для **всех** ReviewAssignment.

**Почему дефект:** singular `target_ref?` не может выразить пару integration с ролями new/learned. Review-step не несёт `review_id`, `dimension`, mode, criteria или assignment ref, поэтому `session next` не может вернуть задание, которое затем корректно закрывается `review close`. При replan непредъявленный review-step может исчезнуть из active plan, но созданный в Manifest ReviewAssignment останется pending и навсегда заблокирует `finish`; ни cancellation outcome, ни correction semantics не заданы.

**Предлагаемая правка:** сделать `PlannedStep` tagged union: review с immutable `review_assignment_id`; growth с target/dimension; integration с `target_refs[]` и ролями; gate/choice со своими refs. В UoW start/replan атомарно создавать, сохранять, переносить или закрывать assignments; определить outcome/reason для удалённого непредъявленного шага и запрет orphan pending-set.

## MAJOR

### R-4. Тотальная таблица классификации системно подавляет риск и содержит неопределённый sort key — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.5: первое правило `saturated → deferrable`, второе `retrievability ≥ 0.85 → maintenance`, только затем `risk ∧ stake → critical`; §4.6: `saturated`, если `exposures_in_window ≥ 3` **либо** серия успехов в малом числе контекстов. §4.4 сортирует по `stake_rank`, который больше нигде не определён.

**Почему дефект:** три показа с тремя провалами удовлетворяют первой ветке и делают критичную цель `deferrable`. Повторяющаяся живая ошибка при Retrievability 0.90 удовлетворяет maintenance раньше risk; именно сигнал, введённый для исправления ошибочного прогноза модели, игнорируется. `stake_rank` не имеет enum/mapping для Topic и LexicalItem, поэтому после классификации порядок снова зависит от реализации.

**Предлагаемая правка:** сделать saturation допустимым только при отсутствии актуального risk либо требовать успеха; поставить подтверждённый risk раньше maintenance. Определить `stake_rank` закрытым enum/tuple и добавить truth-table tests: failed×3, high-R+recurring-error, saturated+AT_RISK, Topic без relevance.

### R-5. Saturation/risk projection ссылается на несуществующее событие и поля, которых нет в delivery event — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.6: входы `STEP_PRESENTED` для «числа показов, контексты» и `ATTEMPT_ASSESSED`; payload `STEP_PRESENTED {step_id, session_id, target_ref?, presented_at}` контекста не содержит. `wiki/modules/evidence.md`, §3/§6 публикует `ATTEMPT_RECORDED`, `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `ERROR_OBSERVED` — события `ATTEMPT_ASSESSED` нет. Control risk использует recurring live error, но `ERROR_OBSERVED` в consumed events отсутствует; evidence отсутствует и в `depends on`.

**Почему дефект:** `distinct_contexts`, `consecutive_independent_successes` и recurring-error window нельзя rebuild-ить из объявленных входов. Один consumer подпишется на несуществующее событие, другой начнёт читать чужую таблицу/API, третий выведет контекст из step type — результаты разойдутся.

**Предлагаемая правка:** использовать канонические owner events (`EVIDENCE_ADDED`/`ATTEMPT_STATE_CHANGED` либо явно добавить `ATTEMPT_ASSESSED` у evidence), добавить `context_id`/context class в delivery/evidence fact, потреблять `ERROR_OBSERVED` и добавить evidence dependency. Зафиксировать reducer order/dedup по event sequence.

### R-6. Reserve всё ещё не даёт заявленную верхнюю границу ожидания — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.5: «безусловно включается **до** `reserved_steps_per_session` целей … в порядке `deferral_count desc`. Это даёт **верхнюю границу ожидания**»; далее определено только, что snooze count не увеличивает.

**Почему дефект:** нет tie-break после одинакового count, события/момента increment, reset после admission/presentation и правила fit относительно `review_max`/diversity. Без reset одна уже обслуженная цель остаётся eligible и может занимать резерв снова; `до 1` допускает ноль; длинный reserved step может не поместиться. Upper bound также зависит от конечного размера eligible backlog, но эта предпосылка и формула bound отсутствуют.

**Предлагаемая правка:** определить state machine deferral counter (`increment`, `reset`, user-defer), canonical order до target/dimension, зарезервированные **секунды** либо fit rule и явную fairness guarantee с предпосылками/формулой. Иначе убрать claim upper bound и оставить best-effort reserve.

### R-7. `control_probe` provenance не защищён, а no-negative покрывает не все отрицательные эффекты — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.7: агент «фиксирует attempt с `origin = control_probe`»; `PROBE_REQUESTED` несёт только target/difficulty/context; `wiki/modules/evidence.md`, API `record_attempt(...)` не принимает probe/request/step ref; `wiki/modules/scoring.md`, §4b сначала закрывает origin enum как `session | placement | re_entry`, следующей строкой использует `control_probe` и запрещает только REGRESSION/state decrease.

**Почему дефект:** если origin задаёт агент, он может маркировать обычные провалы как probe и отключать понижение; если origin должен выводить движок, нет immutable `probe_id` и связи attempt→request, по которой это проверить. Даже честный failed probe может дать отрицательную Mastery/Stability delta или сдвинуть scheduler, потому что запрет касается лишь ReviewOutcome/knowledge state. Кроме того, probe помещён в `review`, хотя definition review требует due-target, а `too_easy` не требует due.

**Предлагаемая правка:** движок создаёт `probe_id`/PlannedStep, attempt ссылается на него, origin выводится сервером и capture-ится в evidence; клиент origin не принимает. Определить no-negative disposition для Mastery, Stability, state, ReviewOutcome, schedule и XP. Обновить единый origin enum и budget-bucket rule для non-due probe.

### R-8. Метрики сравнивают прогноз не того момента и не определяют outcome labels — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.10: calibration error сравнивает Retrievability «на момент выдачи», но следующая MUST говорит о Retrievability, «записанной в trace **при композиции**»; session может быть resumed значительно позже. Formula сводит `REVIEW_OUTCOME` к «1 успех / 0 неуспех», хотя outcome enum имеет пять значений. Alert `growth_rate ≤ 0.10` применяется без ограничения mode, хотя maintenance/re_entry законно имеют ноль growth.

**Почему дефект:** composition time и delivery time расходятся, а Retrievability убывает по реальному времени; метрика будет приписывать policy ошибку, созданную stale plan. Не определено, являются ли `PROGRESS`, `RECOVERED`, `REGRESSION`, `INSUFFICIENT_EVIDENCE` success=1/0/excluded. После трёх нормальных maintenance-сессий growth alert ложно объявит debt spiral; в успешном balanced плане growth floor 0.25 делает threshold 0.10 недостижимым. Заявлены enter/exit thresholds, но policy содержит только один threshold на метрику.

**Предлагаемая правка:** capture prediction в `STEP_PRESENTED` после active delivery check либо детерминированно пересчитать по pinned policy и `presented_at`; задать outcome→label/exclusion map. Считать alerts per-mode и добавить отдельные enter/exit values; определить, какие terminal sessions входят в окно.

### R-9. Availability существует как сущность, но не как алгоритм влияния на план — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: `AvailabilityProfile declared{...}, observed{...}, divergence`; policy задаёт divergence threshold/window; §4.1 утверждает влияние availability на нагрузку. После переписывания §4 не содержит правила расчёта observed/divergence, предложения коррекции или выбора total budget. §7 лишь перечисляет поля v1 и OPEN-29.

**Почему дефект:** не определено, откуда берётся observed `typical_minutes` после честного отказа от STARTED→FINISHED duration, как `sessions_per_week/next_available_at/blackout_until` меняют composition, и что имеет precedence: `session start --duration`, declared typical, observed или default 30. Две реализации будут по-разному адаптировать нагрузку; часть policy values не используется ни одной веткой.

**Предлагаемая правка:** описать v1 algorithm inline: schema declared/observed, источник каждого observed field, precedence total_seconds, deterministic divergence formula, proposal→accept/reject lifecycle и поведение blackout/next_available_at. OPEN-29 оставить только для более богатого календаря.

### R-10. Каталог всё ещё не существует как полный проверяемый набор — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §4.9: «каждый tunable любой спеки имеет строку каталога и наоборот»; показана одна строка для `control.budget.shares.review_max`. `wiki/OPEN.md`, OPEN-27: values «лежат в диапазонах каталога».

**Почему дефект:** поиск по канону находит единственный control `parameter_id`/`allowed_range`. Для остальных budget/classification/starvation/saturation/diversity/availability/alert parameters диапазонов, units, scope, change_mode и metric links нет. Validator, запрещающий activation вне ranges, не имеет входных данных; OPEN-27 снова over-claim-ит существующий artifact.

**Предлагаемая правка:** добавить versioned catalogue artifact/schema со строкой на каждый параметр `control_policy@1` и на ранее объявленные tunables соседей; определить location/loading/duplicate-ID validation. До этого формулировать §4.9 как обязательство реализации, а не существующий диапазонный контроль.

### R-11. Signal union смешивает timestamps с session-count и не разрешает конфликты разных kinds — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2: поле `expires_at?`; §4.7: для `too_repetitive` «`expires_at = +exposure_window_sessions`», для `need_more_practice` и context preference — «+3 сессии»; precedence определён только для «того же kind на ту же цель».

**Почему дефект:** timestamp нельзя заполнить числом сессий без отдельного session boundary/expiry type. Не определены совместные эффекты `need_more_practice + snooze`, `too_easy + too_repetitive`, target-level + domain-level `not_relevant_now`, а также момент consumption одноразового `too_easy`. Replay может считать сигнал активным разное число сессий.

**Предлагаемая правка:** разделить `expires_at` и `expires_after_session_sequence/count`, сохранить deterministic boundary; дать cross-kind compatibility/precedence table и event `SIGNAL_CONSUMED`/supersede rule для одноразовых сигналов.

### R-12. Числовой контракт запрещает float, но сериализует shares как неуточнённые YAML numbers — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §3: `review_max: 0.45`, `growth_min: 0.25`; затем «`floor(total_seconds × share)`. Никаких float».

**Почему дефект:** стандартные YAML loaders могут материализовать `0.45` как IEEE float; тип Decimal/rational, precision и canonical representation не заданы. Integer seconds устраняют дробность результата только после умножения, но само умножение уже может разойтись. Это слабее точного Decimal-контракта scoring и противоречит claim bit-equal SessionPlan.

**Предлагаемая правка:** хранить shares целыми basis points/ppm либо строковым Decimal с фиксированным context и parsing rule; validator запрещает binary float. Зафиксировать integer formula (`floor(total_seconds * share_bp / 10000)`).

### R-13. `is_first_exposure` может устареть внутри одного сохранённого плана — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md`, §2 сохраняет `is_first_exposure` в каждом PlannedStep; §4.3 определяет его отсутствием прежнего `STEP_PRESENTED`; diversity допускает до двух шагов одной темы.

**Почему дефект:** при композиции двух шагов одной новой цели история ещё пуста, поэтому оба получают `is_first_exposure=true`. После выдачи первого второй уже не является первым, но сохранённый plan/allocated growth не меняются. На replan «сохранённые шаги» удерживают stable ID, но правило пересчёта label не задано. Budget/telemetry начинают считать повторное предъявление новым.

**Предлагаемая правка:** запретить более одного first-exposure step на target во всех непредъявленных revisions либо моделировать virtual exposure во время pipeline; перед delivery валидировать flag и при drift требовать атомарный replan/correction.

### R-14. Переписывание удалило нормативный Public API и не синхронизировало flow/CLI registry — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/_TEMPLATE.md`, §3 требует таблицу Public API/events; в `wiki/modules/control.md` §3 теперь policy YAML, операции `compose_session`, classify, present, signal/availability/catalogue API не объявлены. `wiki/flows/session.md` по-прежнему возвращает старый Manifest с review-целями/рекомендациями и в loop не вызывает `session next/replan/STEP_PRESENTED`. `wiki/modules/control.md` CLI содержит `calibration confirm`, центральный `wiki/modules/cli.md` — нет; ссылка CLI `trainer why` ведёт на старый §4.6 вместо §4.8.

**Почему дефект:** lessons нормативно «вызывает `control.compose_session`», но сигнатуры/ошибок/фазы у public operation больше нет. Flow остаётся старой архитектурой, где агент сам выбирает шаги из рекомендаций, что конфликтует с сохранённым SessionPlan. Command registry не разрешит новую calibration command. Это регрессия принципа «полное поведение у owner + flow выводит его».

**Предлагаемая правка:** вернуть отдельный Public API/events section со всеми sync operations, mutations, schemas/errors/phases; обновить session/continuation flows и центральный CLI registry, включая delivery/replan и post-MVP calibration. Исправить section refs.

### R-15. Roadmap/OPEN снова объявили BLOCKER снятыми до проверки исполнимости — MAJOR

**Файл и раздел → точная цитата:** `wiki/roadmap.md`: «пять BLOCKER ревью 0.12 сняты», 0.12 `done-with-open`, вертикальный срез разблокирован; `wiki/OPEN.md` history: «все 5 BLOCKER сняты» и OPEN-27 «реализацию не блокирует».

**Почему дефект:** R-1…R-3 — lifecycle/schema/policy semantics, не эмпирическая калибровка. Для них нет OPEN carrier, owner acceptance tests и dependency; повторяется уже исправлявшаяся ошибка «зарегистрировать/переписать ≠ проверить снятие».

**Предлагаемая правка:** после triage rereview либо закрыть R-1…R-3 в owner/spec/flows, либо вернуть 0.12/phase status в blocked и завести OPEN с явными владельцами. Разблокировку вертикального среза привязать к исполнимому delivery E2E contract.

## Проверено, ок

- `control_policy` действительно добавлена и в foundation registry, и в lessons Session Manifest; retention/`PinnedPolicyUnavailable` теперь применимы к ней.
- Композиция и `SESSION_STARTED` теперь находятся в одной UoW; исходного crash-window между start и compose больше нет.
- Классификатор имеет конечную область (due/overdue) и единственный class result по first-match table; прежних «important/normal» без выбора больше нет.
- Topic больше не читает несуществующий `curriculum_priority_band`; leverage/relevance — допустимый отдельный stake-механизм.
- Конкретные значения `control_policy@1` появились; OPEN-27 теперь действительно может быть про калибровку **после** устранения feasibility/catalogue defects.
- Ложное утверждение о наблюдаемом active duration удалено.
- Glossary получил все публичные control-сущности.
- Решения [PD] по debt spiral и owner-applied calibration согласованы с границами модулей; их в ревью не оспаривал.
- `STEP_PRESENTED` как различение плана и фактической выдачи — правильная сущность; дефект R-1 только в отсутствующем пути её записи.

## Вердикт

**FAIL** — три исходных направления исправлены полностью, два (`budget`, `composition lifecycle`) остаются блокирующими в новых формах. До реализации нужно замкнуть delivery mutation, сделать policy тотальной по modes/empty candidate sets и согласовать SessionPlan/replan с ReviewAssignment lifecycle.
