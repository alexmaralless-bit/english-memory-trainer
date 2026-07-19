# Flow: placement (стартовая диагностика)

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: [[../product/learning-model]] §6 · [[../product/lexical-system]] · Concept Gate 2026-07-19 (две развилки, [PD-2026-07-19]) · концепт одобрен («ок»)
> **Роль**: спинной сценарий (roadmap 0.8, третий из трёх). Как ученик получает стартовые уровни без листания старых чатов и без фиктивных оценок.

---

## Решения этого flow [PD-2026-07-19]

1. **Evidence только проверенным темам.** Каждый placement-item привязан к теме программы или LexicalItem. Проверенные единицы получают настоящий evidence и стартовые состояния (`INTRODUCED`/`LEARNING`/…); все остальные остаются `NEW`. Предположительной разметки «ниже уровня — значит знает» нет: рекомендации строятся от уровней+confidence, не от фиктивных состояний тем.
2. **Placement рекомендован, отказ возможен.** При onboarding агент настойчиво предлагает placement; при отказе старт с консервативной самооценки, помеченной `very-low-confidence`, и rolling-уточнение полностью берёт оценку на себя. Жёсткого гейта нет.

Унаследовано из [[../product/learning-model]] §6: короткий тест ~30–40 мин; grammar/vocabulary/reading — объективно, writing — короткий фрагмент по rubric с ограниченным вкладом; deterministic seed; минимум две формы; результат `low-confidence` с уточнением за 3–5 сессий; после перерыва — re-entry ([[session]]), не повторный placement; повторный placement — по запросу ученика.

## Правило форм

- **MUST**: placement-формы — фиксированные авторские наборы items в curriculum/assessments (версионируемые), не генерённые на лету. Причина: сравнимость результатов между формами и повторными прохождениями; генерённые items несравнимы и недетерминированы.

## Сценарий

```mermaid
sequenceDiagram
    autonumber
    actor L as Ученик
    participant A as Агент
    participant T as trainer CLI

    Note over A,T: onboarding: профиль создан, уровней нет
    A->>L: предлагает placement (~30–40 мин)
    alt ученик согласен
        A->>T: placement start --format json
        T-->>A: форма (seed, версия): секции grammar · vocabulary · reading · writing
        loop по секциям
            A->>L: предъявляет items как есть (без подсказок и переформулировок)
            L-->>A: ответы
            A->>T: placement submit --input answers.json
        end
        T->>T: объективный скоринг + rubric-оценка writing (кодом фиксируется, агент оценивает по rubric)
        T-->>A: уровни по навыкам + confidence; evidence проверенным темам/LexicalItem; вход в личный словарь по критериям
    else отказ
        A->>T: placement decline --self-assessment A2
        T-->>A: консервативный старт: уровни very-low-confidence
    end
    A->>L: итог: стартовая картина + что уточнится в первых сессиях
    Note over T: первые 3–5 сессий: rolling-уточнение confidence по evidence
```

## Правила сценария

- **MUST**: агент предъявляет items дословно — без подсказок, упрощений и переформулировок; это диагностика, не обучение.
- **MUST**: объективные секции оценивает только код; writing оценивается агентом по versioned rubric, evidence сохраняется полностью, вклад ограничен ([[../product/learning-model]] §3).
- **MUST**: placement-items, проверяющие лексику, создают записи личного словаря по критерию «была целью упражнения» ([[../product/lexical-system]] §3).
- **MUST**: отказ от placement фиксируется событием и ничего не блокирует; рекомендации при `very-low-confidence` максимально консервативны.
- **MUST**: rolling-уточнение — обычный механизм evidence первых сессий, не отдельный тест; движок повышает confidence и корректирует уровни автоматически.
- **MUST**: результаты placement (и отказ) попадают в tutor briefing ([[continuation]]).
- **MUST NOT**: повторять placement автоматически; повторный — только по явному запросу ученика.

## Выведенные контракты (фиксируются в спеках модулей)

| Модуль (спека) | Обязан предоставить |
|---|---|
| `assessments` (0.4/0.3) | версионируемые формы с seed; объективный скоринг; привязка item → тема/LexicalItem |
| `curriculum` (0.3) | адресуемость тем и LexicalItem из placement-items |
| `learner` | уровни по навыкам + confidence; consume rolling-evidence; консервативный старт при отказе |
| `evidence` (0.4) | placement-attempts как обычный evidence; вход лексики в личный словарь |
| `scoring` (0.4) | cap вклада rubric-writing; правила rolling-уточнения confidence |
| `cli` (0.7) | `trainer placement start/submit/decline`; JSON-контракт форм и результатов |
| `adapters`/skills (0.7) | skill `run-placement-assessment`: дословное предъявление, запрет подсказок |
| `audit` | события PLACEMENT_STARTED / SUBMITTED / SCORED / DECLINED |

## Открытые вопросы

Нет новых. Состав и объём форм A1–B1 — работа уровня П (наполнение), не развилка.

## История изменений

- **2026-07-19**: создан по Concept Gate: evidence только проверенным темам, placement рекомендован с правом отказа. Все решения [PD-2026-07-19]. Закрывает 0.8.
