# Второе повторное red-team ревью 0.12 после `92d5f4c`

Дата: 2026-07-20  
Предмет: `wiki/modules/control.md` после триажа R-1…R-15 и его нормативные стыки с `lessons`, `evidence`, `scoring`, `scheduler`, CLI, session-flow, OPEN и roadmap.  
Метод: только документы; факты о будущей реализации не предполагаются.

## Резюме

Локальные механизмы трёх прежних BLOCKER в `control.md` появились: delivery получил mutating API, доли — mode-specific policy и waiver, `PlannedStep` — tagged union, replan — явное закрытие выпавшего ReviewAssignment. Однако канон не синхронизирован с новым delivery-протоколом: owner-спека `lessons`, glossary и owner-матрица OPEN по-прежнему требуют read-only `session next`, а принятый session-flow вообще обходит `SessionPlan`. Поэтому R-1 нельзя считать закрытым на уровне системы.

Вердикт — **FAIL**: 1 BLOCKER, 11 MAJOR, 2 MINOR и 2 QUESTION.

Топ-5:

1. `session next` одновременно нормативно mutating и read-only; это прямое межспековое противоречие на owner-границе.
2. `STEP_PRESENTED` коммитится при выдаче ответа агенту, но объявлен фактом показа ученику; crash/обрыв после commit создаёт вымышленный exposure, от которого зависят growth, saturation и starvation.
3. Защищённый `control_probe` невозможно провести через owner API evidence: `Attempt`/`record_attempt` не несут `step_id`, а scoring одновременно закрывает origin-enum без и с `control_probe`.
4. Replan закрывает невыполненное назначение как `INSUFFICIENT_EVIDENCE(reason=replanned)`, а scheduler на любой такой outcome назначает retry через день: внутреннее перепланирование выдаёт себя за учебный исход.
5. Numeric/availability/metrics path всё ещё не тотален: float-пороги конфликтуют с собственным запретом float, availability содержит размерностную ошибку и ненормированную ветку, а доли считаются по плану, не по реально выданным шагам.

## Статус находок прошлого rereview

| Предыдущая находка | Статус после `92d5f4c` | Комментарий |
|---|---|---|
| R-1 delivery mutation | **частично, BLOCKER остаётся** | mutating `claim_next_step` добавлен в control/CLI, но owner `lessons`, glossary, OPEN и flow остались на read-only/старом протоколе (RR2-1) |
| R-2 modes/empty baskets | **BLOCKER снят** | mode-specific shares и детерминированные waiver существуют; осталась дискретная feasibility-дыра уровня MAJOR (RR2-5) |
| R-3 PlannedStep/replan | **BLOCKER снят** | tagged union и UoW closure существуют; выбранный outcome конфликтует с scheduler semantics (RR2-4), а lifecycle ревизий неполон (RR2-6) |
| R-4 classifier order/stake_rank | **снята** | risk идёт первым, `stake_rank` закрыт для Topic/LexicalItem |
| R-5 event inputs/context | **снята** | используются канонические evidence-events, добавлен `context_id`, определены order/dedup |
| R-6 starvation guarantee | **частично** | reserve/fit/tie-break появились, но счётчик живёт по revisions, а bound обещает больше, чем механизм гарантирует (RR2-8) |
| R-7 probe/no-negative | **частично** | no-negative расширен и origin объявлен engine-derived, но owner-связь Attempt→step отсутствует (RR2-3) |
| R-8 metrics | **частично** | prediction перенесён в delivery, labels и mode filter добавлены; denominator/revision/correlation не определены (RR2-11) |
| R-9 availability | **частично** | источники и precedence появились, но вычисление содержит размерностную ошибку и свободную ветку (RR2-10) |
| R-10 catalogue | **снята** | честно объявлен обязательным implementation artifact, не притворяется готовыми данными |
| R-11 signals | **частично** | precedence и два типа expiry описаны, но schema и эффекты им противоречат (RR2-9) |
| R-12 numeric shares | **частично** | shares переведены в bp, остальные decision-пороги остались YAML float (RR2-12) |
| R-13 duplicate growth | **снята** | второй growth той же цели запрещён |
| R-14 Public API | **снята** | API восстановлен |
| R-15 premature status | **снята** | roadmap оставлен `blocked`, OPEN-30 открыт до подтверждающего ревью |

## BLOCKER

### RR2-1. Один и тот же `session next` одновременно mutating и read-only — BLOCKER

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.2: «`trainer session next` **мутирующая** и идемпотентная. Она атомарно помечает следующий непредъявленный шаг выданным, публикует `STEP_PRESENTED`»; `wiki/modules/lessons.md` §4b: «`session next` только читает сохранённый план»; `wiki/glossary.md`, SessionPlan: «`session next` его только читает»; `wiki/OPEN.md`, owner-матрица: «`next` read-only».

Принятый `wiki/flows/session.md` §«Сценарий» также после `session start` сразу переходит к свободному циклу «агент → диалог / упражнение / подмешанная review-цель» и не содержит `session next`, `session peek`, `composition_revision`, `STEP_PRESENTED` или replan.

**Почему дефект:** это не устаревшая пояснительная заметка, а противоположные MUST у владельцев. Реализация по `control`/CLI обязана записать событие; реализация по `lessons` обязана ничего не мутировать. Session-flow разрешает агенту обойти сохранённый план целиком, поэтому Tutor Compliance и exposure-проекция не могут установить, что именно было выдано. В результате прежний R-1 локально исправлен, но системный контракт по-прежнему не имеет единственного поведения.

**Предлагаемая правка:** выбрать уже реализованную в `control` семантику как единственную либо вернуть другой целостный протокол; синхронно обновить owner-MUST в `lessons`, glossary, owner-матрицу OPEN и session-flow. Flow должен явно показывать `next`/`peek`, delivery-event и связь выданного `step_id` с `attempt record`. До этого OPEN-30 не закрывать.

## MAJOR

### RR2-2. `STEP_PRESENTED` фиксирует выдачу агенту, но объявлен фактом показа ученику — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §3b: «`claim_next_step(...)` … атомарно помечает следующий шаг предъявленным и публикует `STEP_PRESENTED`»; §4.6: «публикуется, когда шаг **фактически выдан ученику**»; §4.2: команда сначала мутирует и затем «возвращает шаг».

**Почему дефект:** SQLite-транзакция и возврат CLI/показ в чате не являются одной атомарной системой. После commit возможен crash, потеря ответа или смена агента до того, как текст увидит ученик. Event log уже утверждает exposure; цель перестаёт быть first-exposure, растёт saturation и обнуляется `deferral_count`, хотя learner ничего не видел. Identical retry спасает только если он действительно произойдёт; abandon без retry оставляет ложный факт навсегда. Контракт ранее правильно признал, что движок не наблюдает время живого чата, но здесь снова приписал ему ненаблюдаемый факт.

**Предлагаемая правка:** разделить `STEP_ISSUED_TO_TUTOR`/claim и подтверждённый `STEP_PRESENTED_TO_LEARNER`, либо честно определить `STEP_PRESENTED` как delivery boundary к trusted tutor и ввести идемпотентный ack, от которого считаются exposure/saturation. Зафиксировать recovery для commit-before-display.

### RR2-3. `control_probe` нельзя доказуемо связать с Attempt у владельца evidence — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.7: «Attempt ссылается на `step_id`; `origin = control_probe` движок проставляет сам»; `wiki/modules/evidence.md` §2: `Attempt` имеет «id, target, dimension, mode, raw_answer, span, hints, draft/finalized»; §3: `record_attempt(target, dimension, mode, raw_answer, observations, hints)` — без `step_id`/`probe_id`. `wiki/modules/scoring.md` §4b сначала утверждает закрытый enum «`session | placement | re_entry`», а следующей строкой применяет `origin=control_probe`.

**Почему дефект:** control требует immutable provenance, которого owner-сущность и owner-API не принимают. Вывести origin по «последнему шагу» нельзя безопасно: два агента, replan и повторная доставка делают связь неоднозначной. Если реализация добавит origin из клиентского payload, агент сможет пометить обычный провал как probe и получить no-negative. Кроме того, две соседние MUST scoring задают разные области enum.

**Предлагаемая правка:** добавить обязательный `step_id`/`item_exposure_id` в Attempt и `record_attempt` для plan-backed задания; evidence валидирует ссылку на выданный шаг текущей сессии/revision и сам выводит origin. Свести origin к одному закрытому enum во всех owner-спеках и добавить негативные тесты на чужой, устаревший и неподтверждённый probe-step.

### RR2-4. Replan превращает внутреннюю отмену в учебный outcome с retry — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.2 и `wiki/modules/evidence.md` §4.3: выпавший непредъявленный review-шаг получает `INSUFFICIENT_EVIDENCE(reason=replanned)`; `wiki/modules/scheduler.md` §3: «`INSUFFICIENT_EVIDENCE` — hold … назначается короткий retry `retry_days`, дефолт 1».

**Почему дефект:** ученик не пытался выполнить assignment и не дал недостаточное evidence — система сама убрала шаг. Но scheduler не различает reason и создаёт новый due через день. Replan ради safety, смены длительности или learner choice тем самым порождает review-долг и может вернуть только что исключённую цель. Это также загрязняет метрику исходов системными отменами.

**Предлагаемая правка:** продуктово выбрать одно из двух: отдельный cancellation/disposition, который не является ReviewOutcome, либо тотальная scheduler-ветка по `INSUFFICIENT_EVIDENCE.reason`, где `replanned` не создаёт retry и не считается learner outcome. Это развилка, см. Q-1.

### RR2-5. Проверка долей игнорирует неделимые стоимости шагов и связь `kind → step_type` — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §3: default 30 минут, `integration_task: 420`, `free_conversation: 300`; balanced: `integration_min: 1500`, `choice_min: 1000`; §4.4: «шаг, не помещающийся в остаток корзины, пропускается»; policy validation проверяет только суммы basis points.

**Почему дефект:** при 30 мин integration-reserve равен 270 секундам, меньше единственной явно названной стоимости `integration_task` 420; choice-reserve равен 180, меньше `free_conversation` 300. По first-fit такие шаги не помещаются и корзина систематически получает waiver. Одновременно schema не задаёт допустимые `step_type` для каждого `kind`, поэтому другая реализация может назвать integration контролируемым production за 120 секунд и получить другой план. Алгебраическая проверка shares не доказывает feasibility дискретного плана.

**Предлагаемая правка:** определить матрицу `kind → allowed step_type`, а затем одно правило для неделимого шага: разрешённый overshoot, общий pool после reservation либо minimum как достигнутая доля с валидируемой достижимостью. Добавить policy fixtures для 10/30 минут, первого занятия, отсутствующих корзин и каждого mode.

### RR2-6. Replan не определяет остаточный бюджет и полный lifecycle ревизий — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §2 diagram содержит только `PLANNED → PLANNED`, `PLANNED → CONSUMED`, `PLANNED → DISCARDED`; §4.2: replan «не отменяет уже предъявленные шаги» и создаёт новый `SESSION_COMPOSED`; `SessionBudget` хранит один `allocated{...}` и `total_seconds`.

**Почему дефект:** не сказано, включает ли новая revision уже выданные шаги в `allocated`, получает ли полный бюджет заново или только остаток, и может ли `CONSUMED` быть перепланирован/терминализован. При полном бюджете на каждой revision сессия превышает duration; при исключении старых шагов теряются session-level shares и diversity. У полностью выданного плана нет перехода `CONSUMED → DISCARDED` при finish/abandon. Метрики нескольких `SESSION_COMPOSED` затем не знают, какую revision считать.

**Предлагаемая правка:** определить session-cumulative ledger (`presented_seconds`, retained steps, remaining_seconds, cumulative bucket totals), разрешённые transitions для CONSUMED и формулу новой revision. Один session metric должен иметь однозначный источник при N replans.

### RR2-7. `claim_next_step` не имеет concurrency precondition для двух агентов — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §3b: `claim_next_step(session_id, idempotency_key)`; §4.2 требует atomic claim и cached retry, но CAS указан только для `replan(expected_revision)`. `wiki/OPEN.md` OPEN-11 сохраняет multi-aggregate CAS и same-key/different-payload как kernel-обязательства.

**Почему дефект:** idempotency защищает повтор одного ключа, но не два одновременных разных ключа от двух агентов. Без `expected_revision`/step precondition обе команды могут прочитать один «следующий» шаг; контракт не говорит, обязан ли второй получить следующий шаг, conflict или cached first claim. Если параллельно проходит replan, не определено, к какой revision относится claim. Ссылка на «атомарно» не задаёт наблюдаемого результата гонки.

**Предлагаемая правка:** задать CAS по session/plan delivery revision и uniqueness claim на `step_id`; перечислить outcomes гонок `next↔next` и `next↔replan`, включая identical retry. Payload hash idempotency должен включать session/revision.

### RR2-8. Fairness bound считается по revision и обещает показ, гарантируя лишь включение в план — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.5: `deferral_count` увеличивается, когда цель «была кандидатом ревизии и не вошла в план»; верхняя граница сформулирована как «не позже, чем через `|eligible| / reserved_steps_per_session` занятий»; reset происходит по `STEP_PRESENTED`.

**Почему дефект:** несколько replans в одной сессии увеличат count несколько раз, хотя bound измерен занятиями. Формула требует `ceil`, иначе при 2 целях и reserve=3 получается меньше одного занятия. Главное: reserve гарантирует admission в план, но не `STEP_PRESENTED`; abandon до шага оставляет цель невыданной, а утверждение «граница ожидания» звучит как гарантия предъявления. При ложном delivery из RR2-2 count, наоборот, обнулится без показа.

**Предлагаемая правка:** инкрементировать не более одного раза на цель за терминализованную/закрытую session composition epoch; использовать `ceil(|eligible| / reserved_steps_per_session)`; отдельно назвать guarantee admission и guarantee presentation, с условиями abandon/replan.

### RR2-9. Signal schema противоречит собственным типам expiry, а эффекты не входят в алгоритм — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.7 table задаёт для `too_repetitive`, `need_more_practice`, `prefer_different_context` поле «`expires_at` = +N сессий»; следующая MUST говорит, что session-based срок обязан быть `expires_after_session_seq` и смешивание запрещено. Precedence обещает: `need_more_practice` «повышает частоту», `too_repetitive` «понижает класс».

**Почему дефект:** один и тот же payload одновременно валиден и запрещён. Кроме того, тотальная classifier table §4.5 не имеет входа signal kind и не определяет, на сколько классов понизить/как повысить admission frequency, особенно при конфликте с `risk`. `record_signal` может породить probe, но для остальных видов не определено, применяется ли эффект сразу через replan или только в следующей сессии. Две реализации дадут разные планы и replay.

**Предлагаемая правка:** исправить union fields на `expires_after_session_seq`; дать точную таблицу transformation до/после classifier и момент вступления эффекта в силу. Если active plan меняется, это должна быть явная CAS/replan-команда, не скрытая мутация `record_signal`.

### RR2-10. Availability содержит размерностную ошибку и недетерминированную ветку состава — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §3 называет параметр `divergence_window_sessions: 6`; §4.7 определяет observed `sessions_per_week` как «число терминализованных сессий за `divergence_window_sessions` последних календарных недель»; далее при длинном перерыве composition «повышает долю `critical` … и понижает `growth` до его пола».

**Почему дефект:** значение с единицей sessions используется как количество weeks, а raw count за шесть недель назван sessions-per-week без деления на шесть. Ветка изменения состава не задаёт величину повышения critical, источник «медианного интервала», поведение при null/недостатке истории и перераспределение остальных корзин. Декларация «каждая ветка §4 имеет конкретное значение» поэтому неверна: две реализации с тем же event log и policy законно выберут разные shares.

**Предлагаемая правка:** разделить `window_weeks`/`min_sessions`, определить нормированную формулу observed frequency и no-data. Представить re-entry adjustment конкретной таблицей bp по mode или чистой функцией с фиксированным rounding.

### RR2-11. Метрики долей считают план, а не фактически проведённое занятие — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.3: `review_share = allocated.review / total_seconds`, `growth_rate = allocated.growth / total_seconds`; §4.10 повторяет эти формулы. При этом §4.6 подчёркивает: «`SESSION_COMPOSED` — план, не факт», а §4.2 разрешает несколько revisions и abandon.

**Почему дефект:** сессия может выдать два review-шага и завершиться/оборваться до growth; метрика всё равно отчитается по запланированной доле и не увидит фактическое вырождение урока в повторения — именно риск, ради которого 0.12 создавался. После replan неясно, брать первую, последнюю или сумму allocations. Для `calibration_error` один ReviewOutcome может агрегировать несколько attempts, но связь с конкретным `STEP_PRESENTED.predicted_retrievability` не задана. `backlog_age_p90` не фиксирует метод percentile/tie handling.

**Предлагаемая правка:** развести `planned_*` и `presented_*` metrics; policy-health/alerts считать по delivery ledger с правилами incomplete/abandoned/replanned sessions. Задать correlation `review_assignment_id ↔ presented prediction ↔ terminal outcome` и канонический percentile algorithm.

### RR2-12. Запрет binary float не охватывает собственные decision-пороги — MAJOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §3: `critical_floor_retrievability: 0.50`, `maintenance_floor_retrievability: 0.85`, `divergence_tolerance: 0.30`; §3 затем: «Двоичный float запрещён на всём пути» и ссылается на fixed Decimal scoring.

**Почему дефект:** запрет реализован только для `shares_bp`, тогда как float-пороги участвуют в classifier и availability branch. На граничных Retrievability/divergence разные YAML/runtime decimal conversions могут изменить класс или предложение availability; replay перестанет быть побитово воспроизводимым. Это не калибровка значений, а отсутствующий numeric representation contract.

**Предлагаемая правка:** хранить все вероятности/tolerance как Decimal strings с тем же context/rounding, что scoring, либо как целые fixed-point units/bp; validator должен запрещать YAML float для всех decision-bearing полей, не только shares.

## MINOR

### RR2-13. `SaturationState` теряет dimension и не использует собственную transfer-staleness policy — MINOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §2: `SaturationState` ключуется `target_ref`; `PlannedStep`/evidence работают с `(target_ref, dimension)`; policy содержит `transfer_check_staleness_days: 30`, а saturated predicate §4.6 использует только exposures, successes и contexts.

**Почему дефект:** частые recognition-показы могут сделать deferrable слабую production-dimension той же цели. `last_transfer_check_at` и её порог объявлены, но ни одна ветка их не читает, что противоречит claim тотальности policy.

**Предлагаемая правка:** ключевать saturation минимум `(target, dimension)` либо задать явную cross-dimension aggregation matrix; включить transfer-staleness в predicate/trace или удалить неработающий параметр из v1.

### RR2-14. Источники choice не покрывают объявленный `free_conversation` — MINOR

**Файл и раздел → точная цитата:** `wiki/modules/control.md` §4.3 определяет choice как «свободный разговор или тема, выбранная учеником» и policy содержит `free_conversation: 300`; §4.4 строит choice-кандидаты только из `goals[]`/личного словаря и рекомендации gate.

**Почему дефект:** у ученика без personal vocabulary/gate/подходящей goal choice может получить `NO_CHOICE_CANDIDATE`, хотя свободный разговор по определению доступен без target. Разные реализации либо создадут безусловный candidate, либо выдадут waiver.

**Предлагаемая правка:** явно добавить детерминированный free-conversation candidate и источник `topic_hint`, либо исключить его из v1 и признать choice только target-driven.

## QUESTION

### Q-1. Является ли system-replan учебным исходом ReviewAssignment? — QUESTION

Сейчас выбран ответ «да, `INSUFFICIENT_EVIDENCE`», но scheduler придаёт ему учебную семантику retry. Нужна продуктовая фиксация: cancellation не является outcome либо `reason=replanned` — отдельная тотальная ветка scheduler/metrics без learner penalty и retry.

### Q-2. Какой факт система вправе называть `STEP_PRESENTED`? — QUESTION

Если trusted tutor считается границей доставки, событие должно честно означать «выдано агенту» и recovery должен требовать повтор cached response. Если нужен факт «ученик увидел», необходим отдельный ack/наблюдаемый client event. Сейчас контракт одновременно использует первую механику и вторую семантику.

## Проверено, ок

- `control_policy` реально присутствует в registry kernel и Session Manifest; pinning/retention для control достижимы.
- Start и первая composition находятся в одной UoW; прежнего crash-window между ними нет.
- Mode-specific shares и явные waiver снимают прежнюю логическую невозможность первого занятия и `maintenance/re_entry`; замечание RR2-5 уже про дискретную исполнимость, не про отсутствие ветки.
- `PlannedStep` теперь действительно tagged union и выражает `review_assignment_id`, dimension, integration-роли, gate и probe.
- Risk проверяется раньше saturation/maintenance; `stake` и `stake_rank` определены для Topic и LexicalItem.
- Saturation потребляет существующие owner-events, фиксирует `context_id`, canonical sequence и dedup.
- No-negative для probe текстуально покрывает state, Mastery, Stability и schedule; дефект RR2-3 только в недостижимом provenance path.
- Public API возвращён; catalogue честно назван обязательством реализации, а не уже существующим полным артефактом.
- Safety-overlay не переоценивался: OPEN-14 остаётся открытым carrier для live replacement/correction, и control не объявляет его закрытым.
- Roadmap 0.12 оставлен `blocked`, OPEN-30 открыт, вертикальный срез не объявлен разблокированным. Это корректная консервативная позиция до подтверждения.

## Вердикт

**FAIL** — в `control.md` три прежних локальных механизма добавлены, но R-1 не снят системно: owner-спеки предписывают взаимоисключающие эффекты `session next`. После синхронизации delivery-протокола остаются MAJOR, которые нужно закрыть до реализации policy: observable delivery boundary, Attempt→step provenance, replan disposition, discrete budget feasibility, concurrency и детерминированные availability/metrics/numeric rules.
