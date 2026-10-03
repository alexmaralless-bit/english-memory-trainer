# Повторное сквозное ревью фазы 0 после триажа `bc966ec`

**Дата:** 2026-07-20  
**Объект:** commit `bc966ec` (`Triage the phase-0 review: all four blockers cleared`)  
**База:** `staging/reviews/2026-07-20-phase-0-review-codex.md`  
**Метод:** перепроверка всех 17 исходных findings по нормативным файлам + регрессионный проход по изменённым state/CLI/owner/rebuild стыкам. Реализация не проверялась, канон не редактировался.

## Итог

**Вердикт: `FAIL`.** Найдены 1 `BLOCKER`, 6 `MAJOR`, 2 `MINOR`, 1 `QUESTION`.

Commit существенно исправляет контракты, но утверждение «все четыре BLOCKER сняты» неверно: **P0-4 не исправлен, а корректно зарегистрирован как OPEN-25 и перенесён в незавершённый этап 0.11**. Это хорошая фиксация долга, но не снятие блокера. Сам roadmap признаёт, что owner/API/lifecycle ещё отсутствуют.

Из трёх реально исправленных BLOCKER:

- переходы `REGRESSION` и вход в `AT_RISK` теперь согласованы;
- появилась достижимая команда `trainer review close`, а finish/abandon разведены в основных правилах;
- transparency-precedence добавлен владельцу lexical scoring.

Семантический выбор по P0-1 выглядит корректным: `AT_RISK` теперь означает риск утраты от простоя, а фактически показанная утрата понижает knowledge state. Возвращать regression в `AT_RISK` не требуется. Однако после выбора остался один несинхронизированный outcome — R-2.

## BLOCKER

### R-1 — P0-4 зарегистрирован, но не снят

**Файлы и разделы:** `wiki/OPEN.md` owner-матрица и OPEN-25; `wiki/roadmap.md` 0.10/0.11; `wiki/modules/cli.md` §5; `wiki/README.md` принцип 2.

**Точные цитаты:**

> «0.11 ... `learner.md`, `audit.md`, `gates.md` | **next**»  
> — `wiki/roadmap.md`, строка 26

> «контракт ещё не написан»; «алгоритм и владелец не определены»  
> — `wiki/OPEN.md`, owner-матрица, строки 24–27

> «OPEN-25 — контракты `learner`, `audit`, `gates` отсутствуют ... Не определены API, события, lifecycle и инварианты»  
> — `wiki/OPEN.md`, строка 42

> «все BLOCKER сняты, заведён OPEN-25 → 0.11»  
> — `wiki/roadmap.md`, строка 27

**Почему это дефект:** OPEN и новый roadmap-item честно описывают работу, но target-state по-прежнему отсутствует. Команды `trainer status`, `trainer audit session`, `trainer gate ...` остаются в MVP CLI без owner-contract; `session next` всё ещё формально принадлежит lessons, отсутствует в её public API и не имеет алгоритма. Это исходное условие P0-4 без изменения. Регистрация BLOCKER не превращает его в resolved finding.

**Предлагаемая правка:** оставить OPEN-25/0.11, но считать P0-4 открытым и фазу 0 незавершённой до появления и ревью трёх контрактов и owner-решения для `session next`. В roadmap заменить over-claim «все BLOCKER сняты» на «3 сняты, P0-4 вынесен в блокирующий 0.11». Kernel 1.2 может идти параллельно, но вертикальный срез 2.x — только после 0.11.

**Severity:** `BLOCKER`.

## MAJOR

### R-2 — после новой семантики `RECOVERED after REGRESSION` стал невозможным outcome

**Файлы и разделы:** `wiki/glossary.md` Review outcome; `wiki/modules/scoring.md` §3; `wiki/product/learning-model.md` §4.

**Точные цитаты:**

> «`RECOVERED` — восстановление после AT_RISK/REGRESSION»  
> — `wiki/glossary.md`, строка 49

> `ACTIVE × REGRESSION → LEARNING`; `LEARNING × RECOVERED → LEARNING (no-op)`  
> — `wiki/modules/scoring.md`, строки 42–43

> «`RECOVERED` для NEW/LEARNING семантически невозможен (нет prior AT_RISK)»  
> — `wiki/modules/scoring.md`, строка 47

**Почему это дефект:** после принятого P0-1 regression никогда не создаёт `AT_RISK`: `ACTIVE` падает в `LEARNING`, а `MASTERED` — в `ACTIVE`. Для первого случая следующий outcome `RECOVERED` объявлен glossary допустимым, но scoring считает его corrupted/late и делает no-op. Движок классификации не знает, должен ли после восстановления от regression выдавать `RECOVERED` или `CONFIRMED`; scheduler при этом двигает интервал вперёд для `RECOVERED` независимо от no-op state transition.

**Предлагаемая правка:** при выбранной семантике таблицы определить `RECOVERED` только как восстановление из `AT_RISK` и удалить `/REGRESSION` из glossary. После regression восстановление классифицировать обычными `PROGRESS/CONFIRMED`. Альтернатива потребует отдельного post-regression marker и новых строк таблицы — это уже продуктовая развилка.

**Severity:** `MAJOR`.

### R-3 — P0-5 исправлен только в module specs; continuation и agent-facing вход остались противоречивыми

**Файлы и разделы:** `wiki/modules/lessons.md` §§5–6; `wiki/modules/evidence.md` §3; `wiki/flows/continuation.md` derived contracts; `wiki/modules/cli.md` §5.

**Точные цитаты:**

> «владелец `AGENT_ATTACHED` — lessons ... а не audit»  
> — `wiki/modules/lessons.md`, строка 75

> `audit | событие AGENT_ATTACHED {provider, session}`  
> — `wiki/flows/continuation.md`, строка 80

> Lessons API: `resume(session_id)`; CLI: `session resume --session ID`  
> — `wiki/modules/lessons.md`, строки 67, 83

> «каждое подключение ... `AGENT_ATTACHED` с провайдером»  
> — `wiki/flows/continuation.md`, строка 68

> `SessionNote` объявлен сущностью; flow требует `--note` при фиксации  
> — `wiki/modules/evidence.md`, строка 37; `wiki/flows/continuation.md`, строка 69

**Почему это дефект:** owner в flow не обновлён и прямо противоречит lessons. Для cold resume новый provider невозможно передать через `resume` CLI/API; отдельный `attach_agent(session_id, provider, skills)` не имеет CLI-команды и не сказано, что `resume` вызывает его атомарно. Поэтому обязательное событие при каждом подключении недостижимо через единственную agent-facing границу. SessionNote получила поля, но ни `record_attempt` signature, ни CLI registry/lessons CLI не принимает `note`, а API чтения notes хронологически не определён.

**Предлагаемая правка:** синхронизировать flow owner на lessons; определить одну атомарную agent-facing операцию (`resume --provider ...` либо явный `session attach`) и отношение к `attach_agent`; добавить `note?` в конкретные mutation schemas/CLI input и выдачу notes в `resume` response. Audit только consumes событие.

**Severity:** `MAJOR`.

### R-4 — P0-2 в основных правилах исправлен, но owner-спека всё ещё содержит старый trigger и старое имя команды

**Файлы и разделы:** `wiki/modules/lessons.md` §4; `wiki/modules/evidence.md` §§4.3, 5; `wiki/modules/cli.md` §5.

**Точные цитаты:**

> «FINISHED требует пустой pending-set ... это не авто-закрытие»  
> — `wiki/modules/lessons.md`, строка 46

> «терминализация — второй (наряду с явным close_review) триггер закрытия ReviewAssignment»  
> — `wiki/modules/lessons.md`, строка 48

> Evidence CLI перечисляет `review record`  
> — `wiki/modules/evidence.md`, строка 82

> Канонический CLI теперь содержит `trainer review close`  
> — `wiki/modules/cli.md`, строка 121

**Почему это дефект:** заголовок lessons определяет terminalization как `finish / abandon`, поэтому общий MUST снова включает finish в closure triggers и конфликтует с соседним MUST. Evidence ссылается на несуществующее имя `review record`, хотя command registry валидирует skills по точным именам. Основной happy path теперь понятен, но owner-contract остаётся внутренне противоречивым.

**Предлагаемая правка:** заменить «терминализация» в closure-trigger на конкретный `abandon`; в evidence CLI заменить `review record` на `review close` и перечислить точную команду/параметры.

**Severity:** `MAJOR`.

### R-5 — P0-6 добавил команду, но не определил per-skill payload

**Файлы и разделы:** `wiki/modules/cli.md` §5; `wiki/modules/assessments.md` §§4–5; `wiki/flows/placement.md`.

**Точные цитаты:**

> `trainer placement decline ... опциональный per-skill self-report`  
> — `wiki/modules/cli.md`, строка 129

> `decline(self_assessment?)`; `decline --self-assessment X`  
> — `wiki/modules/assessments.md`, строки 49, 60

> `placement decline --self-assessment A2`  
> — `wiki/flows/placement.md`, строка 64

> «self_reported_level ... по каждому навыку»  
> — `wiki/flows/placement.md`, строка 76

**Почему это дефект:** command registry теперь знает о decline, но два owner/context contracts всё ещё задают один scalar. Не определены ключи навыков, допустимый partial payload, broadcast semantics и versioned schema. Из одного вызова `A2` реализация может либо записать четыре A2, либо одну общую оценку, которой канон не допускает.

**Предлагаемая правка:** определить exact JSON schema, например объект по core-skill IDs, и использовать её в assessments/flow/CLI. Если scalar означает broadcast, это должно быть отдельным явным PD.

**Severity:** `MAJOR`.

### R-6 — P0-7 исправил таблицу источников, но public API по-прежнему обещает event-only rebuild

**Файлы и разделы:** `wiki/modules/memory.md` §§5–6.

**Точные цитаты:**

> «rebuild гибридный ... operational — render из authoritative SQLite (при утрате — из snapshot)»  
> — `wiki/modules/memory.md`, строки 68–75

> `rebuild() | полный пересбор из event-store (isolate-and-swap)`  
> — `wiki/modules/memory.md`, строка 84

**Почему это дефект:** тот же контракт сначала исправляет ложное обещание, а через девять строк повторяет его в публичном API. Реализатор `rebuild()` не знает, обязан ли подключать SQLite/snapshot и как выбирается источник страницы.

**Предлагаемая правка:** описать `rebuild()` как гибридный пересбор по page-source manifest; isolate-and-swap/high-water применить к event-sourced части, operational pages рендерить из authoritative snapshot/state в согласованной точке.

**Severity:** `MAJOR`.

### R-7 — session flow всё ещё требует мутации без API/CLI: observed facts и re-entry outcome/refusal

**Файлы и разделы:** `wiki/flows/session.md`; `wiki/modules/evidence.md` §§3, 5; `wiki/modules/scheduler.md` §§4, 6; `wiki/modules/cli.md` §5.

**Точные цитаты:**

> `A->>T: результат re-entry блока или явный отказ`  
> — `wiki/flows/session.md`, строка 55

> `A->>T: error / vocabulary / chunk observed`  
> — `wiki/flows/session.md`, строка 63

> Evidence API имеет `record_observed`, а §5 называет `error/vocabulary/chunk observed` agent-facing  
> — `wiki/modules/evidence.md`, строки 38, 82

> Scheduler CLI содержит только `trainer review due`  
> — `wiki/modules/scheduler.md`, строки 46–50

**Почему это дефект:** общий command registry не содержит ни observed-команд, ни re-entry submit/decline; lessons также их не предоставляет. `attempt record` может потенциально нести re-entry evidence, но это не сказано, а явный отказ вообще не является attempt. Flow требует сохранённого эффекта, который невозможно выразить через объявленную единственную границу.

**Предлагаемая правка:** назначить owner и exact command schemas для `record_observed` и re-entry result/decline либо нормативно включить их в `attempt record`/session command. Добавить события и idempotency/CAS semantics.

**Severity:** `MAJOR`.

## MINOR

### R-8 — P0-12 остался в lexical-system §6

**Файлы и разделы:** `wiki/product/lexical-system.md` §§1, 5, 6; `wiki/modules/scoring.md` §10; `wiki/roadmap.md` 0.9.

**Точные цитаты:**

> «OPEN-13 закрыт»  
> — `wiki/product/lexical-system.md`, строка 96; `wiki/roadmap.md`, строка 25

> Под заголовком «Открытые вопросы»: `OPEN-13 ... → 0.4`  
> — `wiki/product/lexical-system.md`, строки 213–218

**Почему это дефект:** roadmap исправлен, но сама спека одновременно закрывает и продолжает откладывать OPEN-13. Аналогичные reference-строки в §5 могут ссылаться на resolved механизм, однако строка внутри «Открытых вопросов» должна быть перенесена в history/зачёркнута.

**Предлагаемая правка:** пометить OPEN-13 закрытым со ссылкой на scoring §5/§6; оставить открытыми только OPEN-14/22.

**Severity:** `MINOR`.

### R-9 — P0-14 исправлен в glossary, но Learning Model сохраняет старую развилку half-step

**Файлы и разделы:** `wiki/product/learning-model.md` §5 и §11; `wiki/glossary.md` Working level; `wiki/modules/scoring.md` §4.

**Точные цитаты:**

> «Представление уровня (целые CEFR-bands vs ordinal/sublevel для “полступени”) определяет 0.4»  
> — `wiki/product/learning-model.md`, строка 91

> «OPEN-8: ... ordinal/sublevel уровня → 0.4»  
> — `wiki/product/learning-model.md`, строка 156

> Glossary/scoring уже фиксируют целые bands без подуровней  
> — `wiki/glossary.md`, строка 65; `wiki/modules/scoring.md`, строки 82–96

**Почему это дефект:** финальное решение уже принято, но product contract всё ещё выглядит как незакрытая развилка и ведёт к resolved OPEN. Доменные значения не двусмысленны благодаря scoring, поэтому severity не MAJOR.

**Предлагаемая правка:** синхронизировать §5 с целыми bands и перенести OPEN-8 из «Открытых вопросов» в history/resolved reference.

**Severity:** `MINOR`.

## QUESTION

### R-Q1 — является ли `type` реальной осью LexicalMasteryProfile?

**Файлы и разделы:** `wiki/modules/scoring.md` §6; `wiki/product/lexical-system.md` §1a; `wiki/glossary.md`.

**Точные цитаты:**

> «lookup тотален по `(type, transparency, usage_policy)`»  
> — `wiki/modules/scoring.md`, строка 113

> Следующая таблица имеет только строки `transparency` и столбцы `usage_policy`; `type` в ней отсутствует  
> — `wiki/modules/scoring.md`, строки 116–120

**Вопрос:** `type` намеренно не влияет на required dimensions, кроме отдельного правила агрегации форм lexeme, или type-specific profile ещё не описан? Если первое — lookup фактически задаётся двумя осями + post-processing по type, и это стоит сказать прямо. Если второе — таблица не тотальна по заявленному кортежу и не определяет mastery criteria разных типов.

**Предлагаемая правка:** либо явно зафиксировать `type_default → transparency/usage override → lexeme form aggregation`, либо добавить type rows/default/fallback и schema mastery-критериев.

**Severity:** `QUESTION`.

## Матрица исходных 17 пунктов

| Исходный пункт | Rereview | Комментарий |
|---|---|---|
| P0-1 REGRESSION/AT_RISK | **исправлен частично** | Основной переход согласован; остался `RECOVERED after REGRESSION` (R-2) |
| P0-2 close review | **исправлен частично** | Команда появилась; stale MUST/name в owner specs (R-4) |
| P0-3 transparency | **исправлен** | Precedence определён; type-axis оставлен как QUESTION R-Q1 |
| P0-4 missing owners | **не исправлен, зарегистрирован** | OPEN-25/0.11 — правильный tracking, но BLOCKER остаётся (R-1) |
| P0-5 continuation | **исправлен частично** | Module owner появился; flow/CLI/API не синхронизированы (R-3) |
| P0-6 placement decline | **исправлен частично** | Команда в registry есть; payload всё ещё scalar/не задан (R-5) |
| P0-7 memory rebuild | **исправлен частично** | Boundary table верна; API stale (R-6) |
| P0-8 ninth track | **исправлен** | Curriculum/roadmap/scoring согласованы |
| P0-9 living layer phase | **исправлен** | Workflow/event `[post-mvp]`, постоянные data/legal rules сохранены |
| P0-10 rejected branch | **исправлен** | Одна ветка в product/evidence |
| P0-11 exit codes | **исправлен** | Drift → 6 + `skills.sync`; 3 → invalid structure |
| P0-12 OPEN drift | **исправлен частично** | Roadmap/OPEN-22 исправлены; lexical §6 сохраняет OPEN-13 (R-8) |
| P0-13 update metadata | **исправлен** | Headers/history обновлены для затронутых specs |
| P0-14 Working level | **исправлен частично** | Glossary исправлен; learning-model stale (R-9) |
| Q1 skill preflight | **исправлен** | Resolve → UoW → commit → event |
| Q2 REVIEW_DUE truth | **исправлен** | Idempotent notification, status Clock-derived |
| Q3 Compliance trust | **семантически исправлен** | Engine-observed effects; audit mechanism логично входит в открытый 0.11 |

## Проверено, ок

- Выбранная семантика `AT_RISK` only-overdue согласована между scoring, learning diagram и glossary; скрытого severity regression больше не требуется.
- `trainer review close` зарегистрирован как mutating evidence-command; общая CLI-idempotency применима.
- Transparency ограничивает production сильнее, чем permissive usage policy; ключевая клетка `opaque + safe_to_use` определена корректно.
- `everyday-life` добавлен девятым Track, отделён от informal register; work-only SHOULD исправлен.
- Living-layer workflow и `LEXICAL_ITEM_ADDED` последовательно помечены `[post-mvp]`.
- Observation без подтверждения имеет единственную ветку `rejected` + audit reason.
- Adapter drift больше не маскируется под CAS `CONFLICT`.
- Skill resolution выполняется до commit; `SESSION_STARTED` consumer оставлен только как audit.
- `REVIEW_DUE` не является вторым источником review status и имеет epoch-based idempotency key.
- Tutor Compliance больше не доверяет одному `SKILL_COMPLETED`; требуются наблюдаемые доменные эффекты.
- Foundation invariants, safety-overlay, event-store atomicity, CAS/uniqueness и numeric determinism триаж не регрессировал.

## Финальный вывод

`bc966ec` — содержательно сильный триаж, но **не PASS**. Он снял три из четырёх исходных BLOCKER и правильно поставил четвёртый на отдельный этап. Для снятия FAIL нужно сначала завершить 0.11; перечисленные MAJOR лучше исправить в том же проходе, потому что четыре из них — обычная несинхронизированная поверхность команд/owners, а не новые продуктовые развилки.
