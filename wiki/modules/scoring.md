# Модуль: scoring

> **Status**: current
> **Last updated**: 2026-07-21
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

- **MUST — вход AT_RISK только из overdue-события** [ревью 0.4-2, P0-1]: `AT_RISK` возникает **только** от события `OVERDUE_AT_RISK_TRIGGERED`. REGRESSION в `AT_RISK` **не переводит никогда** — он понижает состояние по таблице выше (`ACTIVE → LEARNING`, `MASTERED → ACTIVE`, `AT_RISK → LEARNING`). Разделение смысловое: `AT_RISK` — «знал, рискует забыть от простоя», REGRESSION — «продемонстрировал, что не владеет», и это разные факты с разными последствиями. Прежняя формулировка «AT_RISK от подтверждённого REGRESSION» противоречила тотальной таблице, в которой такой ветки нет, и требовала несуществующего поля «тяжесть regression». Событие `OVERDUE_AT_RISK_TRIGGERED` — append-only, эмитится scheduler при crossing ([[scheduler]] §4); scoring применяет `STATE_TRANSITION` из этого события, **не из текущего wall-clock**, и replay применяет тот же факт.
- **MUST — STATE_TRANSITION pin-ит scoring policy** [rereview R-1]: результирующий `STATE_TRANSITION` фиксирует версию scoring policy, по которой переход применён, и связан `causation_id` с триггером; trigger и применение — в одной UoW. Иначе активация policy между sweep и apply дала бы разные исходы из одного факта.
- **MUST**: review_status (`not_due/due/overdue`) — ось scheduler, не knowledge state; переход выполняет только движок.

### 3b. `Topic.mastery_criteria` — versioned schema [ревью 0.4-1]

Schema, которой автор программы (П.2) описывает критерии темы; validator curriculum её проверяет ([[curriculum]] §5). Per required dimension:

```yaml
mastery_criteria:
  schema_version: 1               # версия ЭТОЙ schema (не scoring policy, rereview R-6)
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

- **MUST — владение значениями** [rereview R-6]: конкретные значения (`active_threshold`, `retention_*`) **принадлежат теме** и живут в pinned `CurriculumVersion`; scoring policy их только *интерпретирует* (не переопределяет). `schema_version` версионирует форму, а не policy. Апгрейд scoring policy **не** меняет ретроспективно пороги старых тем — retrospective drift исключён.
- **MUST**: `mastery_criteria` задаёт структуру и связь с transition table (§3). Отсутствие критерия на required dimension = ошибка валидации. Эта schema — то, что делает П.2 authoring-возможным (roadmap).
- **MUST — relation к table**: `LEARNING → ACTIVE` при выполнении `per_dimension.active_threshold` + `independent_attempts` по всем required; `ACTIVE → MASTERED` при `mastered.*`.

### 3c. `LexicalMasteryProfile` — см. §6.

## 4. Рабочий CEFR-уровень — целые bands (OPEN-8) [PD-2026-07-20]

- **MUST**: уровни только целые (`A1…C2`), без подуровней. Per-skill CEFR = наивысший band, где выполнено **coverage**: ≥ `min_topics` независимых тем band'а в состоянии ACTIVE+ по required dimensions, ширина dimensions, confidence ≥ `confidence_floor` (все *tunable*). Непроверенная область — **unknown**, не поднимает уровень.
- **MUST — core-skill map** [ревью 0.4-3, rereview R-3]: Track ≠ core skill; вклад задаётся **versioned `core_skill_map`** (часть scoring policy) по `(track, dimension)` с весами и cap. Правило перечисляет **все четыре machine-ID dimension** явно (никакого обобщённого «production»):
  | track | recognition | controlled_production | spontaneous_production | transfer |
  |---|---|---|---|---|
  | `grammar-engine` | Grammar | Grammar | Grammar | Grammar (w<1) |
  | `vocabulary-chunks` | Vocabulary | Vocabulary | Vocabulary | Vocabulary (w<1) |
  | `reading` | Reading | Reading | — | Reading (w<1) |
  | `written-interaction`, `written-production-mediation`, `everyday-life` | Reading (w<1) | Writing | Writing | Writing (w<1) |
  | `us-tech-english`, `everyday-online-informal` | Reading (w<1) | Writing (w<1) | Writing (w<1) | Writing (w<1) |

  `transfer` всегда засчитывается в тот же core skill, что и production данного трека, но с **пониженным весом и отдельным cap** (перенос подтверждает владение, но не заменяет прямое производство). Веса/cap — *tunable*; карта versioned и адресуема, coverage считается по ней, не по track напрямую.
- **MUST**: overall working level (`measured_working_level`) = **не выше слабейшего core-навыка** (целый band; «полступени» снято, E-R4). Внутриуровневый прогресс отражает Learning Score, не уровень.
- **MUST — measured vs provisional** [PD-2026-07-20, ревью 0.4-11]: движок отдаёт два раздельных поля — `measured_working_level` (только из evidence; неизмеренные навыки = unknown, трактуются консервативно) и `provisional_working_estimate` (measured где есть, иначе `self_reported_level`, помечено provisional). **Learning Score и gating используют `measured_working_level`**; briefing/рекомендации могут показывать provisional с флагом. `self_reported_level` замещается измерением per-skill после первого evidence/confidence floor.
- **MUST — confidence**: per-skill confidence (`very_low | low | medium | high`) растёт по объёму/разбросу evidence; rolling-уточнение — versioned policy.

### 4b. Origin и placement-cap [ревью 0.4-4]

- **MUST**: evidence несёт immutable `origin` — единый закрытый enum `session | placement | re_entry | control_probe` [RR2-3], захваченный в событие. Значение выводит движок из выданного `PlannedStep`; клиент его не задаёт ([[evidence]] §3).
- **MUST — no-negative для `control_probe`** [CTRL-10, R-7]: evidence с `origin=control_probe` **не может дать `REGRESSION`**, не понижает knowledge state, **не уменьшает Mastery и Stability и не сокращает интервал** ([[scheduler]] §3). Успех засчитывается обычным порядком в пределах общих cap-ов. `origin` выводит движок по типу шага плана; агент его не задаёт ([[control]] §4.7). Проба — добровольная проверка **выше** требуемого уровня, запрошенная сигналом «слишком легко» ([[control]] §4.7); наказание за неё научило бы не сообщать о лёгкости, и инструмент честной картины начал бы её искажать. Покрыто replay-тестом.
- **MUST — placement ceiling**: evidence с `origin=placement` **не может поднять knowledge state выше `ACTIVE`** (никогда MASTERED — нет retention во времени). Rubric-writing из placement помечается provisional и не поднимает полный Writing CEFR-band (нужны ≥2 независимых non-placement items). Правило в scoring, покрыто replay-тестом.

## 5. Агрегаты (OPEN-12/13)

- **Learning Score** [PD-2026-07-20, rereview R-7]: coverage-взвешенный средний Mastery тем **`measured_working_level`** (именно измеренного, §4 — не provisional/self-report), 0–100. Если `measured_working_level` = unknown (нет допустимого evidence) → Learning Score = `no-data`, не 0. Прогресс-к-следующему — отдельно в roadmap-progress-проекции.
- **Tutor Compliance Score** [ревью 0.4-9]: 0–100, `honored_obligations / total_obligations` за **measurement window** (*tunable*, дефолт последние 10 сессий). **Obligations registry** (versioned): required-skill вызван нужной версии; correction-протокол соблюдён; нет forbidden actions (агент не классифицировал сам, соблюдены finish-postconditions). Каждое obligation вычисляется из **наблюдаемых движком** эффектов — вызовов [[cli]] и порождённых доменных событий, — а не из самоотчёта агента [P0-Q3]. `SKILL_COMPLETED` untrusted ([[adapters]] §3) и сам по себе obligation не закрывает: он засчитывается только при наличии соответствующих доменных эффектов. Иначе агент оценивал бы собственное соблюдение и мог бы отчитаться о работе, которой не было. Нет данных в окне → `no-data`, не 0.
- **Informal Online Competence** (OPEN-13): отдельный 0–100 профиль по informal LexicalItems/навыкам; **не двигает CEFR напрямую**. Informal production через `contribution_scope` даёт компонент writing/transfer с dedup/cap.
- **MUST**: агрегаты — производные проекции; не влияют обратно на per-target Mastery (нет циклов).

## 6. LexicalMasteryProfile (OPEN-13)

- **MUST — разрешение по трём осям** [P0-3]: у каждого LexicalItem versioned `LexicalMasteryProfile`; lookup **тотален** по кортежу `(type, transparency, usage_policy)` ([[../product/lexical-system]] §1a). Прежний lookup по `type`/`usage_policy` не учитывал ось прозрачности и оставлял mastery непрозрачных единиц неопределённой.
- **MUST — precedence: ограничение сильнее разрешения** [P0-3]: `recognition` требуется всегда. `controlled_production` попадает в required, **только если разрешают обе** оси — и `transparency`, и `usage_policy`. Конфликт разрешается в сторону запрета, а не разрешения.

| | `usage_policy` разрешает production (`safe_to_use`, разрешённый `context_dependent`) | `usage_policy` запрещает (`recognition_only`, `avoid`, `obsolete`) |
|---|---|---|
| `transparent` | recognition + controlled_production | только recognition |
| `semi_opaque` | recognition → затем controlled_production | только recognition |
| `opaque` | **только recognition** (production не required никогда) | только recognition |

Ключевая клетка — `opaque` + `safe_to_use`: производить идиому безопасно, но требовать этого нельзя. Понимать `call it a day` обязательно, употреблять — нет; обратное требование наказывало бы ученика за то, что он выражается проще.

- **MUST — роль оси `type`** [R-Q1]: таблица выше задаёт **required dimensions** по `(transparency, usage_policy)`; `type` их не переопределяет, а управляет **пост-обработкой**: для `lexeme` состояние агрегируется из required forms, для остальных типов агрегации нет. Порядок разрешения: `(transparency, usage_policy) → required dimensions → type-специфичная агрегация`. Именно в этом смысле кортеж тотален; отдельных строк на каждый `type` нет и не требуется.
- **MUST**: production, не попавший в required, не «застревает» — единица достигает MASTERED по своим required dimensions.
- **MUST**: lexeme агрегирует состояние из required forms детерминированно.

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
- **events consumed**: `EVIDENCE_ADDED`, `REVIEW_OUTCOME`; `REVIEW_ASSIGNMENT_CANCELLED` — terminal no-op, переход состояния и дельты не вычисляются.
- **consumed by**: scheduler (Retrievability/состояния), lessons (манифест), memory (проекция), learner (агрегаты).

## 10. Открытые вопросы

Контракт **закрывает** OPEN-1 (формула-shape), OPEN-8 (coverage/confidence/уровень), OPEN-10 (таблица), OPEN-12 (шкалы/ledger), OPEN-13 (informal/lexical profile) на уровне модели. Остаётся **калибровка** *tunable*-констант (thresholds, cap'ы, факторы Stability) — итеративно на реальном обучении, versioned; не меняет доменную модель.

## История изменений

- **2026-07-21**: `REVIEW_ASSIGNMENT_CANCELLED` закреплён как terminal no-op, не ReviewOutcome.
- **2026-07-20 (3)**: 0.4-rereview — core_skill_map перечисляет все четыре dimension включая `transfer` (R-3); `schema_version` отделён от scoring policy, значения принадлежат теме (R-6); Learning Score опирается на `measured_working_level` + `no-data` (R-7); STATE_TRANSITION pin-ит scoring policy и связан causation с триггером (R-1).
- **2026-07-20 (2)**: 0.4-review триаж — добавлена **`Topic.mastery_criteria` schema** (§3b, BLOCKER 0.4-1); AT_RISK применяется из replayable-события, не clock (§3, BLOCKER 0.4-2); таблица переходов тотальна (NEW×RECOVERED, 0.4-6); core-skill map (§4, 0.4-3); origin+placement-cap (§4b, 0.4-4); measured vs provisional level (§4, 0.4-11); точный Decimal-контекст + конкретные дефолты (§2, 0.4-8); XP award-schema и Tutor Compliance measurement (§5/§7, 0.4-9).
- **2026-07-20**: создан (контракт 0.4, часть 2). Две оси Mastery/Stability-Retrievability [PD-2026-07-20]; таблица переходов; целые CEFR-bands; Learning Score; Tutor Compliance/Informal; LexicalMasteryProfile; XP-ledger; numeric-детерминизм.
