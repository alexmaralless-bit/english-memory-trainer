# Модуль: scoring

> **Status**: current
> **Last updated**: 2026-09-23
> **Sources**: [[../product/learning-model]] · [[evidence]] · [[assessments]] §3 · Concept Gate 0.4 2026-07-20 (3 развилки, [PD-2026-07-20]) · review triage journals (OPEN-1/8/10/12/13/20) · реальные placement-формы `staging/handoff/2026-09-22-placement-forms-spec.md` ([PD-2026-09-22]) · `staging/concepts/2026-09-23-lesson-brief-report-concept.md` (одобрен, [PD-2026-09-23]) · часть контракта 0.4
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
- **MUST — rubric/informal cap**: вклад rubric- и informal-evidence в Mastery ограничен `rubric_cap` (*tunable*); повышение состояния по ним требует ≥2 независимых сессий ([[evidence]] §4.1). Любой open response, оценённый через rubric profile, остаётся `assessment_basis: rubric` и под cap, даже если все его criterion checks machine-checkable.
- **MUST — tutor-verdict quality, без rubric cap** [PD-2026-09-23, PD-F]: evidence с `assessment_basis: tutor_verdict` ([[evidence]] §4.2) масштабирует дельту тем же способом, что rubric — `quality = Decimal(score_ppm) / Decimal(1000000)` по закреплённой `evidence@2.verdict_scale` — но **не** попадает под `rubric_cap` (явная ветка `scoring/engine.py::fold_scores`, наравне с `objective_check`). Канал сознательно оставлен без дополнительного дисконта: добросовестность вердикта тьютора проверяется постфактум аудитом (`audit-english-tutor`), не движковым cap'ом. Обычный `session_cap` применяется как и ко всем остальным каналам.
- **MUST — graduated rubric quality [П.5, PD-2 B]**: engine-computed `AttemptAssessment.score_ppm` — integer `0..1000000`, полученный из четырёхуровневых criteria по pinned `rubric@1`: `ROUND_HALF_EVEN(sum(weight_units × level_ppm) / sum(weight_units))`. Положительная дельта rubric-evidence умножается на `Decimal(score_ppm) / Decimal(1000000)` до session/rubric caps. Boolean `correct`, если сохраняется для совместимости, вычисляет движок и он не заменяет graded quality.
- **MUST — error severity [П.5, PD-4 C]**: severity принадлежит rubric policy и ограничивает level ровно одного score-bearing criterion; глобального второго штрафа за тот же error-span нет. Нулевая quality не даёт положительной дельты; отрицательная Mastery по-прежнему возникает только из подтверждённого REGRESSION.
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
- **MUST — canonical transition producer [PD-2026-07-22]**: каждое scoring-pinned `review.outcome` и `review.overdue_at_risk` получает ровно один причинно связанный `scoring.state_transition` в той же UoW, включая no-op (`from_state == to_state`). Детерминированный event id выводится из source id. Поэтому отсутствие transition означает неполноту, а не «состояние не изменилось». `trainer scoring transitions backfill` восстанавливает legacy-пробелы строго в source-sequence и идемпотентен; coverage обязана стать полной.
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

- **MUST — владение значениями** [rereview R-6; П.5]: конкретные значения (`active_threshold`, `retention_*`) **принадлежат теме** и живут в pinned `CurriculumVersion`; scoring policy их только *интерпретирует* (не переопределяет). `rubric@1` вычисляет качество одного open response (`score_ppm`) и также не задаёт/не переопределяет required dimensions, mastery thresholds, retention или state transitions. `schema_version` версионирует форму, а не policy. Апгрейд scoring/rubric policy **не** меняет ретроспективно пороги старых тем — retrospective drift исключён.
- **MUST**: `mastery_criteria` задаёт структуру и связь с transition table (§3). Отсутствие критерия на required dimension = ошибка валидации. Эта schema — то, что делает П.2 authoring-возможным (roadmap).
- **MUST — relation к table**: `LEARNING → ACTIVE` при выполнении `per_dimension.active_threshold` + `independent_attempts` по всем required; `ACTIVE → MASTERED` при `mastered.*`.

### 3c. `LexicalMasteryProfile` — см. §6.

### 3d. `automaticity@1` — ось автоматизма [PD-2026-09-22]

Отдельный policy kind и отдельный reducer. Ось введена как **независимая** ([[../product/learning-model]] §4a, PD-A) именно для того, чтобы не трогать §2–§3: тотальная таблица переходов, формула Mastery и модель Stability/Retrievability остаются побайтово прежними, а старое evidence при replay даёт те же значения, что и раньше.

- **MUST — отдельный policy kind**: `automaticity@1` регистрируется в реестре политик kernel наравне с `scoring@1`/`scheduler@1` и пинится в Session Manifest. Значения `scoring@1` он не переопределяет и ими не переопределяется.
- **MUST — `AutomaticityState` per target**: reducer выдаёт на каждый LearningTarget `{state, blocks_observed, sessions_observed, accuracy_ppm, median_latency_ms?, baseline_latency_ms?, confirmations, last_updated_at}`, где `state ∈ {not_measured, deliberate, proceduralized, automatic}`.
- **MUST — входы закрыты**: только (а) точность дрилл-блока — доля `objective_correct` per-item наблюдений блока ([[evidence]] §4.6), (б) per-item `latency_ms`, (в) `response_latency_ms` timed- и spontaneous-форм. Никакие другие факты ось не двигают; предъявление, объяснение и самооценка — не входы.
- **MUST — латентность в brief/report протоколе не поступает** [PD-2026-09-23, PD-E]: схема `lesson_report@1` не несёт `latency_ms`/`response_latency_ms` ни на item'е, ни на item'е дрилл-блока ([[evidence]] §4.6) — каждое evidence чат-занятия несёт `response_latency_ms: null`. Для этого канала ось честно сворачивает **только точность**: `not_measured → deliberate → proceduralized` остаются достижимы из точности дрилл-блока, а `proceduralized → automatic` — **недостижим**, пока латентность не начнёт поступать из другого канала. Синтетическое значение не подставляется.
- **MUST — базовая latency ученика**: `baseline_latency_ms` = медиана per-item latency по целям, уже находящимся в состоянии `ACTIVE` или выше, за последние `baseline_window_sessions` сессий. Если измерений в окне нет, базы нет, и переход в `automatic` невозможен — состояние остаётся `proceduralized`, а не выводится из абсолютного порога.
- **MUST — переходы**:

  | Из | В | Условие |
  |---|---|---|
  | `not_measured` | `deliberate` | зафиксирован первый дрилл-блок по цели |
  | `deliberate` | `proceduralized` | `accuracy_ppm ≥ proceduralized_accuracy_ppm` по ≥ `min_blocks` блокам |
  | `proceduralized` | `automatic` | дополнительно `accuracy_ppm ≥ automatic_accuracy_ppm`, медианная latency ≤ `latency_factor × baseline_latency_ms` по блокам из ≥ `min_sessions` сессий **и** ≥ 1 подтверждение в spontaneous- или timed-форме вне дрилла |
  | `proceduralized` \| `automatic` | `proceduralized` | неуспешный блок (`accuracy_ppm < proceduralized_accuracy_ppm`) |
  | любое | то же | нет новых допустимых входов (no-op) |

  Таблица тотальна: пара «состояние × наблюдение» без строки — no-op, не ошибка. Ниже `deliberate` ось не опускается: однажды измеренная скорость не становится неизмеренной.
- **MUST — конкретные авторские дефолты `automaticity@1`** (не диапазоны, как и во всех исполнимых policy):

```yaml
automaticity_policy:
  version: 1
  proceduralized_accuracy_ppm: 900000
  automatic_accuracy_ppm: 950000
  min_blocks: 3
  min_sessions: 2
  latency_factor: "1.5"          # decimal-строка, не YAML-float
  baseline_window_sessions: 10
```

- **MUST — ось ничего не меняет за своими пределами**: `AutomaticityState` **не** влияет на Mastery, Stability, Retrievability, knowledge state, review status, рабочий CEFR-уровень, Learning Score и XP. Она — вход для планирования ([[control]]) и предъявления ученику, не для оценки знания. Обратных связей нет: ось не попадает в формулы §2 ни прямо, ни через агрегаты.
- **MUST — детерминизм по общим правилам §2.1**: точность — целые ppm, `latency_factor` — `Decimal` из строки в том же фиксированном контексте (precision 28, `ROUND_HALF_EVEN`); медиана — lower median; YAML-float в decision-bearing полях отвергается при активации. Порядок свёртки канонический — по `sequence`, затем `target_id`.
- **MUST — replay покрывает ось**: `trainer scoring replay` пересобирает `AutomaticityState` из тех же событий по pinned `automaticity@1` и сверяет с сохранённым; расхождение — ошибка replay наравне с расхождением Mastery.
- **MUST — видно ученику**: `trainer status --format json` отдаёт `automaticity` отдельным блоком, не смешивая с Mastery и knowledge state. Иначе честный ответ на вопрос «это уже на автомате?» опирался бы на число, которое отвечает на другой вопрос.
- Численные пороги — **авторские дефолты без калибровки**: они исполнимы, но данными не проверены → [[../OPEN]] OPEN-37. Реализацию не блокируют.

## 4. Рабочий CEFR-уровень — целые bands (OPEN-8) [PD-2026-07-20]

- **MUST**: уровни только целые (`A1…C2`), без подуровней. Per-skill CEFR = наивысший band, где выполнено **coverage**: ≥ `min_topics` независимых тем band'а в состоянии ACTIVE+ по required dimensions, ширина dimensions, confidence ≥ `confidence_floor` (все *tunable*). Непроверенная область — **unknown**, не поднимает уровень.
- **MUST — core-skill map** [ревью 0.4-3, rereview R-3]: Track ≠ core skill; вклад задаётся **versioned `core_skill_map`** (часть scoring policy) по `(track, dimension)` с весами и cap. Правило перечисляет **все четыре machine-ID dimension** явно (никакого обобщённого «production»):
  | track | recognition | controlled_production | spontaneous_production | transfer |
  |---|---|---|---|---|
  | `grammar-engine` | Grammar | Grammar | Grammar | Grammar (w<1) |
  | `vocabulary-chunks`, `word-formation` | Vocabulary | Vocabulary | Vocabulary | Vocabulary (w<1) |
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

### 4c. `scoring@2` — раздел `placement`: измеренный уровень из диагностики [PD-2026-09-22]

- **MUST — новый именованный раздел policy**: `scoring@2` вводит раздел `placement` (сосуществует с `scoring@1`, который остаётся pinned-resolvable для старых сессий/replay без изменения поведения — активация не ретроактивна, [[curriculum]] §5). Раздел вычисляет `measured_working_level.<skill>` из objective-items одного placement: наивысший band, для которого **≥ floor этого навыка** **различных** тем band'а имеют **все свои** placement-items правильными. Тема с хотя бы одним неверным item в coverage band'а не засчитывается — правило измеряет надёжность покрытия, а не долю правильных ответов.
- **MUST — floor задаётся по каждому навыку** [PD-2026-09-22]: `placement.min_topics_by_skill` — **тотальная** карта `core skill → положительное целое` по всем core-навыкам, **кроме writing** (у него floor'а нет вовсе, см. ниже); *tunable*, значения `scoring@2`: `grammar: 5`, `vocabulary: 4`, `reading: 3`. Одна общая цифра невозможна: форма тратит свои 40–60 минут на навыки по-разному — grammar-band это 5–8 однотемных items, vocabulary-band 4–5 лексических единиц, reading-band 3 вопроса к одному тексту ([[assessments]] §3), — поэтому при общем floor'е 5 reading был бы структурно неизмерим, а vocabulary упирался бы в потолок B2 при полностью правильном C1-разделе. Floor — это покрытие, которое раздел band'а реально даёт, и не ниже того, что делает band надёжным. Навык без floor'а объективным правилом не измеряется никогда.
- **MUST — confidence и `basis`**: результат правила пишется с `confidence: low` и `basis: placement` ([[../glossary]] `basis`) — placement это одноразовое измерение, не накопленный evidence. Session-evidence затем повышает confidence обычным rolling-правилом **отдельно по каждому навыку** и одновременно переключает его `basis` на `evidence` по мере накопления ([[../product/learning-model]] §5, [[../flows/placement]]).
- **MUST — правило не подменяет таблицу переходов**: темы, проверенные placement-items, проходят обычные правила knowledge state §3 (единственный правильный item → `LEARNING`; ceiling `ACTIVE`, §4b выше). Раздел `placement` только формулирует, как из уже посчитанных per-topic состояний собрать per-skill level специально для контекста диагностики — он не вводит отдельную таблицу переходов и не создаёт нового knowledge state.
- **MUST — writing вне правила**: rubric-assessment письма placement ([[assessments]] §3) не участвует в правиле выше (оно про objective items); полный writing CEFR-band по-прежнему требует ≥2 независимых non-placement items (§4b) — единичный rubric-фрагмент placement даёт только provisional вклад.
- **MUST — provisional writing-уровень из placement** [PD-2026-09-22]: `placement.writing` задаёт `provisional_threshold_ppm` (целое `0…1 000 000`, `scoring@2`: `700000`) и `confidence` (`very_low`). Уровень = **наивысший band среди writing-items этого placement, чей rubric-`score_ppm` ≥ порога**; он пишется как `provisional_working_estimate.writing` с `confidence: very_low`, `basis: placement`, `provisional: true` и **никогда** не попадает в `measured_working_level` (там writing остаётся unknown до ≥2 независимых non-placement items, §4b). Ни один writing-item не дотянул до порога → не пишется ничего: честный unknown, а не band «поменьше». Порог отделяет «фрагмент оценён» от «фрагмент показывает band»: settled-фрагмент с одним положительным finding'ом на критерий даёт ~616 667 ppm и о band'е ещё не говорит.
- **MUST — provisional-оценка потребляет placement**: `provisional_working_estimate` собирается по правилу «measured где есть, иначе provisional» (§4, measured vs provisional) и берёт per-skill сначала измеренный уровень, затем provisional writing-band placement, затем `self_reported_level`; каждая заимствованная строка помечена `provisional` и своим `basis`. Иначе ученик, только что сдавший placement, не получал бы вообще никакой стартовой оценки: writing (unknown по контракту) держал бы общий уровень unknown.
- **MUST**: `trainer status` отдаёт по каждому core skill `level`, `confidence`, `basis` и `provisional`, а также отдельное поле `provisional_working_estimate` (§8); briefing/continuation ([[../flows/placement]]) читает те же поля, не собственную оценку агента.

## 5. Агрегаты (OPEN-12/13)

- **Learning Score** [PD-2026-07-20, rereview R-7]: coverage-взвешенный средний Mastery тем **`measured_working_level`** (именно измеренного, §4 — не provisional/self-report), 0–100. Если `measured_working_level` = unknown (нет допустимого evidence) → Learning Score = `no-data`, не 0. Прогресс-к-следующему — отдельно в roadmap-progress-проекции.
- **Tutor Compliance Score** [ревью 0.4-9]: 0–100, `honored_obligations / total_obligations` за **measurement window** (*tunable*, дефолт последние 10 сессий). **Obligations registry** (versioned, теперь `obligations@4` [PD-2026-09-23]): required-skill вызван нужной версии (`required_skill_effect`); сессия стартовала с явным `lesson_profile` (`lesson_preflight`); отчёт закрыл сессию (`report_committed`); каждое назначенное повторение получило терминальную диспозицию (`reviews_addressed`); нет forbidden actions (`forbidden_action_absence`). Каждое obligation вычисляется из **наблюдаемых движком** эффектов — вызовов [[cli]] и порождённых доменных событий, — а не из самоотчёта агента [P0-Q3]. `SKILL_COMPLETED` untrusted ([[adapters]] §3) и сам по себе obligation не закрывает: он засчитывается только при наличии соответствующих доменных эффектов. Нет данных в окне → `no-data`, не 0.
- **MUST — обязательства brief/report протокола описывают результат, а не последовательность вызовов** [PD-2026-09-23]: `obligations@4` заменяет `delivery_protocol`/`correction_protocol` (пошаговый порядок событий) двумя исход-ориентированными обязательствами: `report_committed` — `lesson.reported` появился раньше `session.finished` этой сессии; `reviews_addressed` — ни одно подобранное сессией ReviewAssignment (операционный SQLite-снимок, не event-sourced) не осталось без `review.outcome` или причинного `INSUFFICIENT_EVIDENCE`. Тьютор больше не классифицирует ответ сам себе — это разворот прежнего правила: правильность решает **он**, [[evidence]] §4.2 — обязательство `forbidden_action_absence` этого не запрещает, а следит только за формальными нарушениями протокола (`MISSING_IDEMPOTENCY_KEY`). Сессии, закреплённые под `obligations@1`/`@2`/`@3`, разрешаются прежним оценщиком без изменений ([[audit]] §4).
- **MUST — точное окно Tutor Compliance [PD-2026-07-22]**: `obligations@4` сохраняет последние `10` полностью наблюдаемых терминальных сессий (`measurement_window_terminal_sessions`). Неполная telemetry исключает сессию и при отсутствии eligible history даёт `no-data`. Audit только коррелирует obligation observations; численный fold и integer `floor(100 * honored / total)` принадлежат scoring. Метрика не влияет на learner scores/XP.
- **Informal Online Competence** (OPEN-13): отдельный 0–100 профиль по informal LexicalItems/навыкам; **не двигает CEFR напрямую**. Informal production через `contribution_scope` даёт компонент writing/transfer с dedup/cap.
- **MUST**: агрегаты — производные проекции; не влияют обратно на per-target Mastery (нет циклов).

## 6. LexicalMasteryProfile (OPEN-13)

- **MUST — разрешение по effective safety profile** [P0-3; П.3 PD-2026-07-21]: у каждого LexicalItem versioned `LexicalMasteryProfile`; lookup **тотален** по кортежу `(type, transparency, effective_usage_policy)`, где `effective_usage_policy` выводится из active usage_policy + active currency + context. Прежний lookup по `type`/`usage_policy` не учитывал ось прозрачности и оставлял mastery непрозрачных единиц неопределённой.
- **MUST — precedence: ограничение сильнее разрешения** [P0-3; PD-4 A]: `recognition` требуется всегда. `controlled_production` попадает в required, **только если разрешают все** оси — transparency, usage_policy, currency и context. `dated` — recognition-only по умолчанию; `obsolete`, `avoid`, `recognition_only`, `opaque` как required production и `context_dependent` вне allowed context запрещают production. Конфликт разрешается в сторону запрета, а не разрешения.

| | effective safety разрешает production (`safe_to_use`, разрешённый `context_dependent`, `currency: current`) | effective safety запрещает (`recognition_only`, `avoid`, `dated`, `obsolete`, запрещённый контекст) |
|---|---|---|
| `transparent` | recognition + controlled_production | только recognition |
| `semi_opaque` | recognition → затем controlled_production | только recognition |
| `opaque` | **только recognition** (production не required никогда) | только recognition |

Ключевая клетка — `opaque` + `safe_to_use`: производить идиому безопасно, но требовать этого нельзя. Понимать `call it a day` обязательно, употреблять — нет; обратное требование наказывало бы ученика за то, что он выражается проще.

- **MUST — роль оси `type`** [R-Q1]: таблица выше задаёт **required dimensions** по `(transparency, usage_policy)`; `type` их не переопределяет, а управляет **пост-обработкой**: для `lexeme` состояние агрегируется из required forms, для остальных типов агрегации нет. Порядок разрешения: `(transparency, usage_policy) → required dimensions → type-специфичная агрегация`. Именно в этом смысле кортеж тотален; отдельных строк на каждый `type` нет и не требуется.
- **MUST**: production, не попавший в required, не «застревает» — единица достигает MASTERED по своим required dimensions.
- **MUST**: lexeme агрегирует состояние из required forms детерминированно. Evidence сгенерированных упражнений фиксирует тестируемый `form_slot` (`base`, `past`, `participle` или policy-объявленный слот); scoring потребляет form-slot evidence, а не текст prompt'а — replay остаётся детерминированным.

## 7. XP-ledger (OPEN-12)

- **MUST — award schema** [ревью 0.4-9]: XP-award — immutable событие `{source_id, award_kind, practice_day, amount}`. `source_id` уникален; **award-once** независимо от replay. **Awardable source event types** (закрытый список): finalized attempt, closed review, completed re-entry block — **mutually exclusive eligibility** (один source event даёт награду ровно одного kind, не двойной зачёт через категории). `amount` = base(kind) × multipliers(independence, difficulty) — все *tunable* policy-значения.
- **MUST — cap/dedup order**: daily cap по ключу `(learner, practice_day)`; при превышении лишнее не начисляется (порядок применения детерминирован по `sequence`). Streak по локальному `practice_day` ([[../product/learning-model]] §8), day-dedup из kernel (OPEN-12/foundation).
- **MUST**: ABANDONED eligibility — начисляется за уже зафиксированные finalized-источники брошенной сессии, но не за незакрытые цели. **Штрафов и списаний нет**.

## 8. CLI-поверхность

| Команда | Что делает |
|---|---|
| `trainer scoring replay` | детерминированный пересбор всех scores **и `AutomaticityState`** из событий + сверка (kernel §5) |
| `trainer status --format json` | текущее состояние: уровни (`level`, `confidence`, `basis`, `provisional` по каждому core skill, §4c) [PD-2026-09-22], `measured_working_level` и отдельное `provisional_working_estimate` (§4c) [PD-2026-09-22], Mastery-сводка, Learning Score, XP, отдельный блок `automaticity` (§3d) [PD-2026-09-22] |

## 9. Границы

- **depends on**: evidence (факты), curriculum (targets/dimensions/profiles/pinned policy), kernel (детерминизм/numeric).
- **events published**: `SCORES_UPDATED`, `STATE_TRANSITION`, `LEVEL_UPDATED`, `XP_AWARDED`, `AUTOMATICITY_UPDATED` (§3d) [PD-2026-09-22].
- **events consumed**: `EVIDENCE_ADDED`, `REVIEW_OUTCOME`; `REVIEW_ASSIGNMENT_CANCELLED` — terminal no-op (недостижим новым протоколом, остаётся для replay старых сессий), переход состояния и дельты не вычисляются.
- **consumed by**: scheduler (Retrievability/состояния), lessons (манифест), memory (проекция), learner (агрегаты).

## 10. Открытые вопросы

- **OPEN-37**: калибровка порогов и `latency_factor` policy `automaticity@1` (§3d); авторские дефолты исполнимы и реализацию не блокируют.
- **OPEN-39**: калибровка правила `scoring@2.placement` (§4c) — `min_topics` для placement-coverage и валидация сложности items против результатов реальных прохождений; после первых реальных placements.

Контракт **закрывает** OPEN-1 (формула-shape), OPEN-8 (coverage/confidence/уровень), OPEN-10 (таблица), OPEN-12 (шкалы/ledger), OPEN-13 (informal/lexical profile) на уровне модели. Остаётся **калибровка** *tunable*-констант (thresholds, cap'ы, факторы Stability) — итеративно на реальном обучении, versioned; не меняет доменную модель.

## История изменений

- **2026-09-23**: [PD-2026-09-23] переход на протокол «задание → отчёт»: §2.1 — явная ветка `tutor_verdict` в `fold_scores` (`quality = score_ppm/1e6`, session cap, без `rubric_cap`, PD-F); §3d — латентность не поступает из чат-занятий, `proceduralized → automatic` честно недостижим этим каналом (PD-E); §5 — Tutor Compliance читает `obligations@4` (`report_committed`, `reviews_addressed`, `lesson_preflight`, `required_skill_effect`, `forbidden_action_absence`) вместо `delivery_protocol`/`correction_protocol`; старые сессии разрешаются прежними версиями обязательств без изменений ([[audit]] §4).
- **2026-09-22 (4)**: [PD-2026-09-22] §4c уточнён по форме реальных форм — floor'ы стали **per-skill** (`min_topics_by_skill`: grammar 5, vocabulary 4, reading 3; writing без floor'а), добавлено правило **provisional writing-уровня** (`placement.writing.provisional_threshold_ppm` 700000, `confidence: very_low`, флаг `provisional`, вне `measured_working_level`) и сборка `provisional_working_estimate` (measured → provisional writing → self-report). При едином floor'е 5 reading был структурно неизмерим, а общий уровень после placement оставался null.
- **2026-09-22 (3)**: [PD-2026-09-22] реальные placement-формы (Д15) — новый §4c: `scoring@2` раздел `placement` вычисляет per-skill `measured_working_level` из объективных placement-items (наивысший band с ≥ `min_topics` полностью верных тем), пишет `confidence: low`/`basis: placement`; §8 `trainer status` отдаёт `basis` рядом с `confidence`. Заведён **OPEN-39** (калибровка правила).
- **2026-09-22**: [PD-2026-09-22] Tutor Compliance читает `obligations@3`: correction — assessed attempt + закрытие review любым триггером, delivery — rendered-снапшот до попытки ([[audit]]).
- **2026-09-22**: [PD-2026-09-22] добавлен §3d — policy kind `automaticity@1` и reducer `AutomaticityState` (`not_measured → deliberate → proceduralized → automatic`) из точности дрилл-блоков и latency относительно базы ученика; ось не влияет на Mastery/Stability/knowledge state/уровень/XP, покрыта replay и отдаётся `trainer status`. Авторские дефолты зафиксированы; калибровка — OPEN-37.
- **2026-07-22 (5)**: [PD-2026-07-22] канонический `scoring.state_transition` сделан тотальным (включая no-op) с causal id/backfill/coverage; Tutor Compliance закреплён за последними 10 fully-observed terminal sessions по `obligations@1`.
- **2026-07-22**: П.5 применена [PD-2026-07-22] — graduated `score_ppm` как множитель качества (PD-2 B), rubric-basis всегда под cap, policy-owned severity бьёт один criterion (PD-4 C), rubric не переопределяет mastery-владение темы.
- **2026-07-21**: `REVIEW_ASSIGNMENT_CANCELLED` закреплён как terminal no-op, не ReviewOutcome.
- **2026-07-20 (3)**: 0.4-rereview — core_skill_map перечисляет все четыре dimension включая `transfer` (R-3); `schema_version` отделён от scoring policy, значения принадлежат теме (R-6); Learning Score опирается на `measured_working_level` + `no-data` (R-7); STATE_TRANSITION pin-ит scoring policy и связан causation с триггером (R-1).
- **2026-07-20 (2)**: 0.4-review триаж — добавлена **`Topic.mastery_criteria` schema** (§3b, BLOCKER 0.4-1); AT_RISK применяется из replayable-события, не clock (§3, BLOCKER 0.4-2); таблица переходов тотальна (NEW×RECOVERED, 0.4-6); core-skill map (§4, 0.4-3); origin+placement-cap (§4b, 0.4-4); measured vs provisional level (§4, 0.4-11); точный Decimal-контекст + конкретные дефолты (§2, 0.4-8); XP award-schema и Tutor Compliance measurement (§5/§7, 0.4-9).
- **2026-07-20**: создан (контракт 0.4, часть 2). Две оси Mastery/Stability-Retrievability [PD-2026-07-20]; таблица переходов; целые CEFR-bands; Learning Score; Tutor Compliance/Informal; LexicalMasteryProfile; XP-ledger; numeric-детерминизм.
