# Модуль: learner

> **Status**: current
> **Last updated**: 2026-09-22
> **Sources**: P0-4/OPEN-25 (контракт отсутствовал, команды уже были назначены) · [[../flows/continuation]] (tutor briefing) · [[../flows/placement]] §88 (уровни, self_reported_level) · [[../product/lexical-system]] §3 (личный словарь) · [[scoring]] §4/§7 (что вычисляет НЕ этот модуль) · контракт 0.11
> **Bounded context**: `src/english_trainer/learner/`

> Спека — **target**. Одна цель продукта, без фазовых тегов (Принцип 4). Термины — по [[../glossary]].

---

## 1. Назначение

Модуль владеет тем, что относится к **человеку**, а не к его знанию: настройки, заявленные о себе сведения, личный словарь и сборка briefing для тьютора. Он же — точка входа за общей картиной (`trainer status`).

Граница проста и проходит по источнику истины: **измеренное вычисляет [[scoring]], заявленное хранит learner**. Модуль не считает ни Mastery, ни уровень, ни XP — он их читает и подаёт.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `LearnerProfile` | сам ученик и его настройки | `learner_id`, `locale`, `timezone`, `goals[]`, `created_at` |
| `SelfReportedLevel` | **заявленный** уровень, отдельно от измеренного | `skill_id`, `level`, `declared_at`, `superseded_at?` |
| `LearnerLexiconEntry` | личный словарь: слой 3 ([[../product/lexical-system]] §3) | `entry_id`, `surface`, `note_ru?`, `added_at`, `source` (`learner` \| `encountered`), `linked_item_id?`; provenance `session_id?`/`provider?`/`source_event_id?`; движковое `normalized_surface` [PD-2026-07-22] |
| `LearnerPreferences` | **как** ученик хочет заниматься (§4a) [PD-2026-09-22] | `preferences_version`, `round_size`, `explanation_language`, `preferred_drill_forms[]`, `timed_limit_seconds`, `feedback_mode`, `updated_at` |
| `TutorBriefing` | собранная сводка для агента при старте/возобновлении | read-model, не хранится как истина |

`SelfReportedLevel` не имеет состояний, кроме «действует / замещён»: замещение происходит **по каждому навыку отдельно** после первого допустимого evidence по нему.

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает |
|---|---|---|
| `get_profile()` / `update_profile(patch)` | API | настройки ученика |
| `status()` | API | сводка: уровни (measured и provisional), активная сессия, просроченное, XP/streak, метрики control |
| `briefing(session_id)` | API | сборка `TutorBriefing` для агента |
| `set_self_report(levels)` | API | заявленные уровни per-skill (из `placement decline` либо явно) |
| `lexicon_add(entry)` / `lexicon_list(filter)` | API | личный словарь ученика |
| `preferences_get()` / `preferences_set(patch, idempotency_key)` | API | чтение и правка `LearnerPreferences` (§4a) [PD-2026-09-22] |
| `SELF_REPORT_DECLARED` | publishes | заявлен уровень (не измерение) |
| `LEARNER_PREFERENCES_UPDATED` | publishes | новая версия предпочтений: полный снимок + `preferences_version` [PD-2026-09-22] |
| `LEARNER_LEXICON_ENTRY_ADDED` | publishes | пополнение личного словаря |

Модуль **не публикует** событий об изменении знания, уровня или XP: их источники — [[scoring]] и [[evidence]].

## 4. Поведение

- **MUST — заявленное отделено от измеренного**: `self_reported_level` хранится и отдаётся **отдельным полем**, никогда не смешиваясь с `measured_working_level`. В `provisional_working_estimate` он участвует с явной пометкой ([[scoring]] §4). Смешение сделало бы самооценку неотличимой от evidence.
- **MUST — замещение per-skill** [rereview A-R3]: заявленный уровень навыка перестаёт учитываться после **первого допустимого evidence по этому навыку**, а не глобально. Ученик может верно оценить чтение и ошибиться в письме.
- **MUST — модуль ничего не вычисляет из evidence**: Mastery, Stability, knowledge state, CEFR-уровни, confidence, XP и streak вычисляет [[scoring]] ([[scoring]] §4, §7). Learner их **читает**. Дублирование расчёта в двух модулях гарантированно разъедется.
- **MUST — briefing это read-model, не истина**: сборка briefing не создаёт и не меняет состояния; агент не может изменить учебное состояние, «ответив» на briefing. Содержимое — уровни с confidence, недавние ошибки, актуальный словарь, рекомендации curriculum, результаты placement и `self_reported_level` с пометкой ([[../flows/continuation]], [[../flows/placement]]).
- **MUST — briefing выдаётся одним документом**: агент получает его целиком при `session start`/`resume`, а не собирает по кускам. Иначе поведение зависит от того, сколько запросов агент успел сделать.
- **MUST — личный словарь не влияет на scoring**: `LearnerLexiconEntry` — заметка ученика. Она может быть связана с `LexicalItem` (`linked_item_id`), и тогда влияет на `learner_relevance` при планировании ([[control]] §4.5), но **никогда** не даёт Mastery. Добавить слово в словарь не значит его знать.
- **MUST — личный словарь не редактирует программу**: запись в личный словарь не создаёт `LexicalItem` в curriculum. Пополнение и stable core, и living layer — только через workflow [[curriculum]] (living layer в продукте — [PD-2026-07-21]); прямой путь из личного словаря в программу отсутствует в любом случае.
- **MUST — логическая идентичность записи и dedup** [PD-2026-07-22]: запись идентифицируется `linked_item_id` (если привязана), иначе нормализованной surface (NFC + collapse whitespace + casefold, как `evidence` §4.1 нормализует ответ). Повторная встреча той же идентичности не создаёт второй логической записи — append-only факт дедуплицируется детерминированной свёрткой, retry/re-encounter возвращает сохранённую запись без второго события. Омонимы с разными надёжными `linked_item_id` не сливаются; одну surface без надёжного id движок не разбивает на смыслы сам. Session-bound запись (`encountered`) требует `expected_session_revision` и атомарно (одна UoW) добавляет событие и увеличивает session revision.
- **MUST — цели ученика влияют только на приоритет**: `goals[]` (например, «скоро поездка») повышают `learner_relevance` в [[control]] и не объявляют темы изученными.

### 4a. `LearnerPreferences` — форма занятий [PD-2026-09-22]

Ученик уже называл предпочтения («раунды по шесть», «объясняй по-русски»), но хранить их было негде, и каждый новый тьютор начинал с нуля. Предпочтения отвечают на вопрос **как** заниматься — и ровно поэтому живут здесь, рядом с заявленным, а не рядом с измеренным.

- **MUST — состав и дефолты**:

  | Поле | Значения | Дефолт |
  |---|---|---|
  | `round_size` | целое, число предъявлений в раунде дрилла | `6` |
  | `explanation_language` | `ru` \| `en` | `ru` |
  | `preferred_drill_forms[]` | подмножество форм дрилла, объявленных generation policy | пусто (все допустимые) |
  | `timed_limit_seconds` | целое, дефолтный лимит timed-форм | `240` |
  | `feedback_mode` | `stage_dependent` \| `always_explain` | `stage_dependent` |

- **MUST — versioned и event-sourced**: каждая правка публикует `LEARNER_PREFERENCES_UPDATED` с **полным** снимком и монотонным `preferences_version`; действует последняя версия. Частичные дельты не хранятся: сборка текущего значения из цепочки патчей дала бы второй путь вычисления того же состояния.
- **MUST — выдаётся в briefing**: `session start` и `session resume` включают действующий снимок в `briefing.preferences` тем же одним документом, что и остальной briefing ([[lessons]] §5). Отдельного запроса предпочтений агент не делает — иначе поведение зависело бы от того, сколько вызовов он успел сделать.
- **MUST NOT — предпочтения не влияют на scoring**: ни одно поле не входит в формулы [[scoring]], не меняет admissibility evidence, не двигает Mastery, уровень, XP и ось automaticity. `feedback_mode: always_explain` меняет только протокол объяснения ([[../product/learning-model]] §9.1), а не то, как оценивается ответ. Предпочтение — про удобство, и оно не вправе превратиться в способ влиять на собственную оценку.
- **MUST — потребители читают, а не дублируют**: `round_size` потребляет [[control]] при сборке `drill_block`, `timed_limit_seconds` — при `timed_writing`, `explanation_language` и `feedback_mode` — тьютор. Собственных копий этих значений потребители не хранят.
- **MUST — валидация до эффекта**: `preferences_set` отвергает `round_size` вне `[3, 12]`, `timed_limit_seconds` вне `[60, 900]`, неизвестный `explanation_language`, `feedback_mode` или форму дрилла — `INVALID_INPUT` без следов ([[cli]] §4.5).

## 5. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer status --format json` | сводка состояния | уровни measured/provisional, активная сессия, просроченное, XP/streak |
| `trainer profile show` \| `set --format json` | настройки ученика | профиль |
| `trainer lexicon add` \| `list --format json` | личный словарь | записи |
| `trainer learner preferences show` \| `set --format json` | форма занятий (§4a): раунд, язык объяснений, формы дрилла, лимит timed, режим обратной связи [PD-2026-09-22] | действующий снимок + `preferences_version` |

`self_reported_level` задаётся через `trainer placement decline --self-assessment` ([[assessments]]) — отдельной команды нет, чтобы не появилось двух путей записи одного значения.

## 6. Границы

- **depends on**: [[scoring]] (уровни, confidence, XP), [[scheduler]] (просроченное), [[curriculum]] (рекомендации), [[lessons]] (активная сессия), [[control]] (метрики для status)
- **events published**: `SELF_REPORT_DECLARED`, `LEARNER_LEXICON_ENTRY_ADDED`, `LEARNER_PREFERENCES_UPDATED`
- **events consumed**: `STATE_TRANSITION`, `SESSION_FINISHED` — для инвалидации read-model

Модуль не владеет ни одним числом, которое вычисляется из evidence.

## 7. Открытые вопросы

- **OPEN-22**: формула `learner_priority` — владелец [[scoring]]; learner поставляет входы (`goals`, личный словарь), но формулу не содержит.

## История изменений

- **2026-09-22**: [PD-2026-09-22] добавлен §4a — versioned event-sourced `LearnerPreferences` (`round_size` 6, `explanation_language` ru, `preferred_drill_forms[]`, `timed_limit_seconds` 240, `feedback_mode` stage_dependent), выдача в `briefing.preferences` на start/resume, команды `trainer learner preferences show|set` и явный запрет влияния на scoring.
- **2026-07-22 (2)**: [PD-2026-07-22] задокументированы logical identity записи (`linked_item_id`, иначе нормализованная surface) + provenance-поля (`session_id`/`provider`/`source_event_id`) и движковое `normalized_surface`; dedup повторных встреч и атомарность session-fence при `encountered`. Реализация — модуль `learner` (roadmap 99).
- **2026-07-22**: фазовые теги `[mvp]`/`[post-mvp]` сняты [PD-2026-07-22]: спека описывает одну цель продукта, порядок и статус — только в roadmap (Принцип 4).
- **2026-07-20**: создан (контракт 0.11, P0-4/OPEN-25). Граница проведена по источнику истины: заявленное — здесь, измеренное — в scoring. Снято лишнее присвоение из [[../flows/session]], где XP-ledger и streak числились за learner, хотя описаны в [[scoring]] §7.
