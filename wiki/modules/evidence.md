# Модуль: evidence

> **Status**: current
> **Last updated**: 2026-07-21
> **Sources**: [[../product/learning-model]] §3 · [[../flows/session]] · [[../flows/placement]] · [[../platform/foundation]] (envelopes, capture-into-event) · review triage journals (OPEN-7/10) · часть контракта 0.4
> **Bounded context**: `src/english_trainer/evidence/`

> Спека — **target**. Фазы `[mvp]`/`[post-mvp]`. Термины — [[../glossary]]. Часть контракта 0.4 (evidence + [[scoring]] + [[scheduler]]).

---

## 1. Назначение

Модуль владеет **фактами владения**: принимает наблюдения агента, проверяет их допустимость и уникальность, вычисляет per-attempt оценку и терминальный review outcome, фиксирует всё как event-sourced evidence. Он — единственный вход, через который знание попадает в scoring. Агент передаёт наблюдения; **оценку и классификацию считает движок**, не агент.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `Attempt` | одна попытка ученика | id, **`step_id`** (выданный шаг, [RR2-3]), target, dimension, mode, raw_answer, span, hints, draft/finalized |
| `Observation` | наблюдение агента по attempt | rubric_criterion_ref, span_ref, machine-checkable часть, subjective часть |
| `Evidence` | сохранённый факт владения | id, target, dimension, origin, primary_scope, contributions[], source_span_hash, item_exposure_id, pinned_versions, AttemptAssessment |
| `CreditAllocation` | как span зачтён по target/dimension | target, dimension, contribution, used\|rejected, reason |
| `AttemptAssessment` | оценка отдельного attempt | score, independence, difficulty, mode-weight — **не терминальна** |
| `ReviewOutcome` | единственный терминальный исход ReviewAssignment | `PROGRESS/CONFIRMED/REGRESSION/RECOVERED/INSUFFICIENT_EVIDENCE` |
| `ObservedError` | зафиксированная ошибка | target, kind, severity, span |

Evidence event-sourced ([[../platform/foundation]] §2); Attempt operational (finalize/recover). Скоринг evidence не считает — отдаёт факты в [[scoring]].

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `finalize_attempt(id)` / `recover` | API | финализация draft-attempt (idempotent) | `[mvp]` |
| `close_review(review_id)` | API | вычисление единственного ReviewOutcome | `[mvp]` |
| `cancel_review(review_id, reason)` | internal API | терминальная системная отмена без ReviewOutcome; v1 reason: `replanned` | `[mvp]` |
| `record_attempt(step_id, raw_answer, observations, hints)` | API | фиксация попытки **по выданному шагу**; target/dimension/mode и `origin` движок берёт из `PlannedStep`, клиент их не задаёт [RR2-3] | `[mvp]` |
| `SessionNote` | сущность | untrusted-заметка агента при фиксации: `session_id`, `author_provider`, `created_at`, `text`; **не evidence**, в scoring не участвует ([[../flows/continuation]], P0-5) | `[mvp]` |
| `list_notes(session_id)` | API | заметки сессии в хронологическом порядке, отдельным блоком от state | `[mvp]` |

- **MUST — у заметки есть путь записи и путь чтения** [R-3]: `--note "..."` — необязательный параметр `trainer attempt record` и `trainer observed record`; чтение — `list_notes`, которое [[lessons]] включает в ответ `session resume` отдельным блоком. Объявить сущность без обеих сторон означало бы контракт, по которому заметку нельзя ни сохранить, ни получить.
- **MUST — заметка не влияет на исход**: её наличие, отсутствие и содержание не меняют ни admissibility фиксации, ни scoring. Автор (`author_provider`) сохраняется, чтобы при смене тьютора было видно, кто что записал.
| `record_observed(kind, ...)` | API | error/vocabulary/chunk observed | `[mvp]` |
| `ATTEMPT_RECORDED` / `EVIDENCE_ADDED` / `REVIEW_OUTCOME` / `REVIEW_ASSIGNMENT_CANCELLED` / `ERROR_OBSERVED` | publishes | append-only факты | `[mvp]` |

## 4. Поведение

### 4.1 Допустимость и уникальность (OPEN-7)
- **MUST**: клиентская готовая классификация запрещена; движок вычисляет AttemptAssessment и ReviewOutcome по versioned policy.
- **MUST — observation schema**: наблюдение ссылается на конкретный `rubric_criterion` и `span/error` в raw_answer, не булев флаг `criterion_satisfied`. Разделены machine-checkable часть (проверяется кодом) и subjective (под cap/trust); observation, не подтверждаемая raw_answer, **отклоняется** (единственная ветка, см. ниже).
- **MUST — семантическая идентичность**: evidence имеет `source_span_hash` (canonical hash ответа/цитаты) и `item_exposure_id`. Один source-span засчитывается **не более раза** на пару (target, dimension); переотправка того же span с новыми ключами/session id нового evidence не создаёт.
- **MUST — независимость**: rubric/informal-повышение состояния требует ≥2 независимых сессий; независимость определяется по **новому prompt/контексту/интервалу**, «другая сессия» сама по себе не считается.
- **MUST — multi-credit allocation** [ревью 0.4-5]: один span, релевантный нескольким target/dimension, зачитывается по **детерминированному алгоритму**, результат фиксируется как `CreditAllocation[]` в evidence-событии: для каждой пары (target, dimension) — `contribution` (вес) и `used | rejected` с `reason`. Primary получает полный вес, дополнительные — сниженный `multi_credit_weight` (*tunable*) с cap на сумму; двойного полного зачёта нет.
- **MUST — выбор primary target: единственное правило precedence** [rereview R-4]: primary определяется по первому сработавшему критерию —
  1. **явный ReviewAssignment** этого attempt (если attempt выполнялся по цели манифеста);
  2. **declared target объективного item'а** (упражнение/placement-item объявляет свой target);
  3. **канонический порядок** `target_id asc` среди кандидатов.
  Выбранный критерий сохраняется в событии как `selection_basis` — initial scoring и replay дают одинаковый allocation для одинакового входа.
- **MUST — непроверенная observation** [ревью 0.4-5]: observation, не подтверждаемая raw_answer, → **`rejected`** (не участвует в scoring), с audit-`reason`. Единственная ветка; «помечается» без участия в scoring исключено.

### 4.2 Trust model [PD-2026-07-19]
- **MUST**: MVP — агент trusted reporter `raw_answer`; допущение зафиксировано, границы — Tutor Compliance ([[scoring]]). Untrusted-захват user-turn — `[post-mvp]`.
- **MUST — объяснение ≠ evidence**: evidence появляется только при отдельном сохранённом learner response; объяснение агентом единицы даёт enrollment, не evidence знания.

### 4.3 AttemptAssessment vs ReviewOutcome (OPEN-10 evidence-часть)
- **MUST**: на один `review_id` возможно несколько attempts; per-attempt AttemptAssessment **не терминальна**.
- **MUST — граница закрытия** [rereview R-5]: терминальная диспозиция ReviewAssignment фиксируется **ровно один раз** по первому из следующих триггеров; ReviewOutcome вычисляется только для первых двух веток:
  1. явный `close_review` (агент отмечает цель выполненной/отклонённой ученицей) — доступен агенту как `trainer review close` ([[cli]] §5);
  2. **`abandon` сессии** — преобразует оставшиеся pending цели в `INSUFFICIENT_EVIDENCE(reason=abandoned)` ([[lessons]] 0.5 владеет этим триггером);
  3. **`replan`** — непредъявленный review-шаг, выпавший из новой ревизии, вызывает `cancel_review(review_id, replanned)` и получает append-only `REVIEW_ASSIGNMENT_CANCELLED {review_id, reason: replanned}` в той же UoW ([[control]] §4.2).

  - **MUST — отмена не является ReviewOutcome** [RR2-4]: `CANCELLED` закрывает ReviewAssignment для проверки pending-set при `finish`, но **не** является учебным исходом: [[scheduler]] не назначает по нему retry, [[scoring]] не применяет переход состояния, и в метрики исходов он не попадает. Ученик не пытался и не дал недостаточного evidence — цель убрала сама система. Закрывать это как `INSUFFICIENT_EVIDENCE` значило бы породить долг повторения из внутреннего перепланирования и загрязнить статистику системными отменами.

  **`finish` целей не закрывает** [P0-2]: он **требует** уже пустой pending-set и отклоняется бизнес-ошибкой, если тот непуст ([[lessons]] §4). Прежняя формулировка «finish/abandon закрывает все pending» противоречила owner-спеке: при ней сессию можно было завершить, не получив исходов, то есть обойти персистентность evidence — ровно то, что finish обязан не допускать.
  После закрытия ReviewAssignment **терминален**: дальнейшие attempts на тот же `review_id` записываются как non-contributing (audit) либо относятся к **новому** assignment, назначенному scheduler. Повторный `close_review` идемпотентен (возвращает прежний outcome).
- **MUST — correction ≠ второй outcome**: исправление уже терминального исхода идёт **только** через correction-событие (`corrects_event_id`, [[../platform/foundation]] §3.6), которое замещает эффект; второго ReviewOutcome на assignment не возникает.
- Владение таймингом: правило закрытия — здесь (0.4); **триггер терминализации сессии — 0.5** ([[../OPEN]] OPEN-10).
- **MUST**: ReviewOutcome и AttemptAssessment — раздельные записи; scoring применяет transition по ReviewOutcome ([[scoring]] §таблица).

### 4.4 contribution_scope — cardinality [ревью 0.4-10]
- **MUST**: scope имеет **один `primary_scope`** (enum: `informal | writing | transfer | core_cefr`) + список `contributions[]` (по одному per-scope с весом и cap-allocation). Одно production-evidence может дать и `writing`, и `transfer` — оба как записи `contributions[]` с явными весами; cap применяется к пересечению informal↔core_cefr.
- **MUST**: Recognition сленга/мемов **никогда** не в core_cefr. Informal production в рабочем контексте даёт компонент writing/transfer с dedup и cap (один span — не в informal и core_cefr сверх cap). Все веса фиксируются в event (см. `CreditAllocation`).

### 4.5 capture-into-event [rereview A-2]
- **MUST**: любое operational значение, влияющее на scoring (вес exposure placement, snapshot ReviewAssignment, `origin`), фиксируется **в самом evidence-событии** с версией policy — не читается из operational store при replay.
- **MUST — attempt ссылается на выданный шаг** [RR2-3]: `record_attempt` принимает `step_id` шага с зафиксированным `STEP_PRESENTED` в указанной активной сессии; ссылка валидируется. Уже выданный шаг остаётся допустимым после replan, даже если его `composition_revision` больше не текущая: replan сохраняет предъявленные шаги и их assignments. Отсюда движок выводит target, dimension, mode и `origin` — клиент их не передаёт.
- **MUST — origin** [ревью 0.4-4, CTRL-10, RR2-3]: evidence несёт immutable `origin` — **единый закрытый enum** `session | placement | re_entry | control_probe`, одинаковый во всех спеках; scoring применяет placement-ceiling по нему ([[scoring]] §4b) и правило no-negative для `control_probe` ([[scoring]] §4b, [[control]] §4.7).

## 5. CLI-поверхность

Через сессию/placement ([[../flows/session]], [[../flows/placement]]): `trainer attempt record`, `trainer review close`, `trainer observed record` — **точные имена**, по которым `skills validate` сверяет `cli_calls` ([[adapters]] §4.3). Прямого пользовательского CLI evidence не имеет (agent-facing через session).

## 6. Границы

- **depends on**: kernel (envelopes, идентичность, capture-into-event), curriculum (target/dimension/rubric refs, pinned versions).
- **events published**: `ATTEMPT_RECORDED`, `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `REVIEW_ASSIGNMENT_CANCELLED`, `ERROR_OBSERVED`.
- **consumed by**: scoring (факты → scores), scheduler (outcome → интервалы), memory (проекция), audit.

## 7. Открытые вопросы

- **OPEN-7** закрыт: identity/independence/**multi-credit allocation record**/observation-disposition определены как единственные ветки; численные веса — *tunable*. Механика hash/exposure — kernel (OPEN-20).

## История изменений

- **2026-07-21**: удалена конкурирующая сигнатура `record_attempt`; attempt валидируется по факту `STEP_PRESENTED`, а не по текущей композиционной ревизии; закрытие формализовано как `ReviewOutcome | CANCELLED`.
- **2026-07-20 (3)**: 0.4-rereview — единственное правило precedence для primary target + `selection_basis` в событии (R-4); явная граница закрытия ReviewAssignment, терминальность, идемпотентный повторный close, correction ≠ второй outcome (R-5).
- **2026-07-20 (2)**: 0.4-review триаж — детерминированный `CreditAllocation` record и единственная ветка для непроверенной observation (`rejected`, 0.4-5); cardinality `contribution_scope` (primary + contributions[], 0.4-10); immutable `origin` для placement-ceiling (0.4-4).
- **2026-07-20**: создан (контракт 0.4, часть 1). Наблюдения→движок, semantic identity, observation schema, AttemptAssessment vs ReviewOutcome, contribution_scope, capture-into-event. Решения из learning-model + review-триажей [PD-2026-07-19/20].
