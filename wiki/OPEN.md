# OPEN — единый реестр нерешённых вопросов

> **Status**: living
> **Last updated**: 2026-07-19

Продуктовые развилки и нерешённые вопросы. Решение принимает человек; принятое решение получает `[PD-YYYY-MM-DD]`, вносится в спеку, строка отсюда уходит в «Решённые». Любой OPEN, упомянутый в спеке, обязан иметь строку здесь. Каждый открытый OPEN указывает контракт-исполнитель, который его закрывает.

OPEN-7…OPEN-18 заведены 2026-07-19 по итогам red-team ревью (первый прогон + rereview): это признанные дыры, механизм которых принадлежит будущим контрактам. Инвариант (что должно выполняться) зафиксирован в спеке; здесь — обязательство контракта достроить механизм. Владельца механизма определяет **owner-матрица** ниже (единый источник, ревью J-R1).

### Owner-матрица (компонент → контракт-владелец)

Каждый механизм принадлежит одному контракту; соседние контракты на него только ссылаются. Platform/kernel не держит бизнес-логику (README).

| Компонент | Владелец |
|---|---|
| Command/event envelopes, idempotency scope, CAS/optimistic revision, Unit of Work, outbox | **0.2 kernel** |
| Evidence admissibility, семантическая идентичность, LearningTarget transition table, lexical scoring/mastery-профиль, agregation форм, XP-ledger, coverage/confidence | **0.4 evidence-scoring** |
| Session + Attempt lifecycle, терминализация, uniqueness терминального outcome на ReviewAssignment | **0.5 lessons** |
| Scheduler-policy: интервалы, re-entry trigger, overdue→AT_RISK порог | **0.4 scheduler** |
| Placement lifecycle, form exposure/cooldown | **assessments** (named artifact в roadmap) |
| Version pinning/replay/deprecation, orphan refs, candidate validate/activate, data provenance/notices | **0.3 curriculum** (+ 0.2 для механики CAS/snapshot) |
| Currency/usage-policy lifecycle, production_eligible, safety-overlay для live manifest, exercise-bank lifecycle | **П.3 policies** (+ 0.4 для scoring-части) |

## Открытые

| ID | Вопрос | Контекст | Блокирует (контракт) |
|---|---|---|---|
| OPEN-1 | Численная scoring-формула и пороги **Mastery/Stability/Retrievability** (только они; агрегаты — в OPEN-8/12/13) | бриф §7 задаёт принципы, формулы нет | 0.4 Evidence, Scoring & Review |
| OPEN-2 | Структура Obsidian vault и политика ручных заметок ученика | vault генерится движком | 0.6 Obsidian Vault |
| OPEN-3 | Способ интеграции с Obsidian: файлы напрямую, CLI или плагин | Obsidian CLI не устанавливался | 0.6 Obsidian Vault |
| OPEN-7 | Целостность evidence: семантическая уникальность (source-span hash, item-exposure), multi-credit/independence, admissibility. **Observation schema** (rereview C-R1): наблюдение ссылается на rubric-criterion и конкретный span/error; machine-checkable часть отделена от subjective, есть consistency-check и реакция на observation, не подтверждённое raw answer | ревью C-2/C-3/C-6/C-7, C-R1 | 0.4 |
| OPEN-8 | CEFR coverage: матрица, мин. темы/dimensions, confidence floor, unknown-as-unknown; confidence-policy; наблюдаемые консервативные рекомендации; формула learner_priority; **ordinal/sublevel-представление уровня и «полступени»** (rereview E-R4) | ревью C-4/E-3/E-7/E-8, E-R4 | 0.4 |
| OPEN-9 | Version pinning и replay: pin **scoring/структуры/rubric** в evidence/session/manifest; активация не ретроактивна; deprecation 1:1/split/merge/retired append-only; бессмертие любого persistent reference. **Safety НЕ пинится** — см. OPEN-14 (rereview G-R1) | ревью G-2/G-3/G-5, G-R1 | 0.3 (+0.2 CAS/snapshot) |
| OPEN-10 | Lifecycle: Attempt state machine + finalize/recover; **AttemptAssessment vs единственный terminal ReviewOutcome и момент закрытия ReviewAssignment** (rereview A-R1); терминализация ABANDONED; crash attempt↔review. Полная LearningTarget transition table — в 0.4 (owner-матрица) | ревью D-2/E-2/G-4/G-6/G-9, A-R1 | 0.5 (+0.4 таблица) |
| OPEN-11 | Idempotency и concurrency: envelope scope, same-key/different-payload, cached response, optimistic revision, correction protocol. Уникальность терминального outcome на ReviewAssignment — бизнес-правило 0.5, kernel даёт CAS | ревью G-7/G-8 | 0.2 kernel |
| OPEN-12 | XP exactly-once ledger; шкалы Learning Score / Tutor Compliance. **Day-attribution streak** (rereview G-R3): immutable `practice_day` из `occurred_at` + snapshot timezone, day dedup, cross-midnight, без ретро-пересчёта при смене зоны | ревью A-6/C-7/E-6, G-R3 | 0.4 |
| OPEN-13 | Informal Online Competence: шкала/dimensions/coverage/cap; `contribution_scope`; dedup; assessable_dimensions по usage_policy. **Generic `LexicalMasteryProfile`** по type/usage_policy для обычных word/chunk (rereview E-R3) | ревью C-5/H-1/H-2, E-R3 | 0.4 |
| OPEN-14 | Currency и usage-policy lifecycle; `context_dependent`; агрегация форм lexeme. **Safety-overlay** (rereview G-R1/H-R1): вычисляемый `production_eligible` из active usage_policy+currency (`obsolete` исключает production); live manifest/review assignment проверяются active safety при доставке, несовместимое отменяется/заменяется append-only event с обеими версиями; `requires_usage_policy` predicate по type/register; `cultural_context` в validator | ревью D-7/D-8/H-3/H-4/H-5/H-6, G-R1/H-R1 | П.3 (+0.4 scoring, +0.5 live delivery) |
| OPEN-15 | Data provenance: `SourceArtifact`, `source_refs`+`transformations` (валидируется, rereview I-R3); **per-source CC BY-SA notices/change-marking/ShareAlike boundary, раздельно CEFR-J A1–B2 и Octanove C1/C2** (rereview I-R1); rights_basis living layer. Первый publish/import блокируется до закрытия | ревью I-2/I-3/I-6, I-R1/I-R3 | 0.3 + П.4 |
| OPEN-16 | Lifecycle банка упражнений: `generated → accepted/rejected`, acceptance criteria, promotion/invalidation, dedup, provenance | ревью E-4 | П.3 |
| OPEN-17 | Placement lifecycle: state machine с **`STARTED|IN_PROGRESS → ABANDONED`, командой `placement abandon`, событиями checkpoint/abandon** (rereview D-R3), incremental/resume/expiry, один терминальный submit; exposure history, cooldown/rotation | ревью G-1/C-6, D-R3 | assessments (+0.5) |
| OPEN-18 | Scheduler-policy: адаптация интервалов; **re-entry trigger — порог длины перерыва + Retrievability** (rereview J-R3); **overdue→AT_RISK порог** (rereview D-R2/D-3) | ревью J-R3, D-R2 | 0.4 scheduler |

## Решённые

| ID | Решение | PD |
|---|---|---|
| — | Обучение как гибкий разговор: prerequisites и гейты рекомендательные, без замков | [PD-2026-07-19], `docs/design-direction.md` §1 |
| — | Охват MVP только текстовые модальности; TOEFL частично (Reading, Writing) | [PD-2026-07-19], `docs/design-direction.md` §3 |
| — | Дев-знание ведётся по wiki-паттернам закрытого проекта в упрощённой форме | [PD-2026-07-19], [[README]] |
| OPEN-4 | Письменная спонтанная речь оценивается rubric-оценкой агента с пониженным весом: evidence сохраняется полностью, вклад в Mastery ограничен, требуется повторяемость между сессиями | [PD-2026-07-19] |
| OPEN-5 | Placement короткий текстовый (~30–40 мин) + rolling уточнение по evidence первых сессий | [PD-2026-07-19] |
| — | Контент-модель гибридная: программа проектируется заранее целиком, упражнения генерятся по policies, удачные — в растущий банк | [PD-2026-07-19], [[roadmap]] фаза П |
| — | Вместо штрафов — re-entry протокол после длительного перерыва, без жёстких гейтов | [PD-2026-07-19] |
| — | XP и streak — лёгкая механика без штрафов и списаний | [PD-2026-07-19], [[product/learning-model]] §8 |
| — | Flow «сессия»: конфликт start решается выбором ученика, finish-postconditions средние, CLI `trainer session` | [PD-2026-07-19], [[flows/session]] |
| — | Flow «continuation»: session notes опциональные (untrusted), tutor briefing одним JSON, без блокировок — событие AGENT_ATTACHED | [PD-2026-07-19], [[flows/continuation]] |
| — | Лексическая система трёхслойная: учебный лексикон, lexeme с формами, личный словарь с не-boolean владением | [PD-2026-07-19], [[product/lexical-system]] |
| — | Flow «placement»: evidence только реально проверенным темам/LexicalItem, отказ возможен, формы фиксированные | [PD-2026-07-19], [[flows/placement]] |
| OPEN-6 | Источники лексикона: CEFR-J + NGSL/NAWL/BSL + wordfreq; CEFR-SP и данные OpenVLT не импортируются. Режим — **build-time/pinned, сырые частотные данные в репо не коммитятся** (ShareAlike минимизирован). Схема notices/provenance — остаётся в OPEN-15 | [PD-2026-07-19], [[modules/curriculum]] §3 |
| — | Программа — can-do граф с 8 треками (включая Informal); концепт Codex одобрен | [PD-2026-07-19], [[modules/curriculum]] |
| — | **Informal→CEFR:** письменное производство в рабочем контексте даёт компонент writing/transfer через `contribution_scope`-тег с dedup и cap; recognition сленга/мемов — никогда не в CEFR (механизм — OPEN-13) | [PD-2026-07-19], [[product/learning-model]] §5 |
| — | **Потолок placement:** никогда не MASTERED; объективно проверенные темы — максимум ACTIVE; writing из одного rubric — provisional (полный уровень — ≥2 независимых items) | [PD-2026-07-19], [[flows/placement]] |
| — | **Режим частотных данных:** build-time/pinned; в репо только отобранный лексикон с source_refs | [PD-2026-07-19], [[modules/curriculum]] §3 |
| — | **День/таймзона:** UTC-хранение + IANA-таймзона ученика; streak — по локальной дате; интервалы — по прошедшему времени (elapsed 24h) | [PD-2026-07-19], [[product/learning-model]] §7–§8 |
| — | **Самооценка при отказе от placement:** хранится отдельно (`self_reported_level`); **scope замещения — per-skill** (перестаёт влиять на конкретный skill после его первого допустимого evidence/confidence floor, provenance сохраняется, rereview A-R3) | [PD-2026-07-19], [[flows/placement]] |
| — | **Safety-overlay (G-R1):** safety (production-eligibility из usage_policy+currency) НЕ пинится — всегда проверяется по active policy при доставке; прошлое evaluation/replay детерминировано по pinned scoring. Ставший `avoid`/`obsolete` item отменяется/заменяется append-only event с обеими версиями (механизм — OPEN-14) | [PD-2026-07-19], [[modules/curriculum]] §5, [[product/lexical-system]] §3b |
| — | **Trust model (C-R3):** для MVP агент — **trusted reporter** raw_answer; допущение зафиксировано, границы — через Tutor Compliance Score; untrusted-захват user-turn на adapter boundary — post-mvp | [PD-2026-07-19], [[product/learning-model]] §3 |

## История изменений

- **2026-07-19 (5)**: rereview триаж — добавлена owner-матрица (J-R1); расширены OPEN-7/8/9/10/12/13/14/15/17, заведён OPEN-18 (scheduler-policy); 3 PD-решения (safety-overlay G-R1, trusted-reporter C-R3, per-skill self-report A-R3).
- **2026-07-19 (4)**: red-team триаж — заведены OPEN-7…17, OPEN-1 сужен, OPEN-6 уточнён, 5 PD-решений.
- **2026-07-19 (3)**: решён OPEN-6 (источники лексикона); зафиксирован can-do концепт программы.
- **2026-07-19 (2)**: решены OPEN-4 и OPEN-5 + контент-модель и re-entry (Concept Gate по 0.1).
- **2026-07-19**: создан; перенесены открытые вопросы из design-direction §6.
