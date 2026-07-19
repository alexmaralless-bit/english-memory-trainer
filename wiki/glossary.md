# Глоссарий

> **Status**: living
> **Last updated**: 2026-07-19

Термины определяются здесь один раз (Принцип 3) и везде используются по имени. Новый термин сначала вводится сюда, потом в спеки. Где термин — machine-ID (enum/поле схемы), он записан `code`-шрифтом; человекочитаемая подпись даётся отдельно.

## Участники

- **Ученик** — русскоязычный IT-профессионал, изучающий американский английский для работы, переписки и TOEFL.
- **Преподаватель (агент)** — LLM-агент (Codex или Claude Code), ведущий сессию. Сменяемый исполнитель роли; не источник истины о прогрессе.
- **Движок** — Python-приложение, единственный управляющий орган: владеет состоянием, scoring, расписанием и рекомендациями.

## Curriculum

- **Тема (Topic)** — единица curriculum со стабильным ID вида `grammar.present-perfect.result`.
- **LearningTarget** — то, что можно осваивать и оценивать: `Topic | LexicalItem`. Mastery, Stability, Retrievability, состояния и review определены для любого LearningTarget.
- **Can-do** — формулировка темы как наблюдаемого умения («Report a completed action that matters now»); обязательна у каждой темы.
- **Skill dimension** — измерение владения. Machine-ID и подписи: `recognition` (узнавание), `controlled_production` (применение в упражнении), `spontaneous_production` (самостоятельное письменное употребление), `transfer` (перенос в новый контекст). Текстовые модальности MVP.
- **Track** — сквозной трек программы через уровни; их восемь, включая Everyday, Online & Informal English и TOEFL R&W (с B1).
- **Curriculum graph** — DAG тем с prerequisites. Карта и источник рекомендаций, не система замков; сила prerequisite — `strong` / `soft` (не «hard»).
- **CurriculumVersion** — версионируемый снимок программы; evidence и сессии pin-ят версию, под которой созданы (см. [[OPEN]] OPEN-9).
- **Level** — CEFR-уровень (A1…C2) с главным can-do результатом.
- **Module** — группа тем уровня вокруг рабочей задачи (`a2.2-results-and-experience`).

## Состояния и исходы (нормативно)

Состояние LearningTarget разложено на **три независимые оси** (rereview D-R1) — один enum их не смешивает:

**1. Enrollment** — взят ли элемент в личное отслеживание: `not_tracked` / `tracked`. Enrollment-триггеры (просьба запомнить, пометка «полезно», первое предъявление) переводят в `tracked` при Mastery 0 — это **не** доказательство знания.

**2. Knowledge state** — отражает знание, меняется только движком по evidence:

- `NEW` — ещё нет допустимого evidence (для tracked-элемента — «взят, но знания не показал»).
- `LEARNING` — есть первые попытки, владение формируется.
- `ACTIVE` — устойчивые результаты по required dimensions.
- `MASTERED` — критерии mastery выполнены и подтверждены retention во времени.
- `AT_RISK` — подтверждённый REGRESSION **или** просрочка вышла за порог ([[OPEN]] OPEN-18). Лёгкий/неподтверждённый regression опускает в `LEARNING`, не в `AT_RISK` (rereview D-R2).

`REVIEW_DUE` устранён из knowledge state (rereview D-R1): наступление интервала выражается осью review status. Восстановление после подтверждения хранит `prior_steady_state` ∈ {ACTIVE, MASTERED} (learning-model §4).

**3. Review status (scheduling)** — служебная ось, управляется часами и scheduler, не evidence: `not_due` / `due` / `overdue`. Сброс в `not_due` — после успешного review или назначения нового интервала. Просрочка сверх порога переводит knowledge state в `AT_RISK` по versioned policy (OPEN-18).

**Review outcome** — классификация результата повторения (machine-ID):

- `PROGRESS` — заметное улучшение, но не подтверждение.
- `CONFIRMED` — знание подтверждено на ожидаемом уровне.
- `REGRESSION` — знание просело относительно прежнего.
- `RECOVERED` — восстановление после AT_RISK/REGRESSION.
- `INSUFFICIENT_EVIDENCE` — попытки не дают основания для вывода (в т.ч. `reason=abandoned`).

## Оценивание

- **Attempt** — одна попытка ученика (ответ, фраза, упражнение). Имеет lifecycle и finalization: незавершённый (draft) attempt не участвует в scoring до финализации (механизм — [[OPEN]] OPEN-10).
- **Evidence** — сохранённое свидетельство владения: исходный ответ + контекст + оценка + версии policy/rubric + идентичность (source-span, item-exposure). Каждая оценка обязана иметь evidence; упоминание темы — не evidence. Один source-span засчитывается не более раза на target/dimension ([[OPEN]] OPEN-7). Raw answer в MVP предоставляет агент как **trusted reporter** (untrusted-захват — post-mvp, [[OPEN]] OPEN-7).
- **AttemptAssessment** — оценка отдельного attempt (может быть несколько на один `review_id`). **Не** терминальна.
- **ReviewOutcome** — единственный терминальный исход ReviewAssignment (см. Review outcome выше), вычисляется движком в определённый момент закрытия (rereview A-R1, [[OPEN]] OPEN-10), не совпадает с per-attempt оценкой.
- **Mastery** — качество владения LearningTarget, 0–100. Меняется только scoring engine.
- **Stability** — предполагаемая устойчивость знания в днях.
- **Retrievability** — вероятность воспроизведения сейчас, 0–1.
- **ReviewAssignment** — конкретное задание на повторение в Session Manifest: `review_id`, целевой LearningTarget (**ReviewTarget**), dimension, режим, критерии. Имеет ровно один ReviewOutcome.
- **Review** — процесс повторения LearningTarget; исход — ReviewOutcome.
- **Confidence** — уверенность движка в оценке; machine-ID enum `very_low | low | medium | high` (отдельно от UI-подписей вида «low-confidence»). Повышается rolling-уточнением.
- **self_reported_level** — самооценка ученика (напр. при отказе от placement). Provisional working estimate, хранится **отдельно** от измеренного уровня; замещается измерением **per-skill** после первого допустимого evidence/confidence floor этого навыка; provenance сохраняется ([[OPEN]] resolved A-R3).
- **Working level** — вычисленный рабочий CEFR-уровень (по навыкам и общий), консервативно относительно слабейшего core-навыка; ordinal/sublevel-представление — [[OPEN]] OPEN-8.
- **Core skill** — базовые навыки, ограничивающие общий уровень: Grammar, Vocabulary, Reading, Writing.
- **Session Summary** — итог сессии, генерируется движком после commit finish (агент может передать `summary_draft`).
- **Gate** — добровольная формальная проверка готовности (topic/module/CEFR boundary). Рекомендация, не барьер.
- **Placement** — внутренняя CEFR-aligned диагностика стартового уровня (текстовые модальности), ~30–40 мин, с rolling-уточнением. Потолок: не выше ACTIVE, никогда MASTERED.
- **Re-entry протокол** — после длительного перерыва движок рекомендует начать сессию с быстрого повторения или короткого теста остаточных знаний; отказ допустим и не штрафуется.

## Лексика

- **Chunk** — устойчивое выражение/фраза, изучаемая как целое.
- **LexicalItem** — единица учебного лексикона со стабильным ID: слово, chunk, phrasal verb или lexeme. Тип informal-единицы: `informal_chunk` / `abbreviation` / `meme_template`.
- **Lexeme** — LexicalItem с формами (`go / went / gone` — один lexeme); владение агрегируется из evidence по required forms детерминированно ([[OPEN]] OPEN-14).
- **corpus_frequency / `frequency_band`** — **только** корпусная частота: numeric score (Zipf/source) + нейтральные band'ы `very_high | high | mid | low | rare` по versioned thresholds. Не содержит педагогических/доменных категорий (rereview E-R5).
- **curriculum_priority_band** — педагогический приоритет в программе: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL`. Policy output, не частота (сюда ушли utility/domain-категории).
- **learner_priority** — персональный приоритет для конкретного ученика (учитывает личную потребность); вычисляется, не хранится как глобальное поле.
- **production_eligible** — вычисляемый признак «можно ли предъявлять как production сейчас» из active `usage_policy` + `currency` (`avoid`/`recognition_only`/`obsolete` → false). Всегда по active policy, не пинится (safety-overlay, [[OPEN]] OPEN-14).
- **LexicalMasteryProfile** — versioned профиль required dimensions и mastery-критериев для LexicalItem по type/usage_policy (обычный word/chunk тоже; [[OPEN]] OPEN-13).
- **volatility** — устойчивость единицы: `stable` / `changing`. Отделена от currency.
- **currency** — актуальность изменчивой единицы: `current` / `dated` / `obsolete`, с датами наблюдения/проверки и владельцем reverification ([[OPEN]] OPEN-14).
- **usage_policy** — политика употребления: `safe_to_use` / `context_dependent` / `recognition_only` / `avoid`. Понимать ≠ употреблять; assessable dimensions зависят от policy.
- **contribution_scope** — тег evidence, определяющий, куда оно засчитывается (informal-профиль / writing / transfer / core CEFR). Разделяет informal recognition (никогда не в CEFR) и письменное производство в рабочем контексте.
- **Личный словарь (LearnerLexicalState)** — индивидуальное состояние LexicalItem: evidence по recognition/production раздельно, ошибки, Mastery/Stability/Retrievability, три оси состояния как выше. «Выучено» — не boolean; вход по критериям — но **сам вход даёт только enrollment**: evidence появляется лишь при отдельном сохранённом learner response, объяснение агента evidence не создаёт (rereview C-R2).
- **Stable core / living layer** — каталоги лексикона: спроектированный заранее / пополняемый из обучения (мемы, сленг) с provenance.
- **Informal Online Competence** — отдельный профиль владения неформальным письменным английским; не двигает CEFR напрямую (отдельная шкала — [[OPEN]] OPEN-13).

## Метрики

- **Learning Score** — агрегированное владение программой (шкала — [[OPEN]] OPEN-12).
- **XP** — очки за практику: выполненные задания, evidence, закрытые повторения, re-entry. **Штрафов и списаний нет**; начисление award-once по уникальному source event ([[OPEN]] OPEN-12).
- **Season** — период агрегации XP (отображение), не отдельная механика со штрафами.
- **Streak** — счётчик подряд идущих дней практики по локальной календарной дате ученика; прерывание обнуляет счётчик, накопленный XP не сгорает.
- **Tutor Compliance Score** — соблюдение программы AI-преподавателем (шкала — [[OPEN]] OPEN-12).

## Система

- **Сессия** — одно занятие. Жизненный цикл: `STARTED → IN_PROGRESS → FINISHED | ABANDONED` (переход `STARTED → ABANDONED` допустим). Внутренняя структура свободная; обязательна фиксация результатов при завершении. `ABANDONED` сохраняет и учитывает всё зафиксированное и атомарно закрывает pending цели.
- **Session Manifest** — сформированный движком план сессии: tutor briefing, рекомендации тем, ReviewAssignment'ы, required skills с версиями; pin-ит версии curriculum/policy.
- **Tutor briefing** — полная картина ученика одним JSON в манифесте/resume. Генерится из состояния движка, не из Markdown.
- **Session notes** — опциональные короткие заметки агента (`--note`). **Untrusted non-evidence**: экранируются в briefing, не интерпретируются как state.
- **Event log** — append-only JSONL журнал DomainEvents; источник истины для learning-состояния и replay ([[platform/foundation]]).
- **Command / DomainEvent envelope** — конверт мутации/факта: `id, type, occurred_at (UTC), actor/provider, correlation_id, causation_id, idempotency_key, pinned_versions, payload_hash` ([[platform/foundation]] §3.3).
- **pinned_versions** — зафиксированные в конверте версии policy (curriculum/scoring/scheduler/generation/rubric), под которыми создан факт; replay резолвит по ним, не по active. Safety (`production_eligible`) — исключение, резолвится по active.
- **Unit of Work** — атомарный commit authoritative state + events + outbox одной транзакцией.
- **Transactional outbox** — надёжная post-commit доставка проекций (Obsidian, внешние) с retry/rebuild; сбой проекции не откатывает commit.
- **Policy registry** — реестр иммутабельных версионируемых policy-снимков, адресуемых по id.
- **Snapshot** — резервная копия SQLite (после checkpoint) + generated Markdown; операционное состояние не rebuildable из событий, поэтому бэкапится.
- **Learner-память** — генерируемая движком Obsidian-проекция состояния (`memory/`). Читаемая проекция, не источник scoring. Не путать с вики разработки.
- **SourceArtifact** — запись о внешнем источнике данных (id, версия, url, sha256, license, attribution, notices); импортированные единицы ссылаются на него ([[OPEN]] OPEN-15).
- **Skill (агентский)** — процедурная инструкция для агента в `agent-skills/`, синхронизируется в `.agents/skills/` и `.claude/skills/`.

## История изменений

- **2026-07-19 (4)**: добавлены kernel-термины (0.2): Command/DomainEvent envelope, pinned_versions, Unit of Work, transactional outbox, Policy registry, Snapshot; Event log уточнён как источник истины learning-части.
- **2026-07-19 (3)**: rereview — три оси состояния (enrollment / knowledge_state / review_status), REVIEW_DUE устранён (D-R1); AT_RISK синхронизирован (D-R2); AttemptAssessment vs ReviewOutcome (A-R1); confidence machine-enum + self_reported_level per-skill (F-R1/A-R3); frequency_band только numeric+нейтральные bands (E-R5); production_eligible, LexicalMasteryProfile; объяснение агента не evidence (C-R2); trusted-reporter (C-R3).
- **2026-07-19 (2)**: red-team триаж (F-1…F-8) — нормативные knowledge states и review outcomes; XP без штрафов + Season как период; machine-ID dimensions; LearningTarget; ReviewAssignment/Attempt/Summary/Confidence/Working level/core skill; разделены corpus_frequency/curriculum_priority/learner_priority и volatility/currency; contribution_scope; CurriculumVersion/Level/Module; SourceArtifact.
- **2026-07-19**: создан, начальный словарь из брифа и design-direction v0.2.
