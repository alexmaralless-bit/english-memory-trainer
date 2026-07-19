# Flow: продолжение без старого чата (continuation)

> **Status**: current
> **Last updated**: 2026-07-19
> **Sources**: [[session]] · [[../product/learning-model]] · Concept Gate 2026-07-19 (три развилки, [PD-2026-07-19]) · концепт одобрен («ок»)
> **Роль**: спинной сценарий (roadmap 0.8). Ключевое свойство системы: контекст чата — не память; любой агент продолжает обучение из состояния движка. Проверяется демо 2.7.

---

## Решения этого flow [PD-2026-07-19]

1. **Session notes — опциональные и untrusted.** При любой фиксации агент МОЖЕТ добавить короткую заметку (о чём говорили, на чём остановились). Resume возвращает заметки хронологически. **Заметки — untrusted non-evidence** [ревью C-8]: они не имеют пути в scoring, экранируются в briefing и никогда не интерпретируются как состояние. Даже если заметка утверждает «ученик уверенно освоил X», источник истины — вычисленный state, а не текст агента.
2. **Tutor briefing в манифесте.** Движок отдаёт полную картину ученика одним JSON внутри Session Manifest (и в ответе resume). Чтение Obsidian агенту не требуется — vault остаётся проекцией для человека; briefing генерится из state. В briefing вычисленный state и свободный текст заметок физически разделены (trust boundary).
3. **Без блокировок, с учётом.** Lease/блокировки сессий в MVP не вводятся: ученик один, реальная одновременность агентов маловероятна ([PD-2026-07-19]). `start`/`resume` регистрируют провайдера событием `AGENT_ATTACHED`. Transport-idempotency не решает семантический конфликт двух агентов [ревью G-8]: MUST — **уникальный терминальный outcome на review-assignment** и **optimistic session revision** (конкурентная запись с устаревшей ревизией отклоняется); полный correction protocol — [[../OPEN]] OPEN-11. Lease — `[post-mvp]`.

## Состав tutor briefing

Генерится движком из состояния (не из Markdown):

- рабочий уровень по навыкам + confidence;
- активные темы и их состояния;
- топ повторяющихся ошибок;
- недавние vocabulary и chunks;
- re-entry статус (перерыв, упавшая Retrievability);
- рекомендации тем и повторений;
- краткая сводка последней сессии (вычисленный итог; session notes — в отдельном untrusted-блоке, не смешаны со state).

## Сценарий A — resume брошенной IN_PROGRESS сессии

Чат умер посреди занятия. Всё зафиксированное сохранено инкрементально ([[session]]); новый агент — тот же или другой провайдер.

```mermaid
sequenceDiagram
    autonumber
    actor L as Ученик
    participant A2 as Новый агент
    participant T as trainer CLI

    A2->>T: session resume --session ID
    T->>T: событие AGENT_ATTACHED {provider}
    T-->>A2: состояние сессии: tutor briefing + выполнено/осталось из манифеста + attempts + ошибки этой сессии + session notes
    A2->>L: честное продолжение: «Продолжаем занятие — вижу, вы разобрали X, остановились на Y»
    L-->>A2: продолжение разговора
    Note over A2,T: далее — обычный цикл flow «сессия»: фиксация сразу, review-цели, finish
```

## Сценарий B — холодный старт нового агента (новая сессия)

Прошлую сессию вёл другой провайдер и завершил её штатно. Новый агент стартует по flow [[session]]; специфика continuation — в протоколе восстановления картины:

```mermaid
sequenceDiagram
    autonumber
    participant A2 as Новый агент
    participant T as trainer CLI

    A2->>T: session start
    T->>T: событие AGENT_ATTACHED {provider}
    T-->>A2: Session Manifest {tutor briefing, re-entry?, review-цели, рекомендации, required_skills}
    Note over A2: агент знает уровень, ошибки, план — не читая старых чатов
```

## Правила сценария

- **MUST**: `resume` и `start` возвращают tutor briefing — агенту достаточно одного вызова CLI, чтобы вести занятие корректно.
- **MUST**: агент честен с учеником: он продолжает по сохранённому состоянию и не притворяется, что помнит разговор дословно.
- **MUST NOT**: агент не восстанавливает картину из Obsidian vault, старых чатов или расспросов ученика «что мы проходили» — источник только движок. (Заглянуть в vault агент может, но любое расхождение трактуется в пользу CLI.)
- **MUST**: каждое подключение агента к сессии фиксируется событием `AGENT_ATTACHED` с провайдером — вход для Tutor Compliance и аудита смены агентов.
- **MAY**: session note при любой фиксации (`--note "..."`); движок хранит их как untrusted-данные и отдаёт при resume в отдельном блоке.
- **MUST**: незакрытые review-цели брошенной сессии остаются обязательными к исходу перед finish (правило [[session]] сохраняется при смене агента).
- **MUST**: при resume двумя агентами — optimistic session revision; конкурентная запись с устаревшей ревизией отклоняется стабильной ошибкой ([[../OPEN]] OPEN-11).

## Выведенные контракты (фиксируются в спеках модулей)

| Модуль (спека) | Обязан предоставить |
|---|---|
| `lessons` (0.5) | `resume` API: полное состояние сессии одним ответом; переживание смены агента без потери обязательств |
| `learner` | агрегация tutor briefing из состояния (уровень, ошибки, vocabulary, рекомендации) |
| `evidence` (0.4) | приём опциональной `--note` (untrusted) при фиксациях; выдача notes хронологически, отдельно от state |
| `audit` | событие `AGENT_ATTACHED {provider, session}`; след смены агентов для Tutor Compliance |
| `cli` (0.7) | briefing в ответах `session start`/`resume` с trust boundary (state vs notes); стабильная схема briefing JSON |
| `kernel` (0.2) | optimistic session revision; уникальный терминальный outcome на review-assignment; correction protocol (OPEN-11) |
| `adapters`/skills (0.7) | cold-start протокол: один вызов CLI → полная картина; запрет восстановления из сторонних источников; notes не трактуются как state |

## Открытые вопросы

Механизм — [[../OPEN]] OPEN-11 (idempotency scope, optimistic concurrency двух агентов, correction protocol). Lease на сессию — `[post-mvp]`.

## История изменений

- **2026-07-19 (2)**: red-team триаж — session notes untrusted non-evidence с trust boundary в briefing (C-8); optimistic session revision и уникальный терминальный outcome против двух агентов (G-8).
- **2026-07-19**: создан по Concept Gate: опциональные session notes, tutor briefing в манифесте, без блокировок с событием AGENT_ATTACHED. Все решения [PD-2026-07-19].
