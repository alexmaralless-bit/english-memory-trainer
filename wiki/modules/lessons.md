# Модуль: lessons

> **Status**: current
> **Last updated**: 2026-07-22
> **Sources**: [[../flows/session]] · [[../flows/continuation]] · [[evidence]] · [[../platform/foundation]] (UoW, CAS, outbox) · Concept Gate 0.5 2026-07-20 (3 развилки, [PD-2026-07-20]) · часть контракта 0.5
> **Bounded context**: `src/english_trainer/lessons/`

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — [[../glossary]]. Часть контракта 0.5 (lessons + [[assessments]]).

---

## 1. Назначение

Модуль владеет **жизненным циклом занятия**: сессия, Attempt, терминализация. Он выдаёт Session Manifest, принимает фиксации, решает, когда сессия завершена, и атомарно применяет завершение. Бизнес-правила поверх kernel-механизмов (UoW/CAS/idempotency); scoring и расписание — не здесь.

## 2. Session lifecycle

```mermaid
stateDiagram-v2
    [*] --> STARTED
    STARTED --> IN_PROGRESS: первая фиксация
    STARTED --> ABANDONED: session abandon / stale
    IN_PROGRESS --> FINISHED: session finish
    IN_PROGRESS --> ABANDONED: session abandon / stale
```

- **MUST**: конфликт `start` при активной сессии → `{error_code, allowed_actions: resume | abandon_and_start}`; выбор делает ученик. `abandon_and_start` — две независимые идемпотентные команды ([[../flows/session]], foundation §3.4).
- **MUST — stale-сессия как replayable факт** [PD-2026-07-20]: сессия без активности дольше `stale_session_days` (*tunable*, дефолт 7) терминализуется как `ABANDONED`. Переход эмитится **append-only событием** `SESSION_STALE_ABANDONED {session_id, boundary_at, last_activity_at, pinned_lessons_policy}`, где `boundary_at` — детерминированный момент пересечения (из `last_activity_at` + порог), **не** wall-clock запуска sweep. Replay применяет событие, а не текущее время. Sweep идемпотентен по `session_id` (сессия терминальна ровно один раз).
- **MUST**: терминальные состояния окончательны: `finish`/`resume`/`abandon` на терминальной сессии — стабильная ошибка; identical retry возвращает cached result (foundation §3.4).

## 3. Attempt lifecycle [PD-2026-07-20]

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> recorded: ответ + наблюдения зафиксированы
    recorded --> assessed: движок посчитал AttemptAssessment
```

- **MUST**: три состояния — `draft` (начат, не доведён), `recorded` (raw answer + observations сохранены), `assessed` (движок вычислил AttemptAssessment, [[evidence]]). Разделение `recorded`/`assessed` нужно для recovery: крэш между фиксацией и оценкой различим.
- **MUST**: в scoring участвует только `assessed`; `draft` и `recorded` — нет.
- **MUST — finalize/recover**: `finalize_attempt` идемпотентен; при resume сессия отдаёт незавершённые attempts с их состоянием, и `recover` доводит `draft`→`recorded`→`assessed` без дублей (kernel idempotency, OPEN-11).

## 4. Терминализация (finish / abandon)

- **MUST — FINISHED требует пустой pending-set**: все attempts `assessed`, каждый ReviewAssignment имеет терминальную диспозицию: ровно один ReviewOutcome **либо** `CANCELLED`. Иначе finish отклоняется бизнес-ошибкой (это **не** авто-закрытие).
- **MUST — ABANDONED преобразует pending**: недостигнутые ReviewAssignment закрываются как `INSUFFICIENT_EVIDENCE(reason=abandoned)`, re-entry-блок получает свой outcome, `draft`/`recorded` attempts закрываются без вклада в scoring.
- **MUST — closure trigger** [OPEN-10, rereview R-5, P0-2/R-4]: второй триггер закрытия ReviewAssignment (наряду с явным `close_review`) — **`abandon`**, а не терминализация вообще. `finish` целей не закрывает: он требует уже пустой pending-set. Правило закрытия — [[evidence]] §4.3, триггер — здесь.
- **MUST — уникальность терминальной диспозиции** [OPEN-11 бизнес-часть]: на один ReviewAssignment допускается ровно одна терминальная ветка: ReviewOutcome либо `CANCELLED`. Для ветки outcome существует ровно один ReviewOutcome. Правило строится **поверх** kernel-CAS (multi-aggregate expected-revisions, foundation §3.5); два агента не могут записать конфликтующие диспозиции. Коррекция — только correction-событием, не вторым outcome.
- **MUST — атомарность**: одной SQLite-транзакцией коммитятся authoritative state + events + outbox; `summary` — engine-generated в той же UoW (агент может передать `--summary-draft`); **Obsidian-проекция post-commit через outbox** (foundation §3.7). Различие FINISHED/ABANDONED — только полнота summary и способ закрытия pending.
- **MUST**: терминализация FINISHED и ABANDONED одинаково пересчитывает производные (scores, расписание, XP, проекция) — рассогласованных производных не остаётся.

## 4b. Session Manifest [0.7]

Манифест — то, что сессия закрепила в момент старта; он делает поведение внутри сессии воспроизводимым, даже если между стартом и завершением активная конфигурация изменилась.

- **MUST — содержимое**: `session_id`, `provider`, `mode`, `pinned_versions` (curriculum, scoring, scheduler, **control**, generation, rubric), **`required_skills[]`** — пары `{skill_name, version}` — и `session_plan_id` со стартовым снимком `{composition_revision: 1, plan_version: 1}`. Manifest неизменяем; живые `SessionPlan`/`DeliveryLedger` хранятся в session aggregate по этой ссылке ([[control]] §4.2). Rendered exercise text не входит в Manifest: он фиксируется отдельным `EXERCISE_RENDERED` перед предъявлением learner prompt.
- **MUST — композиция в UoW старта** [CTRL-2]: `start` синхронно вызывает `control.compose_session` **до** commit и сохраняет план в той же транзакции. Отдельного шага композиции после старта не существует. `session peek` read-only возвращает следующий шаг и `plan_version`; `session next` при совпавшем `expected_plan_version` атомарно помечает шаг выданным, обновляет ledger, увеличивает версию и публикует `STEP_PRESENTED`; `session replan` использует тот же CAS-токен и увеличивает также `composition_revision` ([[control]] §4.2).
- **MUST — replan не оставляет pending-сирот** [R-3, RR2-4]: непредъявленный review-шаг, выпавший из новой ревизии, получает `CANCELLED(reason=replanned)` для своего ReviewAssignment **в той же UoW**. Это терминальная отмена, не ReviewOutcome: scoring и scheduler её игнорируют ([[evidence]] §4.3).
- **MUST — режим занятия** [CTRL-11]: `start` принимает `mode` (`balanced` по умолчанию). Режимы `maintenance`/`re_entry` — единственный путь к занятию без нового материала ([[control]] §4.1), и без параметра это нормативное исключение было недостижимо.
- **MUST — `required_skills` явные** [0.7, бриф §11]: требуемые навыки перечисляются в манифесте, а не подбираются средой по описанию. Implicit invocation делает поведение невоспроизводимым между Codex и Claude Code и лишает [[scoring]] §5 базы для Tutor Compliance: обязательство «вызван нужный skill нужной версии» проверяемо только против явного списка.
- **MUST — разрешимость при старте, синхронно до commit** [P0-Q1]: порядок строгий — `resolve` всех `required_skills` → открытие UoW → commit → `SESSION_STARTED`. `start` падает **до** создания сессии, если хоть одна затребованная версия неразрешима ([[adapters]] §4.2). Post-commit consumer `SESSION_STARTED` в [[adapters]] — только аудит уже обеспеченного инварианта, а не сама проверка: проверка по событию произошла бы после создания сессии и нарушила бы это MUST.
- **MUST — safety не пинится** [П.3]: манифест закрепляет структуру, pinned policies и generation policy, но не safety; `production_eligible` проверяется по active policy при `session next`, bank reuse и `EXERCISE_RENDERED`. `STEP_PRESENTED` без `EXERCISE_RENDERED` восстановим на `resume`: тот же шаг возвращается с той же generation directive. `EXERCISE_RENDERED` без попытки ученика — не evidence и становится reusable только после приёма в банк.
- **MUST — rubric resolution [П.5, PD-5 A/PD-6 B]**: до сохранения open exercise движок разрешает explicit `rubric:<profile_id>` либо exact default по `(step_type, dimension)` только против rubric-версии из Session Manifest. Конкретный versionless ref, `pinned_rubric_version`, `exercise_form`, applicable criteria, machine-check instances/target surfaces/requirements и `rubric_input_hash` входят в immutable `EXERCISE_RENDERED`/content hash. Unknown/incompatible ref или `PinnedPolicyUnavailable` отклоняет render без active/alias fallback. Specialized writing/source-integration требует explicit profile. Для unrendered targeted `free_conversation` exact default разрешается при assessment и материализуется в assessment event; broad fallback запрещён.

## 5. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `start(duration?, provider, mode?)` | API | создаёт сессию + Session Manifest (pinned versions + `required_skills` + план композиции) |
| `resume(session_id)` | API | полное состояние сессии + tutor briefing ([[../flows/continuation]]) |
| `abandon(session_id)` | API | идемпотентная терминализация без summary |
| `finish(session_id, summary_draft?)` | API | проверка postconditions → атомарная терминализация |
| `peek_next_step(session_id)` | API (read-only) | следующий шаг + текущий `plan_version`, без факта выдачи |
| `claim_next_step(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | выдача шага по протоколу [[control]] §4.2; возвращает bank item или generation directive |
| `record_rendered_exercise(session_id, step_id, exercise_instance, idempotency_key)` | API (mutating) | фиксирует иммутабельный rendered-exercise снапшот до предъявления ученику [П.3] |
| `replan(session_id, expected_plan_version, idempotency_key)` | API (mutating, CAS) | новая композиционная ревизия остатка бюджета |
| `SESSION_STARTED` / `FINISHED` / `ABANDONED` / `SESSION_STALE_ABANDONED` | publishes | lifecycle-факты |
| `EXERCISE_RENDERED` | publishes | rendered-exercise снапшот, привязанный к `step_id`; источник для исторических попыток/replay [П.3, PD-1 A] |
| `EXERCISE_ACCEPTED` / `EXERCISE_REJECTED` / `EXERCISE_RETIRED` | publishes | lifecycle банка упражнений; приём только после оценённой попытки или maintainer fast-path [П.3, PD-2 A] |
| `ATTEMPT_STATE_CHANGED` | publishes | draft/recorded/assessed |
| `attach_agent(session_id, provider, skills)` | API | фиксирует подключение агента к сессии |
| `AGENT_ATTACHED` | publishes | к сессии подключился агент: провайдер, версии skills, момент ([[../flows/continuation]]) |

- **MUST — session facade не второй владелец алгоритма**: `peek_next_step`, `claim_next_step` и `replan` здесь — транзакционная CLI-фасада lessons; она без собственной сортировки и бюджетных правил делегирует одноимённым операциям [[control]] §3b. Нормативное поведение композиции и CAS живёт только в control.
- **MUST — владелец `AGENT_ATTACHED` — lessons** [P0-5]: событие сессионное, поэтому живёт здесь, а не в audit; audit его только читает. Flow [[../flows/continuation]] требовал события, но ни один owner его не публиковал — обязательство flow без владельца не исполнимо.
- **MUST — подключение фиксируется теми же командами, что и вход в сессию** [R-3]: `--provider` обязателен у `session start` и `session resume`, и `attach_agent` вызывается **в той же UoW**, что и сама операция — **оба** пути публикуют `AGENT_ATTACHED` для своего провайдера (`start` — стартового, `resume` — возобновляющего). Отдельной CLI-команды `session attach` **нет** намеренно: она позволила бы объявить агента подключённым к сессии, которую он не загрузил, и создать состояние, где `AGENT_ATTACHED` есть, а briefing агент не получал. Смена агента на холодную — это `resume` с новым `--provider`.
- **MUST — session notes untrusted** [P0-5]: заметка агента (`--note` при любой фиксации) — свободный текст с автором и меткой времени; она **не evidence**, не влияет на scoring и не участвует в mastery. Схему и хранение владеет [[evidence]] §3 вместе с attempt; здесь — только факт, что фиксация может её нести.

## 6. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer session start [--duration N] --provider X [--mode balanced\|maintenance\|re_entry] --format json` | старт или конфликт с `allowed_actions`; фиксирует `AGENT_ATTACHED` для стартового провайдера |
| `trainer session next --session ID --expected-plan-version V --idempotency-key K --format json` | **выдаёт** следующий шаг, фиксирует `STEP_PRESENTED`, возвращает новый `plan_version`; идемпотентна |
| `trainer session peek --session ID --format json` | показывает следующий шаг и текущий `plan_version`, ничего не меняя |
| `trainer session replan --session ID --expected-plan-version V --idempotency-key K --format json` | пересборка остатка: `composition_revision + 1`, `plan_version + 1`; выпавшие непредъявленные review-цели получают `CANCELLED` в той же UoW ([[control]] §4.2) |
| `trainer session resume --session ID --provider X --format json` | состояние + briefing + notes; фиксирует `AGENT_ATTACHED` |
| `trainer session abandon --session ID` | идемпотентная терминализация |
| `trainer session finish --session ID [--summary-draft FILE]` | завершение с postconditions |
| `trainer exercise rendered --session ID --step STEP_ID --input FILE --idempotency-key K --format json` | фиксация rendered-exercise снапшота до предъявления ученику; возвращает `exercise_instance_id` |
| `trainer attempt record --session ID --step STEP_ID [--exercise-instance EXERCISE_ID] --input FILE [--note "..."]` | фиксация attempt по выданному шагу; structured-задачи ссылаются на сохранённый exercise-снапшот; `--note` — untrusted-заметка ([[evidence]] §3) |

Ошибки: `error_code` + причины + `allowed_actions` + `next_action`; отдельно бизнес-postconditions и lifecycle/concurrency/idempotency ([[../flows/session]]).

## 7. Границы

- **depends on**: kernel (UoW, CAS, idempotency, outbox), evidence (attempt/outcome), scheduler (манифест, перепланирование), scoring (пересчёт), curriculum (рекомендации, pinned versions), learner (briefing, XP).
- **events published**: см. §5.
- **consumed by**: cli, adapters/skills, memory (проекция на терминализации), audit.

## 8. Открытые вопросы

Закрывает **OPEN-10** (Attempt machine, closure trigger, терминализация) и бизнес-часть **OPEN-11** (uniqueness). Остаётся калибровка `stale_session_days`.

## История изменений

- **2026-07-22 (2)**: П.5 применена [PD-2026-07-22] — rubric resolution при рендере: explicit/exact-default ref против pinned rubric-версии манифеста, rubric_input_hash в EXERCISE_RENDERED, без active/alias fallback; unrendered conversation — default при assessment.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4).
- **2026-07-21**: синхронизированы терминальная диспозиция `ReviewOutcome | CANCELLED` и единый CAS-протокол `plan_version` для `peek → next/replan`.
- **2026-07-20 (0.7)**: добавлен §4b — содержимое Session Manifest и **`required_skills`** с версиями. Поле требовалось брифом §11 и [[adapters]], но нигде не было объявлено: манифест упоминался только как «pinned versions». Без него Tutor Compliance ([[scoring]] §5) не имеет базы для обязательства «вызван нужный skill нужной версии».
- **2026-07-20**: создан (контракт 0.5, часть 1). Attempt `draft→recorded→assessed` и stale-сессия как replayable событие [PD-2026-07-20]; closure trigger, uniqueness поверх CAS, атомарная терминализация с post-commit проекцией.
