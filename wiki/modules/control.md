# Модуль: control

> **Status**: current
> **Last updated**: 2026-07-20
> **Sources**: концепт `staging/journal/2026-07-20-concept-0.12-learning-control.md` (Concept Gate, 6 развилок) · red-team ревью 0.12 `staging/reviews/2026-07-20-control-review-codex.md` (5 BLOCKER, триаж) · [[scheduler]], [[scoring]], [[evidence]], [[lessons]], [[learner]], [[gates]] · контракт 0.12
> **Bounded context**: `src/english_trainer/control/`

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — по [[../glossary]]. Все численные значения §3 — **конкретные авторские дефолты**, не диапазоны: policy обязана быть исполнимой, калибровка приходит позже.

---

## 1. Назначение

Остальные контракты отвечают, одинаков ли результат при одинаковом входе. Этот отвечает, хорош ли выбранный вход. Модуль решает, **что попадёт в занятие и в какой пропорции**, измеряет качество собственных решений и предоставляет механизм безопасной подстройки. Знание он не измеряет и менять не вправе.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `SessionPlan` | сохранённый состав занятия | `session_id`, `composition_revision`, `steps[]`, `budget`, `pinned_control_policy`, `created_at` |
| `PlannedStep` | один шаг занятия — **tagged union по `kind`** (§4.3a) | общие: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?` |
| `SessionBudget` | распределение времени | `total_seconds`, `allocated{review, growth, integration, choice}`, `mode` |
| `UrgencyClass` | класс review-кандидата | `critical \| important \| normal \| maintenance \| deferrable` |
| `SaturationState` | признаки перепоказа цели | `target_ref`, `exposures_in_window`, `consecutive_independent_successes`, `distinct_contexts`, `last_transfer_check_at` |
| `AvailabilityProfile` | ритм занятий | `declared{...}`, `observed{...}`, `divergence`, `updated_at` |
| `LearnerControlSignal` | сигнал ученика (discriminated union, §4.6) | `signal_id`, `kind`, payload по kind, `expires_at?`, `superseded_by?` |
| `DecisionTrace` | основание решения | `decision_id`, `step_id`, `reasons{}`, `pinned_versions{}` |
| `TunableParameter` | строка каталога настроек | §4.9 |
| `PolicyMetric` | определение метрики (§4.10) | `id`, `inputs[]`, `cohort`, `formula`, `window`, `missing_data_rule` |

`SessionBudget.mode` — `balanced` (по умолчанию) · `maintenance` · `re_entry`. Только в двух последних допустимо занятие без нового материала.

```mermaid
stateDiagram-v2
    [*] --> PLANNED: session start (в UoW старта)
    PLANNED --> PLANNED: session replan (revision+1)
    PLANNED --> CONSUMED: все шаги предъявлены
    PLANNED --> DISCARDED: сессия терминализована
```

## 3. `control_policy` — versioned и исполнимая

Регистрируется в реестре политик kernel ([[../platform/foundation]] §3.6) наравне с curriculum/scoring/scheduler и пинится в Session Manifest ([[lessons]] §4b).

```yaml
control_policy:
  version: 1
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
    # Доли — целые basis points (1 bp = 1/10000). Двоичный float запрещён
    # на всём пути: allocation = floor(total_seconds * bp / 10000) [R-12].
    shares_bp_by_mode:
      balanced:    {review_max: 4500, growth_min: 2500, integration_min: 1500, choice_min: 1000}
      maintenance: {review_max: 10000, growth_min: 0, integration_min: 0, choice_min: 1000}
      re_entry:    {review_max: 8000, growth_min: 0, integration_min: 0, choice_min: 2000}
  classification:
    critical_floor_retrievability: 0.50
    maintenance_floor_retrievability: 0.85
    recurring_error_window_sessions: 3
    recurring_error_min_occurrences: 2
    prereq_leverage_min_dependents: 2
  starvation:
    reserved_steps_per_session: 1
    deferrals_to_qualify: 3
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
    divergence_tolerance: 0.30
    divergence_window_sessions: 6
  alerts:                                # только для mode=balanced [R-8]
    review_share_enter_bp: 4200
    review_share_exit_bp: 3500
    review_share_consecutive: 3
    growth_rate_enter_bp: 1000
    growth_rate_exit_bp: 1800
    growth_rate_consecutive: 3
```

- **MUST — policy тотальна и исполнима** `[mvp]`: каждая ветка §4 имеет конкретное значение здесь. Диапазонов нет; `allowed_range` живёт в каталоге (§4.9) и ограничивает будущие версии, а не заменяет значение.
- **MUST — выполнимость долей проверяется на каждый mode** `[mvp]`: для любого режима `growth_min + integration_min + choice_min ≤ 10000` и `review_max + growth_min ≤ 10000`. Версия, нарушающая это хотя бы в одном режиме, не активируется.
- **MUST — целочисленная арифметика** `[mvp]` [R-12]: доли хранятся как целые basis points, время — как целые секунды, аллокация считается как `floor(total_seconds * share_bp // 10000)`. Двоичный float запрещён на всём пути: YAML-загрузчик обязан читать `shares_bp` как int. Это то же требование побитовой воспроизводимости, что и Decimal-контекст [[scoring]] §2.1.

## 3b. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `compose_session(session_id, mode, total_seconds)` | API (sync, в UoW старта) | собирает `SessionPlan` revision 1; ошибки `BUDGET_TOO_SMALL`, `NO_CANDIDATES` | `[mvp]` |
| `replan(session_id, expected_revision)` | API (mutating, CAS) | новая ревизия; закрывает или переносит assignments (§4.2) | `[mvp]` |
| `claim_next_step(session_id, idempotency_key)` | API (mutating) | атомарно помечает следующий шаг предъявленным и публикует `STEP_PRESENTED` | `[mvp]` |
| `classify(candidates)` | API (pure) | `UrgencyClass` по §4.5; детерминирована, без побочных эффектов | `[mvp]` |
| `record_signal(signal)` | API | сигнал ученика; `too_easy` порождает probe-шаг | `[mvp]` |
| `explain(step_id)` | API | `DecisionTrace` | `[mvp]` |
| `availability_get()` / `availability_set(declared)` | API | §4.11 | `[mvp]` |
| `metrics()` / `catalogue()` | API | §4.10, §4.9 | `[mvp]` |
| `propose_calibration()` / `confirm_calibration(id)` | API | §4.9; активацию делает владелец параметра | `[post-mvp]` |
| `SESSION_COMPOSED {session_id, composition_revision, steps[], budget, pinned_versions, active_safety_version}` | publishes | план создан или пересобран | `[mvp]` |
| `STEP_PRESENTED {step_id, session_id, composition_revision, target_ref?, dimension?, context_id, predicted_retrievability?, presented_at}` | publishes | шаг **фактически выдан** | `[mvp]` |
| `LEARNER_SIGNAL_RECORDED`, `SIGNAL_CONSUMED` | publishes | сигнал зафиксирован / израсходован | `[mvp]` |
| `PROBE_REQUESTED {probe_id, target_ref, dimension, requested_difficulty, avoid_context}` | publishes | запрошена проба; `probe_id` выдаёт **движок** | `[mvp]` |
| `AVAILABILITY_UPDATED`, `CALIBRATION_PROPOSED`, `CALIBRATION_APPLIED` | publishes | — | `[mvp]` / `[post-mvp]` |

## 4. Поведение

### 4.1 Инварианты

- **MUST — `due` это кандидат, а не право** `[mvp]`: наступление срока не даёт цели места в занятии. Невзятое остаётся в backlog и ошибкой не является.
- **MUST — защищённый минимум роста** `[mvp]`: в режиме `balanced` корзина `growth` заполняется **первой** (§4.4) и не может быть занята повторениями. Занятие целиком из повторений возможно только в режимах `maintenance`/`re_entry`, выбранных явно.
- **MUST — доступность влияет на нагрузку, никогда на знание** `[mvp]`: `AvailabilityProfile` не входит ни в одну формулу [[scoring]]. Реальное время забывания не подделывается.
- **MUST — self-report запускает проверку, а не пишет оценку** `[mvp]`: см. §4.7.
- **MUST — каждое решение несёт trace** `[mvp]`: §4.8.
- **MUST — подчинение safety-overlay** `[mvp]`: единица, ставшая `avoid`/`obsolete` по **active** policy, исключается из плана независимо от класса. `SESSION_COMPOSED` фиксирует `active_safety_version`, использованную при исключении, — safety при этом **не** становится pinned policy ([[../OPEN]] OPEN-14).
- **MUST — калибровка не ретроактивна** `[mvp]`: §4.9.

### 4.2 Жизненный цикл композиции [CTRL-2]

- **MUST — композиция происходит в UoW старта** `[mvp]`: `lessons.start` синхронно вызывает `compose_session` **до** commit, в той же транзакции сохраняет `SessionPlan` с `composition_revision = 1` и включает его в Session Manifest. `SESSION_COMPOSED` публикуется через outbox той же UoW. Крэш между стартом и композицией невозможен: их нет как двух шагов.
- **MUST — выдача шага это мутация** `[mvp]` [R-1]: `trainer session next` **мутирующая** и идемпотентная. Она атомарно помечает следующий непредъявленный шаг выданным, публикует `STEP_PRESENTED` и возвращает шаг; повтор с тем же `--idempotency-key` отдаёт тот же ответ, не выдавая следующий. Прежняя формулировка «read-only next» делала переход «непредъявлен → предъявлен» невыразимым: шаг никогда не становился предъявленным, `is_first_exposure`, saturation и starvation не двигались, а повторный вызов вечно возвращал одно и то же.
- **MUST — просмотр без выдачи** `[mvp]`: `trainer session peek` — read-only, показывает следующий шаг, ничего не помечая и ничего не публикуя. Диагностика и выдача разделены, чтобы посмотреть план можно было, не потратив шаг.
- **MUST — переплан только явной командой** `[mvp]`: `trainer session replan` — мутирующая идемпотентная команда с CAS по `composition_revision`. Создаёт `revision + 1`, публикует новый `SESSION_COMPOSED`, не отменяет уже предъявленные шаги.
- **MUST — replan не оставляет сирот и не порождает долга** `[mvp]` [R-3, RR2-4]: непредъявленный review-шаг, выпавший из новой ревизии, **в той же UoW** получает `CANCELLED(reason=replanned)` ([[evidence]] §4.3). Это терминальная отмена, а **не** ReviewOutcome: scheduler не назначает retry, scoring не меняет состояние, метрика исходов не загрязняется. Иначе внутреннее перепланирование — ради safety, смены длительности или выбора ученика — само порождало бы долг повторения. Предъявленные шаги сохраняются со своими assignments.
- **MUST — ровно один действующий план** `[mvp]`: на сессию в любой момент действует план последней ревизии; `SESSION_COMPOSED` может быть несколько, но `(session_id, composition_revision)` уникален. Идемпотентность `replan` — по этому ключу.
- **MUST — `step_id` стабилен** `[mvp]`: `step_id` не меняется между ревизиями для сохранённых шагов; `decision_id` ссылается на trace, породивший шаг.

### 4.3 Корзины образуют разбиение [CTRL-1]

- **MUST — каждый шаг ровно в одной корзине** `[mvp]`: `bucket ∈ {review, growth, integration, choice}`, взаимоисключающе и исчерпывающе. `sum(allocated) ≤ total_seconds`.
- **MUST — определения корзин** `[mvp]`:

  | Корзина | Что попадает |
  |---|---|
  | `review` | шаг по цели из due-backlog, классифицированной §4.5 |
  | `growth` | шаг по цели с `is_first_exposure = true` |
  | `integration` | задание, требующее одновременно новую и ранее изученную цель |
  | `choice` | свободный разговор или тема, выбранная учеником |

- **MUST — `is_first_exposure` определяется по факту доставки** `[mvp]`: цель считается новой, если по ней **нет ни одного** `STEP_PRESENTED` (§4.6). `knowledge_state = NEW` для этого не годится: предъявление и объяснение не являются evidence, и цель остаётся `NEW` после нескольких показов.
- **MUST — не более одного growth-шага на цель в плане** `[mvp]` [R-13]: иначе оба шага получили бы `is_first_exposure = true` при композиции, а после выдачи первого второй стал бы ложно считаться новым и в бюджете, и в телеметрии. Повторное обращение к той же цели в том же занятии — шаг `integration` или `review`, не `growth`.

### 4.3a Схема `PlannedStep` — tagged union [R-3]

Общие поля: `step_id`, `decision_id`, `kind`, `bucket`, `step_type`, `expected_seconds`, `order_index`, `presented_at?`.

| `kind` | Обязательные поля |
|---|---|
| `review` | `review_assignment_id`, `target_ref`, `dimension`, `criteria_ref`, `urgency_class` |
| `growth` | `target_ref`, `dimension`, `is_first_exposure: true` |
| `integration` | `targets[]` из `{target_ref, dimension, role: new \| learned}`, минимум по одному каждой роли |
| `choice` | `target_ref?` либо `topic_hint` |
| `gate` | `gate_scope`, `scope_ref` |
| `probe` | `probe_id` (выдан движком), `target_ref`, `dimension`, `requested_difficulty`, `avoid_context?` |

- **MUST — review-шаг несёт `review_assignment_id`** `[mvp]`: без него выданное задание невозможно корректно закрыть через `trainer review close`, а `finish` не может проверить пустоту pending-set.
- **MUST — integration выражает пару** `[mvp]`: одиночный `target_ref` не способен описать задание «новая цель поверх освоенной», ради которого корзина и введена.
- **MUST — доли считаются по корзинам** `[mvp]`: `review_share = allocated.review / total_seconds`; `growth_rate = allocated.growth / total_seconds`. `integration` и `choice` не входят ни в одну из этих двух долей — двойного учёта нет.
- **MUST — вклад integration в цели** `[mvp]`: шаг `integration` может дать evidence нескольким целям, но с dedup и cap по [[evidence]] §4.1. На бюджет он относится целиком к своей корзине.

### 4.4 Канонический конвейер сборки [CTRL-12]

Детерминирован целиком; два корректных исполнения дают побайтово равный `SessionPlan`.

1. **Кандидаты.** `review` — due/overdue от [[scheduler]] §5. `growth` — рекомендации [[curriculum]], отфильтрованные по `is_first_exposure`. `integration` — пары (новая цель, освоенная цель). `choice` — цели из `goals[]`/личного словаря [[learner]] и рекомендация гейта от [[gates]], если она есть.
2. **Исключение по safety** — по active policy; исключённое фиксируется в trace.
3. **Классификация** review-кандидатов — §4.5.
4. **Сортировка внутри класса** — `(retrievability asc, stake_rank asc, deferral_count desc, expected_seconds asc, target_id asc, dimension_id asc)`.
5. **Резервирование полов** в фиксированном порядке `growth → integration → choice` до `*_min` **текущего режима** (§3). Пол — **резервируемая ёмкость, а не обязательная загрузка** [R-2]: если кандидатов корзины нет, фиксируется детерминированный waiver (`NO_GROWTH_CANDIDATE`, `NO_INTEGRATION_CANDIDATE`, `NO_CHOICE_CANDIDATE`) в trace, и освободившиеся секунды переходят следующей корзине по тому же порядку. Это делает исполнимыми первое занятие ученика (освоенных целей ещё нет, значит нет и integration-пар), исчерпание нового материала и режимы `maintenance`/`re_entry`, где `growth_min = 0`.
6. **Резерв против голодания** — §4.5.
7. **Review** по классам `critical → important → normal → maintenance`, пока не достигнут `review_max` или бюджет.
8. **Добор остатка** теми же правилами, не нарушая ни одного потолка.
9. **Квоты разнообразия** — §4.6, применяются как **фильтр при добавлении**, а не постобработкой: шаг, нарушающий квоту, пропускается, берётся следующий по порядку.
10. **Порядок предъявления** — чередование modes при равных прочих, затем `step_id asc`.

- **MUST — first-fit, не best-fit** `[mvp]`: шаг, не помещающийся в остаток корзины, **пропускается**, и берётся следующий кандидат в каноническом порядке. Best-fit запрещён: он даёт другой набор при том же входе.
- **MUST — неразрешимый бюджет** `[mvp]`: если `total_seconds < min_total_minutes × 60`, композиция отклоняется ошибкой `BUDGET_TOO_SMALL`.
- **MUST — пустой план это ошибка, а не результат** `[mvp]` [R-2]: если после waiver'ов не набрался ни один шаг, композиция отклоняется `NO_CANDIDATES` с `next_action`. Сессия с планом из нуля шагов не создаётся.
- **MUST — waiver виден в телеметрии** `[mvp]`: доля занятия, отданная по waiver другой корзине, попадает в trace и в метрики. Иначе систематическая невозможность набрать новый материал выглядела бы как здоровое занятие.

### 4.5 Классификация: тотальная упорядоченная таблица [CTRL-4]

Область — **только review-кандидаты** (due или overdue). Правила применяются по порядку, **первое совпавшее выигрывает**; таблица тотальна.

| # | Условие | Класс |
|---|---|---|
| 1 | `risk ∧ stake` | `critical` |
| 2 | `risk ∧ ¬stake` | `important` |
| 3 | `saturated` (§4.6) | `deferrable` |
| 4 | `retrievability ≥ maintenance_floor_retrievability` | `maintenance` |
| 5 | иначе | `normal` |

**Риск проверяется первым** [R-4]. В прежнем порядке `saturated` стояло первым, и три показа с тремя **провалами** удовлетворяли предикату насыщения, отправляя критичную цель в `deferrable`; а повторяющаяся живая ошибка при Retrievability 0.90 попадала в `maintenance` раньше проверки риска — то есть ровно тот сигнал, который вводился для исправления ошибочного прогноза модели, этим прогнозом и подавлялся.

**`risk`** = `knowledge_state = AT_RISK` **∨** повторяющаяся ошибка (≥ `recurring_error_min_occurrences` в последних `recurring_error_window_sessions`) **∨** `retrievability < critical_floor_retrievability`.

**`stake`** определён для обоих видов `LearningTarget` [CTRL-4]:

| Вид цели | `stake` истинно, если |
|---|---|
| `LexicalItem` | `curriculum_priority_band ∈ {CORE, HIGH}` ∨ leverage ∨ relevance |
| `Topic` | leverage ∨ relevance |

где **leverage** = цель является `strong`-prerequisite не менее чем `prereq_leverage_min_dependents` тем, **relevance** = цель связана с активной `goal` или записью личного словаря ([[learner]] §4). У `Topic` поля `curriculum_priority_band` нет, и вводить его сюда не требуется: для тем ставка выражается через leverage.

- **MUST — резерв против голодания** `[mvp]` [CTRL-7]: до заполнения review-корзины по классам в план **безусловно** включается до `reserved_steps_per_session` целей, отложенных системой не менее `deferrals_to_qualify` раз подряд, в порядке `deferral_count desc`. Это даёт **верхнюю границу ожидания**, а не только бонус к приоритету: прежняя формулировка «рост приоритета с потолком» гарантии не давала — при постоянном притоке более важных целей периферийная проигрывала бы бесконечно.
- **MUST — `stake_rank` закрыт** `[mvp]` [R-4]: `0` — relevance (цель связана с активной `goal` или личным словарём); `1` — `curriculum_priority_band ∈ {CORE, HIGH}` (LexicalItem) либо leverage ≥ `prereq_leverage_min_dependents` (любой вид цели); `2` — ставки нет. Сортировка по возрастанию. Без закрытого enum порядок внутри класса снова зависел бы от реализации.
- **MUST — жизненный цикл `deferral_count`** `[mvp]` [R-6]: увеличивается на 1, когда цель была кандидатом ревизии и **не вошла** в план по решению системы; **обнуляется** при `STEP_PRESENTED` по этой цели. Перенос по решению ученика (`snooze`) его не увеличивает. Порядок отбора в резерв — `(deferral_count desc, retrievability asc, target_id asc, dimension_id asc)`.
- **MUST — граница ожидания и её предпосылка** `[mvp]` [R-6]: резерв даёт верхнюю границу **при конечном множестве eligible-целей**: цель с максимальным `deferral_count` попадает в резерв не позже, чем через `|eligible| / reserved_steps_per_session` занятий. Если зарезервированный шаг не помещается в остаток бюджета, он вытесняет последний по приоритету review-шаг, а не пропускается, — иначе резерв не был бы гарантией. При бесконечно растущем backlog гарантии нет, и это ограничение названо здесь, а не подразумевается.

### 4.6 Доставка, насыщение, разнообразие [CTRL-6]

- **MUST — факт выдачи это граница до тьютора, а не до ученика** `[mvp]` [RR2-2]: `STEP_PRESENTED` фиксирует, что шаг **выдан тьютору** и стал его обязательством. Экран ученика движок не наблюдает — та же граница, что уже признана для времени ответа и усталости (§4.5). Утверждать «показан ученику» значило бы приписать движку ненаблюдаемый факт: между commit и репликой в чате возможны крэш, обрыв и смена агента.
- **MUST — что из этого следует** `[mvp]`: exposure, saturation и сброс `deferral_count` считаются от выдачи тьютору; идемпотентный повтор с тем же ключом возвращает тот же шаг и **не** создаёт второй факт. Если сессия брошена сразу после выдачи, факт остаётся — это честная плата за то, что доставку подтвердить нечем, и она названа здесь, а не замаскирована.
- **MUST — план не равен выдаче** `[mvp]`: `SESSION_COMPOSED` — намерение; в брошенной или перепланированной сессии шаг мог не выдаваться вовсе.
- **MUST — `SaturationState` строится из существующих событий** `[mvp]` [R-5]: входы — `STEP_PRESENTED` (число показов и `context_id`), `EVIDENCE_ADDED` и `REVIEW_OUTCOME` из [[evidence]] §3 (успех, independence), `ERROR_OBSERVED` (повторяющаяся живая ошибка для предиката `risk`). Событие с именем `ATTEMPT_ASSESSED` в каноне отсутствует и здесь не используется. Reducer применяет события в порядке канонического `sequence`, дедуп — по `event_id`.
- **MUST — `context_id` в факте доставки** `[mvp]` [R-5]: `STEP_PRESENTED` несёт `context_id` — идентификатор смыслового контекста задания (домен + тип задания). Без него `distinct_contexts` невыводим, и «три успеха подряд» нельзя отличить от «три успеха в одном и том же шаблоне».
- **MUST — предикат `saturated`** `[mvp]`: `exposures_in_window ≥ max_exposures_in_window` **∨** (`consecutive_independent_successes ≥ consecutive_success_threshold` **∧** `distinct_contexts < min_distinct_contexts`). Устойчивый успех в одном и том же контексте — признак знакомости, а не владения.
- **MUST — насыщение не равно владению** `[mvp]`: понижение класса меняет только план; состояние знания меняет исключительно [[scoring]].
- **MUST — квоты разнообразия** `[mvp]`: `max_steps_per_topic`, `max_consecutive_same_mode`, `max_similar_items`. «Похожие» = единицы, делящие `lemma`/базовый глагол phrasal-verb либо один `topic`.

### 4.7 Сигналы ученика и пробы [CTRL-9, CTRL-10]

- **MUST — discriminated union по `kind`** `[mvp]`:

  | `kind` | Обязательный payload | Срок |
  |---|---|---|
  | `too_easy` | `target_ref` | одноразовый |
  | `too_repetitive` | `target_ref?` | `expires_at` = +`exposure_window_sessions` |
  | `need_more_practice` | `target_ref` | `expires_at` = +3 сессии |
  | `not_relevant_now` | `target_ref` \| `domain` | `expires_at` обязателен |
  | `snooze` | `target_ref`, `until` | `until` |
  | `prefer_different_context` | `target_ref`, `avoid_context` | `expires_at` = +3 сессии |

- **MUST — два раздельных типа истечения** `[mvp]` [R-11]: `expires_at` (метка времени, для `snooze` и `not_relevant_now`) и `expires_after_session_seq` (номер сессии, для сигналов, чей срок задан в занятиях). Смешивать нельзя: «+3 сессии» невозможно записать в timestamp, а replay обязан воспроизвести ровно то же число занятий.
- **MUST — одноразовый сигнал расходуется явно** `[mvp]`: `too_easy` закрывается событием `SIGNAL_CONSUMED` в момент создания probe-шага. Без этого он порождал бы пробу в каждой последующей композиции.
- **MUST — precedence** `[mvp]` [R-11]: при конфликте более поздний сигнал того же `kind` на ту же цель замещает предыдущий (`superseded_by`). Между разными видами действует таблица, от сильного к слабому: `snooze` / `not_relevant_now` (исключают цель) → `need_more_practice` (повышает частоту) → `prefer_different_context` (ограничивает контекст) → `too_repetitive` (понижает класс) → `too_easy` (порождает пробу). Сигнал уровня `domain` слабее сигнала на конкретную цель. Истёкший сигнал перестаёт влиять, но не удаляется — история нужна аудиту.
- **MUST — сигналы не evidence** `[mvp]`: в Mastery, уровень и XP не входят никогда.
- **MUST — `origin` выводится движком, а не заявляется агентом** `[mvp]` [R-7]: `too_easy` порождает `PROBE_REQUESTED` с **выданным движком** `probe_id` и соответствующий `PlannedStep{kind: probe}`. Attempt ссылается на `step_id`; `origin = control_probe` движок проставляет **сам**, по типу шага. CLI параметра `--origin` не имеет. Иначе агент мог бы помечать обычные провалы как пробу и отключать понижение — то есть получил бы через чёрный ход ровно ту власть над оценкой, которую контракт у него забирает ([[cli]] §4.4).
- **MUST — no-negative покрывает все отрицательные эффекты** `[mvp]` [R-7]: evidence с `origin = control_probe` не может дать `REGRESSION`, не понижает knowledge state, **не уменьшает Mastery и Stability и не сдвигает расписание в сторону сокращения интервала**. Успех засчитывается обычным порядком в пределах общих cap'ов. Прежняя формулировка запрещала только смену состояния и оставляла отрицательную дельту возможной — то есть наказание всё равно наступало, просто тише.
- **MUST — probe в своей корзине** `[mvp]` [R-7]: `too_easy` не требует, чтобы цель была due, поэтому probe-шаг **не** относится к `review` (та определена через due-backlog). Probe занимает `choice`: это шаг, инициированный учеником.
- **MUST — бюджет проб** `[mvp]`: не более одного probe-шага на цель в занятии.

### 4.7a Availability — алгоритм v1 [R-9]

Сущность §2 без правил вычисления не задавала поведения; часть значений policy не использовалась ни одной веткой.

- **MUST — схема `declared`** `[mvp]`: `sessions_per_week`, `typical_minutes`, `next_available_at?`, `blackout_until?`. Задаётся `trainer availability set`.
- **MUST — источник `observed`** `[mvp]`: `sessions_per_week` — число терминализованных сессий за `divergence_window_sessions` последних календарных недель; `typical_minutes` — **медиана `planned` `total_seconds`** этих сессий, не разность `STARTED→FINISHED` (та включает сон и потерю чата, §4.2 CTRL-8).
- **MUST — precedence бюджета** `[mvp]`: `total_seconds` берётся первым из непустого: `--duration` команды → `declared.typical_minutes` → `observed.typical_minutes` → `default_total_minutes`. Порядок фиксирован, чтобы две реализации не выбрали разное.
- **MUST — расхождение** `[mvp]`: `divergence = |declared.sessions_per_week − observed.sessions_per_week| / max(declared, 1)`. При `divergence > divergence_tolerance` система **предлагает** уточнить (`AVAILABILITY_UPDATED` не публикуется до согласия ученика) и молча объявленное не переписывает.
- **MUST — влияние на состав** `[mvp]`: при `blackout_until` в будущем либо `next_available_at`, отстоящем дальше медианного интервала, композиция повышает долю `critical` внутри `review_max` и понижает `growth` до его пола — но **не ниже**. Доступность меняет форму нагрузки и никогда не входит в scoring (§4.1).

### 4.8 Decision trace

- **MUST — trace у каждого шага** `[mvp]`: `decision_id`, сработавшие правила классификации с их номерами, значения `risk`/`stake` сигналов, retrievability, класс, состояние насыщения, применённые квоты, занятость корзин, `pinned_versions` (включая `control_policy`) и `active_safety_version`.
- **MUST — доступен по команде** `[mvp]`: `trainer why --step ID`.
- **MUST — поля разрешимы** `[mvp]`: каждое поле trace либо разрешается в строку каталога (§4.9), либо помечено как вычисленный вход.

### 4.9 Каталог tunables и калибровка

```yaml
parameter_id: control.budget.shares.review_max
owner: 0.12 control
scope: global
default: 0.45
allowed_range: [0.30, 0.60]
carried_by: control_policy@1
observed_by: [review_share, growth_rate]
change_mode: propose_confirm
trace_field: review_max
```

- **MUST — реестр, не хранилище** `[mvp]`: значения живут в pinned policy у владельца; каталог хранит метаданные. Два хранилища одного числа разъедутся.
- **MUST — каталог это обязательство реализации, а не существующий артефакт** `[mvp]` [R-10]: строк каталога в каноне ровно столько, сколько показано примером. Реализация обязана создать versioned catalogue-артефакт со строкой на **каждый** параметр `control_policy@1` и на ранее объявленные tunables соседей, и валидатор обязан проверять полноту в обе стороны. До появления артефакта запрет активации вне `allowed_range` **не действует** — проверять его нечем, и утверждать обратное было бы тем же over-claim, что и в OPEN-27.
- **MUST — потолок автономии: propose_confirm** `[PD-2026-07-20]`: ни один параметр не объявляет режим выше. Автоприменение запрещено: при одном ученике шум неотличим от сигнала.
- **MUST — применение делегируется владельцу** `[PD-2026-07-20]` [CTRL-Q2]: control владеет **только** workflow «предложил → подтвердили». Активацию новой версии выполняет **API модуля-владельца** параметра, с его CAS и его событием; control не мутирует чужой aggregate и не становится вторым владельцем policy. `CALIBRATION_APPLIED` фиксирует подтверждение и связан `causation_id` с событием активации у владельца.

### 4.10 Метрики качества политики [CTRL-13]

Каждая — `PolicyMetric` с формулой, окном и правилом отсутствующих данных. Значения ниже — v1.

| id | Формула | Окно | Нет данных |
|---|---|---|---|
| `calibration_error` | среднее \|прогноз Retrievability на момент выдачи − факт (1 успех / 0 неуспех)\| по всем `REVIEW_OUTCOME` | 200 исходов | `no-data` при < 50 |
| `review_share` | `allocated.review / total_seconds`, среднее по сессиям | 10 сессий | `no-data` при < 3 |
| `growth_rate` | `allocated.growth / total_seconds`, среднее по сессиям | 10 сессий | `no-data` при < 3 |
| `backlog_age_p90` | 90-й процентиль `now − first_due_at` по незакрытым due | текущий срез | `no-data` при пустом backlog |
| `max_deferrals` | максимум `deferral_count` среди целей backlog | текущий срез | `0` |
| `lapse_rate_after_mastered` | доля целей, получивших REGRESSION в течение 90 дней после MASTERED | 90 дней | `no-data` при < 10 |
| `transfer_gap` | успех на знакомом шаблоне − успех в новом контексте | 50 исходов каждого | `no-data` |

- **MUST — прогноз фиксируется в `STEP_PRESENTED`, а не при композиции** `[mvp]` [R-8]: `predicted_retrievability` записывается в момент **фактической выдачи**. Композиция и выдача расходятся во времени (сессию можно возобновить через день), а Retrievability убывает по реальному времени — сравнение с прогнозом из плана приписывало бы политике ошибку, созданную устаревшим планом. Пересчёт задним числом запрещён.
- **MUST — разметка исходов** `[mvp]` [R-8]: в `calibration_error` `CONFIRMED` и `PROGRESS` → `1`; `REGRESSION` → `0`; `RECOVERED` → `1`; `INSUFFICIENT_EVIDENCE` → **исключается** из выборки, а не считается нулём. Исход из пяти значений нельзя молча свести к булеву.
- **MUST — аварии считаются только по `balanced`-занятиям** `[mvp]` [R-8]: в режимах `maintenance`/`re_entry` нулевой рост законен, и включение их в окно давало бы ложную тревогу после трёх нормальных поддерживающих занятий.
- **MUST — раздельные пороги входа и выхода** `[mvp]`: авария включается при пересечении `*_enter_bp` подряд `*_consecutive` занятий и выключается только при пересечении `*_exit_bp` — гистерезис не даёт метрике мигать у порога. Пороги — параметры каталога, а не прилагательные «устойчиво» и «близок».
- **MUST — реакция: сообщить, не притормаживать** `[PD-2026-07-20]` [CTRL-Q1]: при аварии система **сообщает** и предлагает выбор (режим `maintenance`, больше времени, отказ от части целей). Автоматическое снижение притока нового материала **не вводится**: скрытое изменение программы без ведома ученика противоречит принципу «движок объясняет, а не решает молча».
- **MUST — честность о статистике** `[mvp]`: при одном ученике большинство метрик долго остаются шумом; `no-data` — легитимный результат, а не ноль.

## 5. CLI-поверхность

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer why --step ID` | control | нет | `DecisionTrace` шага (§4.8) |
| `trainer signal KIND --target ID [payload]` | control | да | сигнал ученика; `too_easy` → `PROBE_REQUESTED` |
| `trainer availability show` \| `set` | control | `set` — да | ритм: объявленный, наблюдаемый, расхождение |
| `trainer tunables list [--owner X]` | control | нет | каталог настроек |
| `trainer metrics` | control | нет | метрики + аварии |
| `trainer calibration list` \| `confirm ID` | control | `confirm` — да | предложения; применение делегируется владельцу |

`trainer session start --mode`, `trainer session next` (мутирующая, §4.2), `trainer session peek` (read-only) и `trainer session replan` принадлежат [[lessons]]; их поведение определяется здесь.

## 6. Границы

- **depends on**: [[scheduler]] (backlog, retrievability), [[scoring]] (состояния, прогнозы), [[evidence]] (исходы, наблюдённые ошибки, ReviewAssignment), [[curriculum]] (priority band, prerequisites, рекомендации), [[learner]] (`goals`, личный словарь → relevance), [[gates]] (рекомендация гейта как кандидат `choice`), [[lessons]] (UoW старта, терминализация)
- **events published**: `SESSION_COMPOSED`, `STEP_PRESENTED`, `LEARNER_SIGNAL_RECORDED`, `PROBE_REQUESTED`, `AVAILABILITY_UPDATED`, `CALIBRATION_PROPOSED`, `CALIBRATION_APPLIED`
- **events consumed**: `REVIEW_SCHEDULED`, `OVERDUE_AT_RISK_TRIGGERED` (← [[scheduler]]), `STATE_TRANSITION` (← [[scoring]]), `EVIDENCE_ADDED`, `REVIEW_OUTCOME`, `ERROR_OBSERVED` (← [[evidence]] §3 — saturation, recurring-error, метрики), `SESSION_STARTED`/`FINISHED`/`ABANDONED` (← [[lessons]])

Модуль не меняет Mastery, Stability, knowledge state, CEFR и интервалы; содержимое заданий генерирует П.3.

## 7. Открытые вопросы

- **OPEN-27**: эмпирическая калибровка значений §3. Все они **существуют и исполнимы**; открыта только их проверка данными → не блокирует реализацию.
- **OPEN-29**: `AvailabilityProfile` в v1 несёт `sessions_per_week`, `typical_minutes`, `next_available_at?` и `blackout_until?`. Полная календарная модель (дни недели, исключения) → `[post-mvp]`; до неё обещание «перенести на ближайшее занятие» опирается на `next_available_at`, а при его отсутствии — на статистическую оценку.
- **OPEN-14**: safety-overlay определяет допустимое к предъявлению.

## История изменений

- **2026-07-20 (3)**: триаж повторного ревью. Выдача шага стала **мутацией** (`session next` идемпотентно помечает шаг предъявленным и публикует `STEP_PRESENTED`; read-only просмотр вынесен в `session peek`) — прежде переход «непредъявлен → предъявлен» был невыразим [R-1]. Полы бюджета стали **резервируемой ёмкостью с waiver** и получили таблицу долей **по режимам**, иначе первое занятие и `maintenance` были неисполнимы [R-2]. `PlannedStep` стал tagged union с `review_assignment_id` и парой ролей у integration; replan закрывает выпавшие assignments в той же UoW, чтобы `finish` не блокировался сиротами [R-3]. Риск проверяется **раньше** насыщения и maintenance [R-4]. Имена потребляемых событий приведены к существующим, добавлен `context_id` [R-5]. У `deferral_count` появился жизненный цикл, у резерва — предпосылка и формула границы [R-6]. `origin=control_probe` выводится движком по типу шага, no-negative распространён на Mastery/Stability/расписание, probe перенесён в корзину `choice` [R-7]. Прогноз для калибровки фиксируется при выдаче, исходы размечены, аварии считаются только по `balanced` и получили гистерезис [R-8]. Описан алгоритм availability [R-9]. Каталог назван обязательством реализации, а не существующим артефактом [R-10]. Сигналы получили два типа истечения и межвидовую precedence [R-11]. Доли переведены в целые basis points [R-12]. Запрещён второй growth-шаг на цель [R-13]. Возвращён раздел Public API [R-14].
- **2026-07-20 (2)**: переписан после red-team ревью (5 BLOCKER). Введена исполнимая `control_policy@1` с конкретными значениями (CTRL-5); корзины сделаны разбиением с независимым признаком `is_first_exposure` (CTRL-1); композиция происходит в UoW старта, `session next` остался read-only, переплан — отдельная мутирующая команда с CAS (CTRL-2); `control_policy` заведена в реестр политик и Manifest (CTRL-3); классификатор заменён тотальной упорядоченной таблицей с определением `stake` для обоих видов LearningTarget (CTRL-4); добавлен факт доставки `STEP_PRESENTED` и потребление событий evidence (CTRL-6); голодание получило резерв мест вместо необеспеченного обещания (CTRL-7); снято ошибочное утверждение, что `STARTED→FINISHED` измеряет учебное время (CTRL-8); сигналы стали discriminated union со сроками (CTRL-9); probe получил отдельный origin и правило no-negative (CTRL-10); зафиксирован канонический конвейер сборки с first-fit (CTRL-12); метрики получили формулы, окна и правила отсутствующих данных (CTRL-13); learner и gates добавлены в зависимости (CTRL-14). Развилки [PD-2026-07-20]: при долговой спирали система **сообщает**, а не притормаживает приток; калибровку чужого параметра применяет **владелец**, control владеет только workflow подтверждения.
- **2026-07-20**: создан (контракт 0.12) после Concept Gate.
