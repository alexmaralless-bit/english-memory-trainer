# Модуль: scheduler

> **Status**: current
> **Last updated**: 2026-07-20
> **Sources**: [[../product/learning-model]] §7 · [[scoring]] · [[../flows/session]] · review triage journals (OPEN-18) · часть контракта 0.4
> **Bounded context**: `src/english_trainer/scheduler/`

> Спека — **target**. Интерфейс scheduler отделён от формулы — базовая формула MVP заменяется FSRS без смены доменной модели ([[../product/learning-model]] §7). Термины — [[../glossary]]. Часть контракта 0.4.

---

## 1. Назначение

Модуль решает **когда повторять**: назначает интервалы, ведёт review_status (`not_due/due/overdue`), выдаёт due-цели в Session Manifest, формирует re-entry рекомендацию, применяет overdue→AT_RISK по policy. Никогда не блокирует темы — только рекомендует.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `ReviewSchedule` | план повторения target | target, dimension, `next_review_at`, interval_index, last_outcome |
| `review_status` | scheduling-ось | `not_due` / `due` / `overdue` (вычисляется из времени) |

Review_status — **не** knowledge state ([[scoring]] §3); operational, управляется часами.

## 3. Модель интервалов [mvp]

- **MUST**: базовая последовательность `1 → 3 → 7 → 14 → 30 → 60 → 120 → 180` дней (*tunable*), адаптируется по outcome: успех (CONFIRMED/RECOVERED) — шаг вперёд; REGRESSION — шаг назад/сброс; PROGRESS — удержание. Интервал считается по **прошедшему времени** (elapsed 24h), не по календарю.
- **MUST — интерфейс отделён от формулы**: scheduler потребляет Retrievability/Stability из [[scoring]] и `target_recall` (*tunable*, дефолт 0.9); конкретная формула next-review за интерфейсом, FSRS — `[post-mvp]` без смены модели.
- **MUST**: `due` когда `now ≥ next_review_at`; `overdue` когда просрочка > `overdue_factor × interval` (*tunable*).

## 4. re-entry и overdue→AT_RISK (OPEN-18) [PD-2026-07-19]

- **MUST — re-entry trigger**: движок формирует re-entry рекомендацию, если перерыв > `gap_threshold` дней **или** средняя Retrievability приоритетных тем < `retrievability_floor` (оба *tunable*, scheduler-policy). Агент предлагает re-entry первым шагом; отказ допустим, ничего не блокирует и не штрафуется; результат обновляет Retrievability и план.
- **MUST — overdue→AT_RISK**: просрочка сверх `at_risk_overdue_threshold` (*tunable*) переводит knowledge state в `AT_RISK` по versioned policy (clock-триггер разрешён явно). Это единственный не-evidence вход в AT_RISK ([[scoring]] §3).

## 5. Backlog и подача в манифест

- **MUST NOT — не блокировать**: overdue backlog влияет только на рекомендации и состав Session Manifest, **не** на доступность тем ([[../product/learning-model]] §1).
- **MUST**: scheduler выдаёт в манифест due/overdue-цели как `ReviewAssignment` (review_id, target, dimension, режим, критерии, pinned versions) — приоритет по Retrievability, просрочке, слабым dimensions, prerequisites следующей темы, retention-гейтам.
- **MUST**: повторение бывает явным, подмешанным (`review_id`) и скрытым (conversation evidence) — все через [[evidence]].

## 6. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer review due --format json` | список due/overdue целей с приоритетом |

## 7. Границы

- **depends on**: scoring (Retrievability/Stability/состояния), curriculum (target refs/pinned policy), kernel (Clock, elapsed-время).
- **events published**: `REVIEW_SCHEDULED`, `REVIEW_DUE`, `RE_ENTRY_RECOMMENDED`.
- **consumed by**: lessons (манифест), evidence (закрытие цели → перепланирование), memory (проекция next-review).

## 8. Открытые вопросы

Контракт **закрывает** OPEN-18 (scheduler-policy: re-entry trigger, overdue→AT_RISK, адаптация интервалов) на уровне модели. Остаётся калибровка *tunable*-порогов и переход на FSRS — `[post-mvp]`.

## История изменений

- **2026-07-20**: создан (контракт 0.4, часть 3). Интервальная модель с интерфейсом под FSRS; review_status; re-entry trigger и overdue→AT_RISK пороги [PD-2026-07-19]; backlog не блокирует. Закрывает OPEN-18 (модель), калибровка отдельно.
