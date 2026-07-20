# 2026-07-20 — триаж ревью 0.4 (Evidence/Scoring/Review)

Провенанс: `staging/reviews/2026-07-20-0.4-review-codex.md` (commit 5da669e). Вердикт **FAIL**: 2 BLOCKER + 9 MAJOR + 1 MINOR + 1 QUESTION. Ключевой инсайт ревью: я смешал «калибровку констант» (законно отложено) с «отсутствующей schema/веткой/событием» (обязано быть определено). Все находки — fix-now, продуктовых форков нет.

## BLOCKER (оба реальны)

- **0.4-1 Topic.mastery_criteria schema** — я заявил П.2 разблокированной «schema есть», но определил только LexicalMasteryProfile, а Topic-criteria — нет. Over-claim. **Fix**: добавлена versioned schema в scoring §3b (per-dimension active_threshold + independent_attempts; mastered: retention_stability_days + confirmations), связана с таблицей переходов. Теперь П.2 действительно возможна.
- **0.4-2 overdue→AT_RISK не replayable** — clock-триггер без события ⇒ replay зависит от wall-clock. **Fix**: scheduler эмитит append-only `OVERDUE_AT_RISK_TRIGGERED {target, boundary_at, pinned policy}` при crossing (idempotent sweep); scoring применяет STATE_TRANSITION из события, replay — из факта, не из времени.

## MAJOR (все исправлены в тексте)

| ID | Fix |
|---|---|
| 0.4-3 core-skill map | versioned `core_skill_map` (track,dimension→Grammar/Vocab/Reading/Writing с весами) — scoring §4 |
| 0.4-4 placement ceiling | immutable `origin` в evidence; placement-origin cap ≤ ACTIVE, rubric-writing provisional — scoring §4b, evidence §4.5 |
| 0.4-5 multi-credit | детерминированный `CreditAllocation[]` в событии; непроверенная observation → `rejected` (единственная ветка) — evidence §4.1 |
| 0.4-6 таблица тотальна | NEW×RECOVERED и все no-op пары определены явно — scoring §3 |
| 0.4-7 scheduler | ветка `INSUFFICIENT_EVIDENCE` (hold+retry); canonical priority tuple со стабильным tie-breaker `target_id` — scheduler §3/§5 |
| 0.4-8 numeric | точный Decimal-контекст (28 цифр, ROUND_HALF_EVEN, Decimal.exp), единый `initial_stability_days=2.0` — scoring §2 |
| 0.4-9 XP/compliance | XP award-schema (source_id, kind, practice_day; mutually-exclusive eligibility; cap/dedup); Tutor Compliance measurement window + obligations registry + no-data — scoring §5/§7 |
| 0.4-10 contribution_scope | cardinality: primary + contributions[] с per-scope cap — evidence §4.4 |
| 0.4-11 self-report | раздельные `measured_working_level` / `provisional_working_estimate`; Learning Score/gating — measured [PD-2026-07-20] — scoring §4 |
| 0.4-12 OPEN/roadmap | схемы определены в спеках (не новые OPEN); П.2 genuinely разблокирована |

## Итог

FAIL снят: оба BLOCKER закрыты определением schema/события, 9 MAJOR — определением структуры (веток/карт/записей). Только численные *значения* остаются tunable (калибровка). Ключевая честная поправка: roadmap-утверждение «mastery_criteria schema есть» было преждевременным на 5da669e — теперь верно. Проверено-ок из ревью подтверждает: observations→движок, AttemptAssessment/ReviewOutcome, safety-overlay, две оси — корректны.

## Замечание

Ценность ревью: первый контракт с численной моделью, и ревьювер точно отделил «отсутствует структура» от «не откалибровано». Стоит прогнать rereview по исправленным спекам до реализации 1.2/2.3.

## Next

0.5 Lesson Lifecycle (OPEN-10/11/17); либо rereview 0.4; либо content-review каркаса перед П.2.
