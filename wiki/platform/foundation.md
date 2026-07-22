# Platform: Application Foundation (kernel)

> **Status**: current
> **Last updated**: 2026-07-22
> **Sources**: `docs/design-direction.md` §4 (kernel-состав) · build-prompt §15 · [[../product/learning-model]] · review triage journals · foundation-review (`staging/reviews/2026-07-19-foundation-review-codex.md`) · Concept Gate [PD-2026-07-19], event-store [PD-2026-07-20]
> **Роль**: технический фундамент, строится **до** бизнес-модулей. Определяет примитивы, на которых работают curriculum/evidence/scoring/scheduler/lessons/… . Kernel не содержит бизнес-логики (README): он даёт механизмы, правила живут в модулях (owner-матрица — [[../OPEN]]).

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — [[../glossary]].

---

## 1. Назначение

Kernel даёт детерминизм, аудит и целостность, без которых честный учёт невозможен: типизированные идентификаторы, управляемое время и случайность, конверты команд/событий, идемпотентность и optimistic concurrency, versioned policy registry с pinning, Unit of Work, transactional outbox, projection framework, JSONL event log. Всё состояние меняется только через эти примитивы.

## 2. Источник истины — гибрид [PD-2026-07-19]

Два класса состояния с разной моделью хранения (projection boundary зафиксирована честно, build-prompt §15):

| Класс | Модель истины | Хранилище |
|---|---|---|
| **Learning-состояние**: evidence, review outcomes, scores (Mastery/Stability/Retrievability), XP-ledger, `practice_day` | **event-sourced** — append-only DomainEvents = источник истины | **SQLite event-table** (authoritative); JSONL — derived export |
| **Операционное**: сессии, Attempt-lifecycle, review-очереди, exposure-очередь/cooldown, черновики | **SQLite-authoritative** | SQLite (события пишутся для аудита, не источник истины) |
| **Проекции для человека**: Obsidian-вольт, SQLite read-models learning-части | derived, rebuildable | обновляются post-commit через outbox |

### 2.1 Event store — единый транзакционный носитель [PD-2026-07-20, ревью A-1/E-1]

- **MUST**: authoritative event log — **append-only таблица событий в SQLite**. Она коммитится в **той же** транзакции, что operational state и outbox-записи — один ресурс, ACID выполним.
- **MUST**: **JSONL — derived, rebuildable export** event-таблицы (для аудита, git, чтения человеком, сверки replay), **не** источник истины. Экспорт идемпотентен и полностью пересоздаётся из event-таблицы.
- **MUST — lag ≠ ошибка** [rereview E-1]: JSONL-export отстаёт от commit'а по контракту (post-commit через outbox, at-least-once). `database check` сверяет JSONL только **до acknowledged export offset / high-water mark**; отставание за offset — это `pending`/outbox-health, **не** integrity-error. Ошибка — только divergence *после* catch-up либо невалидный content/hash. Recovery: догон export'а из event-таблицы по offset.
- **MUST**: файловые проекции (Obsidian, JSONL-export) — **только post-commit** через outbox (rereview E-R1); их сбой не откатывает authoritative commit.

### 2.2 Projection/truth boundary (нормативно) [ревью A-2/A-3/A-4/H-1]

- **MUST — capture-into-event**: любое operational (не-replayable) значение, влияющее на event-sourced scoring, **фиксируется как факт в самом событии** в момент решения (с версией policy), а не читается из operational store при replay. Иначе потеря/восстановление operational state изменит результат replay.
- **MUST**: ведётся versioned **boundary manifest** (aggregate/поле → truth class → canonical event/state → rebuildable? → snapshot?) с CI-проверкой, что каждая persisted-модель зарегистрирована. Минимальная классификация ключевых полей:

| Поле / агрегат | Truth class | Rebuildable / snapshot |
|---|---|---|
| evidence, review outcome, scores, XP-ledger, `practice_day` | event-sourced | rebuildable из event-таблицы |
| `exposure_decision`/вес, применённый к placement-evidence | **захвачен в evidence-событие** (не из очереди) | rebuildable |
| `prior_steady_state` | **явное поле проекции**, детерминированно материализуемое из событий (rereview A-1) | rebuildable |
| `self_reported_level` (provisional, per-skill) | operational; не влияет на scoring, но **влияет на provisional working estimate / briefing / рекомендации** (rereview A-1) | snapshot + recovery |
| ReviewAssignment (queue) | operational; **минимальный snapshot assignment захвачен в outcome-событие** | queue snapshot; outcome rebuildable |
| exposure-очередь/cooldown (не-scoring) | operational | snapshot |

## 3. Компоненты kernel

### 3.1 Типизированные идентификаторы
- **MUST**: доменные ID — типизированные (`TopicId`, `SessionId`, `AttemptId`, `EvidenceId`, `ReviewId`…), не голые строки; генерация сортируемая по времени (ULID-подобная) через injected источник.

### 3.2 Clock и RandomSource
- **MUST**: время и случайность **только** через инъектируемые `Clock` и `RandomSource`; прямой доступ к системным часам/`random` в доменном коде запрещён (архитектурный чек §8). Всё время — UTC-инстанты; локальная дата вычисляется из таймзоны ученика ([[../product/learning-model]] §7–§8).
- **MUST**: детерминированные seeds для placement и любой генерации, воспроизводимые в тестах (fixed-clock).

### 3.3 Command и Event envelopes
- **MUST**: каждая мутация — `Command` в конверте; каждый факт — `DomainEvent` в конверте. Поля конверта: **всегда** — `id`, `type`, `occurred_at` (UTC), `actor`/`provider`, `correlation_id`, `causation_id`, `pinned_versions` (§3.6), `payload_hash`; **условные** (применимость — следующий пункт) — `sequence` (монотонный, §5; только у события, присваивается на append) и `idempotency_key` (§3.4; только у мутирующей команды).
- **MUST — применимость полей** [ревью 1.2-1]: `sequence` есть **только у `DomainEvent`** и присваивается event-store'ом **на append** (до append — не определён/`null`); `Command` порядка не несёт. `idempotency_key` обязателен **только для мутирующих команд** (§3.4); события и read-команды могут его не иметь. `occurred_at` — timezone-aware и **нормализуется в UTC** при построении конверта (эквивалентные инстанты с разным offset дают один canonical-байтовый вид, §5). `payload_hash` перепроверяется на authoritative-границе (event-store) перед записью: payload, мутированный после хэширования, отвергается.
- **MUST — детерминированный порядок и хэш** [ревью B-1]: event-таблица имеет монотонный `sequence` — canonical total order (tie-breaker для равных `occurred_at`); replay применяет события строго по `sequence`. `payload_hash` считается по фиксированному SHA-256 от canonical JSON: сортированные ключи, NFC для строк/ключей, запрет float и коллизий ключей после нормализации. Числовые правила scoring — pinned scoring policy 0.4. Реализация и subprocess replay закрыли OPEN-20.
- **MUST**: event-таблица append-only; перезапись/удаление запрещены (deprecation/коррекции — только новыми append-only событиями, §3.6).

### 3.4 Идемпотентность и compound-команды
- **MUST — cached/error ветки [PD-2026-07-22]**: повтор с тем же global local-store `idempotency_key` и тем же request hash возвращает **прежний результат** до stale/CAS-проверок; тот же ключ с другим payload — стабильная ошибка. Cached schema canonical; retention бессрочный вместе с authoritative state личного инструмента.
- **MUST — key namespace**: ключ глобален внутри одного локального store/единственного learner. Callers используют command-qualified значения; collision между командами не переисполняет эффект, а даёт conflict.
- **MUST — compound-команда** [ревью C-1]: `session start --abandon-active` разложен на **две независимые идемпотентные команды** (`session abandon`, затем `session start`), не одну атомарную. Recovery определён и benign: crash между ними оставляет старую сессию `ABANDONED` и **нет** активной; следующий `start` создаёт новую. Атомарный compound-envelope в контракт **не входит**: одиночные идемпотентные команды поверх UoW покрывают потребность; появится реальная нужда — это новый вопрос в [[../OPEN]], а не молчаливое обещание.

### 3.5 Optimistic concurrency (CAS)
- **MUST**: изменяемые агрегаты имеют `revision`; запись — compare-and-set; конкурентная запись с устаревшей ревизией отклоняется стабильной ошибкой.
- **MUST — multi-aggregate условная запись** [ревью G-1]: одна UoW может атомарно проверить ожидаемые ревизии **нескольких** агрегатов (Session, ReviewAssignment, Attempt/queue, XP) и записать all-or-nothing; частичный success невозможен, stale-revision сообщается явно. Это механизм; бизнес-правило «уникальный терминальный outcome на ReviewAssignment» и выбор границ агрегатов — 0.5 (rereview J-R1).

### 3.6 Versioned policy registry, pinning, correction-события
- **MUST — OPEN-9**: реестр версионируемых policy (`curriculum`, `scoring`, `scheduler`, `control`, `generation`, `rubric`, `assessments`, `lessons`, `evidence`, `obligations`, `tunables`). Каждая версия — иммутабельный snapshot, адресуемый по id; применимые версии пинятся в boundary manifest и разрешаются без fallback.
- **MUST**: команды/сессии/evidence **pin-ят** версии, под которыми созданы. Replay и resume резолвят policy по pinned-версии, не по current active. Активация не ретроактивна.
- **MUST — retention pinned snapshots** [ревью F-1]: все версии/snapshots/tombstones, на которые есть pinned-ссылка, хранятся иммутабельно и не удаляются (retention ≠ immutability). Если версия не резолвится — hard error `PinnedPolicyUnavailable` (не тихий фолбэк на active/alias); recovery/export — [[../OPEN]] OPEN-9.
- **MUST — safety-overlay hook** [PD-2026-07-19]: kernel даёт и pinned-резолв (replay/оценка), и **active-резолв** (`production_eligible` при доставке) + correction-события. Правило «safety не пинится» — П.3/0.4/0.5 ([[../modules/curriculum]] §5).
- **MUST — generic correction envelope** [ревью C-2]: correction — событие с `corrects_event_id`, семантикой (replacement/compensation), позицией в `sequence` и idempotency. Reducer идемпотентен под цепочками corrections; replay **не** засчитывает и исходный, и исправленный эффект. Generic envelope/reducer реализованы в kernel; конкретная бизнес-семантика принадлежит 0.4/0.5.
- **MUST — safety-correction хранит обе версии** [rereview C-1]: для safety-overlay отмены/замены (§3.6 active-резолв) correction-событие несёт `original_pinned_versions` и `active_safety_version` — чтобы audit/replay объяснял, по какой active safety-policy и вместо какого pinned-decision выполнена отмена. Это сохраняет инвариант «с обеими версиями» ([[../modules/curriculum]] §5). Правило eligibility остаётся у П.3/0.4/0.5.

### 3.7 Unit of Work и transactional outbox
- **MUST**: Unit of Work — атомарный commit event-таблицы + operational state + outbox одной SQLite-транзакцией.
- **MUST — семантика доставки outbox** [ревью B-2]: каждая outbox-запись неразделима со своим event и имеет `sequence`; per-consumer offset читается и advances в одной `BEGIN IMMEDIATE` транзакции с effect. Доставка идёт строго по outbox-join sequence; сбой откатывает текущий effect/offset, уже завершённые события не повторяются. OPEN-21 закрыт реализацией.

### 3.8 Projection framework и rebuild
- **MUST**: read-models learning-части rebuildable из event-таблицы детерминированно по `sequence`.
- **MUST — протокол rebuild** [ревью E-2]: у проекции есть applied-offset/checkpoint; rebuild — isolate-and-swap (пересбор в отдельный view до high-water mark, атомарная замена), applied-offset фиксируется атомарно с consumer-state; поздняя outbox-доставка во время rebuild не смешивает старое и новое. Реализация закрыла OPEN-21.
- **MUST**: `memory check`/drift-детект — расхождение проекции с authoritative state завершается ошибкой ([[../modules/memory]], 0.6).

### 3.9 Storage-интерфейсы
- **MUST**: storage за интерфейсами `Repository` и `UnitOfWork`; доменный код не знает про конкретный движок.
- **MUST [PD-2026-07-19]**: реализация — стандартный `sqlite3` (тонкий слой) + простой forward-only мигратор; без ORM. FK включены, integrity check, WAL. Замена движка возможна за интерфейсом только при отдельной реальной потребности; PostgreSQL не реализуется.
- **MUST**: `-wal`/`-shm` не коммитятся; snapshot — только после checkpoint SQLite; generated Markdown сохраняется рядом со snapshot.

## 4. DomainEvent — kernel определяет только конверт

Kernel определяет **конверт** (§3.3), append/replay и correction-механику. **Конкретные типы событий kernel не перечисляет** — каждый принадлежит своему модулю-владельцу (owner-матрица в [[../OPEN]]); примеры типов даются в спеках модулей, не здесь (ревью D-1).

## 5. Детерминизм и replay

- **MUST**: одинаковые события + pinned policy-версии ⇒ одинаковое learning-состояние (byte-идентичность по значимым полям), при применении строго по `sequence` (§3.3), canonical encoding и детерминированных числовых правилах scoring (0.4).
- **MUST**: `scoring replay` пересобирает scores из event-таблицы; результат сверяется с проекцией (расхождение = ошибка).
- **MUST — replay-тесты** (rereview B-1, два разных теста):
  1. **order-independence чтения**: при неизменных event payload + `sequence` replay инвариантен к физическому storage/query order (перестановка строк/выборки не меняет результат);
  2. **детерминированный append-order**: concurrent/equal-`occurred_at` append получает детерминированный total order (`sequence` с tie-break), и этот **записанный** order воспроизводится при replay.
- **MUST**: fixed-clock; разные process hash-seed не меняют исход; crash-recovery (до/после commit event-store, до/после JSONL-export; дубль/переупорядочивание outbox не теряют и не дублируют данные).

## 6. CLI-поверхность (kernel-facing)

| Команда | Что делает |
|---|---|
| `trainer doctor` | диагностика окружения/схемы; первый шаг при проблемах |
| `trainer database check` | integrity: FK, схема, соответствие event-таблица ↔ проекции ↔ JSONL-export |
| `trainer scoring replay` | детерминированный пересбор scores из событий + сверка |
| `trainer snapshot create` | snapshot после checkpoint (SQLite + generated Markdown) |

Agent-facing вывод — JSON в stdout, диагностика в stderr, стабильные exit codes.

## 7. Границы

- **depends on**: только стандартная библиотека + pydantic (валидация конвертов); бизнес-модулей не знает.
- **consumed by**: все модули (curriculum, evidence, scoring, scheduler, lessons, learner, memory, audit, assessments, adapters, cli).
- **events**: определяет конверт и хранилище; типы — у модулей.

## 8. Архитектурные инварианты (CI-gate)

Чеки задаются как **machine-readable правила**, не проза (rereview H-2): декларативный layer/dependency allowlist (директории → разрешённые импорты) + AST/lint-правила (import-linter-подобные). Инструмент и точный список — 1.2, но контракт фиксирует, что́ проверяется и где исключения:

- **MUST**: модули взаимодействуют только через публичные API и события; прямой импорт внутренностей чужого модуля запрещён.
- **MUST**: доменный код не обращается к системным часам/random напрямую — только через Clock/RandomSource. **IO/persistence разрешён только в adapters и kernel** (единственные слои-исключения; доменный код IO не делает).
- **MUST**: platform/kernel не импортирует бизнес-модули (ацикличность).
- **MUST — command registry** [ревью G-2]: каждый published mutation-endpoint регистрируется с классом idempotency/CAS/UoW; contract-test доказывает покрытие (включая `curriculum activate`, placement checkpoint/abandon, XP award, не только attempt/review/finish).

## 9. Открытые вопросы

Единственный остаточный kernel/curriculum вопрос:

- **OPEN-9**: схема pinning/snapshot + **retention pinned-версий**, `PinnedPolicyUnavailable`, deprecation `1:1/split/merge/retired`, alias/migration.

## История изменений

- **2026-07-22 (3)**: kernel 1.2 завершил OPEN-11/19/20/21: global idempotency+cached precedence, structural event/outbox atomicity, canonical NFC/SHA-256/sequence replay, ordered outbox и crash-safe JSONL/projection rebuild. Остался только OPEN-9 retention/deprecation mapping.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). compound-envelope изъят из контракта (уклончивое обещание).
- **2026-07-20 (2)**: foundation-rereview (PASS-with-findings) — JSONL lag ≠ integrity error, сверка до high-water mark (E-1); `prior_steady_state` явное поле проекции, `self_reported_level` влияет на working estimate/рекомендации (A-1); safety-correction хранит обе версии (C-1); replay-тесты разделены на order-independence + детерминированный append-order (B-1); cached-schema/retention «зафиксировать в 1.2» (H-1); `sequence` в глоссарий (I-1).
- **2026-07-20**: foundation-review триаж — **event store: SQLite event-таблица authoritative, JSONL derived export** [PD-2026-07-20] (A-1/E-1 BLOCKER); capture-into-event и boundary-manifest (A-2/A-3/A-4/H-1); `sequence`/canonical encoding/hash (B-1); outbox delivery + rebuild protocol (B-2/E-2); compound-команда как две идемпотентные (C-1); generic correction envelope (C-2); idempotency scope — противоречие устранено (C-3); pinned retention + `PinnedPolicyUnavailable` (F-1); multi-aggregate CAS (G-1); command registry (G-2); CI-gate арх-чеков (H-2); kernel не перечисляет business-типы (D-1); lifecycle-wording (D-2). Заведены OPEN-19/20/21.
- **2026-07-19**: создан (roadmap 0.2). Гибрид event-sourcing и тонкий sqlite3-слой — [PD-2026-07-19]. Kernel как механизм-носитель с owner-границей.
