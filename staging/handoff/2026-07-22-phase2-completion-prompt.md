# Codex handoff — довести Фазу 2 до конца (2.8c → 2.8d → 2.8e → lessons-обвязка → 2.9)

Ты завершаешь вертикальный срез **English Memory Trainer** (детерминированный Python 3.12 движок обучения английскому). Владелец (Claude) на паузе по лимитам и **примет каждый твой шаг независимо, когда вернётся** — поэтому работай так, чтобы каждый коммит был самодостаточным, честным и проверяемым.

## Где мы сейчас (контекст)

Фаза 0 (12 контрактов) и Фаза П (программа A1–C2, лексикон 1142) закрыты. Живут 11 модулей. Фаза 2 (срез): 2.1–2.6 done, 2.7 done-with-open (осталась OPEN-11), **2.8a сигналы+пробы** (`130540f`) и **2.8b saturation+starvation** (`801d1b8`) done как готовые чистые функции, но их **live-wiring в композицию отложен** (см. ниже). Осталось: 2.8c, 2.8d, 2.8e, общий lessons-проход (активация 2.8a/b/c и wiring), 2.9. Полный прогон сейчас: **420 passed / 1 xfailed** (единственный xfail — OPEN-11 в `tests/integration/test_tutor_swap.py`).

## Железные правила (для КАЖДОГО под-инкремента)

1. **Читай спеку перед кодом.** Источник истины — `wiki/`. Следуй каждому MUST. Термины — `wiki/glossary.md`.
2. **Изучай существующие паттерны и повторяй их.** Особенно `src/english_trainer/control/{compose,classify,signals,saturation,deferral,policy}.py`, `lessons/{sessions,delivery,resume}.py`, `evidence/`, `kernel/` (UoW, события, идемпотентность, injected Clock/RandomSource, canonical encoding, CAS `save_aggregate(expected_revision)`).
3. **Детерминизм — не обсуждается.** Только injected clock/random; никакого wall-clock в реплеях/хэшах; целочисленная арифметика на decision-пути (bp/ppm/seconds/days), никакого IEEE float; два прогона над одним логом — байт-идентичны. Новые входы в `compose_plan`/`classify_review_candidates` добавляй **только опциональными параметрами с честным пустым дефолтом**, чтобы дефолтный путь остался байт-идентичным и существующие тесты не менялись.
4. **Границы (арх-гейт `tests/architecture/`).** `control` импортит только `kernel`+`control` (события — межмодульный интерфейс, строковые литералы, не импортируй evidence/scheduler/lessons в control). Слой добавляй в `LAYER_ALLOWLIST` только если реально нужен новый импорт. Не ломай `command_registry()` 1:1 с published surface (+ `tests/cli/test_cli.py` parity) — каждую новую CLI-команду добавляй в оба.
5. **Честность.** `no-data`/пустой результат — легитимный исход, не фейковый ноль. Неполноту/деферралы/находки называй явно (как 2.8a/2.8b называли отложенный wiring). Не выдумывай.
6. **[PD]-развилки НЕ решай сам.** Продуктовые развилки (`wiki/OPEN.md`) решает пользователь. Если упрёшься в неспецифицированное дизайн-решение — **СТОП, оставь честный `xfail`/finding и переходи дальше**, не изобретай семантику.
7. **Env (Windows).** Python из venv: `.\.venv\Scripts\python.exe` (НЕ `python` из PATH — там 3.11 без pytest). pytest всегда с `--basetemp "<tmp>/pytest"`. Уникальные basename тест-файлов (дубли ломают сбор).
8. **Гейты перед каждым коммитом:** `pytest --basetemp ... -q` (полный, зелёный), `ruff check .`, `ruff format --check src tests`, `mypy src` (strict). Не коммить при красном без явного finding-объяснения.
9. **Коммить по-доменно, по одному под-инкременту за коммит**, явными путями (`git add -- <files>`), НЕ `git add -A`. НЕ трогай и НЕ коммить CRLF-шум (`AGENTS.md`, `wiki/modules/control.md`, `curriculum/lexicon/{chunks-work-frames,everyday-reactions,everyday-words,phrasal-verbs}.yaml`) и `Irregular Verbs.md` — у них пустой content-diff. Сообщение коммита кончай строкой `Co-Authored-By: Codex <noreply@openai.com>` (или твоей стандартной).
10. **Оставляй дерево чистым.** Если под-инкремент не доводится — заверши/откати частичное так, чтобы дерево было в коммиченном рабочем состоянии, и явно напиши, где остановился.
11. **Веди журнал прогресса** в `staging/journal/2026-07-22-phase2-completion.md` (append-only): по каждому под-инкременту — что сделал, коммит-хеш, гейты, находки. Это мой след для приёмки.
12. **Обновляй `wiki/roadmap.md`** по мере закрытия: статус-строку под-инкремента (`planned`→`done`), счётчики в блоке «Исполняемое» (тесты/команды/модули), «Ближайшее», запись в «Историю». Правь по одной строке, проверяя целостность таблицы (не слепляй строки). HTML-роадмап НЕ трогай — его пересоберёт владелец.

## Порядок работы (строго по зависимостям)

### 1. 2.8c — Availability (control §4.7a)
Спека: `wiki/modules/control.md` §4.7a (алгоритм v1), §3 policy `availability`, §2 `AvailabilityProfile`, §3b `availability_get/set`, §5 `trainer availability show/set`.
Сделать `src/english_trainer/control/availability.py`:
- целочисленная схема `declared{sessions_per_week_milli, typical_minutes, next_available_at?, blackout_until?}` / `observed{sessions_per_week_milli, typical_minutes, median_interval_seconds?}` (YAML-float запрещён);
- `observed` из окна `divergence_window_weeks` календарных недель (понедельник 00:00 в `LearnerProfile.timezone`; `now`/tz в trace): при `≥ min_observed_sessions` терминализованных сессий — `floor(count×1000/weeks)` и lower-median `total_seconds//60`, иначе `no-data`; `median_interval_seconds` — lower-median разностей соседних `SESSION_STARTED.started_at` при ≥3 стартах, иначе null; длительность STARTED→FINISHED НЕ используется;
- precedence бюджета: `--duration-minutes×60` → `declared.typical_minutes×60` → `observed.typical_minutes×60` → `default_total_minutes×60` (фиксировано);
- `divergence_ppm = floor(abs(declared−observed)×1e6/max(declared,1000))`; при `> divergence_tolerance_ppm` — предложение уточнить, `AVAILABILITY_UPDATED` только после принятого изменения (не переписывать declared без подтверждения);
- предикат длинного перерыва (blackout_until>now ИЛИ next_available_at−now>median_interval_seconds при непустом median); детерминированный re-entry critical-boost в `compose_plan` **после** starvation-резерва (`critical_boost_capacity = min(floor(total×reentry_critical_boost_bp/10000), residual_review_capacity, unplanned_remaining)`, first-fit `critical`, overshoot запрещён, `review_max`/growth-пол не нарушаются, `NO_CRITICAL_AVAILABILITY_CANDIDATE` в trace если нет кандидатов) — опциональным параметром, дефолт байт-идентичен;
- API `availability_get/set`, событие `AVAILABILITY_UPDATED`; CLI `trainer availability show|set` (`set` мутирующая, idempotency-key).
Тесты + коммит + журнал.

### 2. 2.8d — Decision trace (§4.8) + Метрики (§4.10) + Tunables/калибровка (§4.9)
Спека: `wiki/modules/control.md` §4.8, §4.10, §4.9, §3b (`explain`, `metrics`, `catalogue`, `propose_calibration`/`confirm_calibration`, события `CALIBRATION_PROPOSED/APPLIED`), §5 (`trainer why --step`, `trainer metrics`, `trainer tunables list`, `trainer calibration list|confirm`).
- **Trace**: у каждого шага `DecisionTrace` (decision_id, сработавшие правила §4.5 с номерами, risk/stake/retrievability, класс, состояние насыщения, применённые квоты, занятость корзин, применённые сигналы, `pinned_versions` вкл. `control_policy`, `active_safety_version`); каждое поле разрешается в строку каталога (§4.9) или помечено как вычисленный вход. `explain(step_id)` + `trainer why --step ID`. Composе записывает trace при материализации шага (расширь directive/шаг, храни trace как факт/агрегат — детерминированно).
- **Метрики**: `PolicyMetric`-фолды из таблицы §4.10 (`calibration_error`, `presented_review_share`, `presented_growth_rate`, `backlog_age_p90` nearest-rank, `max_deferrals`, `lapse_rate_after_mastered`, `transfer_gap`), каждая с окном и правилом отсутствия данных (`no-data`, не ноль). `calibration_error` берёт `STEP_PRESENTED.predicted_retrievability` **последнего выданного** шага review_assignment_id против терминального исхода (CONFIRMED/PROGRESS/RECOVERED→1, REGRESSION→0, INSUFFICIENT_EVIDENCE исключается, CANCELLED не входит). Аварии с **гистерезисом** (enter/exit пороги, `*_consecutive`, только `balanced`-занятия) — реакция «сообщить, не притормаживать». `trainer metrics`.
  - NB: `predicted_retrievability` должен писаться в `STEP_PRESENTED` **в момент выдачи** (не при композиции). Если его там ещё нет — добавь при claim шага (lessons/control), это часть §4.10 MUST.
- **Tunables**: versioned catalogue-артефакт (строка на КАЖДЫЙ параметр `control_policy@1` + ранее объявленные tunables соседей), валидатор полноты в обе стороны. Калибровка `propose_confirm`: control владеет только workflow «предложил→подтвердили»; активацию версии делает API модуля-владельца параметра (control не мутирует чужой aggregate); `CALIBRATION_APPLIED` связан `causation_id` с активацией у владельца. CLI `trainer tunables list [--owner X]`, `trainer calibration list|confirm ID`.
Тесты + коммит(ы) + журнал (можешь разбить на trace / metrics / tunables отдельными коммитами — так даже лучше для приёмки).

### 3. 2.8e — Reuse банка в композиции + observed-record (закрывает `ERROR_OBSERVED`)
Спека: `wiki/modules/control.md` §4.3a (источник упражнения: ровно одно из `bank_item_id`/`generation_directive`), `wiki/modules/lessons.md` (банк `generated→accepted/rejected→retired`, приём после оценённой попытки), `wiki/modules/evidence.md` §3/§4.5 (observed record, `ERROR_OBSERVED`, contradicts_machine_result).
- **Bank-reuse**: композиция может выбрать принятый ре-валидированный банк-item (`bank_item_id` вместо `generation_directive`), с **ре-валидацией по active safety при claim** и записью `ExerciseUse`. Банк-item НЕ создаёт evidence.
- **Observed-record**: evidence эмитит `ERROR_OBSERVED` (агент — trusted reporter конкретных наблюдений ошибок; движок записывает; `contradicts_machine_result`-проверка). **Согласуй имя события**: 2.8b использует провизорное `evidence.error_observed` в `control/saturation.py` (`EVENT_ERROR_OBSERVED`). Задай реальное имя в evidence и **обнови ссылку в saturation.py на совпадение** — после этого recurring-error (§4.5 risk) и метрики оживают. Обнови и `classify.py`-путь если нужно.
Тесты (в т.ч. что recurring-error теперь срабатывает от реальных `ERROR_OBSERVED`) + коммит(ы) + журнал.

### 4. Lessons-обвязка — активировать 2.8a/2.8b/2.8c/2.8d в живой композиции + OPEN-11
Это «общий lessons-проход», который 2.8a/2.8b/2.8c явно отложили. Домен: `lessons/{sessions,delivery}.py` (+ возможно `control` API-хелперы, `evidence`, `kernel`).
- В `start`/`replan` (UoW): собрать активные сигналы (`control.signals.active_signals`), saturation-state (`control.saturation.reduce_saturation`), recurring-errors, deferral-state (`control.deferral.reduce_deferrals`), availability-бюджет — и передать в `classify_review_candidates` + `compose_plan`; probe-кандидат построить из `PROBE_REQUESTED`; **`SIGNAL_CONSUMED` эмитить из возвращённого `compose`-`consumed` в ТОЙ ЖЕ UoW**, что сохраняет план; персистить `DecisionTrace`. `deferral_count` инкрементить при терминализации сессии (§4.5) — из фолда.
- Проверить сквозной эффект: `too_easy`→replan вставляет probe (origin=control_probe уже готов), сигналы реально двигают классы, saturation реально даёт `deferrable`, starvation-резерв реально admit'ит.
- **OPEN-11 (`expected_session_revision`)**: continuation-flow §Правила требует optimistic session revision — конкурентная запись с устаревшей ревизией отклоняется стабильной ошибкой. Ядро уже имеет CAS `save_aggregate(expected_revision)`. Добавь `expected_session_revision` в публичные session-мутации (`record_attempt`, `finish_session`, `mark_in_progress`, и т.п.), делай CAS по ревизии session-агрегата, стабильная ошибка при промахе; переверни strict-xfail `test_public_mutations_expose_optimistic_session_revision` в `tests/integration/test_tutor_swap.py` в проходящий. **ГАРДРЕЙЛ**: если это неоднозначно взаимодействует с `plan_version`-CAS или требует незаписанного дизайн-решения (multi-aggregate CAS-семантика OPEN-11) — СТОП, оставь xfail и напиши finding/мини-концепт в `staging/concepts/` пользователю на решение. Не изобретай concurrency-семантику.
Тесты + коммит(ы) по доменам + журнал.

### 5. 2.9 — Trust-контур (untrusted-захват + Tutor Compliance)
Спека: `wiki/roadmap.md` строка 2.9, `wiki/modules/audit.md` (корреляция obligations для Tutor Compliance), `wiki/modules/adapters.md`, `wiki/flows/continuation.md`, `wiki/product/learning-model.md`.
- Захват user-turn на adapter boundary (`provider_message_id` + content hash + span) как untrusted-данные; Tutor Compliance Score по расхождениям (audit — read-only корреляция). Session-lease — MAY (строить только если реальная одновременность агентов станет фактом — по умолчанию НЕ строить).
- Это наименее детально специфицированный кусок — если наткнёшься на неспецифицированное — оставь честный finding/xfail и опиши пробел, не выдумывай.
Тесты + коммит + журнал.

## Когда всё закрыто
Обнови `wiki/roadmap.md`: 2.7 → `done` (если OPEN-11 закрыт) или оставь `done-with-open`, 2.8 → `done`, 2.9 → `done`; блок «Исполняемое» и «Ближайшее»; запись в «Историю» с итогом Фазы 2. Финальный полный прогон зелёный. В `staging/journal/2026-07-22-phase2-completion.md` — сводка: что закрыто, какие findings/[PD] остались пользователю, финальные счётчики.

## Что сделает владелец
Когда лимиты сбросятся — независимая приёмка каждого твоего коммита своими гейтами (полный pytest/ruff/mypy), воспроизведение MUST'ов по спеке, разбор findings и [PD]-решений, пересборка HTML-роадмапа. Поэтому: честные коммиты, честный журнал, чистое дерево на каждом шаге.
