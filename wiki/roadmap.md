# Roadmap

> **Status**: living
> **Last updated**: 2026-07-19

Единственное место, где живёт «где мы сейчас». Статусы: `planned / next / in-progress / done / blocked`. Правится руками при каждом существенном сдвиге. Состав фаз — из `docs/design-direction.md` §5; при конфликте главнее этот файл.

## Фаза 0 — дизайн-контракты (текущая)

Каждый контракт пишется как спека в вики (концепт → «ок» → пишем, Принцип 6).

| # | Артефакт | Куда ложится | Статус | Зависимости |
|---|---|---|---|---|
| 0.1 | Learning Model Requirements | `wiki/product/learning-model.md` | next | OPEN-4, OPEN-5 решаются по ходу |
| 0.2 | Application Foundation Contract (kernel) | `wiki/platform/foundation.md` | planned | informed by 0.1 |
| 0.3 | Curriculum Contract | `wiki/modules/curriculum.md` | planned | после 0.1 |
| 0.4 | Evidence, Scoring & Review Contract | `wiki/modules/evidence.md` + `scoring.md` + `scheduler.md` | planned | после 0.1; OPEN-1 |
| 0.5 | Lesson Lifecycle & Completion Contract | `wiki/modules/lessons.md` | planned | после 0.1, 0.4 |
| 0.6 | Obsidian Vault Contract | `wiki/modules/memory.md` | planned | OPEN-2, OPEN-3 |
| 0.7 | CLI и Agent Skills contracts | `wiki/modules/cli.md` + `adapters.md` | planned | после 0.5 |
| 0.8 | Сквозные flows (сессия, продолжение другим агентом, placement) | `wiki/flows/` | planned | пишутся до/вместе со спеками модулей (Принцип 5) |

## Фаза 1 — kernel и каркас

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 1.1 | Пересоздать .venv на Python 3.12+, pyproject, ruff, pytest | planned | — |
| 1.2 | Kernel по контракту 0.2 | planned | 0.2 done |
| 1.3 | Storage: SQLite + миграции + event log + Unit of Work | planned | 1.2 |

## Фаза 2 — вертикальный срез A1–A2

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 2.1 | Curriculum A1–A2 наполнение + валидация | planned | 0.3, 1.3 |
| 2.2 | Сессия end-to-end: start → attempts/evidence → finish | planned | 0.5, 1.3 |
| 2.3 | Scoring + scheduler + replay | planned | 0.4, 2.2 |
| 2.4 | Obsidian-проекция | planned | 0.6, 2.2 |
| 2.5 | Agent skills + sync для Codex/Claude | planned | 0.7, 2.2 |
| 2.6 | Placement (текстовый) | planned | 0.1, 2.3 |
| 2.7 | Демо: сессия провайдером A → продолжение провайдером B без контекста | planned | 2.2–2.5 |

## За горизонтом (не планируется сейчас)

Listening/speaking модальности · полный TOEFL-симулятор · FSRS вместо базовой формулы · web UI · машинные гейты вики (см. [[README]] §Что не переняли).

## История изменений

- **2026-07-19**: создан; фазы 0–2 из design-direction §5 и build-prompt.
