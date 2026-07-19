# 2026-07-19 — триаж red-team ревью концептов

Провенанс триажа 66 находок из `staging/reviews/2026-07-19-concept-review-codex.md`. Триаж проверен независимым Plan-агентом, план одобрен пользователем (`~/.claude/plans/federated-hugging-sloth.md`). Все решения — `[PD-2026-07-19]`.

## Рамка

Спеки 0.1–0.9 — уровень требований. Три класса ответа: **fix-now** (противоречия/баги), **инвариант + OPEN** (реальная дыра, механизм — в контракте 0.2/0.4/0.5/П.3), **downgrade/reject**. FAIL снимается, когда каждый BLOCKER либо исправлен текстом, либо закрыт несущим MUST + зарегистрированным OPEN.

## Продуктовые решения пользователя (4 развилки)

1. **Informal→CEFR (C-5/H-1):** письменное производство в рабочем контексте → writing/transfer через `contribution_scope`-тег с dedup и cap; recognition сленга/мемов — никогда не в CEFR.
2. **Потолок placement (A-7/D-9):** никогда MASTERED; объективные темы — максимум ACTIVE; writing из одного rubric — provisional.
3. **Режим данных (I-1):** build-time/pinned, сырые частотные датасеты не коммитятся; в репо — отобранный лексикон с source_refs.
4. **День/таймзона (G-10):** UTC + IANA-таймзона; streak по локальной дате; интервалы по elapsed 24h.

## Дефолты (без отдельного вопроса)

- **A-2:** самооценка при отказе от placement → `self_reported_level` отдельно, provisional; измеренный CEFR требует evidence.
- **I-5:** ложное «wordfreq даёт Reddit/Twitter presence» исправлено (агрегированный score, snapshot ~2021); источник informal-currency → OPEN-14.
- **I-6:** living layer хранит короткую единицу + свой парафраз, без сторонних excerpts, до rights_basis (OPEN-15).

## Downgrade / reject

- **E-4** MAJOR→SHOULD (банк best-effort; lifecycle → П.3/OPEN-16).
- **E-5** partial: enforcement активации оставлен; attestation-протокол отклонён (осознанный отказ от gate-машинерии, [[../../wiki/README]]).
- **E-9** MAJOR→SHOULD («~30–40 мин» на высоте target допустимо).
- **G-8** severity понижен (lease post-mvp — принятый PD); дешёвый инвариант (optimistic revision) добавлен.

## Новые OPEN (носители отложенных механизмов)

OPEN-7 anti-gaming→0.4/0.2 · OPEN-8 coverage/confidence→0.4 · OPEN-9 pinning/replay/deprecation→0.2/0.3 · OPEN-10 lifecycle/terminalization→0.5/0.2 · OPEN-11 idempotency/concurrency→0.2 · OPEN-12 XP-ledger/шкалы→0.4 · OPEN-13 Informal-профиль→0.4 · OPEN-14 currency/usage-policy lifecycle→curriculum/П.3 · OPEN-15 provenance/notices→0.3/П.4 · OPEN-16 exercise-bank→П.3 · OPEN-17 placement lifecycle→0.5. OPEN-1 сужен до Mastery/Stability/Retrievability (J-3).

## Диспозиция всех 66 находок

| ID | Sev | Диспозиция |
|---|---|---|
| A-1 | BLOCKER | fixed: session — агент передаёт наблюдения, движок вычисляет классификацию |
| A-2 | MAJOR | fixed: learning §5 + placement — `self_reported_level` отдельно |
| A-3 | MAJOR | fixed: OPEN-6 синхронизирован (build-time), двойной статус убран |
| A-4 | MAJOR | fixed: curriculum — единый enum `strong/soft`, hard/soft superseded |
| A-5 | MAJOR | fixed: lexical — `frequency_band` + отдельные volatility/currency |
| A-6 | MAJOR | invariant→OPEN-12 (XP award-once, ABANDONED eligibility) |
| A-7 | QUESTION | resolved Q2 (writing provisional, потолок ACTIVE) |
| B | — | ЧИСТО (замков-безбилетников нет) |
| C-1 | BLOCKER | fixed: session (= A-1) |
| C-2 | BLOCKER | invariant→OPEN-7/10: session — терминализация без обхода |
| C-3 | BLOCKER | invariant→OPEN-7: learning §3 — семантическая идентичность evidence |
| C-4 | BLOCKER | invariant→OPEN-8: learning §5 — CEFR coverage, unknown-as-unknown |
| C-5 | BLOCKER | fixed rule + OPEN-13: contribution_scope, cap/dedup |
| C-6 | MAJOR | invariant→OPEN-17: placement — exposure/cooldown |
| C-7 | MAJOR | invariant→OPEN-12: learning §8 — XP award-once, caps |
| C-8 | MAJOR | fixed: continuation — notes untrusted, trust boundary |
| D-1 | BLOCKER | fixed: learning §4 — restore-on-confirm MASTERED |
| D-2 | MAJOR | invariant→OPEN-10: learning §4 — тотальность переходов |
| D-3 | MAJOR | fixed: learning §4 — knowledge state vs review status слой |
| D-4 | MAJOR | fixed: session — `STARTED → ABANDONED` |
| D-5 | MAJOR | fixed: session — команда `session abandon` |
| D-6 | MAJOR | fixed: glossary + lexical — INTRODUCED = enrollment |
| D-7 | MAJOR | invariant→OPEN-14: lexical §2 — агрегация форм lexeme |
| D-8 | MAJOR | invariant→OPEN-14: lexical §3b — currency lifecycle |
| D-9 | QUESTION | resolved Q2: потолок ACTIVE, никогда MASTERED |
| E-1 | BLOCKER | fixed: mastery_criteria→0.4 schema + roadmap П.2 зависит от 0.4 |
| E-2 | BLOCKER | fixed: session — summary engine-generated, не цикличен |
| E-3 | MAJOR | invariant→OPEN-8: confidence-policy versioned |
| E-4 | MAJOR | downgrade→SHOULD, OPEN-16 |
| E-5 | MAJOR | partial: enforcement оставлен, attestation отклонён |
| E-6 | MAJOR | invariant→OPEN-12: XP exactly-once |
| E-7 | MAJOR | fixed: разделены frequency/curriculum_priority/learner_priority |
| E-8 | MAJOR | invariant→OPEN-8: placement — консервативные рекомендации наблюдаемо |
| E-9 | QUESTION | downgrade→SHOULD |
| F-1 | MAJOR | fixed: glossary — единый XP без штрафов, Season = период |
| F-2 | MAJOR | fixed: glossary — нормативные states + outcomes |
| F-3 | MAJOR | fixed: glossary — machine-ID dimensions отдельно |
| F-4 | MAJOR | fixed: glossary — LearningTarget = Topic \| LexicalItem |
| F-5 | MAJOR | fixed: glossary — ReviewAssignment/Attempt/Summary/Confidence/Working level |
| F-6 | MAJOR | fixed: glossary — corpus_frequency/curriculum_priority/learner_priority |
| F-7 | MAJOR | fixed: lexical/glossary — volatility ≠ currency |
| F-8 | MINOR | fixed: glossary — CurriculumVersion/Level/Module |
| G-1 | BLOCKER | invariant→OPEN-17: placement lifecycle (state machine + resume) добавлен |
| G-2 | BLOCKER | invariant→OPEN-9: curriculum §5 — pinning, не-ретроактивность |
| G-3 | BLOCKER | invariant→OPEN-9: curriculum §5 — deprecation/replay split/merge |
| G-4 | BLOCKER | invariant→OPEN-7/10: session — ABANDONED закрывает pending |
| G-5 | MAJOR | invariant→OPEN-9: curriculum §5 — бессмертие любого reference |
| G-6 | MAJOR | fixed: session — атомарная терминализация FINISHED/ABANDONED |
| G-7 | MAJOR | invariant→OPEN-11: kernel — idempotency semantics |
| G-8 | MAJOR | invariant→OPEN-11: continuation — optimistic revision (severity↓) |
| G-9 | MAJOR | invariant→OPEN-10: session — finalized attempt/recover |
| G-10 | QUESTION | resolved Q4: UTC+IANA, streak локальная дата, интервалы elapsed |
| H-1 | BLOCKER | fixed rule + OPEN-13: Informal Online Competence отдельная шкала |
| H-2 | MAJOR | invariant→OPEN-13: lexical — assessable dimensions по usage_policy |
| H-3 | MAJOR | invariant→OPEN-14: lexical/curriculum — stale-safety банка |
| H-4 | MAJOR | invariant→OPEN-13/14: lexical — context_dependent enforcement |
| H-5 | MAJOR | invariant→OPEN-14: lexical — полная валидация currency provenance |
| H-6 | QUESTION | →OPEN-14: владелец/TTL/reverification мемов |
| I-1 | BLOCKER | resolved Q3: build-time режим |
| I-2 | MAJOR | invariant→OPEN-15: curriculum — CC BY-SA notice boundary |
| I-3 | MAJOR | invariant→OPEN-15: curriculum — SourceArtifact schema |
| I-4 | MINOR | fixed: curriculum — Business Service List (BSL) |
| I-5 | QUESTION | fixed: curriculum — исправлено утверждение wordfreq; currency→OPEN-14 |
| I-6 | QUESTION | default + OPEN-15: rights_basis living layer |
| J-1 | MAJOR | fixed: OPEN.md — реестр синхронизирован |
| J-2 | MAJOR | fixed: OPEN.md — заведены OPEN-7…17 с блокируемыми контрактами |
| J-3 | QUESTION | fixed: OPEN-1 сужен до Mastery/Stability/Retrievability |

## Итог

FAIL снят со всех шести документов: каждый BLOCKER исправлен текстом или закрыт несущим инвариантом + OPEN. Разблокированы: П.1 (каркас программы), контракты 0.2 (kernel) и 0.4 (evidence-scoring) — именно они дописывают механизмы OPEN-7…17. Опционально — второй прогон ревьювера по исправленным спекам.
