# Глоссарий

> **Status**: living
> **Last updated**: 2026-07-22

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
- **Track** — сквозной трек программы через уровни; их десять, включая Everyday Life, Online & Informal Register, Word Formation и TOEFL R&W (с B1, в продукте — [PD-2026-07-21]).
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
- `AT_RISK` — **только** просрочка вышла за порог ([[OPEN]] OPEN-18); вход через событие `OVERDUE_AT_RISK_TRIGGERED`. REGRESSION в `AT_RISK` не переводит никогда — он понижает состояние по тотальной таблице ([[modules/scoring]] §3). Различие: `AT_RISK` — риск забыть от простоя, REGRESSION — продемонстрированная потеря (P0-1).

`REVIEW_DUE` устранён из knowledge state (rereview D-R1): наступление интервала выражается осью review status. Восстановление после подтверждения хранит `prior_steady_state` ∈ {ACTIVE, MASTERED} (learning-model §4).

**3. Review status (scheduling)** — служебная ось, управляется часами и scheduler, не evidence: `not_due` / `due` / `overdue`. Сброс в `not_due` — после успешного review или назначения нового интервала. Просрочка сверх порога переводит knowledge state в `AT_RISK` по versioned policy (OPEN-18).

**Review outcome** — классификация результата повторения (machine-ID):

- `PROGRESS` — заметное улучшение, но не подтверждение.
- `CONFIRMED` — знание подтверждено на ожидаемом уровне.
- `REGRESSION` — знание просело относительно прежнего.
- `RECOVERED` — восстановление **только из `AT_RISK`** (R-2). После REGRESSION состояние уже понижено по таблице, и дальнейший рост классифицируется обычными `PROGRESS`/`CONFIRMED`: отдельного «восстановления после regression» не существует, иначе scheduler двигал бы интервал вперёд при no-op переходе.
- `INSUFFICIENT_EVIDENCE` — попытки не дают основания для вывода (в т.ч. `reason=abandoned`).

## Оценивание

- **Attempt** — одна попытка ученика (ответ, фраза, упражнение). Имеет lifecycle и finalization: незавершённый (draft) attempt не участвует в scoring до финализации (механизм — [[OPEN]] OPEN-10).
- **Evidence** — сохранённое свидетельство владения: исходный ответ + контекст + оценка + версии policy/rubric + идентичность (source-span, item-exposure). Каждая оценка обязана иметь evidence; упоминание темы — не evidence. Один source-span засчитывается не более раза на target/dimension ([[OPEN]] OPEN-7). Raw answer предоставляет агент как **trusted reporter** [PD-2026-07-19]; untrusted-захват user-turn — в продукте, порядок — [[roadmap]] ([[OPEN]] OPEN-7).
- **AttemptAssessment** — оценка отдельного attempt (может быть несколько на один `review_id`). **Не** терминальна.
- **ReviewOutcome** — терминальный **учебный** исход ReviewAssignment (см. Review outcome выше), вычисляемый движком при закрытии по evidence; не совпадает с per-attempt оценкой. Системная отмена `CANCELLED` закрывает assignment, но ReviewOutcome не является.
- **Mastery** — качество владения LearningTarget, 0–100. Меняется только scoring engine.
- **Stability** — предполагаемая устойчивость знания в днях.
- **Retrievability** — вероятность воспроизведения сейчас, 0–1.
- **ReviewAssignment** — конкретное задание на повторение в session aggregate/SessionPlan: `review_id`, целевой LearningTarget (**ReviewTarget**), dimension, режим, критерии. Стартовые assignments отражены в Session Manifest; replan может создать новую композиционную ревизию без мутации Manifest. Имеет ровно одну терминальную диспозицию: ReviewOutcome либо `CANCELLED`.
- **`CANCELLED`** — терминальная системная отмена ReviewAssignment без учебного исхода; не меняет scoring, не назначает retry и не входит в outcome-метрики.
- **Review** — процесс повторения LearningTarget; исход — ReviewOutcome.
- **Confidence** — уверенность движка в оценке; machine-ID enum `very_low | low | medium | high` (отдельно от UI-подписей вида «low-confidence»). Повышается rolling-уточнением.
- **self_reported_level** — самооценка ученика (напр. при отказе от placement). Provisional working estimate, хранится **отдельно** от измеренного уровня; замещается измерением **per-skill** после первого допустимого evidence/confidence floor этого навыка; provenance сохраняется ([[OPEN]] resolved A-R3).
- **Working level** — вычисленный рабочий CEFR-уровень: **целые bands** `A1…C2` по каждому core-навыку плюс общий, не выше слабейшего из них. Подуровней и «полступеней» нет (OPEN-8 закрыт, [[modules/scoring]] §4). Различают `measured_working_level` (только из evidence) и `provisional_working_estimate` (с self-report, помечен provisional).
- **Core skill** — базовые навыки, ограничивающие общий уровень: Grammar, Vocabulary, Reading, Writing.
- **Session Summary** — итог сессии, генерируется движком после commit finish (агент может передать `summary_draft`).
- **Gate** — добровольная формальная проверка готовности (topic/module/CEFR boundary). Рекомендация, не барьер.
- **SessionPlan / PlannedStep** — сохранённый состав занятия и его шаг. `composition_revision` меняется при replan; монотонный `plan_version` меняется при каждом успешном `next`/`replan` и служит CAS-токеном. `session peek` возвращает шаг и токен без мутации; `session next` выдаёт шаг тьютору и публикует `STEP_PRESENTED` ([[modules/control]] §4.2).
- **SessionBudget** — непредъявленный остаток намерения **текущей композиционной ревизии** по четырём непересекающимся корзинам `review / growth / integration / choice`; при `next` шаг атомарно переносится отсюда в `DeliveryLedger`. Единица — целые секунды ([[modules/control]] §4.3).
- **DeliveryLedger** — единственный накопительный факт доставки одной сессии: уже выданные секунды по корзинам и остаток общего бюджета. Не обнуляется при replan ([[modules/control]] §4.2).
- **UrgencyClass** — класс review-кандидата: `critical | important | normal | maintenance | deferrable`. Назначается тотальной упорядоченной таблицей; `critical` требует **одновременно** сигнала риска и сигнала ставки ([[modules/control]] §4.5).
- **SaturationState** — признаки перепоказа цели (показы в окне, серия успехов, однообразие контекстов). Влияет на план, **не** на знание ([[modules/control]] §4.6).
- **AvailabilityProfile** — ритм занятий: объявленный учеником и наблюдаемый системой; частота хранится целым `sessions_per_week_milli`. Влияет на состав нагрузки, никогда на Mastery ([[modules/control]] §4.7a).
- **LearnerControlSignal** — сигнал ученика о форме занятий (`too_easy`, `snooze`, …). **Не evidence**; `too_easy` порождает пробу, а не изменение оценки ([[modules/control]] §4.7).
- **DecisionTrace** — сохранённое основание решения планирования: сработавшие правила, прогнозы, версии политик. Доступен по `trainer why` ([[modules/control]] §4.8).
- **TunableParameter** — строка каталога настроек: владелец, диапазон, несущая policy, наблюдающие метрики, режим изменения. Каталог — **реестр метаданных, не хранилище значений** ([[modules/control]] §4.9).
- **PolicyMetric** — versioned определение метрики качества политики: входы, когорта, формула, окно, правило отсутствующих данных ([[modules/control]] §4.10).
- **STEP_PRESENTED** — факт выдачи шага **тьютору**, то есть граница наблюдаемости движка; не утверждает, что ученик увидел экран. Отличается от `SESSION_COMPOSED` (намерение): непредъявленный шаг мог выпасть при replan ([[modules/control]] §4.6). Текст упражнения этим событием не подразумевается: сгенерированный/выбранный контент фиксируется отдельно.
- **EXERCISE_RENDERED** — иммутабельное событие, сохраняющее авторский снапшот упражнения **до** предъявления ученику: `step_id`, `exercise_instance_id`, content hash, targets, dimensions, контекст, лексикон-ссылки, answer key или rubric ref, версии generation/rubric/curriculum и active safety.
- **ExerciseInstance** — один rendered-снапшот упражнения, привязанный к `PlannedStep`. Может обслуживать текущую попытку сразу, но не reusable до приёма в банк.
- **ExerciseBankItem** — переиспользуемое принятое упражнение с provenance, dedup-ключом, ре-валидацией safety, историей использований и append-only lifecycle `generated → accepted/rejected → retired`.
- **Placement** — внутренняя CEFR-aligned диагностика стартового уровня (текстовые модальности), ~30–40 мин, с rolling-уточнением. Потолок: не выше ACTIVE, никогда MASTERED.
- **Re-entry протокол** — после длительного перерыва движок рекомендует начать сессию с быстрого повторения или короткого теста остаточных знаний; отказ допустим и не штрафуется.

## Лексика

- **Chunk** — многословная **заготовка со слотом**, которую ученик достраивает своим содержанием (`the main advantage is …`). Изучается как целое, но остаётся продуктивным шаблоном.
- **Idiom** — фиксированное **неразложимое** выражение, которое не достраивают (`call it a day`). Отдельный `type`, а не chunk: другая структура и другая учебная цель [PD-2026-07-20].
- **Word formation / `formation`** — продуктивный морфологический паттерн: аффикс + база (`out-` + `run` → `outrun`). Живёт в треке `word-formation`; единица несёт `formation: {affix, base, affix_type}`. Паттерн — помощь **узнаванию**, не генератор слов; тема-паттерн и слово — разные targets [PD-2026-07-21] ([[modules/curriculum]], [[product/lexical-system]] §1b).
- **transparency** — декодируемость многословной единицы: `transparent | semi_opaque | opaque`. Ось, независимая от регистра и домена, и **не** тождественная `usage_policy`: та отвечает за уместность, эта — за то, выводится ли смысл из слов. У `opaque` обязателен `recognition` и запись `literal_trap_ru` о ложном дословном прочтении [PD-2026-07-20].
- **LexicalItem** — единица учебного лексикона со стабильным ID: слово, chunk, idiom, phrasal verb или lexeme. Тип informal-единицы: `informal_chunk` / `abbreviation` / `meme_template`.
- **Lexeme** — LexicalItem с формами (`go / went / gone` — один lexeme); владение агрегируется из evidence по required forms детерминированно ([[OPEN]] OPEN-14).
- **corpus_frequency / `frequency_band`** — **только** корпусная частота: numeric score (Zipf/source) + нейтральные band'ы `very_high | high | mid | low | rare` по versioned thresholds. Не содержит педагогических/доменных категорий (rereview E-R5).
- **curriculum_priority_band** — педагогический приоритет в программе: `CORE → HIGH → USEFUL → SPECIALIZED → INCIDENTAL`. Policy output, не частота (сюда ушли utility/domain-категории).
- **learner_priority** — персональный приоритет для конкретного ученика (учитывает личную потребность); вычисляется, не хранится как глобальное поле.
- **production_eligible** — вычисляемый признак «можно ли предъявлять как production сейчас» из active `usage_policy` + `currency` + контекста + transparency (`avoid`/`recognition_only`/`obsolete`/`dated` без явного recognition-override/`context_dependent` вне allowed_contexts/`opaque` как required production → false). Всегда по active policy, не пинится (safety-overlay).
- **LexicalMasteryProfile** — versioned профиль required dimensions и mastery-критериев для LexicalItem по `(type, transparency, usage_policy)` (обычный word/chunk тоже; [[OPEN]] OPEN-13).
- **volatility** — устойчивость единицы: `stable` / `changing`. Отделена от currency.
- **currency** — актуальность изменчивой единицы: `current` / `dated` / `obsolete`, с датами наблюдения/проверки и владельцем reverification. Истёкший review interval приостанавливает production и открывает review-задачу; `dated` — recognition-only по умолчанию; `obsolete` блокирует новые production/review assignments.
- **generation_policy** — versioned policy-снапшот, pinned в Session Manifest: допустимые схемы упражнений, формы step-type, правила дистракторов, правила приёма/reuse банка, dedup-ключи и safety-предикаты для сгенерированных упражнений.
- **rubric_policy / `rubric@1`** — versioned pinned policy, по которой движок валидирует observations открытого ответа, вычисляет criterion levels и integer `AttemptAssessment.score_ppm`; не владеет topic mastery thresholds или state transitions.
- **RubricProfile / `rubric_ref`** — task-family профиль из общего criterion-каталога; ссылка имеет форму `rubric:<profile_id>`, а версия берётся из `pinned_rubric_version`, не из самой ссылки.
- **rubric_criterion_ref** — ссылка `rubric:<profile_id>#criterion:<criterion_id>` на конкретный criterion; agent observation связывает её с atomic finding code и проверяемым span, но не передаёт готовый verdict/level/score.
- **stale-safety** — ре-валидация по active safety перед доставкой/reuse/рендером; если active usage/currency теперь запрещает production-шаг, шаг или банк-item отменяется/заменяется/ретайрится append-only, а не выдаётся молча.
- **usage_policy** — политика употребления: `safe_to_use` / `context_dependent` / `recognition_only` / `avoid`. Понимать ≠ употреблять; assessable dimensions зависят от policy.
- **contribution_scope** — тег evidence, определяющий, куда оно засчитывается (informal-профиль / writing / transfer / core CEFR). Разделяет informal recognition (никогда не в CEFR) и письменное производство в рабочем контексте.
- **Личный словарь (LearnerLexicalState)** — индивидуальное состояние LexicalItem: evidence по recognition/production раздельно, ошибки, Mastery/Stability/Retrievability, три оси состояния как выше. «Выучено» — не boolean; вход по критериям — но **сам вход даёт только enrollment**: evidence появляется лишь при отдельном сохранённом learner response, объяснение агента evidence не создаёт (rereview C-R2).
- **Stable core / living layer** — каталоги лексикона: спроектированный заранее / пополняемый из обучения (мемы, сленг, новые рабочие выражения) с provenance.
- **LivingLexicalCandidate** — no-evidence кандидат из сессии: нормализованная единица, предложенные метаданные, source pointer/hash и авторское summary. Не LexicalItem и не schedulable до приёма через `maintain-english-curriculum`.
- **lexicon-first micro lane** — малая scheduling-полоса для LexicalItem без topic-ссылок: learner-requested, observed-error, due-review и CORE/HIGH safe единицы; advisory-лимит живёт в generation policy.
- **Informal Online Competence** — отдельный профиль владения неформальным письменным английским; не двигает CEFR напрямую (отдельная шкала — [[OPEN]] OPEN-13).

## Метрики

- **Learning Score** — coverage-взвешенный средний Mastery тем текущего working-уровня, 0–100 («насколько твёрдо владею тем, где я есть»). Прогресс-к-следующему уровню — отдельно ([[modules/scoring]] §5).
- **XP** — очки за практику: выполненные задания, evidence, закрытые повторения, re-entry. **Штрафов и списаний нет**; начисление award-once по уникальному source event ([[OPEN]] OPEN-12).
- **Season** — период агрегации XP (отображение), не отдельная механика со штрафами.
- **Streak** — счётчик подряд идущих дней практики по локальной календарной дате ученика; прерывание обнуляет счётчик, накопленный XP не сгорает.
- **Tutor Compliance Score** — 0–100, доля соблюдённых обязательств агента за недавние сессии: вызваны ли required skills нужных версий, соблюдён ли correction-протокол, не было ли forbidden actions (агент не выставлял оценки, соблюдены postconditions) ([[modules/scoring]] §5).

## Система

- **Сессия** — одно занятие. Жизненный цикл: `STARTED → IN_PROGRESS → FINISHED | ABANDONED` (переход `STARTED → ABANDONED` допустим). Внутренняя структура свободная; обязательна фиксация результатов при завершении. `ABANDONED` сохраняет и учитывает всё зафиксированное и атомарно закрывает pending цели.
- **Session Manifest** — неизменяемый стартовый снимок сессии: tutor briefing, рекомендации тем, ReviewAssignment'ы, required skills и pinned versions; содержит ссылку на созданный в той же UoW `SessionPlan`, чьё живое состояние и ledger затем меняются отдельными CAS-командами.
- **Tutor briefing** — полная картина ученика одним JSON в манифесте/resume. Генерится из состояния движка, не из Markdown.
- **Session notes** — опциональные короткие заметки агента (`--note`). **Untrusted non-evidence**: экранируются в briefing, не интерпретируются как state.
- **Event log** — append-only журнал DomainEvents. Authoritative носитель — **таблица в SQLite** (коммитится с state+outbox одной транзакцией); **JSONL — derived rebuildable export** (аудит/git/сверка replay), не источник истины ([[platform/foundation]] §2.1).
- **Command / DomainEvent envelope** — конверт мутации/факта. Всегда: `id, type, occurred_at (UTC), actor/provider, correlation_id, causation_id, pinned_versions, payload_hash`. Условные: `sequence` (только событие) и `idempotency_key` (только мутирующая команда) ([[platform/foundation]] §3.3).
- **sequence** — монотонный canonical total order событий в event-таблице (tie-breaker для равных `occurred_at`); replay применяет события строго по нему. Есть только у `DomainEvent` (не у `Command`) и присваивается event-store'ом на append — до append не определён.
- **pinned_versions** — зафиксированные в конверте версии policy (curriculum/scoring/scheduler/generation/rubric), под которыми создан факт; replay резолвит по ним, не по active. Safety (`production_eligible`) — исключение, резолвится по active.
- **Unit of Work** — атомарный commit authoritative state + events + outbox одной транзакцией.
- **Transactional outbox** — надёжная post-commit доставка проекций (Obsidian, внешние) с retry/rebuild; сбой проекции не откатывает commit.
- **Policy registry** — реестр иммутабельных версионируемых policy-снимков, адресуемых по id.
- **Snapshot** — резервная копия SQLite (после checkpoint) + generated Markdown; операционное состояние не rebuildable из событий, поэтому бэкапится.
- **Learner-память** — генерируемая движком Obsidian-проекция состояния (`memory/`). Читаемая проекция, не источник scoring. Не путать с вики разработки.
- **SourceArtifact** — запись о внешнем источнике данных (id, версия, url, sha256, license, attribution, notices); импортированные единицы ссылаются на него ([[OPEN]] OPEN-15).
- **Skill (агентский)** — процедурная инструкция для агента в `agent-skills/`, синхронизируется в `.agents/skills/` и `.claude/skills/`.

## История изменений

- **2026-07-22 (2)**: П.5 — термины rubric_policy/`rubric@1`, RubricProfile/`rubric_ref`, rubric_criterion_ref [PD-2026-07-22].
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4). untrusted-захват — в продукте (порядок в roadmap).
- **2026-07-21**: разведены `SessionBudget` и `DeliveryLedger`, введён `plan_version`; `STEP_PRESENTED` исправлен до наблюдаемой границы тьютора; ReviewAssignment получил диспозицию `ReviewOutcome | CANCELLED`; availability приведена к §4.7a.
- **2026-07-20 (6)**: 0.4 — Learning Score и Tutor Compliance получили конкретные определения (владение текущим уровнем / доля соблюдённых обязательств).
- **2026-07-20 (5)**: foundation-rereview — добавлено обязательное поле `sequence` в конверт (I-1); Event log уточнён (SQLite-таблица authoritative, JSONL export).
- **2026-07-19 (4)**: добавлены kernel-термины (0.2): Command/DomainEvent envelope, pinned_versions, Unit of Work, transactional outbox, Policy registry, Snapshot; Event log уточнён как источник истины learning-части.
- **2026-07-19 (3)**: rereview — три оси состояния (enrollment / knowledge_state / review_status), REVIEW_DUE устранён (D-R1); AT_RISK синхронизирован (D-R2); AttemptAssessment vs ReviewOutcome (A-R1); confidence machine-enum + self_reported_level per-skill (F-R1/A-R3); frequency_band только numeric+нейтральные bands (E-R5); production_eligible, LexicalMasteryProfile; объяснение агента не evidence (C-R2); trusted-reporter (C-R3).
- **2026-07-19 (2)**: red-team триаж (F-1…F-8) — нормативные knowledge states и review outcomes; XP без штрафов + Season как период; machine-ID dimensions; LearningTarget; ReviewAssignment/Attempt/Summary/Confidence/Working level/core skill; разделены corpus_frequency/curriculum_priority/learner_priority и volatility/currency; contribution_scope; CurriculumVersion/Level/Module; SourceArtifact.
- **2026-07-19**: создан, начальный словарь из брифа и design-direction v0.2.
