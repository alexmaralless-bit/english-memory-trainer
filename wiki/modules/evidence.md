# Модуль: evidence

> **Status**: current
> **Last updated**: 2026-09-23
> **Sources**: [[../product/learning-model]] §3 · [[../flows/session]] · [[../flows/placement]] · [[../platform/foundation]] (envelopes, capture-into-event) · `staging/concepts/2026-09-23-lesson-brief-report-concept.md` (одобрен, [PD-2026-09-23]) · review triage journals (OPEN-7/10) · часть контракта 0.4

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — [[../glossary]]. Часть контракта 0.4 (evidence + [[scoring]] + [[scheduler]]).

---

## 1. Назначение

Модуль владеет **фактами владения**: принимает решения тьютора и объективные проверки placement, проверяет их допустимость и уникальность, детерминированно агрегирует per-attempt факт и терминальный review outcome, фиксирует всё как event-sourced evidence. Он — единственный вход, через который знание попадает в scoring. Для обычных занятий модуль не имеет собственного CLI: его builders вызывает `lessons.report` внутри одной транзакции коммита LessonReport ([[lessons]] §4d); для placement rubric-конвейер остаётся engine-computed без изменений.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `Attempt` | одна попытка ученика | id, `item_id` (item отчёта, PD-2026-09-23), target, dimension, mode, prompt, raw_answer, span, hints, `status: assessed` (рождается уже финализированным — §4.2), `items[]?` (только для дрилл-блока, §4.6) |
| `DrillItem` | одно предъявление внутри дрилл-блока [PD-2026-09-22] | `index`, `prompt_ref`, `raw_answer`, `objective_correct?`, `credited`, `self_repaired` |
| `Observation` | rubric-наблюдение тьютора (только placement) | rubric_criterion_ref, span_ref, machine-checkable часть, subjective часть ([[assessments]] §3) |
| `Evidence` | сохранённый факт владения | id, target, dimension, origin, primary_target, credit_allocations[], span_hash, pinned_versions, assessment (`objective_check` \| `rubric` \| `tutor_verdict`) |
| `CreditAllocation` | как span зачтён по target/dimension | target, dimension, contribution, used\|rejected, reason |
| `ReviewOutcome` | единственный терминальный исход ReviewAssignment | `PROGRESS/CONFIRMED/REGRESSION/RECOVERED/INSUFFICIENT_EVIDENCE` |
| `ObservedError` | зафиксированная ошибка | target, dimension, span (движком выведенный), learner_form, correction, cause, severity (policy-owned), `reported_by: tutor` |

Evidence event-sourced ([[../platform/foundation]] §2). Scoring evidence не считает — отдаёт факты в [[scoring]].

## 3. Публичный API и события

Для обычных занятий модуль не выставляет CLI-командам прямого доступа [PD-2026-09-23]: перечисленные ниже операции — **чистые builders**, вызываемые `lessons.report::commit_report` внутри его UoW. Rubric-конвейер placement (`rubric.py`, `assessment.py`) остаётся отдельным движковым путём для `trainer placement submit`/`answer` ([[assessments]] §3) и здесь не меняется.

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `verdict_assessment(verdict, policy)` (`evidence/report.py`) | pure builder | assessment-payload `{basis: tutor_verdict, verdict, correct, score_ppm}` по закреплённой `evidence@2.verdict_scale` |
| `derive_span(raw_answer, learner_form)` | pure builder | UTF-8-span первого точного вхождения `learner_form` в `raw_answer` + `span_hash`; движок выводит span сам, тьютор offsets не присылает |
| `item_targets(target_ref, dimension, secondary_targets)` | pure builder | primary/secondary targets item'а в каноническом порядке — `selection_basis: declared_item_target` |
| `build_attempt_payload` / `build_block_attempt_payload` | pure builder | `attempt.recorded` payload одного item'а / дрилл-блока (§4.6) |
| `build_evidence_payload` / `build_block_evidence_payload` | pure builder | `evidence.added` payload contributing-attempt'а; `None` для non-contributing (повторный span, §4.1) |
| `build_error_payload` | pure builder | `evidence.error_observed` по одной заявленной тьютором ошибке, со span, выведенным из `raw_answer` |
| `span_already_credited(store, span_hash, primary_target)` | read | семантическая идентичность (§4.1), читает `store.read()` внутри открытой UoW — видит уже добавленные в этом же отчёте items |
| `closure_from_verdict(...)` / `close_insufficient(...)` (`evidence/reviews.py`) | mutating, внутри чужой UoW | терминальный ReviewOutcome по вердикту / явному skip'у отчёта (§4.3) |
| `automaticity_updates(...)` | pure builder | факты оси `automaticity`, свёрнутые из уже добавленных в этой UoW фактов отчёта |
| `ATTEMPT_RECORDED` / `EVIDENCE_ADDED` / `REVIEW_OUTCOME` / `ERROR_OBSERVED` | publishes | append-only факты, записываемые `lessons.report` в порядке §4.2 |

- **MUST — оценка через сохранённый rubric-facing step type (только placement)** [PD-2026-09-22]: для placement-форм, использующих `reconstruction`/`timed_writing`-подобные kind'ы, профиль разрешается по полю снимка формы — правило принадлежит [[assessments]], не обычным занятиям, у которых rubric-конвейера больше нет.

## 4. Поведение

### 4.1 Допустимость и уникальность (OPEN-7)

- **MUST**: клиентская готовая классификация запрещена для placement (движок вычисляет AttemptAssessment и ReviewOutcome по versioned `rubric@1`); для обычных занятий классификацию даёт тьютор как **вердикт**, а не как «готовую оценку движка» — граница между двумя путями объясняется в §4.2.
- **MUST — цель item'а объявлена явно, не выведена из плана** [PD-2026-09-23]: `selection_basis: declared_item_target` — primary target отчётного item'а это его собственные `target_ref`/`dimension`, secondary — его `secondary_targets[]`, в каноническом порядке (`item_targets`). Прежнее правило precedence («явный ReviewAssignment → declared target объективного item'а → канонический порядок») относилось к попытке, привязанной к выданному `PlannedStep`, — такой привязки в brief/report протоколе не существует: план advisory, а не источник обязательной ссылки ([[lessons]] §4c).
- **MUST — семантическая идентичность**: evidence имеет `span_hash` (canonical hash ответа) и primary target. Один source-span засчитывается **не более раза** на пару (target, dimension); переотправка того же span новым item'ом нового evidence не создаёт — attempt всё равно фиксируется, `evidence.added` за ним не следует (`contributing: false`).
- **MUST — multi-credit allocation** [ревью 0.4-5]: один span, релевантный нескольким target/dimension, зачитывается по **детерминированному алгоритму** (`allocate_credit`), результат — `CreditAllocation[]` в evidence-событии: primary получает полный вес, дополнительные — сниженный `multi_credit_weight` (*tunable*) с cap на сумму.
- **MUST — evidence@1/evidence@2**: primary получает `1.0`, дополнительные цели — `0.5`, общий cap — `2.0` (неизменно между версиями). Версия закрепляется в Session Manifest; replay читает сохранённые allocations и не пересчитывает их по active policy.
- **MUST — непроверенная observation (только placement)** [ревью 0.4-5]: rubric-observation, не подтверждаемая raw_answer, → **`rejected`** (не участвует в scoring), с audit-`reason`. Обычные занятия этого пути не используют — вердикт тьютора не проходит через rubric-observation-модель вовсе.

### 4.2 Trust model и вердикт тьютора [PD-2026-09-23, PD-C]

- **MUST — тьютор решает правильность**: для отчётного item'а (`assessment.basis: tutor_verdict`) итоговая классификация **не пересчитывается движком** — это разворачивает прежнее общее правило «движок вычисляет AttemptAssessment, клиент не задаёт готовую классификацию» ровно для этого канала. Rubric-путь placement (`assessment.basis: rubric`) не затронут: там классификацию по-прежнему считает движок по `rubric@1` ([[assessments]] §3). Разворачивает прежнее «агент не выставляет себе оценки» (`docs/design-direction.md`) и закрывает OPEN-4.
- **MUST — что хранит движок**: `prompt`, дословный `raw_answer`, вердикт (`correct`/`partial`/`incorrect`) и, на каждую заявленную ошибку, `{learner_form, correction, cause}` — ровно как их подал тьютор, без интерпретации содержимого. Движок **сам выводит span** каждого `learner_form` внутри `raw_answer` (первое точное вхождение, UTF-8 byte offsets, `span_hash`, `derive_span`); тьютор offsets никогда не присылает. Форма, не встречающаяся в ответе дословно, отклоняет весь отчёт кодом `learner_form_not_in_answer` (§4.2a).
- **MUST — шкала вердикта** (`evidence@2.verdict_scale`, PD-D): `correct` → `score_ppm 1 000 000`, `partial` → `500 000`, `incorrect` → `0`. Булевы потребители (`correct`-флаг, серии саturation, точность дрилл-блока) читают только `verdict == correct` как истину — `partial` истиной не является ни для какого булева потребителя.
- **MUST — дедуп span'ов явный, не тихий**: повторный span (§4.1) даёt `attempt.recorded` с `assessment.contributing: false` и не даёт `evidence.added`. `session check-report`/`session report` отдают это как явный `duplicate_span` — **не отклоняющее** предупреждение, видимое тьютору до и при записи ([[lessons]] §4d), а не молча пропущенный факт.
- **MUST — без trust-cap на вердикт** [PD-F]: вклад tutor-verdict evidence в Mastery ограничен только обычным session cap ([[scoring]] §2.1, ветка `tutor_verdict`) — никакого дополнительного понижающего множителя или отдельного cap'а поверх вердикта тьютора не вводится. Проверка добросовестности вердикта — постфактум, workflow `audit-english-tutor` по сохранённым `prompt`/`raw_answer`/`verdict`, а не live-гейт на записи.
- **MUST — объяснение ≠ evidence**: evidence появляется только при отдельном сохранённом learner response; объяснение агентом единицы даёт enrollment, не evidence знания.

#### 4.2a Коды отклонения LessonReport

`session check-report`/`session report` отклоняют **весь** отчёт, если хотя бы один item не проходит приём; отклоняющие коды: `unknown_target`, `bad_dimension`, `empty_answer`, `bad_verdict`, `review_mismatch`, `learner_form_not_in_answer`, `block_unknown`, `duplicate_item_id`, `too_many_items` (лимиты — `evidence@2.report_limits`: `max_items 200`, `max_answer_chars 4000`, `max_errors_per_item 10`). Не отклоняющее: `duplicate_span` → `contributing: false` (§4.2); нарушение advisory-требований brief'а — предупреждение, не отклонение ([[lessons]] §4d, PD-G).

### 4.3 Закрытие ReviewAssignment по вердикту [PD-2026-09-23]

- **MUST**: на один `review_id` — ровно одна терминальная диспозиция: ReviewOutcome либо, исторически (реплей старых сессий), `CANCELLED`. Терминальная диспозиция фиксируется **ровно один раз** по первому из следующих триггеров:
  1. **вердикт отчёта** по item'у, ссылающемуся на `review_id` — терминальный outcome вычисляется маппингом закреплённой `evidence@2.review_outcome_by_verdict`: `correct → CONFIRMED`, `partial → CONFIRMED` (частично верный ответ подтверждает цель — учебное решение, PD-D), `incorrect → REGRESSION` (`evidence/reviews.py::closure_from_verdict`). Движок по-прежнему выполняет саму классификацию outcome по таблице — отчёт несёт только вердикт, не готовый outcome.
  2. **явный skip отчёта** — item в `LessonReport.reviews_skipped[{review_id, reason}]` закрывает assignment как `INSUFFICIENT_EVIDENCE(reason)` (`close_insufficient`), где `reason` — `no_time` или `learner_declined`.
  3. **не адресован вовсе** — ReviewAssignment сессии, не упомянутый ни в `items[]`, ни в `reviews_skipped[]`, при коммите отчёта закрывается `INSUFFICIENT_EVIDENCE(reason=not_attempted)` — как часть того же атомарного коммита, не отдельным шагом ([[lessons]] §4).
  4. **`abandon` сессии** — преобразует оставшиеся pending цели в `INSUFFICIENT_EVIDENCE(reason=abandoned)`.
- **MUST — отмена не является ReviewOutcome** [RR2-4]: `CANCELLED` (прежний триггер — `replan`) в brief/report протоколе недостижим: мид-сессионного перепланирования не существует ([[control]] §4.2). Ветка остаётся определена только для replay сессий, записанных под прежним протоколом; `scheduler`/`scoring` по-прежнему трактуют её как terminal no-op, а не учебный исход.
- **MUST — correction ≠ второй outcome**: исправление уже терминального исхода идёт **только** через correction-событие ([[../platform/foundation]] §3.6); второго ReviewOutcome на assignment не возникает.
- **MUST**: ReviewOutcome и per-item вердикт — раздельные записи; scoring применяет transition по ReviewOutcome ([[scoring]] §3).

### 4.4 contribution_scope — cardinality [ревью 0.4-10]

- **MUST**: scope имеет **один `primary_scope`** (enum: `informal | writing | transfer | core_cefr`) + список `contributions[]` (по одному per-scope с весом и cap-allocation). Одно production-evidence может дать и `writing`, и `transfer` — оба как записи `contributions[]` с явными весами; cap применяется к пересечению informal↔core_cefr.
- **MUST**: Recognition сленга/мемов **никогда** не в core_cefr. Informal production в рабочем контексте даёт компонент writing/transfer с dedup и cap (один span — не в informal и core_cefr сверх cap). Все веса фиксируются в event (см. `CreditAllocation`).

### 4.5 capture-into-event [rereview A-2]

- **MUST**: любое operational значение, влияющее на scoring, фиксируется **в самом evidence-событии** с версией policy — не читается из operational store при replay.
- **MUST — rubric capture и атомарность (только placement)** [П.5, PD-2 B/PD-7 C]: rubric-assessment фиксирует resolved `rubric_ref`, pinned rubric version, rubric-input hash, accepted/rejected observations, machine results, integer `score_ppm`, calculation fingerprint и `assessment_basis: rubric`. Атомарный settle остаётся правилом [[assessments]]; обычные занятия этот путь не используют.
- **MUST — упорядоченность внутри коммита отчёта, не ссылка на предшествующий снимок** [PD-2026-09-23]: обычный Attempt больше не ссылается на предварительно зафиксированный `STEP_PRESENTED`/rendered-снапшот — такого снимка не существует. Вместо этого `lessons.report::commit_report` обязан **сначала** добавить `session.step_presented` этого item'а, а сразу за ним, в той же UoW, — его `attempt.recorded`/`evidence.added`/ошибки ([[lessons]] §4d): порядок append, а не предшествующее событие, делает факт «задание дошло до тьютора» наблюдаемым раньше факта «на него дан ответ». Target/dimension/mode item движок берёт из самого item'а (§4.1), не выводит из плана.
- **MUST — origin** [ревью 0.4-4, CTRL-10, RR2-3]: evidence несёт immutable `origin` — **единый закрытый enum** `session | placement | re_entry | control_probe`; scoring применяет placement-ceiling по нему ([[scoring]] §4b).

### 4.6 Латентность и дрилл-блок [PD-2026-09-22, уточнено PD-2026-09-23]

- **MUST — `response_latency_ms` в чат-занятиях не передаётся** [PD-2026-09-23, PD-E]: схема `lesson_report@1` не несёт поля латентности ни на item, ни на item дрилл-блока — каждый Attempt, порождённый отчётом, записывает `response_latency_ms: null` («не измерялось», никогда не ноль — правило ниже не ослаблено, только источник значения исчез). Единственный потребитель поля, ось `automaticity` ([[scoring]] §3d), поэтому в чат-занятиях **свёртывает только точность**: `not_measured → deliberate → proceduralized` остаются достижимы из точности дрилл-блока, а `proceduralized → automatic` — честно **недостижим** для evidence, пришедшего из отчёта, пока другой канал не станет поставлять латентность (без подмены синтетическим значением).
- **MUST NOT — отсутствие это не ноль**: отсутствующее `response_latency_ms` означает «не измерялось». Подставлять ноль, медиану или любое значение по умолчанию запрещено.
- **MUST — один Attempt на дрилл-блок**: блок отчёта (`LessonReport.blocks[]`, `block_id`) фиксируется **одним** Attempt с массивом `items[]` (`evidence/report.py::build_block_attempt_payload`), где каждый элемент — `{index, prompt_ref, raw_answer, verdict, objective_correct, credited, self_repaired}`. `index` монотонен от нуля и уникален внутри блока.
- **MUST — оценка на уровне блока**: блок-Attempt получает `assessment.correct = True`, когда доля credited items с `verdict == correct` достигает `BLOCK_CORRECT_THRESHOLD_PPM`; `block.score_ppm` несёт саму точность. `objective_correct` каждого item'а — производная от вердикта тьютора на этот item, а не отдельная его самооценка.
- **MUST — каждый item это отдельный source-span**: для дедупликации `span_hash` считается **по каждому `items[].raw_answer` отдельно**, и правило «один source-span не более раза на пару (target, dimension)» (§4.1) применяется поштучно — повторный item помечается `credited: false` и в точность блока не входит.
- **MUST — пустой или частичный блок**: блок без `items[]` отклоняет весь отчёт кодом `block_unknown`; item блока без `raw_answer` — недопустимый вход (`empty_answer`), а не «непредъявленный» — отчёт заполняется тьютором постфактум, недостающих items в нём по определению нет.

## 5. CLI-поверхность

Прямого CLI-доступа у evidence нет [PD-2026-09-23]: единственный вход — `trainer session report`/`trainer session check-report`, владеет которыми [[lessons]] (§4d, §6). Rubric-путь placement обслуживают команды [[assessments]] (`trainer placement answer`/`submit`).

## 6. Границы

- **depends on**: kernel (envelopes, идентичность, capture-into-event), curriculum (target/dimension/rubric refs, pinned versions).
- **events published**: `ATTEMPT_RECORDED`, `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `ERROR_OBSERVED` (все — записываются `lessons.report` внутри его UoW, PD-2026-09-23; `REVIEW_ASSIGNMENT_CANCELLED` недостижимо новым протоколом, остаётся для replay).
- **consumed by**: lessons (report commit вызывает builders этого модуля внутри своей UoW), scoring (факты → scores), scheduler (outcome → интервалы), memory (проекция), audit.

## 7. Открытые вопросы

- **OPEN-7** закрыт: identity/independence/multi-credit allocation/observation-disposition определены; численные веса — versioned `evidence@1`/`evidence@2`.

## История изменений

- **2026-09-23**: [PD-2026-09-23] переход на протокол «задание → отчёт»: §4.2 переписан — тьютор решает правильность (вердикт `correct/partial/incorrect` по `evidence@2.verdict_scale`), движок хранит prompt/дословный raw_answer/вердикт/причину ошибки, сам выводит span и дедуплицирует явно (`duplicate_span` — предупреждение check-report, не тихий пропуск); без trust-cap на вердикт (PD-F), проверка — постфактум аудитом. §4.3 переписан — закрытие ReviewAssignment по карте вердикта, явному skip отчёта или неадресованности (`not_attempted`); `CANCELLED` недостижим новым протоколом. §4.6 уточнён — латентность в чат-занятиях не передаётся, `automatic` недостижим без другого источника (PD-E). §3/§5 переписаны — прямого CLI у evidence нет, всё идёт через `lessons.report`; rubric-конвейер остаётся только для placement. Разворачивает прежнее «агент не выставляет себе оценки» и закрывает OPEN-4.
- **2026-09-22 (3)**: [PD-2026-09-22] §3 дополнен: rubric-профиль для `reconstruction`/`timed_writing` разрешается по сохранённому в снимке `rubric_step_type`, а не по сырому `step_type` попытки. *(Историческое: правило теперь применимо только к placement, PD-2026-09-23.)*
- **2026-09-22 (2)**: [PD-2026-09-22] `record_attempt` с `observations` оценивает открытый ответ в той же UoW, а `--close-review` закрывает ReviewAssignment шага там же. *(Историческое: `record_attempt`/`--close-review` ретайрены вместе с пошаговой доставкой, PD-2026-09-23.)*
- **2026-09-22**: [PD-2026-09-22] добавлен §4.6 — опциональное trusted-reported `response_latency_ms` и дрилл-блок как **один** Attempt с per-item `items[]`. *(Историческое: латентность в чат-занятиях больше не передаётся, PD-2026-09-23.)*
- **2026-07-22 (5)**: [PD-2026-07-22] численные multi-credit правила вынесены в `evidence@1`: primary 1.0, secondary 0.5, total cap 2.0, лишние allocations видимы как rejected-by-cap.
- **2026-07-22 (2)**: П.5 применена [PD-2026-07-22] — observation contract, refs/pin `rubric:<profile>`, machine/subjective граница по закрытым opcodes, полнота PD-7 C, rubric capture + атомарный settlement.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). untrusted-захват — в продукте (порядок в roadmap).
- **2026-07-21**: удалена конкурирующая сигнатура `record_attempt`; attempt валидируется по факту `STEP_PRESENTED`, а не по текущей композиционной ревизии; закрытие формализовано как `ReviewOutcome | CANCELLED`.
- **2026-07-20 (3)**: 0.4-rereview — единственное правило precedence для primary target + `selection_basis` в событии (R-4); явная граница закрытия ReviewAssignment, терминальность, идемпотентный повторный close, correction ≠ второй outcome (R-5).
- **2026-07-20 (2)**: 0.4-review триаж — детерминированный `CreditAllocation` record и единственная ветка для непроверенной observation (`rejected`, 0.4-5); cardinality `contribution_scope` (primary + contributions[], 0.4-10); immutable `origin` для placement-ceiling (0.4-4).
- **2026-07-20**: создан (контракт 0.4, часть 1). Наблюдения→движок, semantic identity, observation schema, AttemptAssessment vs ReviewOutcome, contribution_scope, capture-into-event. Решения из learning-model + review-триажей [PD-2026-07-19/20].
