# 2026-07-20 — триаж foundation-review (0.2 kernel)

Провенанс: `staging/reviews/2026-07-19-foundation-review-codex.md` (checkout c9e49c1). 2 BLOCKER (A-1=E-1, один корень), ~13 MAJOR, 2 MINOR, 2 QUESTION. Разделы F-2 (safety precedence), I (глоссарий), K (регрессия триажа), J-2 — ЧИСТО. Регрессия шести спек: **чисто** — предыдущий триаж не внёс новых противоречий.

## Продуктовое решение (BLOCKER)

**Event-store (A-1/E-1) [PD-2026-07-20]:** authoritative event log = append-only **таблица в SQLite**, коммитится с operational state и outbox одной транзакцией (один ресурс → ACID выполним). **JSONL — derived rebuildable export** (аудит, git, чтение человеком, сверка replay), не источник истины. Разрешает противоречие «JSONL authoritative» ↔ «ACID-коммит с SQLite».

## Диспозиция

| ID | Sev | Диспозиция |
|---|---|---|
| A-1/E-1 | BLOCKER | resolved [PD]: SQLite event-таблица authoritative, JSONL export → foundation §2.1; OPEN-19 |
| A-2 | MAJOR | fixed: capture-into-event принцип, exposure-вес в evidence-событии → foundation §2.2 |
| A-3 | MAJOR | fixed: boundary-таблица классифицирует self_reported_level/practice_day/prior_steady_state → §2.2 |
| A-4 | QUESTION | resolved: assignment-snapshot захвачен в outcome-событие → §2.2 |
| B-1 | MAJOR | fixed: `sequence`+tie-break, canonical encoding+hash → foundation §3.3/§5; OPEN-20 |
| B-2 | MAJOR | fixed: outbox message id/dedup/ack/order → §3.7; OPEN-21 |
| C-1 | MAJOR | fixed: compound = две идемпотентные команды + benign recovery → §3.4, session flow |
| C-2 | MAJOR | fixed: generic correction envelope (`corrects_event_id`, reducer idempotent) → §3.6; OPEN-11 |
| C-3 | MAJOR | fixed: namespace задан в 0.2, гранулярность scope открыта — противоречие устранено → §3.4 |
| D-1 | MINOR | fixed: kernel не перечисляет business event types → §4 |
| D-2 | QUESTION | fixed: kernel даёт UoW/CAS для lifecycle-команд, finalize/recover — 0.5 → §9 |
| E-2 | MAJOR | fixed: rebuild protocol (checkpoint/offset, isolate-and-swap) → §3.8; OPEN-21 |
| F-1 | MAJOR | fixed: retention pinned-версий + `PinnedPolicyUnavailable` → §3.6; OPEN-9 |
| G-1 | MAJOR | fixed: multi-aggregate условная запись в одной UoW → §3.5 |
| G-2 | MINOR | fixed: command registry + contract-test coverage → §8 |
| H-1 | MAJOR | fixed: versioned boundary manifest + CI check → §2.2 |
| H-2 | MAJOR | fixed: арх-чеки как machine-readable allowlist/AST, IO только в adapters/kernel → §8 |
| J-1 | MAJOR | fixed: заведены OPEN-19/20/21, расширены OPEN-9/11, owner-матрица kernel |

QUESTION-раздел A-4 и D-2 решены дефолтами (не продуктовые форки). F-2/I/J-2/K — подтверждены чистыми.

## Новое в реестре

- **OPEN-19** event-store atomicity → 0.2/1.2.
- **OPEN-20** determinism-контракт (sequence/encoding/hash + numeric к 0.4) → 0.2/0.4.
- **OPEN-21** outbox delivery + projection rebuild → 0.2/1.2.
- Расширены OPEN-9 (retention/PinnedPolicyUnavailable), OPEN-11 (compound/correction/multi-CAS/scope), owner-матрица (kernel).

## Итог

FAIL снят с 0.2. Корневой BLOCKER был реальным (JSONL-файл вне SQLite-транзакции) — решён стандартным паттерном (event-таблица в SQLite = истина, JSONL = export), JSONL сохранён как артефакт. Остальные MAJOR — инварианты в спеке + OPEN с владельцем. 0.2 остаётся done-with-open (механизм в 1.2/1.3). Регрессия шести спек чистая. Next → 0.4.
