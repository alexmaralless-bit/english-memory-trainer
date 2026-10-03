# Концепт: «задание → отчёт» — тьютор ведёт урок, движок предлагает и фиксирует

> Phase: concept only. Date: 2026-09-23.
> Canon status: **не канон**. `wiki/`, `src/`, `tests/`, `curriculum/`, `agent-skills/` не менялись.
> Триггер: живой урок 2026-09-23 и запрос ученика — «движок не должен быть жёстким бюрократом и диктовать урок… урок должен приходить как промпт с описанием и требованием, а в конце урока загружать отчёт по форме».
> Основа: карта кода (lessons, evidence, scoring, scheduler, control, audit, cli, skills, wiki) и дизайн архитектора (Opus), 2026-09-23.


## Context

Живой урок 2026-09-23 показал, что пошаговый протокол (`session next → exercise rendered → attempt record …`) превращает тьютора в оператора движка: ~25 вызовов на 4 задания, CAS-токены на каждом шаге, план не адаптируется («я это знаю» → всё равно new_material_intro), ошибка формата `rubric_criterion_ref` молча и необратимо сделала evidence non-contributing, `session start` с `--profile/--topic` ложно считал proposal устаревшим. Ученик решил:

- движок **предлагает** (урок, тему, повторения, требования) и **фиксирует** результаты; урок целиком ведёт тьютор;
- взаимодействие — **задание (brief) в начале, один отчёт (report) в конце**;
- обрыв чата — через контекст Claude Code (`resume`), **без** локального черновика и промежуточных чекпойнтов;
- **правильность каждого задания решает тьютор**; движок не перегрейдит, но хранит evidence (prompt + дословный ответ + вердикт + причина ошибки), детерминированно агрегирует, планирует повторения, считает уровни.

Решения ученика по развилкам (AskUserQuestion, 2026-09-23):
- шкала вердикта `correct 1.0 / partial 0.5 / incorrect 0`; **partial закрывает повторение как CONFIRMED**;
- автоматизм — **только точность**: `latency_ms` не передаётся, уровень `automatic` пока недостижим (честно, без выдуманных чисел);
- **никакого trust-cap** на вердикты тьютора; проверка — постфактум `audit-english-tutor` по сохранённым ответам;
- требования brief'а (задание по центральной теме, адресованные повторения) — **только предупреждения**, отчёт не отклоняется.
- (дефолт) практика due-цели без назначенного на старте review → только evidence, без review outcome.

Это разворачивает канон: `docs/design-direction.md` «Агент-преподаватель не выставляет себе оценки», evidence §4.2/§4.3 (trusted reporter + engine verdict), OPEN-4 (закрыт как «вердикт у движка»), фикстура `agent-attempts-self-score`. Всё фиксируется как [PD-2026-09-23].

## Ключевой дизайн-принцип

**Сохранить событийный контракт, сменить только его производителя.** Все потребители (scoring, scheduler, control, audit, memory, xp) читают `session.step_presented`, `attempt.recorded`, `evidence.added`, `review.outcome`, `evidence.error_observed`. Отчёт становится единственным писателем этих фактов → folds почти не меняются, старые события (урок и placement 2026-09-23) реплеятся байт-в-байт.

## Интерфейс

CLI-namespace остаётся `session` ([PD-2026-07-19]).

| Команда | Роль |
|---|---|
| `session propose` (read-only, без изменений) | рекомендация, тьютор объявляет её ученику |
| `session start --profile --topic --duration [--theme]` | явные аргументы = согласие; **`--expected-proposal-hash` удаляется**; внутри всё как сейчас (sweep, pins, `compose_plan`, review assignments, `session.started/composed`); возвращает `{session_id, brief}` |
| `session resume` | для активной сессии — тот же brief, пересобранный из состояния |
| `session check-report --file r.json` (read-only, новая) | валидация без записи: по каждому item accepted/rejected + причины + эффекты (score, contributing, review outcome), предупреждения |
| `session report --file r.json --idempotency-key K` (новая) | атомарная запись всего отчёта + finish; любой rejected item → отказ целиком; без session-revision токена |
| `session abandon`, `session status` | без изменений |

**Brief `lesson_brief@1`** (`lessons/brief.py::build_brief`, поглощает `lessons/resume.py::build_briefing` без `next_step`):
`lesson` (profile, title, reason, agenda, language_envelope, duration) · `central_topic` (target_ref, can_do, newness + факты программы: explanation, typical_errors, фреймы с `frame_of/carries`, reconstruction text для drill) · `reviews_due` (review_id, target_ref, dimension, urgency, RU-подсказка смысла) · `plan` (advisory шаги из `compose_plan` + drill-поля `with_drill_fields`) · `learner` (уровни, known_language, personal lexicon, **реальные** recent errors из `evidence.error_observed` вместо захардкоженного `top_errors: []`, re_entry, last summary, preferences) · `requirements` (advisory) · `report_contract` (schema id, лимиты, `brief_hash`).

**Report `lesson_report@1`**:
```json
{"schema":"lesson_report@1","session_id":"…","brief_hash":"…",
 "items":[{"item_id":"i1","target_ref":"grammar.be.identity","dimension":"controlled_production",
   "kind":"recall|recognition|production|review|drill_item|conversation",
   "prompt":"…","raw_answer":"…","verdict":"correct|partial|incorrect","hints":0,
   "secondary_targets":[], "review_id":null, "block_id":null,
   "errors":[{"learner_form":"a teacher and an editor","correction":"a teacher and editor","cause":"…","topic_error_ref":null}]}],
 "blocks":[{"block_id":"b1","target_ref":"…","mode":"blocked|interleaved"}],
 "reviews_skipped":[{"review_id":"…","reason":"no_time|learner_declined"}],
 "teaching":[{"target_ref":"…","summary":"…"}],
 "lexicon":[{"surface":"pull an all-nighter","linked_item_id":null,"note_ru":"…"}],
 "summary":{"text":"…","next_focus":"…"}}
```
Отклоняющие коды: `unknown_target`, `bad_dimension`, `empty_answer`, `bad_verdict`, `review_mismatch`, `learner_form_not_in_answer` (span движок выводит сам — тьютор никогда не шлёт offsets), `block_unknown`, `duplicate_item_id`, `too_many_items`. Не отклоняющие: `duplicate_span` → `contributing:false`, **явно показан** в check-выводе; нарушения requirements/envelope → warnings.

## Путь записи (`lessons/report.py::commit_report`, одна транзакция)

1. `lesson.reported` — весь отчёт + `report_hash` + результат валидации (provenance/аудит; заменяет teaching snapshots и notes).
2. На каждый item по порядку (builders читают `store.read()` внутри той же UoW — поэтому append по одному, производные после каждого): `session.step_presented` (`source:"lesson_report"`) → attempt aggregate + `attempt.recorded` (`status:"assessed"`, `assessment:{basis:"tutor_verdict", verdict, correct, score_ppm}`) → `evidence.added` (`assessment_basis:"tutor_verdict"`, `allocate_credit`, prompt) → `_automaticity_updates` → по `evidence.error_observed` на каждую ошибку (`reported_by:"tutor"`, выведенный span).
3. Блок: один `attempt.recorded` + `evidence.added` c `form:"drill_block"`, items `{objective_correct: verdict=="correct", verdict}` — поле, которое уже читает `scoring/automaticity.py`.
4. Повторения: referenced review → `review.outcome` по evidence@2-карте (correct/partial→CONFIRMED, incorrect→REGRESSION) + `build_state_transition`; остальные pending → `INSUFFICIENT_EVIDENCE` (reason `not_attempted` или skip-reason). Новое `evidence/reviews.py::closure_from_verdict`; `_outcome_from_assessment` получает ветку `tutor_verdict`.
5. Лексикон: `learner.lexicon_entry_added` через чистый `learner/lexicon.py::build_encounter_events` (новое ребро `lessons→learner` в `LAYER_ALLOWLIST`).
6. `session.finished` через `_close_session` без pending-gate (отчёт закрывает всё атомарно).

Чистые builders — `evidence/report.py` (payload, derivation span, маппинг вердикта); границы слоёв соблюдены.

**Scoring:** явная ветка `tutor_verdict` в `scoring/engine.py::fold_scores` (quality = score_ppm/1e6, session cap, **без rubric_cap**; сейчас неизвестный basis попадает под rubric_cap). Старые события не несут `tutor_verdict` → replay идентичен.

## Политики

| Политика | Содержание |
|---|---|
| `evidence@2` (новая) | multi_credit как @1; `verdict_scale {correct:1000000, partial:500000, incorrect:0}`; `review_outcome_by_verdict {correct:CONFIRMED, partial:CONFIRMED, incorrect:REGRESSION}`; лимиты отчёта; severity tutor-ошибок. `evidence/policy.py::require_valid` → version-aware |
| `lessons@2` (новая) | `stale_session_days`, `brief_schema`, `report_schema`, advisory requirements |
| `obligations@4` (новая) | `report_committed`, `reviews_addressed`, `lesson_preflight`, `required_skill_effect`, `forbidden_action_absence`; `audit/views.py::obligations` сохраняет @3-оценщик для старых сессий |
| `control@3`, `generation@3`, `scheduler@2`, `automaticity@1`, `scoring@2`, `tunables@2` | без изменений, пинятся |
| `rubric@1` | убирается из `_pin_versions` сессии; остаётся для placement (`placement.py` импортирует `compute_rubric_assessment`) и replay |

## Удаление

- **Команды:** `session next/peek/replan/finish`, `teaching rendered`, `exercise rendered/prepare/render-prepared/accept/reject/retire/bank`, `attempt record/record-block/finalize`, `observed record`, `review close`, `turn submit`, `signal`.
- **Остаются:** propose, start, resume, abandon, status, check-report, report, review due, scoring.*, memory.*, curriculum.*, lexicon.*, placement.*, preferences, audit.*, availability, why, metrics, skills.*, adapters compare/capture-turn, doctor, init, snapshot.
- **Модули удаляются:** `lessons/delivery.py`, `rendering.py`, `preparation.py`, `bank.py` (compose получает `bank_items=[]`), `teaching.py`. **Урезаются:** `evidence/attempts.py` (остаются константы, span/credit helpers, `_automaticity_updates`, `session_attempts`), `evidence/observed.py` (константа). **Остаются:** `lessons/forms.py` (brief выбирает фреймы/тексты), `evidence/assessment.py` + `rubric.py` (placement).
- **Старые типы событий читаемы:** строки имён событий удалённых модулей переезжают в потребителей.
- **Тесты:** удаляются тесты удалённого поведения (lessons/test_delivery, test_rendering, test_preparation, test_bank*, test_review_rubric, test_finish_requirements; evidence/test_lean_protocol, test_block_attempts, test_attempts, test_rubric_step_type, test_observed; integration/test_lean_protocol_flow, test_drill_block_flow); переписываются на отчёт test_tutor_swap, test_learner_lexicon, test_automaticity_forms, scoring/test_block_evidence; **новый golden-replay**: хэш `scoring replay` реального журнала 2026-09-23 одинаков до и после.

## Волны (субагенты; Opus 5.5 — сложное, Sonnet 5 — среднее/простое)

**W0 — канон (сразу после одобрения плана).** Я пишу концепт `staging/concepts/2026-09-23-lesson-brief-report.md` (этот план + схемы + политики) и журнал `staging/journal/2026-09-23-brief-report.md`. Ученик говорит «ок» по концепту → W1.

**W1 — фундамент (параллельно, непересекающиеся файлы):**
- **A (Opus):** `evidence/report.py` (новый), `evidence/policy.py`, `evidence/reviews.py` (verdict-ветка), `curriculum/policies/evidence-v2.yaml`, `tests/evidence/test_report_builders.py`. Приёмка: builders чистые, span выводится, пакет items в одной транзакции даёт верные automaticity/transition-факты.
- **B (Sonnet):** `scoring/engine.py` (`tutor_verdict`), `tests/scoring/test_tutor_verdict.py`, golden-replay тест. Приёмка: хэш replay старого журнала неизменен.
- **C (Sonnet):** `learner/lexicon.py::build_encounter_events` + тесты.
- **D (Sonnet):** `audit/views.py` (obligations@4), `obligations-v4.yaml`, `lessons-v2.yaml`, `tests/audit/test_obligations_v4.py`.

**W2 — ядро (Opus, один агент):** `lessons/brief.py`, `lessons/report.py` (`check_report`, `commit_report`), `lessons/sessions.py` (start без hash, pins, close без gate), `lessons/resume.py`, `lessons/__init__.py`; тесты `tests/lessons/test_brief.py`, `test_report.py`, `tests/integration/test_report_flow.py`. Приёмка: start → check → report → replay идентичен; rejected отчёт не пишет ничего; повтор ключа → cached; `presented_targets`/saturation/deferral видят items.

**W3 — CLI и удаление (Sonnet, единственный владелец горячих файлов):** `cli/app.py`, `cli/registry.py`, `tests/architecture/test_boundaries.py` (`lessons→learner`), `tests/cli/test_cli.py`; удаление команд/модулей/тестов из списка выше.

**W4 — параллельно:**
- **E (Opus):** `agent-skills/`: `run-english-session` v10 (+ `references/pedagogy.md`: вердикт тьютора, формат отчёта, сбор items в контексте), `run-drill-block` v4, `run-spaced-review` v6, `coach-english-conversation` v6, `finish-english-session` v2 (check-report → report / abandon), `audit-english-tutor` v2; `correct-learner-output`, `teach-english-topic`, `assess-english-gate` → без CLI-вызовов (педагогические справки) или сливаются; `adapters/compare.py::DEFAULT_FIXTURES` (`agent-attempts-self-score` → фикстура отчёта), `tests/adapters/*`; `skills sync` + `skills validate`.
- **F (Sonnet):** вики: `wiki/modules/lessons.md`, `evidence.md`, `control.md`, `scoring.md`, `audit.md`, `adapters.md`, `cli.md` §5, `wiki/flows/session.md`, `continuation.md`, `glossary.md` (LessonBrief, LessonReport, tutor verdict; снять PlannedStep-доставку), `docs/design-direction.md` (разворот ограничения с [PD-2026-09-23]), `wiki/roadmap.md` (раздел «Фаза 4», «Где мы сейчас», история), `wiki/OPEN.md` (OPEN-4 примечание; OPEN-43 сузить до placement; OPEN-40…43 остаются), `CLAUDE.md` + `AGENTS.md` синхронно.

**W5 — приёмка (я):** полный `.venv/bin/pytest`, `ruff check .`, `ruff format --check src tests`, `mypy src`, `trainer skills validate`, `trainer adapters compare`, `trainer scoring replay`, `trainer memory check`; затем живой урок: `session propose` → `session start` → урок без вызовов → `session check-report` → `session report` → `trainer status`. Коммиты — я, по волнам (первый включает текущие OPEN-40…43).

## Вне скоупа (отдельно после фазы)
- Правка фреймов `be.identity` через `maintain-english-curriculum` (`What are you?` как «кто вы по профессии»; заметка «work as без артикля»).
- OPEN-40/41/42 (placement: resume без items, decline не закрывает активный, ключ всегда первым).
