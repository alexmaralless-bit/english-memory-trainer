# Roadmap

> **Status**: living
> **Last updated**: 2026-07-19

Единственное место, где живёт «где мы сейчас». Статусы: `planned / next / in-progress / done / done-with-open / blocked`. **`done-with-open`** = спека принята и не FAIL, но несёт остаточные OPEN, которые закрывает контракт-исполнитель (не блокирует зависимые работы, кроме явно указанных). Правится руками при каждом существенном сдвиге. Состав фаз — из `docs/design-direction.md` §5; при конфликте главнее этот файл. Owner-матрица OPEN → контракт — в [[OPEN]].

HTML-версия (пересобирается по запросу из этого файла): <https://claude.ai/code/artifact/b2afa615-2340-417b-8aed-89efceb89bfa>

## Фаза 0 — дизайн-контракты (текущая)

Каждый контракт пишется как спека в вики (концепт → «ок» → пишем, Принцип 6).

| # | Артефакт | Куда ложится | Статус | Зависимости |
|---|---|---|---|---|
| 0.1 | Learning Model Requirements | `wiki/product/learning-model.md` | done | OPEN-4/5 решены; после триажа — остаточные OPEN-1/7/8/10/12/13 → 0.4 |
| 0.2 | Application Foundation Contract (kernel) | `wiki/platform/foundation.md` | done-with-open | event-store: SQLite-таблица authoritative + JSONL export [PD-2026-07-20]; 2 прогона ревью пройдены (PASS-with-findings, все сняты); остаточные OPEN-9/10/11/19/20/21 → 1.2/1.3 |
| 0.3 | Curriculum Contract | `wiki/modules/curriculum.md` | done-with-open | can-do граф, 8 треков; остаточные OPEN-9/14/15 |
| 0.4 | Evidence, Scoring & Review Contract | `wiki/modules/evidence.md` + `scoring.md` + `scheduler.md` | next | после 0.1; носитель OPEN-1/7/8/12/13/18 + таблица переходов и scoring из OPEN-10/14 |
| 0.5 | Lesson Lifecycle & Completion Contract (+ assessments) | `wiki/modules/lessons.md` + `assessments.md` | planned | после 0.1, 0.4; носитель OPEN-10/11(uniqueness)/17. `assessments.md` — named artifact для placement lifecycle |
| 0.6 | Obsidian Vault Contract | `wiki/modules/memory.md` | planned | OPEN-2, OPEN-3 |
| 0.7 | CLI и Agent Skills contracts | `wiki/modules/cli.md` + `adapters.md` | planned | после 0.5 |
| 0.8 | Сквозные flows (сессия, продолжение другим агентом, placement) | `wiki/flows/` | done | session · continuation · placement приняты [PD-2026-07-19] |
| 0.9 | Lexical System Requirements | `wiki/product/lexical-system.md` | done-with-open | дизайн пользователя; остаточные OPEN-13/14/15 |
| 0.10 | Red-team ревью (2 прогона) + триаж | `staging/reviews/` | done | 66 находок + rereview (BLOCKER G-R1 + 21 MAJOR); safety-overlay, owner-матрица, OPEN-7…18; FAIL снят повторно |

## Фаза П — учебная программа (после 0.3, параллельно фазе 1)

Программа проектируется заранее целиком — уроки генерятся агентом по ней, поэтому без спроектированной программы корректная генерация невозможна [PD-2026-07-19]. Упражнения при этом НЕ создаются заранее: банк растёт из сессий (гибридная контент-модель).

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| П.1 | Каркас программы A1–C2: уровни, треки, модули (по can-do концепту из journal) | next | 0.10 done — можно начинать (каркас не зависит от mastery_criteria) |
| П.2 | Программа A1–A2 полностью: темы, цели, критерии, prerequisites, типовые ошибки | planned | после П.1 **и 0.4** (schema mastery_criteria, ревью E-1) |
| П.3 | Policies генерации уроков + lifecycle банка | planned | после П.2; informed by 0.1; **закрывает OPEN-14/OPEN-16** (currency/safety-overlay, exercise-bank) |
| П.4 | Учебный лексикон A1–A2: отбор из CEFR-J + NGSL + wordfreq | planned | после П.1; формат из 0.3; **сначала закрыть OPEN-15** (provenance/CC BY-SA/rights), затем импорт |

## Фаза 1 — kernel и каркас

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 1.1 | Пересоздать .venv на Python 3.12+, pyproject, ruff, pytest | in-progress | — (venv 3.12.10 готов, tooling при scaffold) |
| 1.2 | Kernel по контракту 0.2 (envelopes, Clock/Random, UoW, outbox, policy registry, event log) | planned | 0.2 done; закрывает механизм OPEN-9/10/11 |
| 1.3 | Storage: SQLite + миграции + event log + Unit of Work | planned | 1.2 |

## Фаза 2 — вертикальный срез A1–A2

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 2.1 | Загрузка программы A1–A2 в движок + валидация графа | planned | П.2, 1.3 |
| 2.2 | Сессия end-to-end: start → attempts/evidence → finish | planned | 0.5, П.3, 1.3 |
| 2.3 | Scoring + scheduler + replay | planned | 0.4, 2.2 |
| 2.4 | Obsidian-проекция | planned | 0.6, 2.2 |
| 2.5 | Agent skills + sync для Codex/Claude | planned | 0.7, 2.2 |
| 2.6 | Placement (текстовый) | planned | 0.1, 2.3 |
| 2.7 | Демо: сессия провайдером A → продолжение провайдером B без контекста | planned | 2.2–2.5 |

## За горизонтом (не планируется сейчас)

Listening/speaking модальности · полный TOEFL-симулятор · FSRS вместо базовой формулы · web UI · машинные гейты вики (см. [[README]] §Что не переняли).

## История изменений

- **2026-07-20 (14)**: foundation-rereview — PASS-with-findings, новых BLOCKER нет; 4 MAJOR + 2 MINOR (JSONL lag, boundary-поля, safety-correction, replay-тесты, `sequence`) сняты в тексте. 0.2 подтверждён. Next → 0.4.
- **2026-07-20 (13)**: foundation-review (BLOCKER A-1/E-1 + ~13 MAJOR, регрессия триажа чистая) — event-store переопределён: SQLite-таблица authoritative, JSONL derived export [PD-2026-07-20]; заведены OPEN-19/20/21; FAIL снят с 0.2. Next → 0.4.
- **2026-07-19 (12)**: 0.2 Application Foundation Contract принят (`wiki/platform/foundation.md`) — гибрид event-sourcing + тонкий sqlite3 [PD-2026-07-19]; 0.2 → done-with-open (механизм OPEN-9/10/11 в 1.2/1.3); next → 0.4.
- **2026-07-19 (11)**: rereview-триаж (BLOCKER G-R1 + 21 MAJOR) — safety-overlay «safety не пинится» разрешил единственный BLOCKER; добавлены owner-матрица OPEN→контракт и OPEN-18; расширены OPEN-7…17; определён статус `done-with-open`; П.3 закрывает OPEN-14/16, П.4 сначала OPEN-15; assessments.md добавлен к 0.5. FAIL повторно снят со всех спек.
- **2026-07-19 (10)**: red-team триаж 66 находок (`staging/reviews/`) — 0.10 done, FAIL снят; правки шести спек + перестройка OPEN (OPEN-7…17); 0.3/0.9 → done-with-open; П.2 теперь зависит от 0.4 (schema mastery_criteria); П.1 разблокирована; 0.2 и 0.4 подняты в next (носители отложенных BLOCKER).
- **2026-07-19 (9)**: добавлен гейт 0.10 — red-team ревью шести концептов (промпт в `staging/reviews/`); П.1 ждёт итогов ревью.
- **2026-07-19 (8)**: 0.3 done — Curriculum Contract по одобренному концепту Codex (can-do граф, 8 треков с informal, OPEN-6 закрыт: CEFR-J + NGSL + wordfreq); next → П.1.
- **2026-07-19 (7)**: flow «placement» принят — 0.8 done (все три flows); next → 0.3 Curriculum Contract.
- **2026-07-19 (6)**: 0.9 Lexical System Requirements done (дизайн пользователя); добавлена П.4 — отбор лексикона A1–A2; OPEN-6 (frequency source).
- **2026-07-19 (5)**: flow «continuation» (`wiki/flows/continuation.md`) принят; в 0.8 остался placement.
- **2026-07-19 (4)**: 0.8 in-progress — flow «сессия» (`wiki/flows/session.md`) принят; остались continuation и placement.
- **2026-07-19 (3)**: 0.1 done — спека `wiki/product/learning-model.md` принята; next → 0.8 flows (flow-first).
- **2026-07-19 (2)**: добавлена фаза П — учебная программа проектируется заранее [PD-2026-07-19]; 2.1 переориентирована на загрузку готовой программы; ссылка на HTML-версию.
- **2026-07-19**: создан; фазы 0–2 из design-direction §5 и build-prompt.
