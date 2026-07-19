# Platform: Application Foundation (kernel)

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: `docs/design-direction.md` §4 (kernel-состав) · build-prompt §15 · [[../product/learning-model]] · review triage journals (OPEN-9/10/11, owner-матрица) · Concept Gate 2026-07-19 (2 развилки, [PD-2026-07-19])
> **Роль**: технический фундамент, строится **до** бизнес-модулей. Определяет примитивы, на которых работают curriculum/evidence/scoring/scheduler/lessons/… . Kernel не содержит бизнес-логики (README): он даёт механизмы, правила живут в модулях (owner-матрица — [[../OPEN]]).

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — [[../glossary]].

---

## 1. Назначение

Kernel даёт детерминизм, аудит и целостность, без которых честный учёт невозможен: типизированные идентификаторы, управляемое время и случайность, конверты команд/событий, идемпотентность и optimistic concurrency, versioned policy registry с pinning, Unit of Work, transactional outbox, projection framework, JSONL event log. Всё состояние меняется только через эти примитивы.

## 2. Источник истины — гибрид [PD-2026-07-19]

Два класса состояния с разной моделью хранения (projection boundary зафиксирована честно, build-prompt §15):

| Класс | Модель истины | Хранилище |
|---|---|---|
| **Learning-состояние**: evidence, review outcomes, scores (Mastery/Stability/Retrievability), XP-ledger, knowledge state | **event-sourced** — append-only DomainEvents = источник истины | JSONL event log + SQLite как rebuildable read-model |
| **Операционное**: сессии, Attempt-lifecycle, review-очереди, exposure history, черновики | **SQLite-authoritative** | SQLite (события пишутся для аудита, но не источник истины) |
| **Проекции для человека**: Obsidian-вольт | derived, rebuildable | файлы, обновляются post-commit через outbox |

- **MUST**: `scoring replay` детерминированно воссоздаёт всё learning-состояние из event log при тех же policy-версиях (см. §5). Это и есть смысл event-sourcing learning-части.
- **MUST**: одна ACID-транзакция коммитит authoritative state + соответствующие DomainEvents + outbox-записи; файловые проекции — **только post-commit** через outbox (rereview E-R1).
- **MUST**: projection boundary документирована: какие read-models rebuildable из событий, а какие — SQLite-authoritative (не rebuildable, бэкапятся snapshot'ом).

## 3. Компоненты kernel

### 3.1 Типизированные идентификаторы
- **MUST**: доменные ID — типизированные (`TopicId`, `SessionId`, `AttemptId`, `EvidenceId`, `ReviewId`…), не голые строки; генерация сортируемая по времени (ULID-подобная) через injected источник.

### 3.2 Clock и RandomSource
- **MUST**: время и случайность **только** через инъектируемые `Clock` и `RandomSource`; прямой доступ к системным часам/`random` в доменном коде запрещён (архитектурный чек §8). Всё время — UTC-инстанты; локальная дата вычисляется из таймзоны ученика ([[../product/learning-model]] §7–§8).
- **MUST**: детерминированные seeds для placement и любой генерации, воспроизводимые в тестах (fixed-clock).

### 3.3 Command и Event envelopes
- **MUST**: каждая мутация — `Command` в конверте; каждый факт — `DomainEvent` в конверте. Обязательные поля конверта: `id`, `type`, `occurred_at` (UTC), `actor`/`provider`, `correlation_id`, `causation_id`, `idempotency_key`, `pinned_versions` (§3.6), `payload_hash`.
- **MUST**: event log — append-only JSONL; перезапись/удаление запрещены (deprecation/коррекции — только новыми append-only событиями).

### 3.4 Идемпотентность
- **MUST — OPEN-11**: `idempotency_key` имеет определённый scope; повтор с тем же ключом и тем же `payload_hash` возвращает **прежний результат** (cached response), не создаёт нового эффекта; тот же ключ с другим payload — стабильная ошибка. Покрывает attempt/review/finish/placement submit и compound-команды.

### 3.5 Optimistic concurrency (CAS)
- **MUST — OPEN-11**: сессии и другие изменяемые агрегаты имеют `revision`; запись — compare-and-set по ожидаемой ревизии; конкурентная запись с устаревшей ревизией отклоняется стабильной ошибкой. Это механизм; бизнес-правило «уникальный терминальный outcome на ReviewAssignment» строится **поверх** CAS в 0.5, не в kernel (rereview J-R1).

### 3.6 Versioned policy registry и pinning
- **MUST — OPEN-9**: реестр версионируемых policy (curriculum, scoring, scheduler, generation, rubric). Каждая версия — иммутабельный snapshot, адресуемый по id.
- **MUST**: команды/сессии/evidence **pin-ят** версии, под которыми созданы (`pinned_versions` в конверте). Replay и resume резолвят policy по pinned-версии, **не** по current active. Активация новой версии не ретроактивна.
- **MUST — safety-overlay hook** [PD-2026-07-19]: kernel предоставляет и pinned-резолвинг (для replay/оценки), и **active-резолвинг** (для проверки `production_eligible` при доставке) + append-only correction-события с обеими версиями. Само правило «safety не пинится» и что считать eligible — владельцы П.3/0.4/0.5 ([[../modules/curriculum]] §5, [[../OPEN]] OPEN-14); kernel лишь даёт обе точки резолва и correction-события.

### 3.7 Unit of Work и transactional outbox
- **MUST**: Unit of Work — атомарный commit state + events + outbox одной транзакцией.
- **MUST**: transactional outbox — надёжная доставка post-commit эффектов (обновление Obsidian-проекции, внешние проекции) с retry/catch-up и полным rebuild; сбой проекции не откатывает authoritative commit (rereview E-R1).

### 3.8 Projection framework
- **MUST**: read-models learning-части (SQLite-проекции, Obsidian) rebuildable из event log детерминированно; есть команда полного rebuild.
- **MUST**: `memory check`/drift-детект — расхождение проекции с authoritative state завершается ошибкой ([[../modules/memory]], 0.6).

### 3.9 Storage-интерфейсы
- **MUST**: storage за интерфейсами `Repository` и `UnitOfWork`; доменный код не знает про конкретный движок.
- **MUST [PD-2026-07-19]**: реализация MVP — стандартный `sqlite3` (тонкий слой) + простой forward-only мигратор; без ORM. FK включены, integrity check, WAL. Замена движка позже возможна за интерфейсом; PostgreSQL не реализуется.
- **MUST**: `-wal`/`-shm` не коммитятся; snapshot — только после checkpoint SQLite; generated Markdown сохраняется рядом со snapshot.

## 4. DomainEvent — минимальный набор kernel-уровня

Kernel определяет конверт и append/replay; конкретные типы принадлежат модулям. Примеры сквозных: `SKILL_REQUIRED/STARTED/COMPLETED/FAILED`, `AGENT_ATTACHED`, `CURRICULUM_VERSION_ACTIVATED`. Полный перечень — в спеках модулей.

## 5. Детерминизм и replay

- **MUST**: одинаковые события + timestamps + pinned policy-версии ⇒ одинаковое learning-состояние (bit-for-bit по значимым полям).
- **MUST**: `scoring replay` пересобирает scores из event log; результат сверяется с текущей проекцией (расхождение = ошибка).
- **MUST**: тесты fixed-clock, replay и crash-recovery (crash между commit и projection не теряет и не дублирует данные).

## 6. CLI-поверхность (kernel-facing)

| Команда | Что делает |
|---|---|
| `trainer doctor` | диагностика окружения/схемы; первый шаг при проблемах |
| `trainer database check` | integrity: FK, схема, соответствие event log ↔ проекции |
| `trainer scoring replay` | детерминированный пересбор scores из событий + сверка |
| `trainer snapshot create` | snapshot после checkpoint (SQLite + generated Markdown) |

Agent-facing вывод — JSON в stdout, диагностика в stderr, стабильные exit codes.

## 7. Границы

- **depends on**: только стандартная библиотека + pydantic (валидация конвертов); бизнес-модулей не знает.
- **consumed by**: все модули (curriculum, evidence, scoring, scheduler, lessons, learner, memory, audit, assessments, adapters, cli).
- **events**: определяет конверт и хранилище; типы — у модулей.

## 8. Архитектурные инварианты (проверяются автоматически)

- **MUST**: модули взаимодействуют только через публичные API и события; прямой импорт внутренностей чужого модуля запрещён (import-boundary чек в CI).
- **MUST**: доменный код не обращается к системным часам/random/IO напрямую — только через kernel-абстракции (чек).
- **MUST**: platform/kernel не импортирует бизнес-модули (ацикличность).

## 9. Открытые вопросы

Механизмы, чьи детали kernel достраивает (реализация — фаза 1.2/1.3):

- **OPEN-9**: точная схема pinning/snapshot, deprecation `1:1/split/merge/retired`, alias/migration events.
- **OPEN-10**: kernel-часть Attempt/Session lifecycle (finalize/recover, crash между attempt↔review); сами машины — 0.5.
- **OPEN-11**: idempotency scope, same-key/different-payload, CAS/correction protocol.

## История изменений

- **2026-07-19**: создан (roadmap 0.2). Гибрид event-sourcing (learning event-sourced, операционное SQLite-authoritative) и тонкий sqlite3-слой — [PD-2026-07-19]. Kernel как механизм-носитель OPEN-9/10/11 с owner-границей (бизнес-правила — в модулях).
