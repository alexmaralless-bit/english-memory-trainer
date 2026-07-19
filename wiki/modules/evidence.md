# Модуль: evidence

> **Status**: current
> **Last updated**: 2026-07-20
> **Sources**: [[../product/learning-model]] §3 · [[../flows/session]] · [[../flows/placement]] · [[../platform/foundation]] (envelopes, capture-into-event) · review triage journals (OPEN-7/10) · часть контракта 0.4
> **Bounded context**: `src/english_trainer/evidence/`

> Спека — **target**. Фазы `[mvp]`/`[post-mvp]`. Термины — [[../glossary]]. Часть контракта 0.4 (evidence + [[scoring]] + [[scheduler]]).

---

## 1. Назначение

Модуль владеет **фактами владения**: принимает наблюдения агента, проверяет их допустимость и уникальность, вычисляет per-attempt оценку и терминальный review outcome, фиксирует всё как event-sourced evidence. Он — единственный вход, через который знание попадает в scoring. Агент передаёт наблюдения; **оценку и классификацию считает движок**, не агент.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `Attempt` | одна попытка ученика | id, target, dimension, mode, raw_answer, span, hints, draft/finalized |
| `Observation` | наблюдение агента по attempt | rubric_criterion_ref, span_ref, machine-checkable часть, subjective часть |
| `Evidence` | сохранённый факт владения | id, target, dimension, contribution_scope, source_span_hash, item_exposure_id, pinned_versions, AttemptAssessment |
| `AttemptAssessment` | оценка отдельного attempt | score, independence, difficulty, mode-weight — **не терминальна** |
| `ReviewOutcome` | единственный терминальный исход ReviewAssignment | `PROGRESS/CONFIRMED/REGRESSION/RECOVERED/INSUFFICIENT_EVIDENCE` |
| `ObservedError` | зафиксированная ошибка | target, kind, severity, span |

Evidence event-sourced ([[../platform/foundation]] §2); Attempt operational (finalize/recover). Скоринг evidence не считает — отдаёт факты в [[scoring]].

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `record_attempt(target, dimension, mode, raw_answer, observations, hints)` | API | приём attempt + наблюдений, вычисление AttemptAssessment | `[mvp]` |
| `finalize_attempt(id)` / `recover` | API | финализация draft-attempt (idempotent) | `[mvp]` |
| `close_review(review_id)` | API | вычисление единственного ReviewOutcome | `[mvp]` |
| `record_observed(kind, ...)` | API | error/vocabulary/chunk observed | `[mvp]` |
| `ATTEMPT_RECORDED` / `EVIDENCE_ADDED` / `REVIEW_OUTCOME` / `ERROR_OBSERVED` | publishes | append-only факты | `[mvp]` |

## 4. Поведение

### 4.1 Допустимость и уникальность (OPEN-7)
- **MUST**: клиентская готовая классификация запрещена; движок вычисляет AttemptAssessment и ReviewOutcome по versioned policy.
- **MUST — observation schema**: наблюдение ссылается на конкретный `rubric_criterion` и `span/error` в raw_answer, не булев флаг `criterion_satisfied`. Разделены machine-checkable часть (проверяется кодом) и subjective (под cap/trust); observation, не подтверждаемая raw_answer, отклоняется или помечается.
- **MUST — семантическая идентичность**: evidence имеет `source_span_hash` (canonical hash ответа/цитаты) и `item_exposure_id`. Один source-span засчитывается **не более раза** на пару (target, dimension); переотправка того же span с новыми ключами/session id нового evidence не создаёт.
- **MUST — независимость**: rubric/informal-повышение состояния требует ≥2 независимых сессий; независимость определяется по **новому prompt/контексту/интервалу**, «другая сессия» сама по себе не считается.
- **MUST — multi-credit allocation**: один span, релевантный нескольким target/dimension, распределяется по явному правилу (не двойной полный зачёт).

### 4.2 Trust model [PD-2026-07-19]
- **MUST**: MVP — агент trusted reporter `raw_answer`; допущение зафиксировано, границы — Tutor Compliance ([[scoring]]). Untrusted-захват user-turn — `[post-mvp]`.
- **MUST — объяснение ≠ evidence**: evidence появляется только при отдельном сохранённом learner response; объяснение агентом единицы даёт enrollment, не evidence знания.

### 4.3 AttemptAssessment vs ReviewOutcome (OPEN-10 evidence-часть)
- **MUST**: на один `review_id` возможно несколько attempts; per-attempt AttemptAssessment **не терминальна**. `close_review` вычисляет **ровно один** ReviewOutcome в определённый момент (последний attempt / recover / correction); момент фиксируется, не зависит от реализации.
- **MUST**: ReviewOutcome и AttemptAssessment — раздельные записи; scoring применяет transition по ReviewOutcome ([[scoring]] §таблица).

### 4.4 contribution_scope и informal (OPEN-13 evidence-часть)
- **MUST**: каждое evidence помечено `contribution_scope` (informal-профиль / writing / transfer / core-CEFR). Recognition сленга/мемов **никогда** не в CEFR. Informal production в рабочем контексте даёт компонент writing/transfer с dedup и cap (один span — не в informal и CEFR сверх cap).

### 4.5 capture-into-event [rereview A-2]
- **MUST**: любое operational значение, влияющее на scoring (вес exposure placement, snapshot ReviewAssignment), фиксируется **в самом evidence-событии** с версией policy — не читается из operational store при replay.

## 5. CLI-поверхность

Через сессию/placement ([[../flows/session]], [[../flows/placement]]): `attempt record`, `review record`, `error/vocabulary/chunk observed`. Прямого пользовательского CLI evidence не имеет (agent-facing через session).

## 6. Границы

- **depends on**: kernel (envelopes, идентичность, capture-into-event), curriculum (target/dimension/rubric refs, pinned versions).
- **events published**: `ATTEMPT_RECORDED`, `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `ERROR_OBSERVED`.
- **consumed by**: scoring (факты → scores), scheduler (outcome → интервалы), memory (проекция), audit.

## 7. Открытые вопросы

- **OPEN-7** закрывается этим контрактом на уровне правил (identity/independence/multi-credit/observation schema); численные cap'ы — [[scoring]]. Механика hash/exposure — kernel (OPEN-20).

## История изменений

- **2026-07-20**: создан (контракт 0.4, часть 1). Наблюдения→движок, semantic identity, observation schema, AttemptAssessment vs ReviewOutcome, contribution_scope, capture-into-event. Решения из learning-model + review-триажей [PD-2026-07-19/20].
