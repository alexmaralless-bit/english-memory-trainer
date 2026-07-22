# Flow: учебная сессия

> **Status**: current
> **Last updated**: 2026-07-21
> **Sources**: [[../product/learning-model]] · `docs/design-direction.md` §1 · Concept Gate 2026-07-19 (три развилки, [PD-2026-07-19]) · концепт одобрен («ок»)
> **Роль**: спинной сценарий (roadmap 0.8). Выводит межмодульные контракты для 0.3–0.5 и 0.7. Flow не владеет поведением: полные правила фиксируются в спеках модулей, здесь — сценарий и выведенные требования.

---

## Решения этого flow [PD-2026-07-19]

1. **Конфликт активной сессии**: `start` при существующей незавершённой сессии возвращает конфликт с вариантами — `resume` или закрыть старую как `ABANDONED` и начать новую. Выбор делает ученик через агента; CLI сам ничего не бросает и не продолжает. **`abandon_and_start` — это две независимые идемпотентные команды** (`session abandon`, затем `session start`), не одна атомарная (foundation C-1): crash между ними оставляет старую `ABANDONED` и нет активной сессии; следующий `start` создаёт новую — benign ([[../platform/foundation]] §3.4).
2. **Finish-postconditions средние**: каждый записанный attempt финализирован; каждая review-цель имеет терминальную диспозицию — ReviewOutcome либо системную отмену `CANCELLED`; summary создан. Выполнять все цели не обязательно — обязательно честно закрыть каждую допустимой веткой.
3. **CLI-именование**: `trainer session ...` (не `lesson` из брифа) — консистентно с [[../glossary]]. Бриф и build-prompt в этой части superseded.

## Участники

- **Ученик** — ведёт разговор, выполняет задания, принимает решения (resume/abandon, согласие на re-entry).
- **Агент** — ведёт сессию по Session Manifest, генерит упражнения по policies, фиксирует всё через CLI.
- **Движок (`trainer` CLI)** — выдаёт манифест, валидирует и записывает evidence, единолично меняет состояние.

## Состояния сессии

`STARTED` (создана, манифест выдан) → `IN_PROGRESS` (первая фиксация) → `FINISHED` | `ABANDONED`. Переход **`STARTED → ABANDONED` допустим** (только что созданную сессию можно бросить до первой фиксации) [ревью D-4]. Полный lifecycle и Attempt state machine — спека `modules/lessons` (0.5, [[../OPEN]] OPEN-10).

**Терминализация — атомарный commit authoritative state** для `FINISHED` и `ABANDONED`. Важное различие двух видов работы [rereview A-R2/E-R1]:

- **FINISHED** требует **пустого pending-set** как precondition: все attempts финализированы, все review-цели имеют ReviewOutcome либо `CANCELLED`. Если pending есть — finish отклоняется (это НЕ авто-закрытие).
- **ABANDONED** наоборот **атомарно преобразует** pending в явные `INSUFFICIENT_EVIDENCE(reason=abandoned)`, re-entry блок получает свой outcome.
- В обоих случаях **одной ACID-транзакцией** коммитятся только authoritative state + events + outbox; `summary` — в той же UoW либо идемпотентная derived-проекция. **Obsidian-проекция обновляется post-commit** через outbox с retry/catch-up и rebuild — файловую projection нельзя включать в ту же ACID-транзакцию (rereview E-R1). Crash после commit не теряет данные: проекция досоздаётся из state.

- **MUST**: ABANDONED сохраняет зафиксированное evidence, но **не даёт обхода**: «две быстрые abandon-сессии» сами по себе не образуют двух независимых сессий для rubric-повторяемости ([[../product/learning-model]] §3, [[../OPEN]] OPEN-7/OPEN-10).

## Сценарий

```mermaid
sequenceDiagram
    autonumber
    actor L as Ученик
    participant A as Агент
    participant T as trainer CLI

    A->>T: session start [--duration N]
    alt есть незавершённая сессия
        T-->>A: конфликт {error_code, allowed_actions: resume | abandon_and_start}
        A->>L: продолжить прошлую или начать новую?
        L-->>A: выбор
        A->>T: session resume | session abandon + session start
    end
    T-->>A: Session Manifest + SessionPlan {plan_version: 1, review-цели[review_id], required_skills, pinned versions}

    opt re-entry рекомендован (перерыв / упавшая Retrievability)
        A->>L: предлагает быстрое повторение или короткий тест
        L-->>A: согласие или отказ
        A->>T: результат re-entry блока или явный отказ (без последствий)
    end

    Note over T: план занятия собран в той же UoW, что и старт ([[../modules/control]] §4.2)

    loop разговор идёт по плану, но формулировки свободны
        opt агент хочет посмотреть, не расходуя шаг
            A->>T: session peek
            T-->>A: следующий шаг + plan_version V (ничего не меняется)
        end
        A->>T: session next --expected-plan-version V --idempotency-key K
        T->>T: пометить шаг выданным + ledger + plan_version++ + STEP_PRESENTED (одна UoW)
        T-->>A: PlannedStep {step_id, kind, …} + plan_version V2
        A->>L: диалог / упражнение / повторение — по этому шагу
        L-->>A: ответ (текст)
        A->>T: attempt record --step STEP_ID + observations (raw answer, span, hints, rubric-obs)
        T->>T: AttemptAssessment (не терминальна); origin выводится из kind шага
        A->>T: review close (когда цель отработана) · observed record (по ходу)
        opt ученик сообщает too_easy
            A->>T: signal too_easy --target TARGET --session ID
            T-->>A: probe_id + next_action: session.replan + current_plan_version V2
        end
        opt план устарел: записан сигнал, safety-исключение, шаги кончились
            A->>T: session replan --session ID --expected-plan-version V2 --idempotency-key R
            T->>T: composition_revision++ + plan_version++; выпавшие невыданные review отменяются
            T-->>A: новый план + plan_version V3 (probe включён, если помещается)
        end
    end

    A->>T: session finish [--summary-draft]
    T->>T: проверка pending-set пуст → ACID commit (state+events+outbox) → summary
    T-->>A: summary (engine-generated) + рекомендация следующей сессии
    Note over T: Obsidian-проекция — post-commit через outbox (retry/rebuild)
    A->>L: итоги: что получилось, что повторим, что дальше
```

## Правила сценария

- **MUST — агент фиксирует наблюдения, не оценки** [ревью A-1/C-1]: агент передаёт raw answer, span-ссылки, hints, rubric-observations (наблюдение ссылается на rubric-criterion и span, не готовый флаг — [[../product/learning-model]] §3); итоговый outcome вычисляет движок. Клиентская готовая классификация запрещена.
- **MUST — AttemptAssessment ≠ ReviewOutcome** [rereview A-R1]: на один `review_id` может быть несколько attempts; per-attempt оценка (AttemptAssessment) не терминальна. ReviewAssignment получает ровно одну терминальную диспозицию: один ReviewOutcome либо `CANCELLED`; correction не создаёт второй outcome ([[../modules/evidence]] §4.3).
- **MUST — safety при доставке** [rereview G-R1]: движок проверяет `production_eligible` по **active** policy внутри UoW `session next`, до `STEP_PRESENTED`; ставший `avoid`/`obsolete`/вне-контекста item не выдаётся, а команда возвращает `PRECONDITION_FAILED` с `next_action: session.replan` ([[../modules/curriculum]] §5, [[../OPEN]] OPEN-14).
- **MUST**: агент фиксирует attempt через CLI сразу после завершения задания/проверки — инкрементальность даёт устойчивость к потере чата (сессия остаётся `IN_PROGRESS`, продолжение — отдельный flow `continuation`).
- **MUST — summary генерирует движок** [ревью E-2]: summary создаётся движком после commit терминализации; агент может передать `--summary-draft` как вход. Postcondition «summary создан» не цикличен: его выполняет сам finish, а не предварительное условие входа.
- **MUST — finalized attempt** [ревью G-9]: attempt имеет состояние; незавершённый (draft) attempt не участвует в scoring. При обрыве между attempt и его завершением resume видит draft и предоставляет идемпотентный finalize/recover (Attempt lifecycle — 0.5, [[../OPEN]] OPEN-10).
- **MUST**: Session Manifest содержит `required_skills` с версиями и **pinned versions** curriculum/policy; агент не полагается на implicit invocation.
- **MUST**: каждая review-цель к моменту finish имеет ReviewOutcome либо `CANCELLED`; replan-отмена не маскируется под `INSUFFICIENT_EVIDENCE` и не создаёт retry.
- **MUST**: отказ от re-entry и невыполнение рекомендаций ничего не блокируют ([[../product/learning-model]] §7).
- **MUST — причины отклонения finish** [rereview G-R2]: для **валидной команды к текущей ревизии активной сессии** finish отклоняется только из-за бизнес-postconditions (непустой pending-set). **Отдельно** — общие lifecycle/concurrency/idempotency ошибки: stale session revision, несуществующая/чужая сессия, уже терминальное состояние, key collision; identical retry возвращает cached result, не ошибку. Coarse fence закрыт [PD-2026-07-22] ([[../modules/lessons]] §2). Все — с `error_code`, причинами и `next_action`.
- **MUST NOT**: агент меняет scores, состояния тем или расписание — только записывает наблюдения; вычисление и пересчёт делает движок на терминализации.

## Выведенные контракты (фиксируются в спеках модулей)

| Модуль (спека) | Обязан предоставить |
|---|---|
| `lessons` (0.5) | Session + Attempt lifecycle (вкл. `STARTED → ABANDONED`); конфликт start → allowed_actions; атомарная терминализация; engine-generated summary (OPEN-10) |
| `scheduler` (0.4) | детект re-entry; due review-цели в манифест; назначение интервалов (elapsed 24h) на терминализации |
| `evidence` (0.4) | запись attempt + observations с семантической идентичностью (OPEN-7); фиксация error/vocabulary/chunk |
| `scoring` (0.4) | вычисление review outcome и пересчёт на терминализации (finish и abandon) по evidence |
| `curriculum` (0.3) | рекомендации тем с флагом recommended/early; pinned versions в манифест |
| `scoring` | XP award-once и streak по локальной дате на терминализации ([[../modules/scoring]] §7). `learner` их только читает для `trainer status` — расчёт в двух модулях разъехался бы |
| `memory` (0.6) | обновление Obsidian-проекции на терминализации |
| `cli` (0.7) | `trainer session start/peek/next/replan/resume/abandon/finish`, `attempt record`; JSON, `plan_version`, `error_code` + `allowed_actions` + `next_action` |
| `adapters`/skills (0.7) | session-skill по этому flow; протокол фиксации наблюдений (не оценок) |

## Открытые вопросы

Механизмы этого flow закрыты в принятых контрактах: evidence identity/observations, Attempt/Session lifecycle, coarse idempotency/concurrency fence, active safety overlay и re-entry scheduler. Остаточных OPEN у flow нет.

## История изменений

- **2026-07-21**: flow сведён к исполнимому `peek → next(expected plan_version) → attempt --step → signal → replan(expected plan_version)`; finish принимает `ReviewOutcome | CANCELLED`.
- **2026-07-20 (4)**: foundation-review — `abandon_and_start` уточнён как две независимые идемпотентные команды с benign recovery (C-1).
- **2026-07-19 (3)**: rereview — FINISHED требует пустой pending-set, ABANDONED преобразует pending (A-R2); Obsidian post-commit через outbox, не в ACID (E-R1); AttemptAssessment vs terminal ReviewOutcome (A-R1); причины отклонения finish разделены на бизнес vs lifecycle/concurrency (G-R2); safety при доставке production из live-манифеста (G-R1).
- **2026-07-19 (2)**: red-team триаж — агент фиксирует наблюдения, движок вычисляет классификацию (A-1/C-1); engine-generated summary без цикличности (E-2); атомарная терминализация FINISHED/ABANDONED, закрытие pending целей, запрет обхода (C-2/G-4/G-6); `STARTED → ABANDONED` и команда `session abandon` (D-4/D-5); finalized attempt и recover (G-9); pinned versions в манифесте.
- **2026-07-19**: создан по Concept Gate: конфликт start через выбор, средние finish-postconditions, CLI-именование `session`. Все решения [PD-2026-07-19].
