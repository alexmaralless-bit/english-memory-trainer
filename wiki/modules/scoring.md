# Модуль: scoring

> **Status**: current
> **Last updated**: 2026-07-20
> **Sources**: [[../product/learning-model]] · [[evidence]] · Concept Gate 0.4 2026-07-20 (3 развилки, [PD-2026-07-20]) · review triage journals (OPEN-1/8/10/12/13/20) · часть контракта 0.4
> **Bounded context**: `src/english_trainer/scoring/`

> Спека — **target**. Все формулы **versioned и детерминированы**; scoring replay воспроизводит их точно. Численные константы — дефолты, помеченные *tunable* (калибруются позже, без смены доменной модели). Термины — [[../glossary]].

---

## 1. Назначение

Модуль вычисляет всё оценочное состояние из evidence: Mastery/Stability/Retrievability по target, knowledge state, рабочий CEFR-уровень, агрегаты (Learning Score, Tutor Compliance, Informal Online Competence) и XP-ledger. Единственный, кто меняет scores. Детерминирован и версионируем.

## 2. Модель: две оси [PD-2026-07-20]

Разделены **качество** (Mastery) и **память** (Stability/Retrievability).

### 2.1 Mastery — качество, 0–100
- **MUST**: per-target Mastery = взвешенный агрегат score по каждой required dimension (веса — часть scoring policy). Overall Mastery не выше покрытия required dimensions (unknown dimension не поднимает).
- **MUST — дельта за evidence**: каждый admissible evidence даёт градуированную дельту от: correctness, difficulty, independence (hints снижают), mode-weight (`recognition < controlled_production < spontaneous_production < transfer`), error severity, temporal spacing.
- **MUST — cap за сессию**: прирост Mastery на target за сессию ≤ `session_cap` (*tunable*, дефолт 15). Одна попытка не переводит в MASTERED.
- **MUST — rubric/informal cap**: вклад rubric- и informal-evidence в Mastery ограничен `rubric_cap` (*tunable*); повышение состояния по ним требует ≥2 независимых сессий ([[evidence]] §4.1).
- **MUST — monotonicity**: при устойчивых успехах Mastery не убывает в пределах сессии; убывает только на подтверждённый REGRESSION.
- **MUST — детерминизм чисел** [ревью 0.4-8]: все вычисления — `Decimal` с **фиксированным контекстом**: precision 28 значащих цифр, rounding `ROUND_HALF_EVEN`; никакого IEEE float в scoring-пути. `exp` вычисляется методом `Decimal.exp()` в этом контексте (детерминированный, не platform-`math.exp`). Порядок агрегации канонический (по `sequence`/`target_id`). Контекст — часть pinned scoring policy; каждая versioned policy **total и executable** (никаких диапазонов).

### 2.2 Stability (дни) и Retrievability (0–1)
- **MUST**: `Retrievability(t) = Decimal.exp(-elapsed_days / Stability)`, elapsed по реальному времени (UTC, [[../product/learning-model]] §7), не по календарю.
- **MUST**: начальная Stability — **единственный** default policy-параметра `initial_stability_days = 2.0` (*tunable*, но конкретное значение в каждой версии, не диапазон); успешный review умножает Stability на фактор `f(outcome_quality, current_stability)` (растёт медленнее у стабильных); REGRESSION уменьшает по фактору. Все факторы — именованные policy-параметры с конкретными дефолтами.
- **MUST**: Mastery и Stability обновляются раздельно из одного evidence; scheduler ([[scheduler]]) использует Retrievability для интервалов.

## 3. Knowledge state — полная таблица переходов (OPEN-10)

Оси — [[../glossary]] (enrollment / knowledge_state / review_status). Таблица `(state, ReviewOutcome)`:

Таблица **тотальна** — определена каждая пара (нет «—»):

| state \ outcome | PROGRESS | CONFIRMED | REGRESSION(подтв.) | RECOVERED | INSUFFICIENT_EVIDENCE |
|---|---|---|---|---|---|
| NEW | LEARNING | LEARNING | NEW (no-op) | NEW (no-op)⁴ | NEW (no-op) |
| LEARNING | LEARNING | ACTIVE¹ | LEARNING (no-op) | LEARNING (no-op) | LEARNING (no-op) |
| ACTIVE | ACTIVE | MASTERED² | LEARNING | ACTIVE (no-op) | ACTIVE (no-op) |
| MASTERED | MASTERED | MASTERED | ACTIVE | MASTERED (no-op) | MASTERED (no-op) |
| AT_RISK | AT_RISK | prior_steady_state³ | LEARNING | prior_steady_state³ | AT_RISK (no-op) |

¹ при threshold required dimensions + independence + repeatability (по `mastery_criteria` §3b). ² при `mastery_criteria` + retention (Stability ≥ `mastered_stability_days`, *tunable*). ³ restore в `prior_steady_state` ∈ {ACTIVE, MASTERED}. ⁴ `RECOVERED` для NEW/LEARNING семантически невозможен (нет prior AT_RISK) → **no-op**, не error; corrupted/late outcome с невозможной парой — no-op с audit-записью (не меняет state, не бросает).

- **MUST — вход AT_RISK только через факт** [ревью 0.4-2]: `AT_RISK` возникает от подтверждённого REGRESSION **или** от события `OVERDUE_AT_RISK_TRIGGERED` (append-only, эмитит scheduler при crossing, [[scheduler]] §4). Scoring применяет `STATE_TRANSITION` из этого события — **не из текущего wall-clock**. Replay применяет тот же факт → historical state детерминирован независимо от времени запуска replay.
- **MUST**: review_status (`not_due/due/overdue`) — ось scheduler, не knowledge state; переход выполняет только движок.

### 3b. `Topic.mastery_criteria` — versioned schema [ревью 0.4-1]

Schema, которой автор программы (П.2) описывает критерии темы; validator curriculum её проверяет ([[curriculum]] §5). Per required dimension:

```yaml
mastery_criteria:
  version: 1                      # selector версии scoring policy
  per_dimension:
    recognition:
      active_threshold: 70        # Mastery-порог для вклада в ACTIVE (tunable)
      independent_attempts: 2     # мин. независимых (evidence §4.1)
    controlled_production:
      active_threshold: 75
      independent_attempts: 2
    spontaneous_production:       # required не у всех тем
      active_threshold: 75
      independent_attempts: 2
  mastered:
    all_required_active: true     # все required dimensions ≥ active
    retention_stability_days: 30  # Stability ≥ для MASTERED (tunable)
    retention_confirmations: 2    # подтверждений на разных интервалах
```

- **MUST**: `mastery_criteria` определяет только *структуру и связь* с transition table (§3); численные значения — *tunable* policy-константы. Отсутствие критерия на required dimension = ошибка валидации. Эта schema — то, что делает П.2 authoring-возможным (roadmap).
- **MUST — relation к table**: `LEARNING → ACTIVE` при выполнении `per_dimension.active_threshold` + `independent_attempts` по всем required; `ACTIVE → MASTERED` при `mastered.*`.

### 3c. `LexicalMasteryProfile` — см. §6.

## 4. Рабочий CEFR-уровень — целые bands (OPEN-8) [PD-2026-07-20]

- **MUST**: уровни только целые (`A1…C2`), без подуровней. Per-skill CEFR = наивысший band, где выполнено **coverage**: ≥ `min_topics` независимых тем band'а в состоянии ACTIVE+ по required dimensions, ширина dimensions, confidence ≥ `confidence_floor` (все *tunable*). Непроверенная область — **unknown**, не поднимает уровень.
- **MUST — core-skill map** [ревью 0.4-3]: Track ≠ core skill; вклад темы в core-навык задаётся **versioned `core_skill_map`** (часть scoring policy) по `(track, dimension)` с весами и cap. Дефолт:
  - `grammar-engine` → Grammar; `vocabulary-chunks` → Vocabulary; `reading` → Reading;
  - `written-interaction` + `written-production-mediation` → Writing;
  - `us-tech-english`, `everyday-online-informal` — вклад по dimension: recognition→Reading, production→Writing (с весом < 1, dedup со своим основным треком).
  Карта versioned и адресуема; coverage считается по ней, а не по track напрямую.
- **MUST**: overall working level (`measured_working_level`) = **не выше слабейшего core-навыка** (целый band; «полступени» снято, E-R4). Внутриуровневый прогресс отражает Learning Score, не уровень.
- **MUST — measured vs provisional** [PD-2026-07-20, ревью 0.4-11]: движок отдаёт два раздельных поля — `measured_working_level` (только из evidence; неизмеренные навыки = unknown, трактуются консервативно) и `provisional_working_estimate` (measured где есть, иначе `self_reported_level`, помечено provisional). **Learning Score и gating используют `measured_working_level`**; briefing/рекомендации могут показывать provisional с флагом. `self_reported_level` замещается измерением per-skill после первого evidence/confidence floor.
- **MUST — confidence**: per-skill confidence (`very_low | low | medium | high`) растёт по объёму/разбросу evidence; rolling-уточнение — versioned policy.

### 4b. Origin и placement-cap [ревью 0.4-4]

- **MUST**: evidence несёт immutable `origin` (`session | placement | re_entry`), захваченный в событие.
- **MUST — placement ceiling**: evidence с `origin=placement` **не может поднять knowledge state выше `ACTIVE`** (никогда MASTERED — нет retention во времени). Rubric-writing из placement помечается provisional и не поднимает полный Writing CEFR-band (нужны ≥2 независимых non-placement items). Правило в scoring, покрыто replay-тестом.

## 5. Агрегаты (OPEN-12/13)

- **Learning Score** [PD-2026-07-20]: coverage-взвешенный средний Mastery тем **текущего working-уровня**, 0–100 («насколько твёрдо владею тем, где я есть»). Прогресс-к-следующему — отдельно в roadmap-progress-проекции, не здесь.
- **Tutor Compliance Score** [ревью 0.4-9]: 0–100, `honored_obligations / total_obligations` за **measurement window** (*tunable*, дефолт последние 10 сессий). **Obligations registry** (versioned): required-skill вызван нужной версии; correction-протокол соблюдён; нет forbidden actions (агент не классифицировал сам, соблюдены finish-postconditions). Каждое obligation берётся из audit-события (raw input — событийный лог, не текст агента). Нет данных в окне → `no-data`, не 0.
- **Informal Online Competence** (OPEN-13): отдельный 0–100 профиль по informal LexicalItems/навыкам; **не двигает CEFR напрямую**. Informal production через `contribution_scope` даёт компонент writing/transfer с dedup/cap.
- **MUST**: агрегаты — производные проекции; не влияют обратно на per-target Mastery (нет циклов).

## 6. LexicalMasteryProfile (OPEN-13)

- **MUST**: у каждого LexicalItem versioned `LexicalMasteryProfile` — required dimensions и mastery-критерии по `type`/`usage_policy`: `recognition_only`/`avoid`/`obsolete` → только recognition (production не требуется и не «застревает»); `safe_to_use`/разрешённый `context_dependent` → + production. Lexeme агрегирует состояние из required forms детерминированно.

## 7. XP-ledger (OPEN-12)

- **MUST — award schema** [ревью 0.4-9]: XP-award — immutable событие `{source_id, award_kind, practice_day, amount}`. `source_id` уникален; **award-once** независимо от replay. **Awardable source event types** (закрытый список): finalized attempt, closed review, completed re-entry block — **mutually exclusive eligibility** (один source event даёт награду ровно одного kind, не двойной зачёт через категории). `amount` = base(kind) × multipliers(independence, difficulty) — все *tunable* policy-значения.
- **MUST — cap/dedup order**: daily cap по ключу `(learner, practice_day)`; при превышении лишнее не начисляется (порядок применения детерминирован по `sequence`). Streak по локальному `practice_day` ([[../product/learning-model]] §8), day-dedup из kernel (OPEN-12/foundation).
- **MUST**: ABANDONED eligibility — начисляется за уже зафиксированные finalized-источники брошенной сессии, но не за незакрытые цели. **Штрафов и списаний нет**.

## 8. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer scoring replay` | детерминированный пересбор всех scores из событий + сверка (kernel §5) |
| `trainer status --format json` | текущее состояние: уровни, Mastery-сводка, Learning Score, XP |

## 9. Границы

- **depends on**: evidence (факты), curriculum (targets/dimensions/profiles/pinned policy), kernel (детерминизм/numeric).
- **events published**: `SCORES_UPDATED`, `STATE_TRANSITION`, `LEVEL_UPDATED`, `XP_AWARDED`.
- **consumed by**: scheduler (Retrievability/состояния), lessons (манифест), memory (проекция), learner (агрегаты).

## 10. Открытые вопросы

Контракт **закрывает** OPEN-1 (формула-shape), OPEN-8 (coverage/confidence/уровень), OPEN-10 (таблица), OPEN-12 (шкалы/ledger), OPEN-13 (informal/lexical profile) на уровне модели. Остаётся **калибровка** *tunable*-констант (thresholds, cap'ы, факторы Stability) — итеративно на реальном обучении, versioned; не меняет доменную модель.

## История изменений

- **2026-07-20 (2)**: 0.4-review триаж — добавлена **`Topic.mastery_criteria` schema** (§3b, BLOCKER 0.4-1); AT_RISK применяется из replayable-события, не clock (§3, BLOCKER 0.4-2); таблица переходов тотальна (NEW×RECOVERED, 0.4-6); core-skill map (§4, 0.4-3); origin+placement-cap (§4b, 0.4-4); measured vs provisional level (§4, 0.4-11); точный Decimal-контекст + конкретные дефолты (§2, 0.4-8); XP award-schema и Tutor Compliance measurement (§5/§7, 0.4-9).
- **2026-07-20**: создан (контракт 0.4, часть 2). Две оси Mastery/Stability-Retrievability [PD-2026-07-20]; таблица переходов; целые CEFR-bands; Learning Score; Tutor Compliance/Informal; LexicalMasteryProfile; XP-ledger; numeric-детерминизм.
