# Модуль: audit

> **Status**: current
> **Last updated**: 2026-09-24
> **Sources**: P0-4/OPEN-25 (контракт отсутствовал) · [[cli]] §4.3 (`correlation_id`) · [[../platform/foundation]] §2 (event-таблица authoritative, JSONL — derived export) · [[scoring]] §5 (Tutor Compliance) · [[adapters]] §3 (события skill'ов недоверенные) · `staging/concepts/2026-09-23-lesson-brief-report-concept.md` (одобрен, [PD-2026-09-23]) · контракт 0.11
> **Bounded context**: `src/english_trainer/audit/`

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — по [[../glossary]].

---

## 1. Назначение

Модуль отвечает на вопрос «что на самом деле произошло». Он собирает из событийного лога связные картины: что случилось в сессии, что делал агент, чем обосновано решение движка, почему у цели такое состояние.

Ценность в том, что при сменяемом тьюторе и длинной истории единственный надёжный рассказ о прошлом — это события, а не память чата и не отчёт агента о себе.

## 2. Сущности и состояния

Модуль **не владеет состоянием**. Он владеет запросами над чужим.

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `AuditView` | связная выборка событий по ключу | `key_kind` (`session` \| `correlation` \| `target` \| `learner`), `key`, `events[]`, `built_at` |
| `ObligationObservation` | наблюдаемый факт исполнения обязательства агентом | `obligation_id`, `session_id`, `satisfied`, `observed_effects[]`, `self_report_events[]` |

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `session_view(session_id)` | API | полная картина сессии: команды, события, решения, исходы |
| `correlation_view(correlation_id)` | API | всё, что породил один вызов CLI |
| `target_history(target_id, dimension?)` | API | история состояний цели с причинами переходов |
| `obligations(session_id)` | API | наблюдения по обязательствам агента для Tutor Compliance |

- **MUST — модуль не публикует событий**: он только читает. Аудит, порождающий события, попал бы в собственную выборку и превратил бы наблюдение в участие.

## 4. Поведение

- **MUST — только чтение**: у модуля нет ни одной мутирующей операции. Все его команды в [[cli]] помечены `mutating: false` и подчиняются правилу «диагностика не чинит» ([[cli]] §4.4). Аудит, который «поправляет» найденное расхождение, лишает себя доказательной силы.
- **MUST — источник: authoritative event-таблица**: выборки строятся по SQLite event-таблице, **не** по JSONL-экспорту. JSONL — производный артефакт с возможным лагом ([[../platform/foundation]] §2); строить по нему аудит значит смотреть на копию и принимать её за оригинал.
- **MUST — гибридность состояния учитывается**: часть состояния SQLite-authoritative и не event-sourced ([[../platform/foundation]] §2, [[memory]] §5). Выборка, включающая такие данные, **помечает** их как снимок операционного состояния, а не как восстановленный из событий факт. Иначе аудит незаметно смешает воспроизводимое с невоспроизводимым.
- **MUST — самоотчёт агента отделён от наблюдаемого**: в `ObligationObservation` события `SKILL_STARTED`/`COMPLETED`/`FAILED` попадают в `self_report_events` и **никогда** в `observed_effects`. Обязательство считается исполненным только по наблюдаемым эффектам — вызовам [[cli]] и доменным событиям ([[scoring]] §5, [[adapters]] §3).
- **MUST — расхождение самоотчёта и эффектов само является выводом**: `SKILL_COMPLETED` без соответствующих доменных событий не ошибка выборки, а находка — агент отчитался о работе, которой нет. Модуль отдаёт её явно, а не молча отбрасывает.
- **MUST — детерминированный порядок**: события в выборке упорядочены по каноническому `sequence` (kernel 1.2; OPEN-20 закрыт), не по порядку возврата БД. Две одинаковые выборки совпадают побайтово.
- **MUST — аудит не является evidence**: его выводы не влияют на Mastery, уровень и XP. Tutor Compliance ([[scoring]] §5) — метрика **тьютора**, не ученика.
- **MUST — ретеншн честен**: если событие или pinned-политика недоступны (retention, OPEN-9), выборка сообщает о неполноте явно, а не отдаёт частичную картину как полную.
- **MUST — outer CLI telemetry [PD-2026-07-22]**: транспорт пишет `cli.command_invoked` и `cli.command_terminated` для каждого вызова, включая read-only команды и отказы. Это не мутация audit-модуля и не business effect: telemetry добавляет только append-only наблюдение с correlation/causation, redacted `argv_shape_hash`, session hint, exit/error и outcome; raw аргументы и пользовательский текст туда не попадают. Если целостность event-store нарушена, диагностика обязана по-прежнему вернуть исходную проблему, а не упасть из-за попытки telemetry.
- **MUST — obligations@4 [PD-2026-09-23]**: сессии, закреплённые под brief/report протоколом, разрешаются отдельным оценщиком (`audit/views.py::_obligations_v4`), выбранным по пиненной версии; `obligations@1`/`@2`/`@3` продолжают резолвиться прежним matcher'ом для сессий, которые их закрепили (обратной миграции нет). `delivery_protocol`/`correction_protocol`/`teaching_snapshot` из более ранних версий здесь не наблюдаются: пошаговой доставки и per-step rendered-снапшота, которые они проверяли, у brief/report протокола нет. Пять обязательств `obligations@4`, в `matching_order`:
  1. **`required_skill_effect`** — требуемый эффект без изменений: разрешённый успешный CLI-эффект, потребляемый не более раза; но состав self-report расширен [PD-2026-09-23] — у lean-протокола нет отдельного вызова `skills report`, поэтому `lesson.reported` этой сессии (actor `agent`, `provider` заполнен) тоже засчитывается как self-report для каждого закреплённого через `skill.required` навыка, наравне с `skill.completed`; он остаётся в `self_report_events`, никогда не смешиваясь с `observed_effects` (§4 «самоотчёт агента отделён от наблюдаемого»).
  2. **`lesson_preflight`** — применимо к любой стартовавшей сессии; удовлетворено, если `session.started` несёт `manifest.lesson_profile`. Богатый снимок title/reason/agenda/language_envelope, который проверяли более ранние версии, здесь не требуется: явный профиль на старте — то, что действительно защищает ученика в протоколе, где урок ведёт тьютор.
  3. **`report_committed`** — применимо, если сессия дошла до `session.finished`; удовлетворено, если `lesson.reported` этой сессии предшествует `session.finished` по каноническому `sequence`. Отдельной команды `session finish` не существует — `session report` завершает сессию атомарно ([[lessons]] §4), поэтому обязательство спрашивает именно о том факте, от которого это по-прежнему зависит.
  4. **`reviews_addressed`** — применимо, если сессия подобрала хотя бы одно ReviewAssignment; удовлетворено, если у каждого из них есть либо `review.outcome` (INSUFFICIENT_EVIDENCE — обязательно с `reason`), либо `review.assignment_cancelled` (историческое, недостижимо новым протоколом — [[control]] §4.7). Источник самих assignment'ов — **операционный SQLite-снимок** (`review_assignment`), не event-sourced создание; наблюдение помечается `snapshot_source: review_assignment`, по правилу §4 «гибридность состояния учитывается» — читается как снимок, а не как восстановленный из событий факт.
  5. **`forbidden_action_absence`** — без изменений смысла: набор `forbidden_error_codes` (сейчас `MISSING_IDEMPOTENCY_KEY`) не должен встретиться среди CLI-эффектов сессии.

  Разворот прежнего инварианта: тьютор **решает** правильность каждого item'а отчёта ([[evidence]] §4.2, [PD-2026-09-23]) — это больше не запрещённое действие. `forbidden_action_absence` этого не проверяет и не запрещает; он остаётся про формальные нарушения протокола (idempotency), не про то, кто классифицирует ответ.
- **MUST — obligations@3 [PD-2026-09-22]** (историческое, только для сессий, закрепивших эту версию): сохраняет все шесть обязательств `obligations@2` и переформулирует два из них в терминах результата, а не последовательности вызовов. `delivery_protocol` требует, чтобы immutable rendered-снапшот существовал **после `STEP_PRESENTED` и до попытки** по этому шагу; `session peek` не наблюдается и не требуется. `correction_protocol` считается исполненным при наличии attempt, дошедшего до `assessed` (одновызовный `attempt record` с наблюдениями, `attempt record-block` или двухшаговый `record` + `finalize`), **и** закрытия review через любой из двух триггеров (`attempt record[-block] --close-review` или `review close`); закрытия, написанные движком на `abandon`, обязательство не закрывают — они не действие тьютора.
- **MUST — obligations@1/@2 [PD-2026-07-22]/[PD-2026-07-23]** (историческое, только для сессий, закрепивших эти версии): matcher идёт в policy-order, затем по event `sequence`, и один observed effect потребляется не более одного раза. `obligations@2` добавляет к трём семействам `obligations@1` (required-skill effect, correction protocol, forbidden-action absence) наблюдаемые lesson-preflight contract, TeachingSegment до learner-facing объяснения и порядок structured delivery — факты берутся из pinned LessonArc, `TEACHING_SEGMENT_RENDERED`, `STEP_PRESENTED`, `EXERCISE_RENDERED` и CLI telemetry.

## 5. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer audit session SESSION_ID --format json` | полная картина сессии | события, решения, исходы, обязательства |
| `trainer audit correlation ID --format json` | всё, что породил один вызов | цепочка событий |
| `trainer audit target ID [--dimension D] --format json` | история состояний цели с причинами | переходы + триггеры |

Все — `mutating: false` относительно бизнес-состояния. Outer CLI transport всё равно фиксирует audit telemetry по правилу §4.

## 6. Границы

- **depends on**: storage (event-таблица), [[../platform/foundation]] (envelopes, `correlation_id`, `causation_id`, `sequence`)
- **events published**: нет
- **events consumed**: читает все, ни на одно не реагирует действием

Модуль не интерпретирует педагогику: он не решает, хорош ли результат, — только показывает, что произошло.

## 7. Открытые вопросы

- **OPEN-9**: retention pinned-версий и snapshots → определяет, как далеко в прошлое аудит вообще способен смотреть.
- Канонический `sequence` и encoding реализованы в kernel; остаточный OPEN-9 определяет лишь глубину доступной истории.

## История изменений

- **2026-09-24**: [PD-2026-09-23] `required_skill_effect` в `obligations@4`: `lesson.reported` (actor `agent`, `provider` заполнен) засчитывается как self-report наравне с `skill.completed`, потому что lean-протокол не оставил отдельного вызова `skills report` — реализовано только в оценщике (`_obligations_v4`), yaml-полезная нагрузка `obligations-v4.yaml` не менялась (уже активирована на живой БД). `obligations@1`–`@3` не затронуты.
- **2026-09-23**: [PD-2026-09-23] введён `obligations@4` для brief/report протокола: `delivery_protocol`/`correction_protocol`/`teaching_snapshot` заменены `lesson_preflight` (упрощён до `manifest.lesson_profile`), `report_committed` (`lesson.reported` раньше `session.finished`) и `reviews_addressed` (гибридное наблюдение — читает операционный снимок `review_assignment`, помечено `snapshot_source`); `required_skill_effect`/`forbidden_action_absence` без изменений смысла. `obligations@1`/`@2`/`@3` остаются разрешимыми для сессий, которые их закрепили.
- **2026-09-22**: [PD-2026-09-22] введён `obligations@3`: `delivery_protocol` наблюдает rendered-снапшот до попытки (peek не требуется), `correction_protocol` — assessed attempt и закрытие review любым из двух триггеров. `obligations@2` остаётся разрешимым для сессий, которые его закрепили.
- **2026-07-23**: [PD-2026-07-23] obligations@2 наблюдает lesson preflight, teaching snapshot и порядок выдачи структурированного задания.
- **2026-07-22 (2)**: [PD-2026-07-22] зафиксированы outer CLI telemetry и `obligations@1`: policy-order + event sequence, one-effect-once, три семейства обязательств, `no-data` при неполном окне.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4).
- **2026-07-20**: создан (контракт 0.11, P0-4/OPEN-25). Модуль объявлен строго read-only и без собственных событий; источник — authoritative event-таблица, не JSONL-экспорт; самоотчёт агента отделён от наблюдаемых эффектов, а их расхождение объявлено находкой, а не шумом.
