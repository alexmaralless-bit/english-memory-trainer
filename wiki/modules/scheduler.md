# Модуль: scheduler

> **Status**: current
> **Last updated**: 2026-09-22
> **Sources**: [[../product/learning-model]] §7 · [[scoring]] · [[../flows/session]] · review triage journals (OPEN-18) · часть контракта 0.4
> **Bounded context**: `src/english_trainer/scheduler/`

> Спека — **target**. Интерфейс scheduler отделён от формулы — базовая формула MVP заменяется FSRS без смены доменной модели ([[../product/learning-model]] §7). Термины — [[../glossary]]. Часть контракта 0.4.

---

## 1. Назначение

Модуль решает **когда повторять**: назначает интервалы, ведёт review_status (`not_due/due/overdue`), выдаёт due-цели в Session Manifest, формирует re-entry рекомендацию, применяет overdue→AT_RISK по policy. Никогда не блокирует темы — только рекомендует.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `ReviewSchedule` | план повторения target | target, dimension, `schedule_epoch`, `next_review_at`, interval_index, last_outcome, `ladder_index?` (ступень лестницы §3a), `permanent_interleave` [PD-2026-09-22] |

- **MUST — `schedule_epoch`** [rereview R-1]: монотонный счётчик расписания на пару (target, dimension); инкрементируется при каждом **новом** назначении интервала. Входит в ключ идемпотентности и в payload события — позволяет отличить легитимное новое пересечение порога от дубля прежнего.
| `review_status` | scheduling-ось | `not_due` / `due` / `overdue` (вычисляется из времени) |

Review_status — **не** knowledge state ([[scoring]] §3); operational, управляется часами.

## 3. Модель интервалов

- **MUST**: базовая последовательность `1 → 3 → 7 → 14 → 30 → 60 → 120 → 180` дней (*tunable*), адаптируется по outcome: CONFIRMED/RECOVERED — шаг вперёд; REGRESSION — шаг назад/сброс; PROGRESS — удержание; **`INSUFFICIENT_EVIDENCE` — hold** для любого значения `reason`, включая `abandoned` (интервал не сдвигается, назначается короткий retry `retry_days`, *tunable* дефолт 1) [ревью 0.4-7]; неизвестный `reason` сохраняется для аудита, но не создаёт новую scheduler-ветку. **`CANCELLED` — не исход**: расписание не трогается вовсе, retry не назначается [RR2-4]. Интервал по **прошедшему времени** (elapsed 24h), не по календарю.
- **MUST — интерфейс отделён от формулы**: scheduler потребляет Retrievability/Stability из [[scoring]] и `target_recall` (*tunable*, дефолт 0.9); конкретная формула next-review за интерфейсом; FSRS — MAY, замена формулы без смены модели.
- **MUST**: `due` когда `now ≥ next_review_at`; `overdue` когда просрочка > `overdue_factor × interval` (*tunable*).

## 3a. `scheduler@2` — короткая лестница закрепления и постоянный ярус [PD-2026-09-22]

Базовая таблица §3 не меняется; `scheduler@2` добавляет к ней **фазу перед** ней и одно правило выхода из неё.

```yaml
scheduler_policy:
  version: 2
  relearning_ladder_days: [1, 2, 4]
  # базовая таблица §3 без изменений
```

- **MUST — лестница идёт перед базовой таблицей** [PD-2026-09-22, PD-D]: после первого предъявления цели (`STEP_PRESENTED` по ней) её первые успешные повторения назначаются по `relearning_ladder_days` — 1, затем 2, затем 4 дня. Только пройдя все ступени, цель входит в базовую последовательность `1 → 3 → 7 → 14 → …` с её первого элемента. Мотив — [[../product/learning-model]] §7: недельный интервал после двух подтверждений слишком велик для морфосинтаксиса.
- **MUST — провал повторяет ту же ступень**: неуспешная ступень лестницы (`REGRESSION` либо outcome ниже `CONFIRMED`) назначает **ту же** ступень заново, а не откатывает цель и не продвигает её. `schedule_epoch` при этом инкрементируется как при любом новом назначении (§2).
- **MUST — ветки исходов не меняются**: `INSUFFICIENT_EVIDENCE` внутри лестницы остаётся **hold** с коротким `retry_days`, `CANCELLED` по-прежнему **не исход** и расписания не трогает вовсе. Лестница — это другая последовательность чисел, а не другая семантика исходов.
- **MUST — артикльные фреймы не покидают очередь** [PD-2026-09-22, PD-F]: фрейм артикльного яруса ([[../product/lexical-system]] §1c) несёт `permanent_interleave: true`. Такая цель, пройдя базовую лестницу до её конца, **не выбывает** из due-очереди, а переназначается на **последний** базовый интервал (180 дней) бессрочно. Знание артиклей без постоянной практики распадается, поэтому «дошёл до конца таблицы» для них не означает «больше не нужно». Правило действует и при `MASTERED`: состояние знания оно не меняет, меняет только расписание.
- **MUST — постоянный ярус не вытесняет остальное**: цели с `permanent_interleave` подчиняются обычному приоритету §5 и обычному `review_max` бюджета ([[control]] §3); отдельной квоты у них нет. Ограничение их числа в одном занятии — [[../OPEN]] OPEN-38.

## 4. re-entry и overdue→AT_RISK (OPEN-18) [PD-2026-07-19]

- **MUST — re-entry trigger**: движок формирует re-entry рекомендацию, если перерыв > `gap_threshold` дней **или** средняя Retrievability приоритетных тем < `retrievability_floor` (оба *tunable*, scheduler-policy). Агент предлагает re-entry первым шагом; отказ допустим, ничего не блокирует и не штрафуется; результат обновляет Retrievability и план.
- **MUST — оба исхода re-entry достижимы через CLI** [R-7]: **результат** блока — обычные attempts (`trainer attempt record`), потому что это evidence; **явный отказ** — `trainer reentry decline`, потому что отказ attempt'ом не является и иначе не имеет способа быть сохранённым. Идемпотентность — по `(learner, recommendation_id)`. Отказ не влияет ни на Mastery, ни на XP.
- **MUST — overdue→AT_RISK как replayable факт** [ревью 0.4-2, BLOCKER]: при пересечении порога `at_risk_overdue_threshold` (*tunable*) scheduler-sweep эмитит **append-only событие** `OVERDUE_AT_RISK_TRIGGERED {target, dimension, schedule_epoch, boundary_at, next_review_at, pinned_scheduler_policy}`. `boundary_at` = детерминированный момент пересечения (из `next_review_at` + threshold), **не** wall-clock запуска sweep. **Replay применяет событие, а не текущее время** → historical AT_RISK детерминирован.
  - **MUST — идемпотентность sweep** [rereview R-1]: ключ идемпотентности — `(target, dimension, schedule_epoch)`; повторный sweep не эмитит дубль, а новое расписание (новый `schedule_epoch`) даёт легитимное новое событие.
  - **MUST — pin scoring policy при применении** [rereview R-1]: событие pin-ит scheduler-policy; **результирующий `STATE_TRANSITION` (scoring) pin-ит scoring policy**, по которой переход применён — иначе активация scoring policy между sweep и apply дала бы разные исходы из одного факта. Trigger и применение связаны `causation_id` и коммитятся в **одной UoW** ([[../platform/foundation]] §3.7).

## 5. Backlog и подача в манифест

- **MUST NOT — не блокировать**: overdue backlog влияет только на рекомендации и состав Session Manifest, **не** на доступность тем ([[../product/learning-model]] §1).
- **MUST — детерминированный порядок** [ревью 0.4-7]: scheduler выдаёт в манифест due/overdue-цели как `ReviewAssignment` (review_id, target, dimension, режим, критерии, pinned versions). Приоритет — **canonical tuple** с явным порядком ключей: `(retrievability asc, curriculum_priority_rank asc, is_prereq_of_next desc, weakest_dimension_gap desc, overdue_days desc, target_id asc, dimension_id asc)` [PD-2026-07-20, OPEN-26]. Ведёт **риск утраты**, а не срок простоя: прежний порядок начинался с `overdue_days`, из-за чего периферийная единица, просроченная на 90 дней, обгоняла базовый навык с Retrievability 0.3, просроченный на два. Срок теперь разводит близкие случаи, а не задаёт порядок. **Это промежуточная мера**: лексикографический tuple в принципе не выражает конъюнкцию «риск И ставка», поэтому 0.12 заменяет его классами срочности ([[control]] §4.5), где оба сигнала обязательны одновременно. Два последних ключа — стабильный tie-breaker: у одного target может быть несколько due-dimensions, поэтому `target_id` **недостаточен** (rereview R-2). Порядок не зависит от SQLite/query order; покрыт тестом equal-priority/same-target.
- **MUST**: повторение бывает явным, подмешанным (`review_id`) и скрытым (conversation evidence) — все через [[evidence]].

## 6. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer review due --format json` | список due/overdue целей с приоритетом |

## 7. Границы

- **depends on**: scoring (Retrievability/Stability/состояния), curriculum (target refs/pinned policy), kernel (Clock, elapsed-время).
- **events published**: `REVIEW_SCHEDULED`, `REVIEW_DUE`, `RE_ENTRY_RECOMMENDED`, `OVERDUE_AT_RISK_TRIGGERED`.
- **events consumed**: `REVIEW_OUTCOME`; `REVIEW_ASSIGNMENT_CANCELLED` — явный terminal no-op без изменения schedule/retry.
- **MUST — `REVIEW_DUE` это идемпотентное уведомление, не источник истины** [P0-Q2]: `due` — **вычисляемый** статус (`now ≥ next_review_at`), и потребители обязаны выводить его из расписания и Clock, а не из факта получения события. Событие несёт `boundary_at` (детерминированный момент пересечения, не wall-clock рассылки) и идемпотентно по ключу `(target_id, dimension_id, schedule_epoch)`: повторная рассылка не создаёт второго факта. Трактовать его как истину означало бы два источника статуса с разной задержкой. Ср. `OVERDUE_AT_RISK_TRIGGERED` — тот, наоборот, **является** фактом: он меняет knowledge state и потому append-only и replayable ([[scoring]] §3).
- **consumed by**: lessons (манифест), evidence (закрытие цели → перепланирование), memory (проекция next-review).

## 8. Открытые вопросы

- **OPEN-38**: нужен ли потолок числа `permanent_interleave`-целей в одном занятии (§3a) → [[control]] после эксплуатации.

Контракт **закрывает** OPEN-18 (scheduler-policy: re-entry trigger, overdue→AT_RISK, адаптация интервалов) на уровне модели. Остаётся калибровка *tunable*-порогов; переход на FSRS — MAY (замена формулы за интерфейсом).

## История изменений

- **2026-09-22**: [PD-2026-09-22] добавлен §3a — `scheduler@2`: короткая лестница закрепления `relearning_ladder_days: [1, 2, 4]` **перед** базовой таблицей, провал повторяет ту же ступень; артикльные фреймы получают `permanent_interleave: true` и после базовой лестницы переназначаются на последний базовый интервал вместо выбывания. Ветки `INSUFFICIENT_EVIDENCE`/`CANCELLED` не изменены. Потолок яруса на занятие — OPEN-38.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). FSRS — MAY (замена формулы за интерфейсом).
- **2026-07-21**: `CANCELLED` закреплён как отдельное событие-terminal no-op; ветка `INSUFFICIENT_EVIDENCE` тотальна по `reason`; исправлена ссылка на control §4.5.
- **2026-07-20 (3)**: 0.4-rereview — `schedule_epoch` в ReviewSchedule/событии/ключе идемпотентности + pin scoring policy в STATE_TRANSITION и одна UoW (R-1); tie-break расширен `dimension_id` (R-2).
- **2026-07-20 (2)**: 0.4-review триаж — overdue→AT_RISK стал replayable-событием `OVERDUE_AT_RISK_TRIGGERED` с идемпотентным sweep (BLOCKER 0.4-2); добавлена ветка `INSUFFICIENT_EVIDENCE` (hold+retry, 0.4-7); canonical priority tuple со стабильным tie-breaker `target_id` (0.4-7).
- **2026-07-20**: создан (контракт 0.4, часть 3). Интервальная модель с интерфейсом под FSRS; review_status; re-entry trigger и overdue→AT_RISK пороги [PD-2026-07-19]; backlog не блокирует.
