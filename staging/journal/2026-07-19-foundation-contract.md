# 2026-07-19 — 0.2 Application Foundation Contract (kernel)

Провенанс: контракт `wiki/platform/foundation.md` (roadmap 0.2). Concept Gate из двух архитектурных развилок, обе решены [PD-2026-07-19].

## Решения

1. **Источник истины — гибрид.** Learning-состояние (evidence, review outcomes, scores, XP-ledger, knowledge state) — event-sourced: append-only DomainEvents = истина, `scoring replay` воссоздаёт его точно; SQLite — rebuildable read-model. Операционное состояние (сессии, Attempt-lifecycle, очереди, exposure) — SQLite-authoritative. Obsidian — post-commit проекция. Соответствует требованию «replay должен работать» без полного event-sourcing везде (build-prompt §15). Projection boundary задокументирована честно.
2. **Storage-стек — тонкий `sqlite3`.** За интерфейсами Repository/UnitOfWork; forward-only мигратор; без ORM; FK/WAL/integrity check; замена движка возможна за интерфейсом. SQLAlchemy+Alembic отклонены как избыточные для локального single-user файла.

## Что зафиксировано в контракте

Kernel-компоненты (design-direction §4 + инварианты ревью): типизированные ID; injected Clock/RandomSource (прямой доступ к часам/random запрещён — архитектурный чек); Command/DomainEvent envelopes (correlation/causation/idempotency/pinned_versions/payload_hash); идемпотентность (OPEN-11: same-key/different-payload, cached response); optimistic CAS по revision (OPEN-11; uniqueness-правило — 0.5, не kernel); versioned policy registry + pinning (OPEN-9) с **safety-overlay hook** (kernel даёт pinned-резолв для replay и active-резолв для доставки + correction-события; правило «safety не пинится» — П.3/0.4/0.5); Unit of Work; transactional outbox (проекции post-commit, E-R1); projection framework + rebuild; JSONL event log append-only; архитектурные чеки (import-boundary, no-direct-clock, ацикличность platform).

Owner-граница соблюдена: kernel = механизм, бизнес-правила — в модулях (README, rereview J-R1).

## Остаточное

OPEN-9/10/11 — инварианты в спеке, механизм достраивается в реализации (1.2 kernel / 1.3 storage). 0.2 → done-with-open.

## Следующий шаг

Roadmap 0.4 — Evidence, Scoring & Review Contract (носитель OPEN-1/7/8/12/13/18 + таблица переходов и lexical scoring). Опираться на kernel-примитивы 0.2. Это разблокирует П.2.
