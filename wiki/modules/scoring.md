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
- **MUST — детерминизм чисел** [OPEN-20]: все вычисления — fixed-precision decimal с документированным rounding (не IEEE float); порядок агрегации канонический.

### 2.2 Stability (дни) и Retrievability (0–1)
- **MUST**: `Retrievability(t) = exp(-elapsed_days / Stability)`, elapsed по реальному времени (UTC, [[../product/learning-model]] §7), не по календарю.
- **MUST**: начальная Stability из первого успешного evidence (*tunable*, дефолт 1–3 дня); успешный review умножает Stability на фактор от outcome-качества и текущей Stability (растёт медленнее у уже стабильных); REGRESSION уменьшает.
- **MUST**: Mastery и Stability обновляются раздельно из одного evidence; scheduler ([[scheduler]]) использует Retrievability для интервалов.

## 3. Knowledge state — полная таблица переходов (OPEN-10)

Оси — [[../glossary]] (enrollment / knowledge_state / review_status). Таблица `(state, ReviewOutcome)`:

| state \ outcome | PROGRESS | CONFIRMED | REGRESSION(подтв.) | RECOVERED | INSUFFICIENT_EVIDENCE |
|---|---|---|---|---|---|
| NEW | LEARNING | LEARNING | NEW | — | NEW |
| LEARNING | LEARNING | ACTIVE¹ | LEARNING | LEARNING | LEARNING |
| ACTIVE | ACTIVE | MASTERED² | LEARNING | ACTIVE | ACTIVE |
| MASTERED | MASTERED | MASTERED | ACTIVE | MASTERED | MASTERED |
| AT_RISK | AT_RISK | prior_steady_state³ | LEARNING | prior_steady_state³ | AT_RISK |

¹ при достижении threshold required dimensions + independence + repeatability. ² при mastery-критериях + retention (Stability ≥ `mastered_stability`, *tunable*). ³ restore-on-confirm в `prior_steady_state` ∈ {ACTIVE, MASTERED}.

- **MUST**: `AT_RISK` вход — только подтверждённый REGRESSION или overdue сверх порога ([[scheduler]], OPEN-18). Review_status (`not_due/due/overdue`) — ось scheduler, не knowledge state.
- **MUST**: переход выполняет только движок; тотальность гарантирована (каждая пара определена, INSUFFICIENT_EVIDENCE — обычно no-op).

## 4. Рабочий CEFR-уровень — целые bands (OPEN-8) [PD-2026-07-20]

- **MUST**: уровни только целые (`A1…C2`), без подуровней. Per-skill (Grammar/Vocabulary/Reading/Writing) CEFR = наивысший band, где выполнено **coverage**: ≥ `min_topics` независимых тем band'а в состоянии ACTIVE+ по required dimensions, ширина dimensions, confidence ≥ `confidence_floor` (все *tunable*). Непроверенная область — **unknown**, не поднимает уровень.
- **MUST**: overall working level = **не выше слабейшего core-навыка** (целый band; правило «полступени» снято, E-R4). Внутриуровневый прогресс отражает Learning Score, не уровень.
- **MUST**: `self_reported_level` (provisional, per-skill) хранится отдельно, замещается измерением по каждому навыку после его первого evidence/confidence floor ([[../product/learning-model]] §5).
- **MUST — confidence**: per-skill confidence (`very_low..high`) растёт по объёму/разбросу evidence; rolling-уточнение первых сессий — versioned policy, не «после 3–5» на глаз.

## 5. Агрегаты (OPEN-12/13)

- **Learning Score** [PD-2026-07-20]: coverage-взвешенный средний Mastery тем **текущего working-уровня**, 0–100 («насколько твёрдо владею тем, где я есть»). Прогресс-к-следующему — отдельно в roadmap-progress-проекции, не здесь.
- **Tutor Compliance Score**: доля соблюдённых обязательств агента за недавние сессии — вызваны ли required skills нужных версий, соблюдён ли correction-протокол, не было ли forbidden actions (агент не выставлял оценки, соблюдены postconditions finish). 0–100.
- **Informal Online Competence** (OPEN-13): отдельный 0–100 профиль по informal LexicalItems/навыкам; **не двигает CEFR напрямую**. Informal production через `contribution_scope` даёт компонент writing/transfer с dedup/cap.
- **MUST**: агрегаты — производные проекции; не влияют обратно на per-target Mastery (нет циклов).

## 6. LexicalMasteryProfile (OPEN-13)

- **MUST**: у каждого LexicalItem versioned `LexicalMasteryProfile` — required dimensions и mastery-критерии по `type`/`usage_policy`: `recognition_only`/`avoid`/`obsolete` → только recognition (production не требуется и не «застревает»); `safe_to_use`/разрешённый `context_dependent` → + production. Lexeme агрегирует состояние из required forms детерминированно.

## 7. XP-ledger (OPEN-12)

- **MUST**: XP — immutable award-events с уникальным `source_id`; award-once независимо от replay. База за практику (выполненные задания, evidence, закрытые повторения, re-entry) + множители за independence/difficulty (*tunable*); daily cap. **Штрафов и списаний нет**; eligibility для ABANDONED определена. Streak — по локальному `practice_day` ([[../product/learning-model]] §8).

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

- **2026-07-20**: создан (контракт 0.4, часть 2). Две оси Mastery/Stability-Retrievability [PD-2026-07-20]; полная таблица переходов; целые CEFR-bands; Learning Score = владение текущим уровнем; Tutor Compliance/Informal шкалы; LexicalMasteryProfile; XP-ledger; numeric-детерминизм. Закрывает OPEN-1/8/10/12/13 (модель), калибровка отдельно.
