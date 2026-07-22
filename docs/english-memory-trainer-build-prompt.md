# Master prompt: создать English Memory Trainer MVP

> **Scope override [PD-2026-07-22]:** действующий продукт постоянно ограничен Reading, Writing,
> grammar, vocabulary и текстовым chat-production. Listening/Speaking изучаются вне тренажёра и
> не планируются. Любые ниже расположенные требования, веса, substitutes или демо для этих
> модальностей — исторический исходный prompt и не являются нормативными. Канон — `wiki/`, затем
> `docs/design-direction.md`.

Скопируй этот prompt целиком в Codex или Claude Code, запущенный в корне нового или существующего Git-репозитория.

---

Ты — senior Python architect, product engineer и specialist по agentic systems. Твоя задача — спроектировать и реализовать работающий local-first MVP приложения **English Memory Trainer**.

Не ограничивайся созданием документации или заглушек. Построй проверяемый вертикальный сценарий, запусти тесты и оставь репозиторий в рабочем состоянии. Если репозиторий пустой, инициализируй проект в нём. Не публикуй изменения и не выполняй внешние destructive actions.

## 1. Продуктовая цель

Это AI-тренажёр американского английского для русскоязычного IT-профессионала, который хочет:

- довести построение английских фраз до автоматизма;
- понимать живую американскую речь;
- работать в американской IT-компании;
- общаться об AI, AEC, SaaS, продуктах, данных и engineering workflows;
- в дальнейшем сдать TOEFL.

Ученик занимается два часа ежедневно. Codex и Claude Code должны быть взаимозаменяемыми преподавателями. Контекст чата может исчезнуть полностью, но прогресс, программа и следующий шаг не должны потеряться.

## 2. Непереговорные требования

1. Python-приложение является управляющим движком.
2. LLM не является источником истины.
3. Используй local-first архитектуру.
4. Храни состояние в Markdown + SQLite + append-only JSONL event log.
5. Храни curriculum и policies в version-controlled YAML/Markdown.
6. Используй Python CLI как единственный agent-facing интерфейс.
7. Не используй MCP.
8. Поддержи Codex и Claude Code через общий канонический набор Agent Skills.
9. Реализуй prerequisite graph и блокировку недопустимых переходов.
10. Реализуй placement, topic, module и CEFR-level gates как расширяемую модель.
11. Разделяй Learning Score, Season XP и Tutor Compliance Score.
12. Любая оценка должна иметь сохранённое evidence.
13. Любое изменение scoring должно быть воспроизводимо через replay событий.
14. Не пытайся полностью наполнить curriculum A1–C2 в первой версии. Создай расширяемый каркас и качественный вертикальный срез A1–A2.
15. Система должна безопасно модернизироваться по ходу реального обучения.

## 3. Сначала изучи контекст

Перед реализацией:

1. Проверь содержимое репозитория и сохрани существующие пользовательские изменения.
2. Если рядом находится файл продуктового брифа `english-memory-trainer-brief.md`, прочитай его полностью и считай более точным источником требований.
3. Создай короткий implementation plan с зависимостями и acceptance criteria.
4. Не задавай вопросы, если можешь выбрать безопасный, обратимый вариант. Явно зафиксируй существенные допущения.

## 4. Рекомендуемый технический стек

Используй современный, простой и хорошо тестируемый Python:

- Python 3.12+;
- `uv` для environment и dependency management, если доступен;
- `typer` для CLI;
- `pydantic` для schemas и validation;
- `SQLAlchemy 2.x` и `Alembic` либо обоснованно более простой слой SQLite;
- `pytest`;
- `ruff`;
- `mypy` или `pyright`;
- YAML parser;
- стандартный `sqlite3` backup API для snapshots.

Не добавляй тяжёлый framework без необходимости. Спрячь storage за интерфейсами, чтобы позже SQLite можно было заменить, но не реализуй PostgreSQL.

## 5. Доменная модель

Минимальные сущности:

- `LearnerProfile`;
- `CurriculumVersion`;
- `Level`;
- `Track`;
- `Module`;
- `Topic`;
- `Prerequisite`;
- `SkillDimension`;
- `TopicState`;
- `LessonSession`;
- `SessionStep`;
- `Attempt`;
- `Evidence`;
- `ObservedError`;
- `VocabularyItem`;
- `Chunk`;
- `ReviewSchedule`;
- `GateDefinition`;
- `GateAttempt`;
- `Assessment`;
- `AssessmentItem`;
- `ScoreSnapshot`;
- `XpTransaction`;
- `AgentSkillInvocation`;
- `TutorAudit`;
- `DomainEvent`.

Используй стабильные IDs, UTC timestamps и versioned policies.

## 6. Curriculum graph

Реализуй directed acyclic graph с:

- hard prerequisites;
- soft prerequisites;
- related topics;
- unlock policy;
- mastery policy;
- retention requirements.

CLI validation должна обнаруживать:

- циклы;
- отсутствующие topic IDs;
- дубли;
- неправильные CEFR transitions;
- пустые обязательные dimensions;
- изменение или удаление уже использованного стабильного ID.

Создай каркас A1–C2, но наполни только репрезентативный A1–A2 vertical slice. Включи как минимум:

- `to be`;
- базовый порядок слов;
- Present Simple;
- Present Continuous;
- Past Simple;
- основные irregular verbs;
- `there is / there are`;
- `a / an / the`;
- базовые предлоги;
- have/has;
- past participle;
- Present Perfect for result/experience;
- going to / will;
- базовые conversational chunks;
- простые AI/SaaS work scenarios.

## 7. Topic scoring

Для каждой темы храни:

- Mastery 0–100;
- Stability в днях;
- Retrievability 0–1;
- score по каждой required dimension;
- attempts count;
- independent attempts;
- hints usage;
- retention history.

Состояния:

```text
LOCKED, AVAILABLE, INTRODUCED, LEARNING, ACTIVE,
MASTERED, REVIEW_DUE, AT_RISK
```

Сделай scoring engine детерминированным и versioned. Одна попытка не должна позволять скачок от знакомства до Mastered. Учитывай:

- correctness;
- difficulty;
- independence;
- hints;
- exercise mode;
- temporal spacing;
- repeated evidence;
- error severity.

Не выдавай ложную научную точность. Документируй формулу и добавь property/unit tests: bounds, monotonicity, caps, repeatability и replay.

## 8. Scheduling

Для MVP реализуй расширяемый scheduler с базовой последовательностью:

```text
1, 3, 7, 14, 30, 60, 120, 180 дней
```

Отдели scheduling interface от конкретной формулы, чтобы позже можно было перейти на FSRS. Поддержи:

- due reviews;
- overdue reviews;
- Retrievability decay;
- recovery mode;
- блокировку новой темы при чрезмерном backlog;
- hidden review через conversation evidence.

## 9. Ученические гейты

Реализуй модели и минимум один рабочий пример каждого типа:

- Recognition Gate;
- Controlled Production Gate;
- Conversation Gate;
- Transfer Gate;
- Retention Gate;
- Module Gate;
- CEFR Boundary Gate.

Gate нельзя пройти одной случайной попыткой. Он должен проверять required dimensions, independent attempts и retention conditions.

## 10. Placement assessment

Реализуй внутренний CEFR-aligned placement MVP. Он не должен заявляться как официальная сертификация.

Разделы и стартовые веса:

```text
Grammar    15%
Vocabulary 15%
Reading    15%
Listening  20%
Writing    15%
Speaking   20%
```

Для CLI MVP допускается:

- объективно оценивать grammar/vocabulary/reading;
- использовать transcript fixture или textual listening substitute для инфраструктурного vertical slice;
- принимать structured rubric evidence для writing/speaking;
- явно помечать unavailable modality, не подменяя её фиктивным score.

Храни отдельный level estimate по skill, а общий working level вычисляй консервативно. Поддержи deterministic random seed и несколько форм теста.

## 11. Agent Skills

Создай канонические skills в `agent-skills/`:

1. `run-english-session`;
2. `run-placement-assessment`;
3. `run-spaced-review`;
4. `teach-english-topic`;
5. `coach-english-conversation`;
6. `correct-learner-output`;
7. `assess-english-gate`;
8. `finish-english-session`;
9. `audit-english-tutor`;
10. `maintain-english-curriculum`.

Каждый skill должен иметь короткий `SKILL.md` с `name` и точным `description`, обязательными inputs, steps, forbidden actions, CLI calls, outputs и postconditions. Подробности выноси в `references/`, deterministic validation — в Python, а не в длинный prompt.

Реализуй:

```bash
trainer skills sync
trainer skills validate
trainer adapters compare
```

Команда `sync` должна создавать совместимые project skills:

- `.agents/skills/` для Codex;
- `.claude/skills/` для Claude Code.

Избегай platform-fragile symlinks: для MVP можно генерировать deterministic copies с manifest/hash и drift check.

Не полагайся только на implicit invocation. Session Manifest обязан содержать `required_skills` с версиями. Сохраняй события `SKILL_REQUIRED`, `SKILL_STARTED`, `SKILL_COMPLETED`, `SKILL_FAILED`.

Создай skill eval fixtures минимум для:

- правильного trigger;
- неправильного trigger;
- попытки перескочить prerequisite;
- попытки агента самостоятельно изменить score;
- незавершённого обязательного review;
- попытки закончить урок без persistence;
- одинакового поведения Codex/Claude adapters.

## 12. CLI contract

Реализуй как минимум:

```bash
trainer doctor
trainer init
trainer status --format json
trainer placement start --format json
trainer placement submit --input FILE --format json
trainer lesson start --duration 120 --provider codex --format json
trainer lesson next --session SESSION_ID --format json
trainer attempt record --session SESSION_ID --input FILE --format json
trainer review due --format json
trainer gate begin --session SESSION_ID --topic TOPIC_ID --format json
trainer gate submit --session SESSION_ID --input FILE --format json
trainer gate evaluate --session SESSION_ID --topic TOPIC_ID --format json
trainer lesson finish --session SESSION_ID --format json
trainer memory render
trainer audit session SESSION_ID --format json
trainer curriculum validate
trainer skills sync
trainer skills validate
trainer adapters compare
trainer database check
trainer memory check
trainer scoring replay
trainer snapshot create
```

Agent-facing команды должны:

- печатать валидный JSON в stdout;
- отправлять diagnostics в stderr;
- возвращать стабильные exit codes;
- валидировать schemas;
- быть транзакционными;
- защищаться от повторной отправки одного event/attempt;
- возвращать `error_code`, `message`, `allowed_actions` и `next_action` при отказе.

## 13. Lesson state machine

Реализуй:

```text
START
→ WARMUP
→ REQUIRED_REVIEWS
→ NEW_TOPIC
→ CONTROLLED_PRACTICE
→ CONVERSATION
→ OPTIONAL_GATE
→ SESSION_SUMMARY
→ FINISHED
```

`trainer lesson next` должен детерминированно выбирать следующий step из состояния, curriculum, due reviews и policies.

Пример ответа:

```json
{
  "session_id": "session-2026-07-20-001",
  "state": "REQUIRED_REVIEWS",
  "action": "run_review",
  "required_skill": {
    "name": "run-spaced-review",
    "version": "1.0.0"
  },
  "topic_id": "grammar.past-simple.irregular-verbs",
  "minimum_items": 8,
  "new_topic_locked": true,
  "expected_output_schema": "schemas/review-result.schema.json"
}
```

Запрети переход в `FINISHED`, если отсутствуют обязательные reviews, summary, persistence или tutor audit data.

## 14. Markdown memory

После завершения урока детерминированно генерируй:

```text
memory/learner-profile.md
memory/current-level.md
memory/roadmap-progress.md
memory/recurring-errors.md
memory/learned-chunks.md
memory/learned-vocabulary.md
memory/test-history.md
memory/next-session.md
memory/sessions/YYYY/YYYY-MM-DD.md
```

Генератор должен иметь stable ordering и идемпотентный output. Добавь `trainer memory check`, который завершается ошибкой при drift между SQLite/events и Markdown.

## 15. SQLite, events и Git snapshots

Используй SQLite для operational queries и транзакций. Используй append-only JSONL event log для аудита и replay.

Требования:

- migrations;
- foreign keys;
- unique idempotency keys;
- integrity check;
- deterministic replay;
- snapshot только после commit/checkpoint SQLite;
- не добавлять `-wal` и `-shm` в Git;
- сохранить generated Markdown рядом со snapshot;
- не пытаться реализовать multi-device merge.

Если полное event-sourcing слишком велико для первой итерации, реализуй минимально достаточный event log и честно задокументируй projection boundary. Но `scoring replay` должен работать.

## 16. Методика преподавания

Закодируй в skills и policies:

- American English;
- practice first, theory second;
- короткие объяснения;
- постоянное производство английского учеником;
- понятный язык текущего уровня;
- краткая русская поддержка;
- active recall;
- immediate reuse исправленной конструкции;
- mixed practice;
- work contexts AI/AEC/SaaS;
- умение объяснять сложные идеи просто.

Correction protocol:

```text
You said: ...
Correct: ...
More natural: ...
Why: коротко по-русски
Next: немедленная новая попытка
```

## 17. GitHub references

Перед копированием любого кода или данных проверь LICENSE в конкретной revision и сохрани attribution. Не импортируй материалы с неясной лицензией. Используй источники прежде всего как references:

### OpenVLT

<https://github.com/englishcentral/ovlt>

- MIT;
- reference для vocabulary placement, IRT и adaptive testing;
- vocabulary score не считать полным CEFR level.

### CEFR-J English Profiles

<https://github.com/openlanguageprofiles/olp-en-cefrj>

- vocabulary/grammar profiles по CEFR;
- использовать для curriculum blueprint и сложности items;
- соблюдать attribution и отдельные условия C1/C2.

### CEFR-SP

<https://github.com/yukiar/CEFR-SP>

- 17k CEFR-annotated sentences;
- использовать как research reference;
- не импортировать dataset без подтверждённой лицензии.

### TOEFL-QA

<https://github.com/iamyuanchung/TOEFL-QA>

- 963 listening/question-answering examples;
- research reference для listening comprehension;
- не является актуальным full TOEFL 2026;
- не импортировать без license review.

### TOEFL iBT simulator

<https://github.com/hezretaly/toefl>

- MIT;
- reference для architecture, timers и section/task separation;
- обязательно сверять с текущим TOEFL 2026.

### Repeater

<https://github.com/shaankhosla/repeater>

- Apache-2.0;
- Markdown-first cards, SQLite и FSRS;
- reference для scheduler и human-readable source of truth.

### Fluent

<https://github.com/m98/fluent>

- MIT;
- reference для language-learning skills, hooks, active recall и progress tracking;
- не связывать нашу реализацию только с Claude Code.

Официальные TOEFL 2026 источники являются главным эталоном формата:

- <https://www.ets.org/toefl/test-takers/ibt/about/content.html>
- <https://www.ets.org/toefl/test-takers/ibt/scores/understand-scores.html>
- <https://www.ets.org/toefl/test-takers/ibt/prepare.html>

Не копируй закрытые вопросы ETS. Создавай собственные аналогичные task types.

## 18. Repo guidance

Создай:

- `AGENTS.md` для Codex;
- `CLAUDE.md` для Claude Code;
- общий `config/agent-policy.yaml` как каноническую policy;
- проверку отсутствия semantic drift между provider guidance;
- команды setup, test, lint, typecheck и validation;
- архитектурные decision records только для действительно важных решений.

`AGENTS.md` и `CLAUDE.md` должны требовать:

- читать состояние через CLI;
- не редактировать progress напрямую;
- запускать required skill;
- записывать evidence;
- завершать урок только через CLI;
- не менять curriculum без `maintain-english-curriculum`;
- запускать релевантные тесты после изменений.

## 19. Tests и CI

Создай unit и integration tests минимум для:

- prerequisite graph;
- unlock rules;
- scoring bounds и caps;
- scheduling;
- Retrievability decay;
- idempotent attempt submission;
- valid/invalid state transitions;
- gate evaluation;
- event append и replay;
- Markdown rendering;
- SQLite integrity;
- skill sync и drift detection;
- Codex/Claude parity;
- complete vertical lesson flow;
- second provider continuation without prior chat context.

Добавь CI workflow, который выполняет:

```bash
pytest
ruff check .
ruff format --check .
trainer curriculum validate
trainer skills validate
trainer adapters compare
trainer database check
trainer memory check
trainer scoring replay
```

Если type checker настроен, добавь его в CI.

## 20. Required vertical demo

Создай fixtures или demo script, доказывающий:

1. Создание learner profile.
2. Placement assessment с deterministic seed.
3. Получение отдельного score по skills и working CEFR estimate.
4. Старт двухчасового урока с provider `codex`.
5. Обязательное повторение Past Simple.
6. Разблокировка или блокировка Present Perfect по prerequisites.
7. Запись нескольких attempts и observed errors.
8. Conversation evidence на тему SaaS/project update.
9. Gate evaluation.
10. Завершение урока и генерация Markdown.
11. Старт следующего урока с provider `claude` без старого chat context.
12. Получение корректного следующего шага.
13. Replay scoring и database integrity check.

Предоставь команду, запускающую demo без внешнего API и без сетевого доступа.

## 21. Definition of Done

Не объявляй работу завершённой, пока:

- CLI устанавливается и запускается;
- vertical demo работает;
- тесты проходят;
- lint проходит;
- curriculum validation проходит;
- skills синхронизируются и валидируются;
- Codex/Claude adapters не расходятся;
- scoring replay воспроизводим;
- Markdown memory создаётся детерминированно;
- README содержит точные setup и demo commands;
- известные ограничения перечислены честно;
- diff проверен на случайно добавленные secrets, generated junk и SQLite WAL files.

## 22. Формат выполнения работы

Работай итеративно:

1. Inspect.
2. Plan.
3. Scaffold.
4. Implement core domain.
5. Implement CLI vertical slice.
6. Implement skills and adapters.
7. Implement memory and replay.
8. Add fixtures/demo.
9. Test and fix.
10. Review final diff.

В конце сообщи:

- что реализовано;
- какие команды запускать;
- результаты тестов;
- какие архитектурные решения приняты;
- какие ограничения остались;
- какой следующий increment рекомендуется.

---

Конец master prompt.
