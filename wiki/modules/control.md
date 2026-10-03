# Модуль: control

> **Status**: current
> **Last updated**: 2026-09-23
> **Sources**: концепт `staging/journal/2026-07-20-concept-0.12-learning-control.md` (Concept Gate, 6 развилок) · red-team ревью 0.12 `staging/reviews/2026-07-20-control-review-codex.md` (5 BLOCKER, триаж) · `staging/concepts/2026-09-23-lesson-brief-report-concept.md` (одобрен, [PD-2026-09-23]) · [[scheduler]], [[scoring]], [[evidence]], [[lessons]], [[learner]], [[gates]] · контракт 0.12
> **Bounded context**: `src/english_trainer/control/`

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — по [[../glossary]]. Все численные значения §3 — **конкретные авторские дефолты**, не диапазоны: policy обязана быть исполнимой, калибровка приходит позже.

---

## 1. Назначение

Остальные контракты отвечают, одинаков ли результат при одинаковом входе. Этот отвечает, хорош ли выбранный вход. Модуль решает, **что попадёт в занятие и в какой пропорции**, измеряет качество собственных решений и предоставляет механизм безопасной подстройки. Знание он не измеряет и менять не вправе.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `SessionPlan` (advisory) [PD-2026-09-23] | рекомендованный состав занятия, вкладываемый целиком в `LessonBrief.plan` | `session_id`, `lesson_arc`, `steps[]`, `budget`, `pinned_control_policy`, `created_at` — без `composition_revision`/`plan_version`: не CAS-aggregate |
| `LessonProposal` | read-only объявление до старта | `profile`, `title`, `duration_class`, `central_topic`, `reason`, `agenda`, `language_envelope`, `proposal_hash` |
| `PlannedStep` | один рекомендованный шаг — **tagged union по `kind`** (§4.3a) | общие: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `generation_directive?`, `lexicon_first?` — без `presented_at?`/`bank_item_id?`: план не отслеживает выдачу и не ссылается на банк упражнений (retired) |
| `UrgencyClass` | класс review-кандидата | `critical \| important \| normal \| maintenance \| deferrable` |
| `SaturationState` | признаки перепоказа | ключ **`(target_ref, dimension)`** [RR2-13], `exposures_in_window`, `consecutive_independent_successes`, `distinct_contexts`, `last_transfer_check_at` |
| `AvailabilityProfile` | ритм занятий | `declared{...}`, `observed{...}`, `divergence`, `updated_at` |
| `DecisionTrace` | основание решения | `decision_id`, `step_id`, `reasons{}`, `pinned_versions{}` |
| `TunableParameter` | строка каталога настроек | §4.9 |
| `PolicyMetric` | определение метрики (§4.10) | `id`, `inputs[]`, `cohort`, `formula`, `window`, `missing_data_rule` |

`SessionPlan.budget.mode` — `balanced` (по умолчанию) · `maintenance` · `re_entry`. Только в двух последних допустимо занятие без нового материала.

[PD-2026-09-23] `LessonArc` и `LearnerControlSignal` ретайрены ([[../glossary]]): связную дугу занятия теперь несёт `LessonBrief.lesson`/`central_topic` напрямую, а сигналам ученика (`too_easy`, `snooze`, …) больше некуда применяться — мид-сессионного `replan`, которому они были адресованы, не существует (§4.7).

`SessionPlan` не lifecycle-aggregate: у него нет состояний PLANNED/CONSUMED/DISCARDED. `compose_plan` — чистая функция текущего состояния ученика и pinned `control_policy`; она вызывается заново при каждом `LessonBrief` (`start` или `resume`, §4.2) и между вызовами не хранится как CAS-версионируемая сущность.

## 3. `control_policy` — versioned и исполнимая

Регистрируется в реестре политик kernel ([[../platform/foundation]] §3.6) наравне с curriculum/scoring/scheduler и пинится в Session Manifest ([[lessons]] §4b).

```yaml
control_policy:
  version: 3                             # [PD-2026-09-22]: + step_types контура автоматизации
  budget:
    default_total_minutes: 30
    min_total_minutes: 10
    expected_seconds_by_step_type:      # оценка стоимости шага
      recognition_check: 30
      controlled_production: 120
      spontaneous_production: 360
      transfer_task: 480
      new_material_intro: 300
      integration_task: 420
      gate_item: 180
      free_conversation: 300
      drill_block: 300          # [PD-2026-09-22]
      timed_writing: 300        # [PD-2026-09-22]
      reconstruction: 300       # [PD-2026-09-22]
    # Доли — целые basis points (1 bp = 1/10000). Двоичный float запрещён
    # на всём пути: allocation = floor(total_seconds * bp / 10000) [R-12].
    shares_bp_by_mode:
      balanced:    {review_max: 4500, growth_min: 2500, integration_min: 1500, choice_min: 1000}
      maintenance: {review_max: 10000, growth_min: 0, integration_min: 0, choice_min: 1000}
      re_entry:    {review_max: 8000, growth_min: 0, integration_min: 0, choice_min: 2000}
  classification:                        # вероятности — целые ppm (1e-6), не float
    critical_floor_retrievability_ppm: 500000
    maintenance_floor_retrievability_ppm: 850000
    recurring_error_window_sessions: 3
    recurring_error_min_occurrences: 2
    prereq_leverage_min_dependents: 2
  starvation:
    reserved_steps_per_session: 1
    deferrals_to_qualify: 3
  signals:
    default_effect_sessions: 3
  saturation:
    exposure_window_sessions: 5
    max_exposures_in_window: 3
    consecutive_success_threshold: 3
    min_distinct_contexts: 2
    transfer_check_staleness_days: 30
  diversity:
    max_steps_per_topic: 2
    max_consecutive_same_mode: 2
    max_similar_items: 2
  availability:
    divergence_tolerance_ppm: 300000
    divergence_window_weeks: 6
    min_observed_sessions: 3
    reentry_critical_boost_bp: 1000
  alerts:                                # только для mode=balanced [R-8]
    review_share_enter_bp: 4200
    review_share_exit_bp: 3500
    review_share_consecutive: 3
    growth_rate_enter_bp: 1000
    growth_rate_exit_bp: 1800
    growth_rate_consecutive: 3
```

- **MUST — policy тотальна и исполнима**: каждая ветка §4 имеет конкретное значение здесь. Диапазонов нет; `allowed_range` живёт в каталоге (§4.9) и ограничивает будущие версии, а не заменяет значение.
- **MUST — выполнимость долей проверяется на каждый mode**: для любого режима `growth_min + integration_min + choice_min ≤ 10000` и `review_max + growth_min ≤ 10000`. Версия, нарушающая это хотя бы в одном режиме, не активируется.
- **MUST — дискретная достижимость полов** [RR2-5]: алгебра долей не доказывает, что план собирается. Для каждого режима, каждого ненулевого пола и каждого значения `total_seconds` от `min_total_minutes` до `default_total_minutes` валидатор проверяет, что существует хотя бы один допустимый для корзины `step_type` с `expected_seconds ≤ total_seconds`. Размер самого пола **не** обязан покрывать шаг: это противоречило бы следующему правилу и делало бы дефолт `integration_min = 1500 bp` невалидным при 30 минутах.
- **MUST — неделимый шаг разрешено превысить резерв** [RR2-5]: следующий шаг, которым корзина впервые достигает или пересекает ненулевой остаточный пол, допускается целиком, даже если его стоимость больше оставшейся ёмкости пола, при условии что он помещается в общий остаток бюджета текущей сборки (`total_seconds` минус уже допущенные в этом же вызове `compose_plan` шаги). После него пол считается закрытым; последующие шаги подчиняются обычному first-fit. Пол — гарантия **попытки**, а не потолок.
- **MUST — целочисленная арифметика на всём decision-пути** [R-12, RR2-12]: **каждое** поле policy, влияющее на решение, хранится целым: доли — basis points, вероятности и допуски — ppm (1e-6), время — секунды. Аллокация — `floor(total_seconds * share_bp // 10000)`; сравнение с порогом — над Retrievability, приведённой к ppm тем же правилом округления, что и [[scoring]] §2.1. Валидатор **отвергает YAML-float в любом decision-bearing поле**, а не только в долях: на граничной Retrievability разные преобразования float меняли бы класс, и replay переставал бы быть побитовым.

## 3b. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `compose_plan(...)` (`control/compose.py::compose_plan`) | API (pure, вызывается синхронно внутри `start`/`resume`) | строит advisory `SessionPlan`, вкладываемый в `LessonBrief.plan`; ошибки `BUDGET_TOO_SMALL`, `NO_CANDIDATES` |
| `propose_lesson(duration?, profile?, topic?, theme?)` | API (read-only) | предлагает название, причину, один central target, agenda и language envelope; возвращает `proposal_hash` |
| `classify(candidates)` | API (pure) | `UrgencyClass` по §4.5; детерминирована, без побочных эффектов |
| `explain(step_id)` | API | `DecisionTrace` |
| `availability_get()` / `availability_set(declared)` | API | §4.7a |
| `metrics()` / `catalogue()` | API | §4.10, §4.9 |
| `propose_calibration()` / `confirm_calibration(id)` | API | §4.9; активацию делает владелец параметра |
| `SESSION_COMPOSED {session_id, steps[], budget, pinned_versions, active_safety_version}` | publishes | advisory-план собран для очередного `LessonBrief` (start либо resume); без `composition_revision`/`plan_version` |
| `AVAILABILITY_UPDATED`, `CALIBRATION_PROPOSED`, `CALIBRATION_APPLIED` | publishes | — |

[PD-2026-09-23] **Retired**: `replan`, `claim_next_step`, `peek_next_step`, `record_signal` и события `LEARNER_SIGNAL_RECORDED`, `SIGNAL_CONSUMED`, `PROBE_REQUESTED`. `STEP_PRESENTED` остаётся типом события, но control им больше не владеет: его публикует отчёт постфактум, по каждому item'у ([[lessons]] §4d, [[../glossary]]). Мид-сессионной мутации плана не существует — `compose_plan` пересобирается целиком на каждый `LessonBrief`.

## 4. Поведение

### 4.1 Инварианты

- **MUST — `due` это кандидат, а не право**: наступление срока не даёт цели места в занятии. Невзятое остаётся в backlog и ошибкой не является.
- **MUST — защищённый минимум роста**: в режиме `balanced` корзина `growth` заполняется **первой** (§4.4) и не может быть занята повторениями. Занятие целиком из повторений возможно только в режимах `maintenance`/`re_entry`, выбранных явно.
- **MUST — доступность влияет на нагрузку, никогда на знание**: `AvailabilityProfile` не входит ни в одну формулу [[scoring]]. Реальное время забывания не подделывается.
- **MUST — каждое решение несёт trace**: §4.8.
- **MUST — подчинение safety-overlay**: единица, ставшая `avoid`/`obsolete` по **active** policy, исключается из плана независимо от класса. `SESSION_COMPOSED` фиксирует `active_safety_version`, использованную при исключении, — safety при этом **не** становится pinned policy ([[../OPEN]] OPEN-14).
- **MUST — калибровка не ретроактивна**: §4.9.

### 4.2 Жизненный цикл композиции [CTRL-2, PD-2026-09-23]

- **MUST — композиция синхронна с каждым brief'ом**: `lessons.start` и `lessons.resume` синхронно вызывают `compose_plan` **до** возврата ответа, в той же UoW, что создаёт/читает сессию, и вкладывают результат прямо в `LessonBrief.plan` ([[lessons]] §4c). Композиция — чистая функция текущего состояния ученика и pinned `control_policy`; отдельного персистентного `SessionPlan`-агрегата, версionируемого CAS-командами, не существует. `SESSION_COMPOSED` публикуется через outbox той же UoW.
- **MUST — план не мутируется между brief'ами**: нет `claim_next_step`, `peek_next_step`, `replan`, `plan_version`. Тьютор ведёт занятие свободно в пределах budget'а, который brief предложил; если он выходит за пределы предложенного плана (другая тема, больше повторений), движок этого не гейтит — он узнаёт об этом постфактум из `LessonReport.items[]`.
- **MUST — safety на композиции, не на доставке** [PD-2026-09-23]: `production_eligible` исключает единицы из плана в момент `compose_plan` (§4.1, safety-overlay) — так же, как исключало раньше из `SessionPlan`. Отдельной live-проверки перед показом задания, которая раньше отклоняла `session next` с `PRECONDITION_FAILED {reason: safety_changed}`, больше нет: контент, который тьютор фактически использует в чате, движку виден только постфактум, из отчёта. Программный safety-каталог по-прежнему решает состав плана и рекомендаций; добросовестность фактически проведённого содержимого проверяет постфактум `audit-english-tutor` ([[lessons]] §4b).
- **MUST — `resume` пересобирает план заново**: у `resume` нет сохранённого «остатка бюджета» — он вызывает `compose_plan` с текущим состоянием ученика и возвращает пересобранный `LessonBrief` ([[lessons]] §4c). Незакрытые ReviewAssignment брошенной/не отчитанной сессии остаются кандидатами `review`-корзины при пересборке.
- **MUST — `step_id` не требует межвызовной стабильности**: план собирается заново на каждый brief, поэтому понятия «тот же шаг между ревизиями», которое раньше защищал `replan`, больше нет; `decision_id` по-прежнему ссылается на trace, породивший шаг текущего вызова.

### 4.2a Learner-facing профиль и связная дуга [PD-2026-07-23]

- **MUST — профиль отделён от механики**: `LessonProfile` объясняет ученику вид занятия; внутренние `mode` и `step_type` продолжают управлять бюджетом и отдельными шагами и не используются как название урока.
- **MUST — preflight**: до старта система строит `LessonProposal` с названием, профилем, длительностью (`micro` 10–19 минут, `full` от 20), центральной темой, причиной, agenda и language envelope. Прямой запрос `--profile`/`--topic`/`--theme` является согласием. Автоматическая рекомендация требует объявления и подтверждения. [PD-2026-09-23] Сверка `--expected-proposal-hash` на `start` удалена вместе с CAS-протоколом доставки: прямой запрос принимается как согласие без сверки хеша устаревшего предложения.
- **MUST — выбор ученика главнее рекомендации**: явный topic/theme/profile заменяет системный выбор, но не меняет scoring и не обходит safety. [PD-2026-09-23] Мид-сессионного `lesson_request`/`replan` не существует: новый выбор темы в уже начатой, но ещё не отчитанной сессии достижим только новым `start` (после `abandon` прежней) либо естественно — план advisory, и тьютор просто ведёт занятие по-своему, не будучи им ограничен.
- **MUST — одна центральная новая тема**: `program_lesson` имеет не более одного central new target. Допустимы короткий warm-up и один связанный уже известный target. Несколько несвязанных `new_material_intro` не образуют полный урок.
- **MUST — динамическая генерация**: профили задают структуру, а не матрицу заранее написанных уроков. План строится из curriculum, состояния ученика и прямого запроса. Full lesson проходит orientation → connection → explanation → guided retrieval → independent use → recap; micro lesson сохраняет ту же причинную дугу в меньшем объёме.
- **MUST — разговор ограничен понятностью**: `free_conversation` получает известные target'ы из briefing и допускает 1–3 новые полезные единицы; каждая незнакомая единица проходит `lexicon encounter`, который остаётся enrollment, не evidence.
- **MUST — профиль `drill`** [PD-2026-09-22]: одиннадцатый learner-facing профиль ([[../glossary]] LessonProfile) — занятие процедурализации. Каноническая agenda: **retrieval-разминка по due-материалу → ввод набора фреймов (правило одной строкой) → раунд 1 дрилла blocked → раунд 2 interleaved → реконструкция текста → timed writing → дебриф**. Профиль подчиняется общим правилам: он не меняет evidence-модель, не обходит safety и не отменяет ни `review_max`, ни полы корзин. Правило «объём практики превышает объём объяснения» ([[../product/learning-model]] §9.1) для него нормативно: полное «почему» живёт в финальном дебрифе, а не в ходе раундов.

### 4.3 Корзины образуют разбиение [CTRL-1]

- **MUST — каждый шаг ровно в одной корзине**: `bucket ∈ {review, growth, integration, choice}`, взаимоисключающе и исчерпывающе. [PD-2026-09-23] Для собранного плана `sum(steps[].expected_seconds) ≤ total_seconds` — проверяется один раз, при сборке; накопительного учёта между вызовами (`presented`/`planned`) больше нет.
- **MUST — определения корзин**:

  | Корзина | Что попадает |
  |---|---|
  | `review` | шаг по цели из due-backlog, классифицированной §4.5 |
  | `growth` | шаг по цели с `is_first_exposure = true` |
  | `integration` | задание, требующее одновременно новую и ранее изученную цель |
  | `choice` | свободный разговор или тема, выбранная учеником |

- **MUST — `is_first_exposure` определяется по факту доставки**: цель считается новой, если по ней **нет ни одного** `STEP_PRESENTED` (§4.6). `knowledge_state = NEW` для этого не годится: предъявление и объяснение не являются evidence, и цель остаётся `NEW` после нескольких показов.
- **MUST — не более одного growth-шага на цель в плане** [R-13]: иначе оба шага получили бы `is_first_exposure = true` при композиции, а после выдачи первого второй стал бы ложно считаться новым и в бюджете, и в телеметрии. Повторное обращение к той же цели в том же занятии — шаг `integration` или `review`, не `growth`.

### 4.3a Схема `PlannedStep` — tagged union [R-3]

Общие поля: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `generation_directive?`, `lexicon_first?`.

- **MUST — `generation_directive` advisory, не обязателен к использованию** [PD-2026-09-23]: шаг **может** нести `generation_directive` — каноничную подсказку для тьютора под pinned `generation@1`. Это ориентир, а не источник, который движок потом сверяет: тьютор волен вести задание иначе, и содержимое, которое он фактически использовал, движку видно только постфактум из отчёта ([[lessons]] §4b). Банк упражнений (`bank_item_id`, reuse принятых сгенерированных упражнений) ретайрен вместе с пошаговой доставкой ([[../glossary]] ExerciseBankItem).
- **MUST — план не создаёт evidence**: выбор шага или его `generation_directive` не создаёт evidence. Evidence по-прежнему требует сохранённого ответа ученика через отчёт ([[evidence]]).

| `kind` | Обязательные поля |
|---|---|
| `review` | `review_assignment_id`, `target_ref`, `dimension`, `criteria_ref`, `urgency_class` |
| `growth` | `target_ref`, `dimension`, `is_first_exposure: true` |
| `integration` | `targets[]` из `{target_ref, dimension, role: new \| learned}`, минимум по одному каждой роли |
| `choice` | `target_ref?` либо `topic_hint` |
| `gate` | `gate_scope`, `scope_ref` |

[PD-2026-09-23] `probe` (кандидат `too_easy`-сигнала) ретайрен вместе с сигналами (§4.7) — движку больше некуда его вставить мид-сессионно.

- **MUST — `kind → bucket` тотален**: `review → review`, `growth → growth`, `integration → integration`, а `choice | gate → choice`. Иных пар нет.
- **MUST — дополнительные поля `drill_block`** [PD-2026-09-22]: шаг с `step_type: drill_block` сверх полей своего `kind` несёт `rounds` (2–3), `round_size` (из `LearnerPreferences.round_size`, [[learner]] §2) и `targets[]` из `{target_ref, dimension, role: target | contrast}` — ровно одна запись с `role: target` и 0 либо 2–4 записи с `role: contrast` по правилу §4.6. Шаг с `step_type: timed_writing` несёт `declared_limit_seconds`, которое тьютор обязан объявить ученику до начала ([[lessons]] §5); шаг `reconstruction` несёт `text_ref` на текст из [[curriculum]] §2d.
- **MUST — допустимые `step_type` по `kind`** [RR2-5]: без этой матрицы одна реализация назвала бы integration заданием на 420 секунд, другая — на 120, и планы разошлись бы при одинаковом входе.

| `kind` | Допустимые `step_type` |
|---|---|
| `review` | `recognition_check`, `controlled_production`, `spontaneous_production`, `transfer_task`, **`drill_block`** |
| `growth` | `new_material_intro`, `controlled_production`, **`drill_block`** |
| `integration` | `integration_task`, `transfer_task`, **`reconstruction`**, **`timed_writing`** |
| `choice` | `free_conversation`, `spontaneous_production`, **`timed_writing`** |
| `gate` | `gate_item` |

- **MUST — три `step_type` контура автоматизации** [PD-2026-09-22]: `drill_block` (серия раундов по одному паттерну, [[../glossary]] Drill block), `timed_writing` (письмо под объявленным лимитом) и `reconstruction` (восстановление авторского текста по ключевым словам, [[curriculum]] §2d). Стоимость каждого — 300 секунд (§3), корзина выводится из `kind` обычным тотальным правилом `kind → bucket`. Пары, отсутствующие в таблице выше, запрещены: `drill_block` не бывает `integration`-шагом (он работает с одним паттерном, а не с парой ролей), а `reconstruction` не бывает `growth`-шагом (восстанавливать можно только то, что уже введено).

- **MUST — review-шаг несёт `review_assignment_id`** [PD-2026-09-23]: без него отчёт не может сослаться на конкретный ReviewAssignment, чтобы закрыть его по вердикту ([[evidence]] §4.3); движком по-прежнему проверяется, что каждый ReviewAssignment сессии получает терминальную диспозицию — теперь не как предпосылка `finish`, а как часть атомарного коммита отчёта ([[lessons]] §4).
- **MUST — integration выражает пару**: одиночный `target_ref` не способен описать задание «новая цель поверх освоенной», ради которого корзина и введена.
- **MUST — `review_share` считается один раз, при сборке** [PD-2026-09-23]: `review_share = sum(review-шагов.expected_seconds) / total_seconds` собранного плана — единственная величина, которую проверяют `review_max` и полы. Прежнее различение «ревизия / эффективный состав / факт доставки» (RR2-6/RR2-11) относилось к накопительному учёту через `replan`, которого больше нет. `integration` и `choice` не входят в review.
- **MUST — вклад integration в цели**: шаг `integration` может дать evidence нескольким целям, но с dedup и cap по [[evidence]] §4.1. На бюджет он относится целиком к своей корзине.

### 4.4 Канонический конвейер сборки [CTRL-12]

Детерминирован целиком; два корректных исполнения дают побайтово равный `SessionPlan`.

1. **Кандидаты.** `review` — due/overdue от [[scheduler]] §5, включая review LexicalItem'ов. `growth` — рекомендации [[curriculum]], отфильтрованные по `is_first_exposure`, плюс lexicon-first micro lane из `generation@1` для learner-requested / observed-error / due-review / CORE-HIGH safe unlinked-единиц (advisory: не более одного growth item за сбалансированную сессию, кроме maintenance или явного vocabulary-запроса). **Явный learner-request** — привязанная запись личного словаря ([[learner]] §3, §4.5) с разрешимым `linked_item_id` — допускает свой `LexicalItem` в этот lane **даже если он уже привязан к теме**: именованное исключение из «только unlinked» и из кэпа «один item», поднимает `learner_relevance` цели, но evidence/schedule не создаёт [PD-2026-07-22]. `integration` — пары (новая цель, освоенная цель). `choice` — цели из `goals[]`/личного словаря [[learner]] и рекомендация гейта от [[gates]], если она есть.
2. **Исключение по safety** — по active policy; исключённое фиксируется в trace.
3. **Классификация** review-кандидатов — §4.5.
3a. **Активные сигналы** — фильтры и сдвиги §4.7 применяются после базовой классификации.
3b. **Свободный разговор — безусловный кандидат** `choice` [RR2-14]: он не требует цели, поэтому доступен всегда и `NO_CHOICE_CANDIDATE` при `choice_min > 0` возникнуть не может. `topic_hint` берётся из активной `goal`, иначе пуст.
4. **Каноническая сортировка.** Review внутри класса: `(retrievability asc, stake_rank asc, deferral_count desc, expected_seconds asc, target_id asc, dimension_id asc, candidate_id asc)`. Growth: `(curriculum_priority_rank asc, learner_relevance desc, target_id asc, dimension_id asc, step_type_rank asc, candidate_id asc)`. Integration: `(new_target growth-key, learned_target_id asc, learned_dimension_id asc, step_type_rank asc, candidate_id asc)`. Choice: `(source_rank asc, target_id_or_empty asc, step_type_rank asc, candidate_id asc)`, где `source_rank`: явный выбор ученика `1`, active goal `2`, личный словарь `3`, gate `4`, free conversation `5` (ранг `0`, прежде отданный probe, ретайрен вместе с сигналами [PD-2026-09-23] и не переиспользуется). `step_type_rank`: `new_material_intro 0`, `recognition_check 1`, `controlled_production 2`, `spontaneous_production 3`, `transfer_task 4`, `integration_task 5`, `gate_item 6`, `free_conversation 7`, `drill_block 8`, `reconstruction 9`, `timed_writing 10` [PD-2026-09-22]. `candidate_id` обязателен и стабилен в нормализованном входе. Новые ранги **дописаны в конец**, а не вставлены по смыслу: перенумерация изменила бы порядок уже существующих планов при одинаковом входе.
5. **Резервирование остаточных полов** в фиксированном порядке `growth → integration → choice` до величин из §4.2. Пол — **резервируемая ёмкость, а не обязательная загрузка** [R-2]: пересекающий пол шаг может превысить остаточную ёмкость по §3. Если кандидатов нет, фиксируется `NO_<BUCKET>_CANDIDATE`; если после добавлений кандидаты закончились ниже пола — `<BUCKET>_CANDIDATES_EXHAUSTED`; если кандидаты есть, но ни один не помещается в общий остаток после предыдущих корзин, — `NO_<BUCKET>_STEP_FITS`. Во всех трёх случаях незанятый резерв переходит следующей корзине. Это делает исполнимыми первое занятие (нет integration-пар), короткие бюджеты с неделимыми шагами и режимы `maintenance`/`re_entry`, где `growth_min = 0`.
6. **Резерв против голодания** — §4.5.
6b. **Availability-boost** — §4.7a; только после starvation-reserve, чтобы не отменить его гарантию. [PD-2026-09-23] Шаг 6a (pending probe) ретайрен вместе с сигналами (§4.7); номерация сохранена как есть — «6b» не переименован, чтобы не путать историю пайплайна с текущим составом шагов.
7. **Review** по классам `critical → important → normal → maintenance`, пока не достигнут `review_max` или бюджет.
8. **Добор остатка** после review — фиксированными проходами `growth → integration → choice`; каждая корзина исчерпывает свой канонически отсортированный список first-fit, затем управление переходит следующей. Второго цикла нет. Ни один потолок или правило «не более одного growth на цель» не нарушается.
9. **Квоты разнообразия** — §4.6, применяются как **фильтр при добавлении**, а не постобработкой: шаг, нарушающий квоту, пропускается, берётся следующий по порядку.
10. **Порядок предъявления** — чередование modes при равных прочих, затем `step_id asc`.

- **MUST — first-fit, не best-fit**: после разрешённого первого overshoot шага §3 кандидат, не помещающийся в доступную ёмкость корзины или общий `remaining_seconds`, **пропускается**, и берётся следующий кандидат в каноническом порядке. Best-fit запрещён: он даёт другой набор при том же входе.
- **MUST — неразрешимый бюджет**: если `total_seconds < min_total_minutes × 60`, композиция отклоняется ошибкой `BUDGET_TOO_SMALL`.
- **MUST — пустой план это ошибка, а не результат** [R-2]: если после waiver'ов не набрался ни один шаг, композиция отклоняется `NO_CANDIDATES` с `next_action`. Сессия с планом из нуля шагов не создаётся.
- **MUST — waiver виден в телеметрии**: доля занятия, отданная по waiver другой корзине, попадает в trace и в метрики. Иначе систематическая невозможность набрать новый материал выглядела бы как здоровое занятие.

### 4.5 Классификация: тотальная упорядоченная таблица [CTRL-4]

Область — **только review-кандидаты** (due или overdue). Правила применяются по порядку, **первое совпавшее выигрывает**; таблица тотальна.

| # | Условие | Класс |
|---|---|---|
| 1 | `risk ∧ stake` | `critical` |
| 2 | `risk ∧ ¬stake` | `important` |
| 3 | `saturated` (§4.6) | `deferrable` |
| 4 | `retrievability ≥ maintenance_floor_retrievability` | `maintenance` |
| 5 | иначе | `normal` |

**Риск проверяется первым** [R-4]. В прежнем порядке `saturated` стояло первым, и три показа с тремя **провалами** удовлетворяли предикату насыщения, отправляя критичную цель в `deferrable`; а повторяющаяся живая ошибка при Retrievability `900000 ppm` попадала в `maintenance` раньше проверки риска — то есть ровно тот сигнал, который вводился для исправления ошибочного прогноза модели, этим прогнозом и подавлялся.

**`risk`** = `knowledge_state = AT_RISK` **∨** повторяющаяся ошибка (≥ `recurring_error_min_occurrences` в последних `recurring_error_window_sessions`) **∨** `retrievability < critical_floor_retrievability`.

**`stake`** определён для обоих видов `LearningTarget` [CTRL-4]:

| Вид цели | `stake` истинно, если |
|---|---|
| `LexicalItem` | `curriculum_priority_band ∈ {CORE, HIGH}` ∨ leverage ∨ relevance |
| `Topic` | leverage ∨ relevance |

где **leverage** = цель является `strong`-prerequisite не менее чем `prereq_leverage_min_dependents` тем, **relevance** = цель связана с активной `goal` или записью личного словаря ([[learner]] §4). У `Topic` поля `curriculum_priority_band` нет, и вводить его сюда не требуется: для тем ставка выражается через leverage.

- **MUST — резерв против голодания** [CTRL-7]: до заполнения review-корзины по классам в план **безусловно допускается** до `reserved_steps_per_session` целей, достигших `deferrals_to_qualify`, в порядке §4.5. Admission означает наличие шага в хотя бы одной зафиксированной ревизии сессии; это не обещание `STEP_PRESENTED`.
- **MUST — `stake_rank` закрыт** [R-4]: `0` — relevance (цель связана с активной `goal` или личным словарём); `1` — `curriculum_priority_band ∈ {CORE, HIGH}` (LexicalItem) либо leverage ≥ `prereq_leverage_min_dependents` (любой вид цели); `2` — ставки нет. Сортировка по возрастанию. Без закрытого enum порядок внутри класса снова зависел бы от реализации.
- **MUST — жизненный цикл `deferral_count`** [R-6]: счётчик меняется **не более одного раза за сессию**, при её `FINISHED`/`ABANDONED`. Он увеличивается на 1, если цель была eligible review-кандидатом хотя бы одной ревизии этой сессии, не была admitted ни в одну её зафиксированную ревизию именно из-за системного отбора и не была исключена сигналом ученика. Несколько replan одной сессии не дают несколько инкрементов. `STEP_PRESENTED` по цели обнуляет счётчик. Порядок резерва — `(qualified_at_session_seq asc, deferral_count desc, retrievability asc, target_id asc, dimension_id asc)`; новые qualification-эпизоды не обгоняют уже открытые.
- **MUST — эпизод qualification**: достижение порога открывает один qualification-эпизод и фиксирует `qualified_at_session_seq`; первое последующее admission закрывает его. Без `STEP_PRESENTED` новый эпизод может открыться только после нового системного deferral в более поздней терминализованной сессии. Поэтому уже admitted, но не показанная цель не захватывает резерв бесконечно.
- **MUST — граница ожидания и её предпосылка** [R-6, RR2-8]: для конечного множества открытых эпизодов `Q` на старте отсчёта все цели из `Q` admitted не позже чем через `ceil(|Q| / reserved_steps_per_session)` **последующих qualifying sessions**; от нулевого счётчика граница равна `deferrals_to_qualify + ceil(|Q| / reserved_steps_per_session)`. Qualifying session — сессия, в которой после защищённых ненулевых полов помещается хотя бы один допустимый шаг старейшей зарезервированной цели; недостаточно длинная сессия не расходует эпизод и фиксирует `STARVATION_STEP_DOES_NOT_FIT`. Если шаг помещается, он вытесняет последний незарезервированный review-шаг, иначе последний незарезервированный шаг добора, не нарушая ненулевые полы. Admission не гарантирует presentation.

### 4.6 Доставка, насыщение, разнообразие [CTRL-6]

- **MUST — факт выдачи фиксируется постфактум, отчётом** [RR2-2, уточнено PD-2026-09-23]: `STEP_PRESENTED` фиксирует, что тьютор провёл это задание с учеником, но публикует его теперь `lessons.report` — в момент коммита отчёта, по каждому item'у, `source: lesson_report` ([[lessons]] §4d). Смысл факта не изменился (движок не наблюдает экран ученика напрямую, тьютор остаётся trusted reporter, [[evidence]] §4.2), изменился только момент: раньше событие фиксировало обязательство «шаг выдан, что бы дальше ни случилось», теперь — свершившийся факт «это было проведено», сообщённый после занятия.
- **MUST — что из этого следует**: exposure, saturation и сброс `deferral_count` считаются от `STEP_PRESENTED`-фактов отчёта — то есть только у сессий, по которым отчёт действительно дошёл до коммита. Сессия, брошенная без отчёта (`abandon`), не оставляет ни одного факта выдачи: exposure по её содержимому не засчитывается, потому что подтвердить его нечем.
- **MUST — план не равен выдаче**: `SESSION_COMPOSED` — намерение; тьютор мог провести занятие не по предложенному плану вовсе, и тогда его `STEP_PRESENTED`-факты этому плану не соответствуют.
- **MUST — `SaturationState` строится из существующих событий** [R-5]: входы — `STEP_PRESENTED` (число показов и `context_id`), `EVIDENCE_ADDED` и `REVIEW_OUTCOME` из [[evidence]] §3 (успех, independence), `ERROR_OBSERVED` (повторяющаяся живая ошибка для предиката `risk`). Reducer применяет события в порядке канонического `sequence`, дедуп — по `event_id`; форма и источник входных фактов не изменились с переходом на brief/report — изменился только их производитель (§3b).
- **MUST — цели и `context_id` в факте доставки** [R-5; П.3]: `STEP_PRESENTED.targets[]` перечисляет все пары `(target_ref, dimension)` item'а, а `context_id` идентифицирует смысловой контекст. Событие также несёт `step_type` и `active_safety_version`. [PD-2026-09-23] Полей `bank_item_id`/`generation_directive_hash` больше нет: контент задания не проходит рендер по банку/generation directive — движок видит его только как `prompt`/`raw_answer` отчёта. Reducer обновляет saturation для каждой пары; `review_id`, когда item ссылается на повторение, делает разрешимой корреляцию §4.10.
- **MUST — предикат `saturated`** [RR2-13]: считается **per-dimension**; `exposures_in_window ≥ max_exposures_in_window` **∨** (`consecutive_independent_successes ≥ consecutive_success_threshold` **∧** `distinct_contexts < min_distinct_contexts` **∧** `last_transfer_check_at != null` **∧** `now − last_transfer_check_at ≤ transfer_check_staleness_days`). При `last_transfer_check_at = null` вторая конъюнкция ложна. Ключ по цели без dimension позволил бы частым проверкам узнавания заглушить слабое производство той же цели. Если transfer давно не проверялся или не проверялся вообще, устойчивый успех в знакомом шаблоне **не** считается насыщением.
- **MUST — насыщение не равно владению**: понижение класса меняет только план; состояние знания меняет исключительно [[scoring]].
- **MUST — квоты разнообразия**: `max_steps_per_topic`, `max_consecutive_same_mode`, `max_similar_items`. «Похожие» = единицы, делящие `lemma`/базовый глагол phrasal-verb либо один `topic`.
- **MUST — дрилл-блок считается как одно предъявление** [PD-2026-09-22]: шаг `drill_block` даёт `exposures_in_window += 1` **независимо** от числа items внутри него, и `max_steps_per_topic` считает его как **один** шаг. Иначе `max_exposures_in_window: 3` исчерпывался бы внутри половины первого блока, и серия массированных повторений — то, ради чего `drill_block` и введён, — была бы неисполнима. Симметрично `consecutive_independent_successes` увеличивается на 1 за успешный блок, не за успешный item.
- **MUST — interleaving со второго предъявления** [PD-2026-09-22]: если по цели уже есть **хотя бы один** зафиксированный `STEP_PRESENTED`, её `drill_block` **обязан** нести 2–4 контрастные цели в `targets[]` с `role: contrast`, взятые из `contrasts` темы либо из артикльного яруса ([[../product/lexical-system]] §1c). Блок при первом предъявлении цели — и только при нём — идёт **blocked**, без контрастов. Blocked-ввод нужен, чтобы паттерн вообще сложился; дальше именно перемешивание с конкурирующими формами даёт отложенную точность, а чистый blocked-дрилл её не даёт.
- **MUST — роль `contrast` не создаёт evidence по контрастной цели**: `role: contrast` в `targets[]` объявляет, что цель предъявлена как помеха выбора, а не как проверяемая цель блока. Evidence по ней возникает только обычным путём — из сохранённого ответа с её собственным source-span ([[evidence]] §4.6); дедуп и cap multi-credit применяются без изменений.
- **MUST — не хватает контрастов**: если для цели не набирается двух допустимых контрастных целей, блок выдаётся как **blocked** (без контрастов), а `NO_CONTRAST_CANDIDATE` фиксируется в waivers плана и в trace шага. Пропуск цели ради недобора контрастов лишил бы практики именно ту цель, которой она нужна; предпочтительнее массированный раунд, чем отсутствие раунда [PD-2026-09-22].

### 4.7 Сигналы ученика (retired) [CTRL-9, CTRL-10, PD-2026-09-23]

Мид-сессионный `replan` — единственный адресат `LearnerControlSignal`/`PROBE_REQUESTED` — удалён вместе с пошаговой доставкой ([[lessons]] §4d): применить сигнал (`too_easy`, `too_repetitive`, `need_more_practice`, `not_relevant_now`, `snooze`, `prefer_different_context`) стало больше некуда, поскольку план не мутируется после того, как brief его вернул. `trainer signal` удалён из CLI (§5).

- Тунабл `signals.default_effect_sessions` пинят только старые сессии `control@3`; новый протокол его не читает — payload пинится неизменным (§3), и это осознанное историческое наследие, а не живая настройка.
- `origin = control_probe` остаётся закрытым членом enum'а `origin` ([[evidence]] §4.5, [[scoring]] §4b) и его no-negative правило сохраняет силу для исторического evidence — но с retire'ом `probe` (§4.3a) новых producer'ов у этого значения больше нет.
- Идея пробы (добровольная проверка выше требуемого уровня) не запрещена продукту — просто не имеет больше отдельного мид-сессионного механизма; тьютор волен предложить более сложное задание сам, и оно ляжет в отчёт как обычный item.

### 4.7a Availability — алгоритм v1 [R-9]

Сущность §2 без правил вычисления не задавала поведения; часть значений policy не использовалась ни одной веткой.

- **MUST — целочисленная схема** [RR2-10, RR2-12]: `declared{sessions_per_week_milli, typical_minutes, next_available_at?, blackout_until?}` и `observed{sessions_per_week_milli, typical_minutes, median_interval_seconds?}`. `1000` milli = одна сессия в неделю; все числовые поля — целые, YAML-float запрещён. Профиль задаётся `trainer availability set`.
- **MUST — источник `observed`**: окно — `[start_of_week(now) − (divergence_window_weeks − 1) недель, now]`, то есть текущая неполная и предшествующие полные недели, всего ровно `divergence_window_weeks` календарных корзин. `start_of_week` — понедельник 00:00 в `LearnerProfile.timezone`, а использованные `now` и timezone захватываются в trace. Если в окне не менее `min_observed_sessions` терминализованных сессий, `observed.sessions_per_week_milli = floor(count × 1000 / divergence_window_weeks)`, а `typical_minutes` — lower median их `SessionPlan.budget.total_seconds // 60`. Иначе оба поля получают `no-data`. `median_interval_seconds` — lower median разностей соседних `SESSION_STARTED.started_at` при наличии минимум трёх стартов; иначе `null`. Длительность `STARTED→FINISHED` не используется.
- **MUST — precedence бюджета**: `total_seconds` берётся первым из непустого: `--duration-minutes × 60` → `declared.typical_minutes × 60` → `observed.typical_minutes × 60` → `default_total_minutes × 60`. Порядок фиксирован.
- **MUST — расхождение**: если `declared.sessions_per_week_milli` отсутствует либо observed = `no-data`, результат `no-data` и предложение не создаётся. Иначе `divergence_ppm = floor(abs(declared_milli − observed_milli) × 1_000_000 / max(declared_milli, 1000))`. При `divergence_ppm > divergence_tolerance_ppm` система предлагает уточнить и не переписывает declared без подтверждения; `AVAILABILITY_UPDATED` публикуется только после принятого изменения.
- **MUST — предикат длинного перерыва**: он истинен, если `blackout_until > now`, либо одновременно заданы `next_available_at > now` и `median_interval_seconds`, причём `next_available_at − now > median_interval_seconds`. При `median_interval_seconds = null` одно лишь `next_available_at` усиление не включает; blackout включает всегда.
- **MUST — детерминированное влияние на состав**: при длинном перерыве после резервирования остаточных полов §4.4 вычисляется `critical_boost_capacity = min(floor(total_seconds × reentry_critical_boost_bp / 10000), residual_review_capacity, unplanned_remaining_seconds)`. До обычного review и до добора growth сверх его пола в эту ёмкость first-fit отбираются `critical`-шаги в порядке §4.4; overshoot для boost не разрешён. Если подходящих `critical` нет, trace получает `NO_CRITICAL_AVAILABILITY_CANDIDATE`, ёмкость возвращается обычному добору. `review_max` и growth-пол не нарушаются; Availability никогда не входит в scoring (§4.1).

### 4.8 Decision trace

- **MUST — trace у каждого шага**: `decision_id`, сработавшие правила классификации с их номерами, значения `risk`/`stake` сигналов, retrievability, класс, состояние насыщения, применённые квоты, занятость корзин, `pinned_versions` (включая `control_policy`) и `active_safety_version`.
- **MUST — доступен по команде**: `trainer why --step ID`.
- **MUST — поля разрешимы**: каждое поле trace либо разрешается в строку каталога (§4.9), либо помечено как вычисленный вход.

### 4.9 Каталог tunables и калибровка

```yaml
parameter_id: control.budget.shares.review_max
owner: 0.12 control
scope: global
unit: basis_points
default: 4500
allowed_range: [3000, 6000]
carried_by: control_policy@1
observed_by: [presented_review_share, presented_growth_rate]
change_mode: propose_confirm
trace_field: review_max
```

- **MUST — реестр, не хранилище**: значения живут в pinned policy у владельца; каталог хранит метаданные. Два хранилища одного числа разъедутся.
- **MUST — полный versioned catalogue [PD-2026-07-22]**: `tunables@1` содержит 60 строк — все 48 числовых decision-leaf `control@1` и 12 явно объявленных tunables владельцев lessons/evidence/scoring/scheduler/assessments/obligations. Структурные числа generation/rubric не являются tunables и не входят. Валидатор проверяет полноту в обе стороны при активации curriculum. [PD-2026-09-22] `control@3` добавляет три числовых decision-leaf (`expected_seconds_by_step_type` для `drill_block`, `timed_writing`, `reconstruction`), поэтому каталог обязан вырасти до **63** строк новой версией (`tunables@2`): проверка полноты в обе стороны иначе не пройдёт, и это ровно то, ради чего она заведена. Диапазоны новых строк заморожены как `[default, default]` до эмпирических данных. `balanced.review_max` имеет принятый advisory range `[3000, 6000]`; до эмпирических данных все остальные диапазоны заморожены как `[default, default]`, а не выдуманы.
- **MUST — потолок автономии: propose_confirm** `[PD-2026-07-20]`: ни один параметр не объявляет режим выше. Автоприменение запрещено: при одном ученике шум неотличим от сигнала.
- **MUST — применение делегируется владельцу** `[PD-2026-07-20]` [CTRL-Q2]: control владеет **только** workflow «предложил → подтвердили». Активацию новой версии выполняет **API модуля-владельца** параметра, с его CAS и его событием; control не мутирует чужой aggregate и не становится вторым владельцем policy. `CALIBRATION_APPLIED` фиксирует подтверждение и связан `causation_id` с событием активации у владельца.
- **MUST — confirm атомарен [PD-2026-07-22]**: подтверждение строит новый immutable snapshot policy владельца, валидирует range/catalogue, активирует его CAS-событием `policy.version_activated`, затем пишет причинно связанный `calibration.applied` в той же UoW. Повтор idempotency-key возвращает исходный результат; применённое предложение повторно не активируется.

### 4.10 Метрики качества политики [CTRL-13]

Каждая — `PolicyMetric` с формулой, окном и правилом отсутствующих данных. Значения ниже — v1.

| id | Формула | Окно | Нет данных |
|---|---|---|---|
| `calibration_error` | среднее \|прогноз Retrievability на момент выдачи − факт (1 успех / 0 неуспех)\| по всем `REVIEW_OUTCOME` | 200 исходов | `no-data` при < 50 |
| `presented_review_share` | по сессии — **ledger**, если он заполнен (историческая сессия), иначе **счёт по отчёту** (см. ниже); `review_bp = review-единицы / все репортнутые единицы` | 10 сессий | `no-data` при < 3 |
| `presented_growth_rate` | то же по сессии; `growth_bp = growth-единицы / все репортнутые единицы` | 10 сессий | `no-data` при < 3 |
| `backlog_age_p90` | 90-й процентиль `now − first_due_at` по незакрытым due; метод — **nearest-rank**, ties разводятся `(target_id, dimension_id)` | текущий срез | `no-data` при пустом backlog |
| `max_deferrals` | максимум `deferral_count` среди целей backlog | текущий срез | `0` |
| `lapse_rate_after_mastered` | доля целей, получивших REGRESSION в течение 90 дней после MASTERED | 90 дней | `no-data` при < 10 |
| `transfer_gap` | успех на знакомом шаблоне − успех в новом контексте | 50 исходов каждого | `no-data` |

- **MUST — связь прогноза с исходом** [RR2-11]: `calibration_error` соотносит `STEP_PRESENTED.predicted_retrievability` **последнего выданного** шага данного `review_assignment_id` с терминальным исходом этого assignment. Один исход агрегирует несколько попыток, поэтому без явного правила пара «прогноз ↔ факт» была бы неоднозначной. Отменённые (`CANCELLED`) assignment в выборку не входят.
- **MUST — прогноз фиксируется в `STEP_PRESENTED`, а не при композиции** [R-8]: `predicted_retrievability` записывается в момент **фактической выдачи**. Композиция и выдача расходятся во времени (сессию можно возобновить через день), а Retrievability убывает по реальному времени — сравнение с прогнозом из плана приписывало бы политике ошибку, созданную устаревшим планом. Пересчёт задним числом запрещён.
- **MUST — разметка исходов** [R-8]: в `calibration_error` `CONFIRMED` и `PROGRESS` → `1`; `REGRESSION` → `0`; `RECOVERED` → `1`; `INSUFFICIENT_EVIDENCE` → **исключается** из выборки, а не считается нулём. Исход из пяти значений нельзя молча свести к булеву.
- **`presented_review_share`/`presented_growth_rate` пересобраны под report-факты** [PD-2026-09-23]: раньше они читались из `DeliveryLedger`, которого больше нет (§4.2); report-протокольная сессия его не заполняет никогда. Источник по сессии выбирается по наличию `LESSON_REPORTED`: **историческая** сессия (заполненный `session_plan.ledger`, без `LESSON_REPORTED`) считается как раньше; **report-протокольная** сессия (с `LESSON_REPORTED`) считается по собственным `STEP_PRESENTED`-фактам отчёта (`source: lesson_report`, [[lessons]] §4d) следующим образом:
  - **знаменатель** — каждая репортнутая единица весом `1`; drill-блок весит **по числу его members** (`len(item_ids)`), а не `1` за блок целиком, чтобы у отчётного item'а и у члена блока был равный вес, а шестипунктовый блок не схлопывался до веса одного item'а;
  - **`review_bp`** — доля единиц, чей `STEP_PRESENTED` несёт `review_assignment_id` (у блока это решается на уровне блока: весь блок либо адресует ревью, либо нет — все его members считаются вместе);
  - **`growth_bp`** — доля единиц, чья первичная цель (`targets[0]`, запись с `role: target`) не имела **ни одного** `STEP_PRESENTED`-факта (любого источника — ledger или report) до первого события этой сессии в журнале. Это то же определение `is_first_exposure`, что и в §4.3 (цель новая, если по ней ещё не было факта доставки), переиспользованное, а не изобретённое заново: `evidence.added` намеренно не используется — §4.6 уже называет именно доставку, а не evidence, фактом экспозиции, и цель может быть показана (и даже не получить evidence) не переставая быть «уже показанной».
  - Пустой отчёт (без `STEP_PRESENTED`-фактов) не даёт сэмпла — как и историческая сессия с нулевым `presented_seconds`.
- **MUST — аварии считаются по факту и только по `balanced`-занятиям** [R-8, RR2-11]: входы аварий — `presented_*` (источник — пункт выше); в режимах `maintenance`/`re_entry` нулевой рост законен, и включение их в окно давало бы ложную тревогу после трёх нормальных поддерживающих занятий.
- **MUST — раздельные пороги входа и выхода**: авария включается при пересечении `*_enter_bp` подряд `*_consecutive` занятий и выключается только при пересечении `*_exit_bp` — гистерезис не даёт метрике мигать у порога. Пороги — параметры каталога, а не прилагательные «устойчиво» и «близок».
- **MUST — реакция: сообщить, не притормаживать** `[PD-2026-07-20]` [CTRL-Q1]: при аварии система **сообщает** и предлагает выбор (режим `maintenance`, больше времени, отказ от части целей). Автоматическое снижение притока нового материала **не вводится**: скрытое изменение программы без ведома ученика противоречит принципу «движок объясняет, а не решает молча».
- **MUST — честность о статистике**: при одном ученике большинство метрик долго остаются шумом; `no-data` — легитимный результат, а не ноль.

## 5. CLI-поверхность

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer why --step ID` | control | нет | `DecisionTrace` шага (§4.8) |
| `trainer availability show` \| `set` | control | `set` — да | ритм: объявленный, наблюдаемый, расхождение |
| `trainer tunables list [--owner X]` | control | нет | каталог настроек |
| `trainer metrics` | control | нет | метрики + аварии |
| `trainer calibration list` \| `confirm ID` | control | `confirm` — да | предложения; применение делегируется владельцу |

[PD-2026-09-23] `trainer signal` удалён — мид-сессионного адресата у сигналов ученика больше нет (§4.7). `trainer session start --mode` принадлежит [[lessons]]; advisory-план, который она возвращает внутри `LessonBrief`, собирает `compose_plan` (здесь, §3b/§4.2). `trainer session next/peek/replan` удалены вместе с CAS-протоколом доставки.

## 6. Границы

- **depends on**: [[scheduler]] (backlog, retrievability), [[scoring]] (состояния, прогнозы), [[evidence]] (исходы, наблюдённые ошибки, ReviewAssignment), [[curriculum]] (priority band, prerequisites, рекомендации), [[learner]] (`goals`, личный словарь → relevance), [[gates]] (рекомендация гейта как кандидат `choice`), [[lessons]] (UoW старта, терминализация)
- **events published**: `SESSION_COMPOSED`, `AVAILABILITY_UPDATED`, `CALIBRATION_PROPOSED`, `CALIBRATION_APPLIED`. [PD-2026-09-23] `STEP_PRESENTED` больше не публикуется control'ом — владеет им [[lessons]] §4d (отчёт, постфактум); `LEARNER_SIGNAL_RECORDED`/`SIGNAL_CONSUMED`/`PROBE_REQUESTED` ретайрены вместе с сигналами (§4.7).
- **events consumed**: `REVIEW_SCHEDULED`, `OVERDUE_AT_RISK_TRIGGERED` (← [[scheduler]]), `STATE_TRANSITION` (← [[scoring]]), `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `ERROR_OBSERVED` (← [[evidence]] §3 — saturation, recurring-error, метрики), `SESSION_STARTED`/`FINISHED`/`ABANDONED` (← [[lessons]])

Модуль не меняет Mastery, Stability, knowledge state, CEFR и интервалы; содержимое заданий генерирует П.3.

## 7. Открытые вопросы

- **OPEN-27**: эмпирическая калибровка значений §3. Все они **существуют и исполнимы**; открыта только их проверка данными → не блокирует реализацию.
- **OPEN-29**: `AvailabilityProfile` в v1 несёт `sessions_per_week_milli`, `typical_minutes`, `next_available_at?` и `blackout_until?`. Полная календарная модель (дни недели, исключения) — нерешённое расширение этого же вопроса; до неё обещание «перенести на ближайшее занятие» опирается на `next_available_at`, а при его отсутствии — на статистическую оценку.
- OPEN-14 закрыт; safety-overlay определяет допустимое к предъявлению. Открыты только эмпирическая калибровка (OPEN-27) и опциональное календарное расширение (OPEN-29).

## История изменений

- **2026-09-23 (2)**: [PD-2026-09-23] закрыт названный в предыдущей записи пробел: `presented_review_share`/`presented_growth_rate` пересобраны под report-факты. По сессии источник выбирается по наличию `LESSON_REPORTED` — историческая сессия (заполненный ledger, без него) считается как раньше; report-протокольная считается по собственным `STEP_PRESENTED`-фактам отчёта (`source: lesson_report`): знаменатель — каждая репортнутая единица, блок весит по числу members (не `1` за блок); `review_bp` — доля единиц с `review_assignment_id`; `growth_bp` — доля единиц, чья первичная цель не имела ни одного `STEP_PRESENTED`-факта (любого источника) до первого события сессии в журнале — то же `is_first_exposure`, что и в §4.3, не новое определение через `evidence.added`. Реализация: `control/metrics.py::_terminal_session_shares`.
- **2026-09-23**: [PD-2026-09-23] переход на протокол «задание → отчёт»: `compose_plan` собирает advisory-план заново на каждый `LessonBrief` (`start`/`resume`), а не мутирует CAS-версионируемый `SessionPlan`; `claim_next_step`/`peek_next_step`/`replan` и их события (`STEP_PRESENTED` как control-факт, `LEARNER_SIGNAL_RECORDED`, `SIGNAL_CONSUMED`, `PROBE_REQUESTED`) ретайрены; §4.7 «Сигналы ученика» закрыт — мид-сессионного адресата не осталось; `SessionBudget`/`DeliveryLedger`/`LessonArc`/`LearnerControlSignal`/`probe`-kind retired ([[../glossary]]); safety проверяется на композиции плана, не на доставке контента; `--expected-proposal-hash` удалён из preflight; `trainer signal` удалён из CLI. Метрики `presented_review_share`/`presented_growth_rate` требуют пересборки под report-факты — открыто, не изобретено. `control@3`/`tunables@2` payload не меняются (пинятся).
- **2026-09-22**: [PD-2026-09-22] `control@3` — добавлены `step_type` `drill_block`/`timed_writing`/`reconstruction` (по 300 секунд) и их клетки в матрице `kind → step_type`; ранги сортировки дописаны в конец, чтобы прежние планы не переупорядочились; дрилл-блок считается **одним** предъявлением и одним шагом темы независимо от числа items; со второго предъявления блок обязан нести 2–4 контрастные цели `role: contrast` (blocked — только при первом); заведён одиннадцатый профиль `drill` с канонической agenda. Целочисленная арифметика §3 не изменена.
- **2026-07-24**: [PD-2026-07-24] разрешена приватная фоновая подготовка упражнений: draft не learner-facing и не меняет state; публикация остаётся после `STEP_PRESENTED` и сверяет candidate.
- **2026-07-23**: [PD-2026-07-23] добавлены 10 learner-facing LessonProfile, read-only proposal с hash/consent, связный LessonArc с одной центральной новой темой и `lesson_request`→replan; `control@2` сохраняет прежнюю целочисленную бюджетную схему.
- **2026-07-22 (7)**: [PD-2026-07-22] §4.4 шаг 1 — явный learner-request (привязанная запись личного словаря) допускает `LexicalItem` в lexicon-first micro-lane даже при привязке к теме; поднимает `learner_relevance`, evidence/schedule не создаёт. Реализация — модуль `learner` (roadmap 99).
- **2026-07-22 (6)**: [PD-2026-07-22] принят `tunables@1`: 60 параметров (48 control + 12 соседних), balanced review range 3000–6000, остальные ranges честно frozen; confirm атомарно активирует successor policy и причинно связывает `calibration.applied`.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). calibration-API — часть цели (порядок в roadmap); календарная модель — нерешённое расширение OPEN-29.
- **2026-07-21**: после подтверждающего red-team устранены структурные дефекты: введён CAS-токен `plan_version`, связанный с каждой мутацией; бюджет текущей ревизии отделён от накопительного ledger через `effective`; валидатор полов согласован с разрешённым overshoot; fairness считает deferral один раз за сессию и гарантирует admission через `ceil`; сигналы получили точные сроки, преобразования и явный replan-протокол; availability переведена в целочисленные размерности и детерминированный boost. Статус 0.12 остаётся `blocked` до независимого подтверждения.
- **2026-07-20 (4)**: третий прогон ревью — BLOCKER и 11 MAJOR сняты. Семантика `session next` сведена к одной во всех владельцах и во flow [RR2-1]; факт выдачи честно назван границей до тьютора [RR2-2]; `Attempt` получил `step_id`, origin выводит движок [RR2-3]; replan закрывает выпавшую цель как `CANCELLED`, не порождая retry [RR2-4]; добавлены матрица `kind → step_type` и проверка **дискретной** достижимости полов с разрешённым превышением резерва неделимым шагом [RR2-5]; введён `DeliveryLedger`, новая ревизия получает только остаток, доли режима проверяются по накопительному итогу [RR2-6]; выдача идёт под CAS с заданными исходами гонок [RR2-7]; граница ожидания получила `ceil` и различение admission/presentation [RR2-8]; сроки сигналов приведены к `expires_after_session_seq` [RR2-9]; исправлена размерность availability [RR2-10]; метрики и аварии считаются по **факту**, а не по плану, задана связь прогноз↔исход и метод перцентиля [RR2-11]; целочисленный контракт распространён на все decision-пороги (ppm) [RR2-12]; saturation ключуется `(target, dimension)` и наконец использует `transfer_check_staleness_days` [RR2-13]; свободный разговор объявлен безусловным кандидатом `choice` [RR2-14].
- **2026-07-20 (3)**: триаж повторного ревью. Выдача шага стала **мутацией** (`session next` идемпотентно помечает шаг предъявленным и публикует `STEP_PRESENTED`; read-only просмотр вынесен в `session peek`) — прежде переход «непредъявлен → предъявлен» был невыразим [R-1]. Полы бюджета стали **резервируемой ёмкостью с waiver** и получили таблицу долей **по режимам**, иначе первое занятие и `maintenance` были неисполнимы [R-2]. `PlannedStep` стал tagged union с `review_assignment_id` и парой ролей у integration; replan закрывает выпавшие assignments в той же UoW, чтобы `finish` не блокировался сиротами [R-3]. Риск проверяется **раньше** насыщения и maintenance [R-4]. Имена потребляемых событий приведены к существующим, добавлен `context_id` [R-5]. У `deferral_count` появился жизненный цикл, у резерва — предпосылка и формула границы [R-6]. `origin=control_probe` выводится движком по типу шага, no-negative распространён на Mastery/Stability/расписание, probe перенесён в корзину `choice` [R-7]. Прогноз для калибровки фиксируется при выдаче, исходы размечены, аварии считаются только по `balanced` и получили гистерезис [R-8]. Описан алгоритм availability [R-9]. Каталог назван обязательством реализации, а не существующим артефактом [R-10]. Сигналы получили два типа истечения и межвидовую precedence [R-11]. Доли переведены в целые basis points [R-12]. Запрещён второй growth-шаг на цель [R-13]. Возвращён раздел Public API [R-14].
- **2026-07-20 (2)**: переписан после red-team ревью (5 BLOCKER). Введена исполнимая `control_policy@1` с конкретными значениями (CTRL-5); корзины сделаны разбиением с независимым признаком `is_first_exposure` (CTRL-1); композиция происходит в UoW старта, `session next` остался read-only, переплан — отдельная мутирующая команда с CAS (CTRL-2); `control_policy` заведена в реестр политик и Manifest (CTRL-3); классификатор заменён тотальной упорядоченной таблицей с определением `stake` для обоих видов LearningTarget (CTRL-4); добавлен факт доставки `STEP_PRESENTED` и потребление событий evidence (CTRL-6); голодание получило резерв мест вместо необеспеченного обещания (CTRL-7); снято ошибочное утверждение, что `STARTED→FINISHED` измеряет учебное время (CTRL-8); сигналы стали discriminated union со сроками (CTRL-9); probe получил отдельный origin и правило no-negative (CTRL-10); зафиксирован канонический конвейер сборки с first-fit (CTRL-12); метрики получили формулы, окна и правила отсутствующих данных (CTRL-13); learner и gates добавлены в зависимости (CTRL-14). Развилки [PD-2026-07-20]: при долговой спирали система **сообщает**, а не притормаживает приток; калибровку чужого параметра применяет **владелец**, control владеет только workflow подтверждения.
- **2026-07-20**: создан (контракт 0.12) после Concept Gate.
