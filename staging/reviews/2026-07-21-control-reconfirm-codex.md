# Повторное подтверждающее ревью control 0.12 (5-й прогон)

## 1. Вердикт

**PASS** — B=0, M=0, m=0, Q=0. Блокирующие расхождения системно сняты; новых исполнимых дефектов не найдено. Числовую калибровку `control_policy@1` и OPEN-27 не оценивал.

## 2. Проверка находок 4-го прогона

| Находка | Статус | Проверка и соседний контракт |
|---|---|---|
| B-1 | снята | `control.md` §3 прямо разрешает overshoot неделимым шагом, а §4.4 резервирует полы в том же режиме. Для 1800 s integration floor=270, шаг 420 s допустим и помещается в общий остаток. Матрица integration допускает `integration_task`; его стоимость 420 определена в §3. |
| B-2 | снята | `record_signal(signal, session_id?, ...)` объявлен в API; `too_easy` только создаёт `PROBE_REQUESTED`, а `PlannedStep{kind: probe}` появляется лишь при `compose_session`/явном `replan` (`control.md` §4.7). `SIGNAL_CONSUMED` атомарен с добавлением шага; при нехватке бюджета фиксируется `PROBE_BUDGET_UNAVAILABLE`, сигнал не расходуется. `flows/session.md` §73–80 требует явного `session.replan`. |
| B-3 | снята | `control.md` §4.2, `evidence.md` §4.3, `scheduler.md` §3 и `lessons.md` §4/§4b единообразно задают `ReviewOutcome | CANCELLED`; `CANCELLED` — terminal no-op без retry и scoring. `lessons.md` §4 требует именно эту диспозицию для `finish`, а replan пишет `CANCELLED(reason=replanned)`. |
| M-1 | снята | `glossary.md` определяет `STEP_PRESENTED` как выдачу **тьютору**, не ученику; то же MUST повторено в `control.md` §4.6. |
| M-2 | снята | `evidence.md` §3 и §4.4 оставляют единственную сигнатуру `record_attempt(step_id, ...)`; target/dimension/origin выводятся движком из предъявленного шага. |
| M-3 | снята | `control.md` §4.2/§4.3a разделяет `revision_planned_review_share`, `effective_review_share = presented + planned` и `presented_review_share`; метрики читаются из `DeliveryLedger`. |
| M-4 | снята | `control.md` §4.2 требует инкремент `plan_version` при каждой успешной мутации `next`/`replan`; lessons и flow передают `expected_plan_version` в обе команды. |
| M-5 | снята | `control.md` §4.4 задаёт `ceil`-границу, admission отдельно от presentation и изменение `deferral_count` не более одного раза за сессию. |
| M-6 | снята | `control.md` §4.7 разделяет `expires_at` и `expires_after_session_seq`, задаёт монотонный `session_seq` и точные преобразования сигналов. |
| M-7 | снята | `control.md` §4.7a задаёт целочисленный `sessions_per_week_milli`, `divergence_ppm` и формулу с `floor`; все decision-bearing поля integer. |
| N-1 | снята | Проверены ссылки: используются существующие §4.2, §4.3, §4.5, §4.7, §4.10; ссылок на §4.11 не найдено. Соседние specs ссылаются на существующий `evidence.md` §4.3. |

## 3. Новые дефекты (слой 2)

Не обнаружены. `plan_version` согласован между control API, lessons facade и `flows/session.md`; `next` и `replan` требуют CAS-токен. Роли effective/revision_planned/presented не смешаны. Ветка `CANCELLED` тотальна по причине `replanned` и явно no-op для scheduler/scoring. Все `kind → step_type` матрицы имеют стоимость в §3 (`gate_item`, `free_conversation`, `integration_task` и остальные перечислены).

## 4. Сквозная исполнимость (слой 3)

1. **Первое занятие, 30 минут, без освоенных целей:** план собирается: свободный разговор — безусловный кандидат `choice` (`control.md` §4.4, шаг 3b), поэтому отсутствие integration-пар не даёт пустого плана.
2. **`maintenance`, growth=0:** режим разрешён, review-пол и choice-пол имеют конкретные значения; тот же безусловный choice-кандидат позволяет пройти pipeline без нового материала.
3. **`too_easy → replan → probe → attempt`:** сигнал требует предъявленного шага, создаёт probe request; явный replan добавляет probe либо возвращает `PROBE_BUDGET_UNAVAILABLE`. Probe получает `origin=control_probe`, и no-negative правило не понижает состояние.
4. **Срединный replan:** выпавший непредъявленный review закрывается `CANCELLED(reason=replanned)` в той же UoW; scheduler retry не назначает, а `finish` видит терминальную диспозицию и не блокируется.

## 5. Проверено, ок

Проверены `wiki/modules/control.md`, `evidence.md`, `scheduler.md`, `lessons.md`, `wiki/flows/session.md`, `wiki/glossary.md`; канон не изменялся.

## 6. Можно ли снимать `blocked`

**Да.** По результатам независимого подтверждения блок снят; статус 0.12 можно переводить из `blocked`.
