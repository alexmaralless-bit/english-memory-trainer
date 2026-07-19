# OPEN — единый реестр нерешённых вопросов

> **Status**: living
> **Last updated**: 2026-07-19

Продуктовые развилки и нерешённые вопросы. Решение принимает человек; принятое решение получает `[PD-YYYY-MM-DD]`, вносится в спеку, строка отсюда уходит в «Решённые». Любой OPEN, упомянутый в спеке, обязан иметь строку здесь. Каждый открытый OPEN указывает контракт-исполнитель, который его закрывает.

OPEN-7…OPEN-17 заведены 2026-07-19 по итогам red-team ревью концептов: это признанные дыры, механизм которых принадлежит будущим контрактам. Инвариант (что должно выполняться) уже зафиксирован в соответствующей спеке; здесь — обязательство контракта достроить механизм.

## Открытые

| ID | Вопрос | Контекст | Блокирует (контракт) |
|---|---|---|---|
| OPEN-1 | Численная scoring-формула и пороги **Mastery/Stability/Retrievability** (только они; агрегаты — в OPEN-8/12/13) | бриф §7 задаёт принципы, формулы нет | 0.4 Evidence, Scoring & Review |
| OPEN-2 | Структура Obsidian vault и политика ручных заметок ученика | vault генерится движком | 0.6 Obsidian Vault |
| OPEN-3 | Способ интеграции с Obsidian: файлы напрямую, CLI или плагин | Obsidian CLI не устанавливался | 0.6 Obsidian Vault |
| OPEN-7 | Целостность evidence против накрутки: семантическая уникальность (source-span hash, item-exposure ID), правила multi-credit allocation и independence, admissibility | ревью C-2/C-3/C-6/C-7: один ответ/цитату/упражнение нельзя пере-зачесть | 0.4 + 0.2 kernel |
| OPEN-8 | CEFR coverage: матрица покрытия, мин. число независимых тем/dimensions, confidence floor, unknown-as-unknown; confidence-policy (конец окна «3–5 сессий»); «максимально консервативные» рекомендации наблюдаемо; формула learner_priority | ревью C-4/E-3/E-7/E-8 | 0.4 |
| OPEN-9 | Version pinning и deterministic replay: pin curriculum+scoring+scheduler+generation+rubric в evidence/session/manifest; активация не ретроактивна; deprecation 1:1/split/merge/retired через append-only alias/migration events; бессмертие любого persistent reference (orphan refs) | ревью G-2/G-3/G-5 | 0.2 kernel + 0.3 |
| OPEN-10 | Полнота lifecycle: Attempt state machine + finalize/recover; полная таблица переходов тем `(state, outcome)`; терминализация ABANDONED (закрытие pending целей, re-entry outcome, атомарный пересчёт производных); crash attempt↔review | ревью D-2/E-2/G-4/G-6/G-9 | 0.5 lessons + 0.2 kernel |
| OPEN-11 | Idempotency и concurrency: CommandEnvelope scope, same-key/different-payload, cached response; два агента — optimistic session revision, уникальный терминальный outcome на review-assignment, correction protocol | ревью G-7/G-8 | 0.2 kernel |
| OPEN-12 | XP exactly-once ledger: immutable award-event с уникальным source ID, award-once, caps, eligibility (вкл. ABANDONED); шкалы и определения Learning Score и Tutor Compliance Score | ревью A-6/C-7/E-6, метрики без шкал | 0.4 |
| OPEN-13 | Informal Online Competence: отдельная шкала/dimensions/coverage/cap; `contribution_scope`-тег и component-level evidence; dedup между informal/writing/transfer/CEFR; assessable_dimensions по usage_policy | ревью C-5/H-1/H-2 | 0.4 |
| OPEN-14 | Lexical currency и usage-policy lifecycle: переходы `current→dated→obsolete`, владелец/TTL/reverification, update-event; enforcement `context_dependent` (allowed/disallowed contexts); ре-валидация stale bank/assessment против active policy; агрегация форм lexeme | ревью D-7/D-8/H-3/H-4/H-5/H-6 | curriculum detail + П.3 |
| OPEN-15 | Data provenance и лицензии: схема `SourceArtifact {id, exact_version, url, retrieved_at, sha256, license, attribution, notices}`, `source_refs`+`transformations` на записи, CC BY-SA notice boundary; rights_basis для living layer (excerpts vs парафраз) | ревью I-2/I-3/I-6; режим (build-time) уже выбран | 0.3 detail + П.4 |
| OPEN-16 | Lifecycle банка упражнений: `generated → accepted/rejected`, versioned acceptance criteria, promotion/invalidation, dedup, provenance | ревью E-4 (понижен до SHOULD) | П.3 |
| OPEN-17 | Placement lifecycle: state machine `STARTED→IN_PROGRESS→SUBMITTED→SCORED|ABANDONED`, incremental/checkpoint/resume/expiry, один терминальный submit; exposure history форм, cooldown/rotation, понижение веса повторно увиденных items | ревью G-1/C-6 | 0.5 lessons + assessments |

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
| — | **Самооценка при отказе от placement:** хранится отдельно (`self_reported_level`), даёт только provisional working estimate; измеренный CEFR требует evidence | [PD-2026-07-19], [[flows/placement]] |

## История изменений

- **2026-07-19 (4)**: red-team триаж — заведены OPEN-7…17 (дыры с механизмом в будущих контрактах), OPEN-1 сужен до Mastery/Stability/Retrievability, OPEN-6 уточнён (build-time режим), добавлены 5 PD-решений (Informal→CEFR, потолок placement, режим данных, таймзона, self-assessment).
- **2026-07-19 (3)**: решён OPEN-6 (источники лексикона); зафиксирован can-do концепт программы.
- **2026-07-19 (2)**: решены OPEN-4 и OPEN-5 + контент-модель и re-entry (Concept Gate по 0.1).
- **2026-07-19**: создан; перенесены открытые вопросы из design-direction §6.
