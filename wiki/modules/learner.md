# Модуль: learner

> **Status**: current
> **Last updated**: 2026-07-20
> **Sources**: P0-4/OPEN-25 (контракт отсутствовал, команды уже были назначены) · [[../flows/continuation]] (tutor briefing) · [[../flows/placement]] §88 (уровни, self_reported_level) · [[../product/lexical-system]] §3 (личный словарь) · [[scoring]] §4/§7 (что вычисляет НЕ этот модуль) · контракт 0.11
> **Bounded context**: `src/english_trainer/learner/`

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — по [[../glossary]].

---

## 1. Назначение

Модуль владеет тем, что относится к **человеку**, а не к его знанию: настройки, заявленные о себе сведения, личный словарь и сборка briefing для тьютора. Он же — точка входа за общей картиной (`trainer status`).

Граница проста и проходит по источнику истины: **измеренное вычисляет [[scoring]], заявленное хранит learner**. Модуль не считает ни Mastery, ни уровень, ни XP — он их читает и подаёт.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `LearnerProfile` | сам ученик и его настройки | `learner_id`, `locale`, `timezone`, `goals[]`, `created_at` |
| `SelfReportedLevel` | **заявленный** уровень, отдельно от измеренного | `skill_id`, `level`, `declared_at`, `superseded_at?` |
| `LearnerLexiconEntry` | личный словарь: слой 3 ([[../product/lexical-system]] §3) | `entry_id`, `surface`, `note_ru?`, `added_at`, `source` (`learner` \| `encountered`), `linked_item_id?` |
| `TutorBriefing` | собранная сводка для агента при старте/возобновлении | read-model, не хранится как истина |

`SelfReportedLevel` не имеет состояний, кроме «действует / замещён»: замещение происходит **по каждому навыку отдельно** после первого допустимого evidence по нему.

## 3. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `get_profile()` / `update_profile(patch)` | API | настройки ученика | `[mvp]` |
| `status()` | API | сводка: уровни (measured и provisional), активная сессия, просроченное, XP/streak, метрики control | `[mvp]` |
| `briefing(session_id)` | API | сборка `TutorBriefing` для агента | `[mvp]` |
| `set_self_report(levels)` | API | заявленные уровни per-skill (из `placement decline` либо явно) | `[mvp]` |
| `lexicon_add(entry)` / `lexicon_list(filter)` | API | личный словарь ученика | `[mvp]` |
| `SELF_REPORT_DECLARED` | publishes | заявлен уровень (не измерение) | `[mvp]` |
| `LEARNER_LEXICON_ENTRY_ADDED` | publishes | пополнение личного словаря | `[mvp]` |

Модуль **не публикует** событий об изменении знания, уровня или XP: их источники — [[scoring]] и [[evidence]].

## 4. Поведение

- **MUST — заявленное отделено от измеренного** `[mvp]`: `self_reported_level` хранится и отдаётся **отдельным полем**, никогда не смешиваясь с `measured_working_level`. В `provisional_working_estimate` он участвует с явной пометкой ([[scoring]] §4). Смешение сделало бы самооценку неотличимой от evidence.
- **MUST — замещение per-skill** `[mvp]` [rereview A-R3]: заявленный уровень навыка перестаёт учитываться после **первого допустимого evidence по этому навыку**, а не глобально. Ученик может верно оценить чтение и ошибиться в письме.
- **MUST — модуль ничего не вычисляет из evidence** `[mvp]`: Mastery, Stability, knowledge state, CEFR-уровни, confidence, XP и streak вычисляет [[scoring]] ([[scoring]] §4, §7). Learner их **читает**. Дублирование расчёта в двух модулях гарантированно разъедется.
- **MUST — briefing это read-model, не истина** `[mvp]`: сборка briefing не создаёт и не меняет состояния; агент не может изменить учебное состояние, «ответив» на briefing. Содержимое — уровни с confidence, недавние ошибки, актуальный словарь, рекомендации curriculum, результаты placement и `self_reported_level` с пометкой ([[../flows/continuation]], [[../flows/placement]]).
- **MUST — briefing выдаётся одним документом** `[mvp]`: агент получает его целиком при `session start`/`resume`, а не собирает по кускам. Иначе поведение зависит от того, сколько запросов агент успел сделать.
- **MUST — личный словарь не влияет на scoring** `[mvp]`: `LearnerLexiconEntry` — заметка ученика. Она может быть связана с `LexicalItem` (`linked_item_id`), и тогда влияет на `learner_relevance` при планировании ([[control]] §4.5), но **никогда** не даёт Mastery. Добавить слово в словарь не значит его знать.
- **MUST — личный словарь не редактирует программу** `[mvp]`: запись в личный словарь не создаёт `LexicalItem` в curriculum. Пополнение и stable core, и living layer — только через workflow [[curriculum]] (living layer в продукте — [PD-2026-07-21]); прямой путь из личного словаря в программу отсутствует в любом случае.
- **MUST — цели ученика влияют только на приоритет** `[mvp]`: `goals[]` (например, «скоро поездка») повышают `learner_relevance` в [[control]] и не объявляют темы изученными.

## 5. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer status --format json` | сводка состояния | уровни measured/provisional, активная сессия, просроченное, XP/streak |
| `trainer profile show` \| `set --format json` | настройки ученика | профиль |
| `trainer lexicon add` \| `list --format json` | личный словарь | записи |

`self_reported_level` задаётся через `trainer placement decline --self-assessment` ([[assessments]]) — отдельной команды нет, чтобы не появилось двух путей записи одного значения.

## 6. Границы

- **depends on**: [[scoring]] (уровни, confidence, XP), [[scheduler]] (просроченное), [[curriculum]] (рекомендации), [[lessons]] (активная сессия), [[control]] (метрики для status)
- **events published**: `SELF_REPORT_DECLARED`, `LEARNER_LEXICON_ENTRY_ADDED`
- **events consumed**: `STATE_TRANSITION`, `SESSION_FINISHED` — для инвалидации read-model

Модуль не владеет ни одним числом, которое вычисляется из evidence.

## 7. Открытые вопросы

- **OPEN-22**: формула `learner_priority` — владелец [[scoring]]; learner поставляет входы (`goals`, личный словарь), но формулу не содержит.

## История изменений

- **2026-07-20**: создан (контракт 0.11, P0-4/OPEN-25). Граница проведена по источнику истины: заявленное — здесь, измеренное — в scoring. Снято лишнее присвоение из [[../flows/session]], где XP-ledger и streak числились за learner, хотя описаны в [[scoring]] §7.
