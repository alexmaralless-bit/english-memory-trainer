# 2026-07-20 — 0.5 Lesson Lifecycle & Completion (+ assessments)

Провенанс: `wiki/modules/lessons.md` + `wiki/modules/assessments.md` (roadmap 0.5). Concept Gate из трёх развилок, все решены [PD-2026-07-20]. Последний крупный контракт-носитель фазы 0.

## Решения

1. **Stale-сессия — авто-abandon по порогу, событием.** Сессия без активности дольше `stale_session_days` (дефолт 7) терминализуется как ABANDONED через append-only `SESSION_STALE_ABANDONED {boundary_at, last_activity_at, pinned policy}`. Мусор не копится, детерминизм сохранён.
2. **Attempt: три состояния** `draft → recorded → assessed`. Разделение «записано» и «оценено» нужно для recovery после крэша между фиксацией и scoring; в scoring участвует только `assessed`.
3. **Placement: окно resume, затем истечение.** Resume в пределах `placement_resume_window` (дефолт 48 ч); дальше `PLACEMENT_EXPIRED` → ABANDONED. Обоснование: диагностика должна быть связной по времени.

## Проактивно применённый урок ревью

Оба clock-триггера (stale-сессия, истечение placement) сразу сделаны **replayable-событиями** с детерминированным `boundary_at` — тот же паттерн, что `OVERDUE_AT_RISK_TRIGGERED`. Это ровно класс дефекта, который ревью поймало в 0.4 (BLOCKER 0.4-2: historical state зависел от времени запуска replay). Здесь ошибка не повторена.

## Что зафиксировано

- **lessons**: session lifecycle со `STARTED→ABANDONED`; терминальность и стабильные ошибки; Attempt machine + идемпотентный finalize/recover; FINISHED требует пустой pending-set, ABANDONED преобразует pending; **closure trigger** для ReviewAssignment (правило закрытия — в 0.4, триггер — здесь); **uniqueness терминального outcome поверх kernel-CAS**; атомарная терминализация (state+events+outbox одной транзакцией, Obsidian post-commit).
- **assessments**: placement lifecycle с checkpoint/resume/терминальным идемпотентным submit; запрет abandon после SUBMITTED; exposure history + cooldown с **capture-into-event** веса; `origin=placement` и потолок ACTIVE.

## Закрыто

**OPEN-10** (Attempt machine, closure trigger, терминализация), **OPEN-17** (placement lifecycle, exposure/cooldown), бизнес-часть **OPEN-11** (uniqueness). Остаётся калибровка `stale_session_days`, `placement_resume_window`, `form_cooldown_days`.

## Состояние фазы 0

Закрыты 0.1–0.5, 0.8–0.10. Остались **0.6** (Obsidian Vault — нужны решения OPEN-2/3) и **0.7** (CLI + Agent Skills).

## Замечание

0.5 стоит прогнать ревью вместе с 0.4-rereview-правками: контракты сильно связаны (closure trigger ↔ ReviewOutcome, терминализация ↔ scoring/scheduler), и стык — типичное место для дефектов, невидимых внутри одной спеки.
