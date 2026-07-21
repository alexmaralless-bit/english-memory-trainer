# Corrective pass 0.12 после подтверждающего ревью

Дата: 2026-07-21  
Основание: `staging/reviews/2026-07-21-control-confirm-codex.md` — FAIL, 3 BLOCKER / 7 MAJOR / 1 MINOR.

## Что изменено

- Введён монотонный `plan_version`: `peek` возвращает токен, каждый успешный `next`/`replan` увеличивает его; гонки `next↔next` и `next↔replan` имеют выводимый CAS-результат.
- `SessionBudget` закреплён как session-level total + план текущей ревизии; `DeliveryLedger` — единственный накопительный факт. Доли проверяются по `presented + planned`, replan получает только остаток.
- Validator дискретной достижимости согласован с неделимыми шагами; overshoot и waiver paths заданы без противоположных predicates.
- Replan закрывает выпавший review через `REVIEW_ASSIGNMENT_CANCELLED`, а finish принимает терминальную диспозицию `ReviewOutcome | CANCELLED`. Scoring и scheduler трактуют cancellation как terminal no-op.
- `record_attempt` имеет единственную сигнатуру с `step_id`; ранее предъявленный шаг остаётся допустим после replan; `origin` выводит движок.
- Сигналы получили session-sequence expiry, точные transformations и протокол `record_signal → explicit replan → probe → attempt`.
- Fairness считает deferral не более одного раза за сессию, использует `ceil` и различает admission/presentation.
- Availability переведена в `sessions_per_week_milli`, integer ppm и детерминированный critical boost с правилами no-data.
- Синхронизированы `control`, `lessons`, `evidence`, `scoring`, `scheduler`, CLI, session-flow, glossary и owner-матрица; исправлены ссылки на разделы.

## Сквозная проверка

1. Первый balanced-сеанс, 30 минут, learned-целей нет: policy проходит validator; integration получает waiver; growth и безусловный free-conversation candidate дают непустой план.
2. `maintenance`, `growth_min = 0`: growth не требуется; choice-floor закрывается безусловным free-conversation candidate; pipeline не пуст.
3. `too_easy`: сигнал сохраняет engine-issued `probe_id`, возвращает `next_action: session.replan`; replan под `plan_version` добавляет probe, attempt ссылается на выданный `step_id`, `control_probe` не даёт отрицательного эффекта.
4. Replan середины занятия: выпавший непредъявленный review получает `REVIEW_ASSIGNMENT_CANCELLED`; scheduler не создаёт retry; cancelled assignment не остаётся pending и не блокирует finish.

## Проверки

- `git diff --check` — без ошибок.
- `pytest -q` — 11 passed; только предупреждение о недоступном `.pytest_cache`.
- `ruff check .` / `ruff format --check .` — не запускались: `ruff` отсутствует в PATH и в доступном Python (`No module named ruff`); Python-код не менялся.
- Поиск устаревших форм: `expected_revision`, `INSUFFICIENT_EVIDENCE(reason=replanned)`, `divergence_window_sessions` — 0 совпадений в нормативных стыках.

## Статус

0.12 остаётся `blocked`. Этот corrective pass не снимает блок: требуется новый независимый подтверждающий ревьювер по OPEN-30.
