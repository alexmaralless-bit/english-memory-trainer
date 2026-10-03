# Codex handoff — лексикон: метаданные neutral-регистра + advisory-покрытие

Чистый контент-проход по `curriculum/lexicon/**`. Два задания. Дисциплина —
как в maintain-english-curriculum: минимальные точечные правки, после — валидация
и ПОЛНЫЙ прогон инвариантов (не только `tests/curriculum`). Не коммить в чужие
домены; параллельно идут правки в `src/control` и `src/lessons` — их не трогай.

## Контракт (источники истины)

- `wiki/product/lexical-system.md` — §1 (`register`: formal/neutral/casual/slang; типы; `transparency`), §1a, §3/§3b (usage_policy/currency/communities/allowed_contexts — когда какие поля уместны), правило покрытия частотой и advisory-links.
- Отчёт `staging/reviews/2026-07-22-P4c-content-review.md` и лог P.4c: 50 mislabeled `register: slang` переразмечены (42→casual, 8→neutral). **P.4c явно флагнул**, что 8 ставших `neutral` юнитов (`show-up`, `catch-up`, `come-over`, `sleep-in`, `hold-on`, `pull-off`, `bump-into`, `weird`) всё ещё несут informal-only поля (`usage_policy: safe_to_use`/`context_dependent` + `communities` + `neutral_equivalent`), читающиеся странно на нейтральном юните — оставлены на maintain-workflow. Это ты сейчас и закрываешь.

## Задание A — метаданные neutral-регистра

Найди ВСЕ `register: neutral` юниты, несущие поля, несовместимые с нейтральным регистром, и выправь по спеке:

- `neutral_equivalent` на `neutral`-юните бессмысленен (юнит сам нейтрален) → **удалить**.
- `communities` (in-group маркер) не свойственен нейтральной лексике → **удалить** (если юнит реально community-specific, значит регистр не neutral — тогда это находка, доложи, но по умолчанию P.4c уже решил регистр = neutral).
- `usage_policy`: нейтральный повседневный phrasal — `safe_to_use` (production-eligible), не `context_dependent`/`recognition_only`; выстави по спеке §3b (если спека требует конкретного значения для нейтральных production-eligible единиц — используй его).
- Ничего, кроме несовместимых полей, не меняй: `register`, `cefr`, `meaning_ru`, `examples`, `transparency`, `transformations`, `id` — не трогай. Начни с 8 явно флагнутых, но примени проверку ко всем `neutral`-юнитам (вдруг есть ещё).

Если по какому-то юниту правильное значение поля неочевидно из спеки — оставь как есть и вынеси в findings, не угадывай.

## Задание B — advisory-покрытие непривязанной лексики

- Прогони покрытие `_suggested-topic-links.yaml`: найди непривязанные единицы с `curriculum_priority_band ∈ {CORE, HIGH}` (и `type: chunk`) — инвариант `test_chunks_and_priority_items_have_an_advisory_link` требует у них ссылку. Сейчас он зелёный (P.4c привязал 6 HIGH-slang); убедись, что остаётся зелёным, и **привяжи любые оставшиеся/новые CORE/HIGH без ссылки** к РЕАЛЬНЫМ topic id (проверь существование в программе, не выдумывай).
- Для непривязанных единиц band ниже (USEFUL и т.д.): сделай осмысленный проход — привяжи те, у кого есть очевидный релевантный топик; **не выдумывай ссылки** ради числа (пустая ссылка честнее натянутой). В отчёте — сколько было непривязано, сколько привязал, сколько осознанно оставил (с причиной).
- Advisory-ссылки не гейты: CEFR-разброс топик↔единица допустим.

## Границы (строго)

- Трогать ТОЛЬКО `curriculum/lexicon/**` (в первую очередь файлы с neutral-юнитами и `_suggested-topic-links.yaml`).
- НЕ трогать: `src/**`, `tests/**`, `wiki/**`, `curriculum/{topics,tracks,levels,modules,policies}/**`, `staging/**` (кроме чтения), `Irregular Verbs.md`.
- Коммить только свой домен (`curriculum/lexicon/**`) отдельным коммитом на `main`.

## Env (Windows)

- Python из venv: `.\.venv\Scripts\python.exe` (НЕ `python` из PATH).
- pytest с `--basetemp "<tmp>/pytest"`.

## Self-verification (обязательно ОБА набора тестов)

1. `trainer curriculum validate --format json` → `ok: true, errors: []`.
2. `.\.venv\Scripts\python.exe -m pytest tests/curriculum tests/test_lexicon_invariants.py --basetemp "<tmp>/pytest" -q` — зелёно. **Важно: инварианты лексикона живут в `tests/test_lexicon_invariants.py` (корень `tests/`), НЕ под `tests/curriculum/` — scoped-прогон их пропустит.**
3. Отчёт: какие neutral-юниты выправлены и как (какие поля удалены/изменены), покрытие advisory (было/привязал/оставил с причиной), findings, команды и их вывод, что НЕ трогал (границы).

Владелец проведёт независимую приёмку (свой `curriculum validate` + оба набора тестов + проверка, что тронуты только несовместимые поля и реальные topic id) и примет по домену.
