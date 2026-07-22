# Модуль: cli

> **Status**: current
> **Last updated**: 2026-07-22
> **Sources**: `docs/english-memory-trainer-build-prompt.md` §12 (CLI contract), §11 (skills) · `CLAUDE.md` инварианты · [[../platform/foundation]] (envelopes, idempotency, correlation) · [[lessons]], [[assessments]], [[evidence]], [[scoring]], [[memory]], [[curriculum]] (владельцы команд) · все решения [PD-2026-07-20]
> **Bounded context**: `src/english_trainer/cli/`

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — по [[../glossary]].

---

## 1. Назначение

CLI — **единственная** граница, через которую внешний мир, включая AI-тьютора, читает и меняет состояние ученика. Движок остаётся авторитетом; агент — сменный клиент, который умеет только вызывать команды и читать их ответ. Модуль не содержит бизнес-логики: он транслирует аргументы в команды доменных модулей и сериализует результат в стабильный, машинно-разбираемый контракт.

Ценность в том, что тьютора можно заменить (Codex ↔ Claude Code ↔ следующий), не трогая ни одного правила обучения.

## 2. Сущности и состояния

Модуль **не владеет** состоянием ученика. Он владеет только контрактом вызова.

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `CommandDescriptor` | реестр команд: имя, владелец, мутирующая ли, требует ли idempotency-key | `name`, `owner_module`, `mutating`, `requires_idempotency_key`, `phase` |
| `ResponseEnvelope` | единая оболочка любого ответа | `schema_version`, `ok`, `command`, `correlation_id`, `data` \| `error` |
| `ErrorPayload` | отказ в машинно-разбираемом виде | `error_code`, `message`, `allowed_actions[]`, `next_action` |

Envelope **тотален**: успех и отказ имеют одну форму, различаясь полем `ok`. Агенту не нужно угадывать, что он читает.

```json
{
  "schema_version": 1,
  "ok": false,
  "command": "session.finish",
  "correlation_id": "01J...",
  "error": {
    "error_code": "SESSION_ALREADY_FINISHED",
    "message": "Session 01J... reached FINISHED at 2026-07-20T08:11:03Z.",
    "allowed_actions": ["session.start", "audit.session"],
    "next_action": "session.start"
  }
}
```

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `dispatch(argv)` | API | разбирает аргументы, вызывает команду владеющего модуля, сериализует envelope |
| `command_registry()` | API | реестр `CommandDescriptor` — источник для `trainer skills validate` и adapters parity |

Модуль **не публикует бизнес-доменных событий**: их публикуют владеющие модули. [PD-2026-07-22] Outer transport публикует только операционные audit-факты `cli.command_invoked` / `cli.command_terminated`; CLI также пробрасывает тот же `correlation_id` внутрь, чтобы вызов, его исход и доменные эффекты были связуемы.

## 4. Поведение

### 4.1 Контракт вывода

- **MUST — чистый stdout**: при `--format json` stdout содержит **ровно один** JSON-документ и ничего больше. Прогресс, предупреждения, отладка — только stderr. Агент парсит stdout целиком, а не ищет в нём JSON.
- **MUST — отказ тоже JSON**: если команда падает при `--format json`, на stdout всё равно печатается валидный envelope с `ok: false`. Исключение, вылетевшее наружу необёрнутым, — дефект: агент получает неразбираемый мусор и не может выбрать следующий шаг. Это относится и к внутренним ошибкам (`INTERNAL`), не только к доменным отказам.
- **MUST — `next_action` обязателен при отказе**: каждый отказ называет допустимые действия и рекомендованное следующее. Отказ без выхода оставляет агента в цикле повторов.
- **MUST — человеческий формат по умолчанию**: без `--format json` вывод рассчитан на человека и **не является контрактом** — его форма может меняться свободно. Контракт версионируется только для JSON.
- **MUST — `schema_version`**: в каждом envelope. Несовместимое изменение формы ответа увеличивает версию; агент вправе отказаться работать с незнакомой мажорной версией.

### 4.2 Exit codes — закрытый набор

- **MUST**: коды стабильны и закрыты; добавление кода — правка этой спеки.

| Код | Имя | Когда |
|---:|---|---|
| 0 | `OK` | успех |
| 1 | `INTERNAL` | непредвиденная ошибка движка |
| 2 | `USAGE` | неверные аргументы, неизвестная команда |
| 3 | `INVALID_INPUT` | вход не прошёл schema/доменную валидацию |
| 4 | `NOT_FOUND` | сущность по ID не существует |
| 5 | `CONFLICT` | состояние изменилось под вызовом (CAS), либо действие уже выполнено |
| 6 | `PRECONDITION_FAILED` | действие недопустимо в текущем состоянии |

- **MUST — различимость 5 и 6**: `CONFLICT` означает «повтори с актуальным состоянием», `PRECONDITION_FAILED` — «так нельзя, делай другое». Слияние их в один код лишает агента возможности выбрать между retry и сменой плана.

### 4.3 Идемпотентность

- **MUST — ключ обязателен для мутирующих команд**: каждая мутирующая команда принимает `--idempotency-key` и **требует** его при `--format json`. Причина не в удобстве: процесс может упасть **после** commit и **до** печати ответа, и тогда агент не знает, состоялось ли действие. Без ключа единственный безопасный выбор — не повторять, то есть терять работу ученика.
- **MUST — повтор возвращает исходный результат**: тот же ключ с тем же payload возвращает первоначальный envelope и код `0`, не выполняя действие повторно — cached result проверяется до теперь уже stale session fence. Тот же ключ с **другим** payload — `CONFLICT`. [PD-2026-07-22] Namespace глобален внутри локального store/единственного learner; cache хранится без срока вместе с authoritative state.
- **MUST — `correlation_id`**: генерируется на вызов (или принимается извне), проставляется во все события вызова, возвращается в envelope. `trainer audit` умеет собрать по нему полную картину.

### 4.4 Граница авторитета

- **MUST NOT — нет команды, записывающей оценку**: в поверхности отсутствует операция, принимающая Mastery, Stability, CEFR-уровень или knowledge state как **вход**. Агент подаёт evidence и свою rubric-оценку как наблюдение; число вычисляет [[scoring]] по pinned policy. Команда, позволяющая агенту записать балл, сделала бы детерминизм недостижимым и обессмыслила `trainer scoring replay`.
- **MUST — запись только через команды**: прямые правки SQLite, JSONL и сгенерированных файлов `memory/` запрещены (`CLAUDE.md`). CLI — не удобная обёртка, а единственный вход.
- **MUST — read-only команды не мутируют бизнес-состояние**: команды, помеченные `mutating: false`, не изменяют state/projections даже косвенно (не «чинят» найденный drift, не досоздают недостающее). Единственное исключение — outer audit telemetry, не являющаяся business effect. Диагностика, меняющая диагностируемое состояние, недопустима.
- **MUST — полная CLI telemetry [PD-2026-07-22]**: перед dispatch записывается invocation, после любого успеха/отказа/внутренней ошибки — terminal fact с causation на invocation, exit code и стабильным error code. Аргументы представлены только redacted shape/hash; raw values и user content запрещены. Для session-команд оба факта несут `session_id`, даже если бизнес-команда отказана. Нарушенная БД не маскируется telemetry-ошибкой.

### 4.5 Безопасность и валидация

- **MUST — валидация до эффекта**: вход валидируется против versioned schema до начала транзакции; `INVALID_INPUT` не оставляет следов.
- **MUST — транзакционность**: команда либо применяет весь свой эффект (состояние + outbox), либо ничего ([[../platform/foundation]]).
- **MUST — safety по active policy**: команды доставки контента сверяют `production_eligible` с **active** policy, а не с pinned (safety-overlay, [[../OPEN]] OPEN-14).

## 5. CLI-поверхность

Пространство имён — `session`, не `lesson` [PD-2026-07-19]. Владелец команды — модуль, которому она принадлежит; здесь только контракт вызова.

### Диагностика и настройка

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer doctor` | cli | нет | среда, версии, целостность путей; запускается первым при разборе поломки |
| `trainer init` | storage | да | инициализация локального состояния |
| `trainer status` | learner | нет | сводка: уровень, активная сессия, что просрочено |

### Обучение

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer session start` | lessons | да | открывает сессию; композиция плана — в той же UoW; `--mode` задаёт режим занятия |
| `trainer session next` | lessons | **да** | требует `--expected-session-revision`, `--expected-plan-version` и `--idempotency-key`; выдаёт шаг и увеличивает оба токена ([[control]] §4.2) |
| `trainer session peek` | lessons | нет | показывает следующий шаг и текущий `plan_version`, ничего не помечая |
| `trainer session replan` | lessons | да | требует `--expected-session-revision`, `--expected-plan-version` и `--idempotency-key`; `composition_revision + 1`, `plan_version + 1`, новое `SESSION_COMPOSED` |
| `trainer session resume` | lessons | да | возобновляет `IN_PROGRESS` после потери чата; `--provider` обязателен и атомарно фиксирует `AGENT_ATTACHED` |
| `trainer session finish` | lessons | да | требует `--expected-session-revision`; **единственный** способ завершить сессию; требует persisted evidence |
| `trainer session abandon` | lessons | да | требует `--expected-session-revision`; явный отказ от сессии |
| `trainer attempt record` | evidence | да | требует `--expected-session-revision`; фиксирует попытку по **выданному шагу** (`--step`); target/dimension/mode и `origin` движок берёт из плана. `--note` — необязательная untrusted-заметка |
| `trainer attempt finalize` | evidence | да | требует session revision; движок применяет pinned rubric и атомарно фиксирует assessment/evidence |
| `trainer review due` | scheduler | нет | что подлежит повторению |
| `trainer review close` | evidence | да | вычисляет терминальный ReviewOutcome по накопленному evidence; идемпотентен, повтор возвращает прежний исход |
| `trainer observed record` | evidence | да | фиксирует наблюдённый факт (ошибка, слово, chunk), замеченный в свободном ответе, — вход `record_observed` ([[evidence]] §3); принимает `--note` |
| `trainer reentry decline` | scheduler | да | ученик отказался от предложенного re-entry: факт сохраняется, ничего не блокирует и не штрафуется ([[scheduler]] §4) |
| `trainer gate begin` \| `submit` \| `evaluate` | gates | да | рекомендательный гейт по теме |

### Placement

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer placement start` \| `answer` \| `submit` \| `resume` \| `abandon` | assessments | да | жизненный цикл placement ([[assessments]]) |
| `trainer placement decline` | assessments | да | отказ от placement с опциональным **per-skill** self-report ([[assessments]] §4) |

### Данные и проверки

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer curriculum show` \| `validate` \| `activate` \| `lexicon` | curriculum | `activate` — да | снапшоты, валидация кандидата, активация |
| `trainer memory render` \| `check` \| `rebuild` | memory | `render`/`rebuild` — да | проекция Obsidian и drift-check |
| `trainer database check` | storage | нет | целостность SQLite |
| `trainer scoring replay` | scoring | нет | воспроизведение оценок по pinned policy |
| `trainer scoring transitions backfill` | scoring | да | идемпотентно восстанавливает отсутствующие canonical transition facts |
| `trainer audit session SESSION_ID` | audit | нет | полная картина по `correlation_id` |
| `trainer audit correlation ID` \| `target ID` | audit | нет | причинная цепочка вызова / история LearningTarget |
| `trainer snapshot create` | storage | да | git-снапшот после checkpoint |

### Skills и адаптеры

| Команда | Владелец | Мутирует | Что делает |
|---|---|---|---|
| `trainer skills sync` \| `validate` | adapters | `sync` — да | синхронизация и drift-check канонических skills ([[adapters]]) |
| `trainer skills report` | adapters | да | untrusted started/completed/failed self-report по pinned skill |
| `trainer adapters capture-turn` | adapters | да | полный локальный untrusted user-turn + hash/span на provider boundary |
| `trainer why` | control | нет | почему выбран этот шаг: decision trace ([[control]] §4.8) |
| `trainer signal KIND` | control | да | записывает сигнал; при активной сессии `too_easy` возвращает `probe_id` и `next_action: session.replan`, но сам план не меняет |
| `trainer availability show` \| `set` | control | `set` — да | объявленный и наблюдаемый ритм занятий |
| `trainer tunables list` | control | нет | каталог настроек: владелец, диапазон, режим изменения |
| `trainer metrics` | control | нет | метрики качества политики + аварийные признаки |
| `trainer calibration list` \| `confirm ID` | control | `confirm` — да | предложения калибровки; активацию выполняет владелец параметра ([[control]] §4.9) |
| `trainer adapters compare` | adapters | нет | паритет тьюторов по фикстурам ([[adapters]]) |

- **MUST — `--format json` у всех agent-facing команд**. Команды, не предназначенные агенту (`doctor`, `init`), тоже его поддерживают: их зовут в автоматике диагностики.

## 6. Границы

- **depends on**: все доменные модули (как диспетчер), [[../platform/foundation]] (envelopes, idempotency, correlation)
- **events published**: только `cli.command_invoked`, `cli.command_terminated` (audit telemetry; не бизнес-домен)
- **events consumed**: нет

Бизнес-правила в CLI не живут. Если команда «знает», когда сессию можно завершить, — правило утекло из [[lessons]].

## 7. Открытые вопросы

- **OPEN-11 закрыт [PD-2026-07-22]**: global local-store scope, бессрочный cache, same-payload cached replay до stale session fence, coarse session revision.
- **OPEN-23**: политика совместимости JSON-контракта — что считается несовместимым изменением, поддерживается ли предыдущая мажорная версия и как долго → блокирует смену тьютора на закреплённой версии skills.

## История изменений

- **2026-07-22 (3)**: [PD-2026-07-22] добавлены fail-closed session revision на все мутации, outer invocation/terminal telemetry (включая read-only/отказы), новые audit/tunables/calibration/ingress/transition команды; OPEN-11 закрыт.
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4).
- **2026-07-21**: `next`/`replan` синхронизированы с единым CAS-токеном `plan_version`; исправлена ссылка decision trace и явный replan после `too_easy`.
- **2026-07-20**: спека создана (0.7). Тотальный envelope, закрытый набор exit codes с различением `CONFLICT`/`PRECONDITION_FAILED`, обязательный idempotency-key для мутирующих команд (мотив — падение между commit и печатью), запрет команды, принимающей оценку, запрет мутаций в read-only диагностике. Заведён OPEN-23.
