# 2026-07-20 — 0.4 Evidence, Scoring & Review Contract

Провенанс: три спеки `wiki/modules/evidence.md` + `scoring.md` + `scheduler.md` (roadmap 0.4). Concept Gate из трёх развилок, все решены [PD-2026-07-20].

## Решения (3 развилки)

1. **Scoring-модель — две оси.** Mastery 0–100 (качество: аккумулятор по evidence с cap за сессию, веса dimensions, штраф за hints) отдельно от Stability/Retrievability (память: `Retrievability=exp(−elapsed/Stability)`, Stability растёт с успешными повторениями). FSRS — за scheduler-интерфейсом позже. Соответствует брифу («простая формула сначала, FSRS без смены модели»).
2. **CEFR — целые bands A1–C2.** Без подуровней; working level не выше слабейшего core-навыка (правило «полступени» снято, закрывает E-R4). Внутриуровневый прогресс — Learning Score, не уровень.
3. **Learning Score = владение текущим уровнем.** Coverage-взвешенный Mastery тем working-уровня; прогресс-к-следующему — отдельно.

## Что зафиксировано

- **evidence.md**: наблюдения→движок (не готовая классификация); observation ссылается на criterion+span; semantic identity (source_span_hash, item_exposure_id); independence по новому контексту; AttemptAssessment (не терминальна) vs единственный ReviewOutcome; contribution_scope; capture-into-event; trusted-reporter.
- **scoring.md**: две оси с формулами; cap за сессию/rubric-cap/monotonicity; **полная таблица переходов** (state × outcome, закрывает table-часть OPEN-10); целые bands + coverage/confidence (OPEN-8); Learning Score / Tutor Compliance / Informal шкалы (OPEN-12/13); LexicalMasteryProfile; XP-ledger award-once; numeric — fixed-precision decimal (OPEN-20 numeric-часть).
- **scheduler.md**: интервалы 1…180 за интерфейсом под FSRS; review_status; re-entry trigger + overdue→AT_RISK пороги (OPEN-18); backlog не блокирует; подача due-целей в манифест.

## Закрыто / сужено

- **Закрыты (модель)**: OPEN-1, OPEN-7, OPEN-8, OPEN-12, OPEN-13, OPEN-18. Остаётся **калибровка** *tunable*-констант (cap'ы, пороги, факторы Stability) — итеративно на реальном обучении, versioned, без смены доменной модели (принцип design-direction).
- **Сужены**: OPEN-10 → только Attempt/Session lifecycle machine (0.5); OPEN-20 → kernel encoding/hash (numeric-interface закрыт).

## Замечание к ревью

0.4 — первый контракт с численной моделью и формулами; появился новый класс возможных ошибок (границы монотонности, cap-обходы, детерминизм чисел, полнота таблицы переходов, циклы в агрегатах). Стоит прогнать отдельным ревью до реализации.

## Следующий шаг

П.2 разблокирована по 0.4 (mastery_criteria schema есть) — ждёт только каркас П.1 от Codex. Roadmap next → 0.5 (Lesson Lifecycle, носитель OPEN-10/17). Параллельно: каркас П.1 (Codex), 1.1 tooling.
