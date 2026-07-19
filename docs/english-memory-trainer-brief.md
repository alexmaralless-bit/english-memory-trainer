# English Memory Trainer — продуктовый бриф MVP

Версия: 1.0  
Дата: 19 июля 2026  
Статус: согласованный бриф для проектирования и реализации MVP

## 1. Краткое описание

English Memory Trainer — локальное Python-приложение для системного изучения американского английского с помощью сменяемых AI-преподавателей, прежде всего Codex и Claude Code.

Приложение должно работать так, будто преподаватель меняется после каждого урока, но новый преподаватель всегда знает:

- полную программу обучения;
- текущий CEFR-уровень ученика;
- изученные и заблокированные темы;
- зависимости между темами;
- результаты тестов и гейтов;
- баллы по каждой теме и навыку;
- расписание повторений;
- изученные слова и устойчивые выражения;
- повторяющиеся ошибки;
- историю уроков, пропусков, XP и штрафов;
- точный обязательный план следующего занятия.

Контекст диалога с LLM считается временным и ненадёжным. Ни Codex, ни Claude не являются источником истины. Состояние обучения хранится локально в репозитории в Markdown, SQLite, YAML/JSON и append-only журнале событий.

## 2. Пользователь и цель

Ученик — русскоязычный IT-профессионал уровня примерно strong beginner / early intermediate. Стартовый уровень должен быть подтверждён диагностикой.

Основные цели:

1. Свободно и автоматически строить фразы на американском английском.
2. Понимать живую речь.
3. Работать в американской IT-компании.
4. Общаться на темы AI, AEC, SaaS, продуктов, данных и технического сотрудничества.
5. Подготовиться к TOEFL после формирования достаточной общей базы.

Плановая нагрузка — 2 часа ежедневно.

## 3. Главный архитектурный принцип

> LLM — сменяемый исполнитель роли преподавателя. Python-движок — единственный управляющий орган. Репозиторий и локальные данные — долговременная память.

AI-преподаватель не должен самостоятельно:

- выбирать следующую тему вне выданного плана;
- разблокировать темы;
- рассчитывать Mastery;
- менять CEFR-уровень;
- назначать следующий интервал повторения;
- объявлять gate пройденным;
- напрямую редактировать SQLite;
- завершать урок без обязательной фиксации результатов.

Агент выполняет учебную работу через skills и Python CLI. Все изменения состояния валидирует и применяет learning engine.

## 4. Границы MVP

### Входит в MVP

- local-first Python CLI;
- Git-репозиторий;
- SQLite;
- append-only event log;
- Markdown-память;
- curriculum graph с prerequisites;
- базовая структура CEFR A1–C2;
- рабочее наполнение для вертикального среза A1–A2;
- placement test MVP;
- module gates и level gates;
- интервальные повторения;
- Mastery, Stability и Retrievability;
- геймификация, streak и штрафы;
- skills для Codex и Claude Code;
- обязательная state machine урока;
- structured evidence;
- Tutor Compliance Score;
- тесты целостности и CI;
- возможность безопасно модернизировать curriculum, scoring и skills по ходу реального обучения.

### Не входит в MVP

- MCP;
- веб-интерфейс или мобильное приложение;
- синхронизация между устройствами;
- многопользовательский режим;
- облачная база;
- полное авторское наполнение всех тем A1–C2;
- заявление о сертифицированной психометрической точности CEFR;
- копирование закрытых или защищённых экзаменационных материалов;
- автоматическая регистрация или сдача TOEFL.

## 5. Слои памяти

### 5.1 Стратегическая память

Хранит:

- CEFR-роадмап;
- tracks, modules, topics и skills;
- prerequisite graph;
- правила scoring;
- правила scheduling;
- gate policies;
- rubrics;
- форматы уроков;
- правила поведения преподавателя.

Формат: version-controlled YAML и Markdown.

### 5.2 Операционная память ученика

Хранит:

- попытки;
- evidence;
- оценки;
- состояния тем;
- даты повторений;
- тестовые результаты;
- XP, streak и штрафы;
- историю вызова agent skills;
- сессии и их state machine.

Формат: SQLite.

### 5.3 Аудит и восстановление

Каждое значимое действие записывается в append-only JSONL event log. Система должна уметь проверить соответствие SQLite журналу и при необходимости пересоздать read models.

Примеры событий:

- `LESSON_STARTED`;
- `SKILL_REQUIRED`;
- `SKILL_COMPLETED`;
- `REVIEW_COMPLETED`;
- `ATTEMPT_RECORDED`;
- `ERROR_OBSERVED`;
- `VOCABULARY_ADDED`;
- `GATE_PASSED`;
- `GATE_FAILED`;
- `TOPIC_UNLOCKED`;
- `LESSON_COMPLETED`;
- `SESSION_MISSED`;
- `XP_PENALTY_APPLIED`.

### 5.4 Читаемая память преподавателя

Markdown генерируется из состояния после каждого завершённого урока:

```text
memory/
├── learner-profile.md
├── current-level.md
├── roadmap-progress.md
├── recurring-errors.md
├── learned-chunks.md
├── learned-vocabulary.md
├── test-history.md
├── next-session.md
└── sessions/YYYY/YYYY-MM-DD.md
```

Новый агент должен получить достаточную картину из CLI и этих файлов, не обращаясь к старому диалогу.

## 6. Curriculum model

Иерархия:

```text
CEFR level
└── Track
    └── Module
        └── Topic
            └── Skill dimension
                └── Exercise / Review / Gate
```

Основные tracks:

1. Grammar Engine.
2. Vocabulary and Chunks.
3. Speaking.
4. Listening and Pronunciation.
5. Reading.
6. Writing.
7. US Tech English.
8. TOEFL Preparation.

У каждой темы должны быть:

- стабильный `topic_id`;
- CEFR-уровень;
- обязательные и мягкие prerequisites;
- связанные темы;
- required dimensions;
- критерии unlock;
- критерии mastery;
- retention requirements;
- список типичных ошибок;
- версии контента и scoring policy.

Пример:

```yaml
id: grammar.present-perfect.result
title: Present Perfect for present results
cefr: A2
prerequisites:
  hard:
    - grammar.have-has
    - grammar.past-participle
  soft:
    - grammar.past-simple
required_dimensions:
  recognition: 75
  controlled_production: 75
  listening: 70
  spontaneous_speaking: 75
mastery_threshold: 85
retention_checks: [7d, 30d, 90d]
```

Нельзя начинать полноценное изучение темы, пока не закрыты hard prerequisites. Допускается раннее знакомство без начисления mastery.

## 7. Scoring

### 7.1 Учебные показатели

Для каждой темы отслеживаются:

- `Mastery` — качество владения, 0–100;
- `Stability` — предполагаемая устойчивость знания в днях;
- `Retrievability` — вероятность воспроизведения сейчас;
- баллы по skill dimensions;
- количество независимых попыток;
- количество попыток с подсказками;
- даты и результаты retention checks.

Одна удачная попытка не может мгновенно поднять тему до Mastered. Прирост за одну сессию ограничивается. Оценка должна учитывать:

- сложность задания;
- самостоятельность;
- режим: recognition, writing, listening, prepared или spontaneous speaking;
- использование подсказок;
- повторяемость результата;
- временной интервал;
- тип и серьёзность ошибки.

### 7.2 Состояния темы

- `LOCKED`;
- `AVAILABLE`;
- `INTRODUCED`;
- `LEARNING`;
- `ACTIVE`;
- `MASTERED`;
- `REVIEW_DUE`;
- `AT_RISK`.

Mastered не означает «больше не повторять». После снижения Retrievability тема возвращается в review queue.

### 7.3 Разделение знаний и дисциплины

Штрафы за пропуски не должны искусственно снижать CEFR или Mastery.

Показываются отдельно:

- `Learning Score` — агрегированное владение программой;
- `Season XP` — дисциплина, выполненные планы, бонусы и штрафы;
- `Tutor Compliance Score` — соблюдение программы AI-преподавателем.

Штраф Season XP можно компенсировать recovery session или дополнительными повторениями.

## 8. Интервальные повторения

Начальная последовательность:

```text
1 → 3 → 7 → 14 → 30 → 60 → 120 → 180 дней
```

Интервал адаптируется по результату. Архитектура должна позволять позже заменить простую формулу на полноценный FSRS без изменения доменной модели и истории событий.

Повторение бывает:

- явным тестом;
- active recall;
- контролируемым упражнением;
- скрытым использованием в свободном разговоре;
- listening recognition;
- переносом темы в новый профессиональный контекст.

Если overdue backlog превышает лимит, gate новой темы блокируется до recovery.

## 9. Гейты ученика

### Topic gates

1. Recognition.
2. Controlled Production.
3. Conversation.
4. Transfer to a new context.
5. Retention after time intervals.

### Module gate

Проверяет объединённое использование нескольких тем, а не сумму изолированных тестов.

### CEFR boundary gates

Размещаются между:

- A1 → A2;
- A2 → B1;
- B1 → B2;
- B2 → C1;
- C1 → C2.

Ключевой level gate выполняется минимум в два разных дня. Общий уровень не должен скрывать слабые навыки: система хранит отдельные уровни Grammar, Vocabulary, Reading, Listening, Writing и Speaking.

## 10. Диагностика уровня

Initial Placement Test запускается при onboarding, после длительного перерыва или при сомнении в уровне.

Предварительные веса:

| Раздел | Вес |
|---|---:|
| Grammar | 15% |
| Vocabulary | 15% |
| Reading | 15% |
| Listening | 20% |
| Writing | 15% |
| Speaking | 20% |

Объективные задания оцениваются кодом. Writing и Speaking оцениваются по versioned rubric, с сохранением исходного ответа, объяснением оценки и несколькими независимыми попытками.

Тест MVP является внутренней CEFR-aligned диагностикой, а не официальной сертификацией.

## 11. Skills AI-преподавателя

Skills — процедурная память. Curriculum определяет, чему учить; skill определяет, как агент обязан действовать.

Обязательные skills MVP:

1. `run-english-session` — оркестратор урока.
2. `run-placement-assessment` — начальная и повторная диагностика.
3. `run-spaced-review` — интервальное повторение.
4. `teach-english-topic` — короткое объяснение и активная практика.
5. `coach-english-conversation` — свободное общение на доступном американском английском.
6. `correct-learner-output` — единый формат исправления.
7. `assess-english-gate` — формальная проверка без подсказок.
8. `finish-english-session` — обязательное сохранение результатов.
9. `audit-english-tutor` — проверка соблюдения плана.
10. `maintain-english-curriculum` — безопасное развитие программы.

Skills хранятся канонически в `agent-skills/` и синхронизируются Python-командой в:

- `.agents/skills/` для Codex;
- `.claude/skills/` для Claude Code.

В MVP не используется MCP. Каждый skill вызывает Python CLI. Session Manifest явно перечисляет required skills и их версии. Агент не может полагаться только на implicit invocation.

Каждый skill должен иметь тесты:

- trigger tests;
- workflow tests;
- forbidden behavior tests;
- persistence tests;
- cross-provider parity tests.

## 12. CLI как единый интерфейс

Основные команды:

```bash
trainer doctor
trainer status --format json
trainer lesson start --duration 120 --provider codex --format json
trainer lesson next --session SESSION_ID --format json
trainer attempt record --session SESSION_ID --input attempt.json
trainer gate begin --session SESSION_ID --topic TOPIC_ID
trainer gate submit --session SESSION_ID --input evidence.json
trainer gate evaluate --session SESSION_ID --topic TOPIC_ID
trainer lesson finish --session SESSION_ID
trainer memory render
trainer audit session SESSION_ID
trainer curriculum validate
trainer skills sync
trainer skills validate
trainer database check
trainer scoring replay
```

CLI должен:

- возвращать JSON для agent-facing команд;
- использовать стабильные exit codes;
- валидировать input через схемы;
- быть идемпотентным там, где это возможно;
- использовать транзакции;
- блокировать недопустимые state transitions;
- выдавать объяснимые ошибки и next actions.

## 13. State machine урока

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

`trainer lesson next` является основным маршрутизатором. Он возвращает:

- следующее действие;
- обязательный skill;
- тему;
- минимальный объём;
- ограничения;
- ожидаемый output schema;
- причины блокировки.

Урок нельзя завершить, пока не выполнены обязательные postconditions.

## 14. Формат двухчасового урока

Базовый шаблон:

| Блок | Время |
|---|---:|
| Разогрев и retrieval | 10 минут |
| Просроченные повторения | 25 минут |
| Новая тема | 20 минут |
| Контролируемая практика | 25 минут |
| Свободный разговор | 30 минут |
| Проверка и сохранение | 10 минут |

Шаблон адаптируется. При большом backlog новая тема может быть заменена recovery practice.

Методика:

- практика раньше теории;
- короткие объяснения на русском только при необходимости;
- основное взаимодействие на понятном американском английском;
- ученик производит большую часть языка;
- рабочие контексты AI, AEC и SaaS;
- исправление сразу используется в новой фразе;
- сложные идеи объясняются простыми словами.

## 15. TOEFL

С 21 января 2026 года TOEFL iBT использует шкалу 1–6 с шагом 0,5 и привязкой к CEFR; в переходный период также показывается сопоставимый результат 0–120. Актуальный экзамен включает Reading, Listening, Writing и Speaking и занимает примерно два часа.

Официальные источники:

- формат: <https://www.ets.org/toefl/test-takers/ibt/about/content.html>
- scoring: <https://www.ets.org/toefl/test-takers/ibt/scores/understand-scores.html>
- подготовка: <https://www.ets.org/toefl/test-takers/ibt/prepare.html>

TOEFL-трек вводится постепенно примерно с B1, а полноценные экзаменационные симуляции — после стабилизации общей базы B1/B2. Старые тесты нельзя считать точной симуляцией формата 2026.

## 16. GitHub-референсы

Эти проекты служат источниками архитектурных идей, открытых профилей или дополнительных данных. Перед импортом контента обязательно проверить актуальную лицензию и attribution requirements.

### OpenVLT

<https://github.com/englishcentral/ovlt>

- MIT;
- открытый vocabulary level test;
- CEFR-aligned;
- использует идеи Item Response Theory и computer-adaptive testing;
- пригоден как reference или компонент vocabulary placement;
- не измеряет весь CEFR-уровень.

### CEFR-J English Profiles

<https://github.com/openlanguageprofiles/olp-en-cefrj>

- CEFR-размеченные vocabulary и grammar profiles;
- можно использовать для проектирования curriculum и item blueprints;
- требуется корректное цитирование;
- C1/C2 subset имеет отдельную CC BY-SA 4.0 лицензию.

### CEFR-SP

<https://github.com/yukiar/CEFR-SP>

- около 17 000 предложений, размеченных специалистами по CEFR;
- пригоден для анализа и калибровки сложности;
- не импортировать данные в MVP до отдельной проверки лицензии.

### TOEFL-QA

<https://github.com/iamyuanchung/TOEFL-QA>

- 963 примера question answering для spoken-content comprehension;
- пригоден как research reference для listening tasks;
- не является полным или актуальным TOEFL 2026;
- не копировать данные до проверки лицензии.

### TOEFL iBT Test Simulator

<https://github.com/hezretaly/toefl>

- MIT;
- full-stack reference симулятора Reading, Listening, Speaking и Writing;
- можно изучить архитектуру, таймеры и разделение task types;
- содержание и формат необходимо сверять с TOEFL 2026.

### Repeater

<https://github.com/shaankhosla/repeater>

- Apache-2.0;
- Markdown-first spaced repetition;
- SQLite progress tracking;
- FSRS и целевая вероятность recall;
- полезный reference для scheduling и human-readable cards.

### Fluent

<https://github.com/m98/fluent>

- MIT;
- language-learning kit для Claude Code;
- spaced repetition, active recall, hooks, skills и progress tracking;
- использовать как reference для agent workflow;
- наша система должна оставаться provider-neutral и иметь более строгий Python gate engine.

## 17. Предлагаемая структура репозитория

```text
english-memory-trainer/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── agent-skills/
├── .agents/skills/
├── .claude/skills/
├── curriculum/
│   ├── graph.yaml
│   ├── A1/
│   ├── A2/
│   ├── B1/
│   ├── B2/
│   ├── C1/
│   ├── C2/
│   ├── TOEFL/
│   └── assessments/
├── config/
│   ├── scoring.yaml
│   ├── scheduling.yaml
│   ├── gates.yaml
│   └── agent-policy.yaml
├── memory/
├── state/
│   ├── learning.sqlite3
│   ├── events.jsonl
│   └── snapshots/
├── schemas/
├── src/english_trainer/
│   ├── cli/
│   ├── domain/
│   ├── curriculum/
│   ├── scoring/
│   ├── scheduler/
│   ├── gates/
│   ├── lessons/
│   ├── assessments/
│   ├── skills/
│   ├── storage/
│   ├── memory/
│   └── audit/
└── tests/
    ├── unit/
    ├── integration/
    ├── curriculum/
    ├── skills/
    └── cross_provider/
```

## 18. CI и качество

Минимальные проверки:

```bash
pytest
trainer curriculum validate
trainer skills validate
trainer database check
trainer memory check
trainer scoring replay
trainer adapters compare
```

CI проверяет:

- отсутствие циклов и битых prerequisites;
- стабильность topic IDs;
- валидность schemas;
- deterministic scoring replay;
- соответствие Markdown текущему состоянию;
- целостность SQLite и event log;
- совпадение канонических skills для Codex и Claude;
- недопустимые state transitions;
- обратную совместимость migrations.

## 19. Definition of Done для MVP

MVP считается готовым, когда с чистого репозитория можно выполнить следующий сценарий:

1. Инициализировать профиль ученика.
2. Провести placement test MVP.
3. Получить skill-level и общий стартовый CEFR estimate.
4. Сгенерировать детерминированный двухчасовой Session Manifest.
5. Провести урок через обязательные skills и CLI.
6. Записать объективные и rubric-based attempts.
7. Изменить Mastery только через scoring engine.
8. Назначить повторения.
9. Закрыть урок только после выполнения postconditions.
10. Обновить SQLite, event log и Markdown.
11. Начать новую сессию другим provider и получить правильное продолжение.
12. Полностью воспроизвести scoring из событий.
13. Пройти все unit, integration, curriculum и cross-provider tests.

## 20. Принцип развития после MVP

Система развивается во время реального обучения:

- ошибки преподавателя превращаются в новые agent rules или skill tests;
- недостатки curriculum исправляются versioned migrations;
- scoring изменяется только с replay старых событий;
- новые CEFR-модули добавляются после проверки предыдущего шаблона;
- контент TOEFL обновляется по официальным материалам ETS;
- ни одна модернизация не должна терять историю ученика.

