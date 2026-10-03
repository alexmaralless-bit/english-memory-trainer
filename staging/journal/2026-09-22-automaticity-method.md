# 2026-09-22 — метод автоматизации: решения и запуск работ

## Контекст

Ученик сформулировал целевой метод: «учить не заучиванием правил (хотя это тоже должно быть), а заучиванием целых фраз и предложений, чтобы на автомате вылетали артикли и правильное построение предложения и глаголов, при этом я не сидел и не вспоминал правила применительно к конкретной ситуации».

Аудит канона показал: текущая модель измеряет точность и строит урок вокруг объяснения; меры скорости нет; состав занятия запрещает дрилл (saturation ≤ 3 показов / 5 сессий, ≤ 2 шага на тему); обратная связь всегда возвращает к правилу; артиклей — одна тема из 275; лестница повторений 1→3→7 без короткой фазы закрепления. Исследовательская сводка и модель — `staging/concepts/2026-09-22-automaticity-method-concept.md`.

## Принятые решения [PD-2026-09-22]

Ученик подтвердил концепт и разбиение работ («ок») и попросил выполнять максимально быстро, субагентами (opus — сложное, sonnet — среднее, haiku — простое и массовое), с **полным** набором примеров.

- **PD-A**: автоматизм — отдельная ось состояния per target (`not_measured → deliberate → proceduralized → automatic`), собственный policy kind `automaticity@1`; Mastery, Stability и таблица переходов не меняются.
- **PD-B**: `response_latency_ms` принимается от агента как trusted-reporter поле (как raw_answer) и интерпретируется относительно базы ученика; timed-формы имеют объявленный лимит.
- **PD-C**: фрейм — существующий тип `chunk` с новыми полями `frame_of` (тема) и `carries` (закрытый словарь тегов); нового типа нет.
- **PD-D**: короткая лестница закрепления `relearning_ladder_days: [1, 2, 4]` как отдельная фаза перед основной `1 → 3 → 7 → …` (`scheduler@2`).
- **PD-E**: обратная связь по стадиям: в дрилле подсказка → самоисправление → правильная фраза → повтор целиком; объяснение только по запросу или при повторе ошибки ×2; полное «почему» — в дебрифе. Запрет «только исправленная строка» снимается.
- **PD-F**: программа артиклей расширяется до девяти тем (A1–B2) плюс постоянный interleaved-ярус артикльных фреймов.
- Новый вид данных программы: тексты для реконструкции (`curriculum/texts/reconstruction/`), versioned вместе с curriculum.
- Правило одной строкой **до** практики, полное объяснение **в дебрифе**; для программного урока полная дуга сохраняется, но фреймы идут раньше формы.

## План работ

Разбиение по типам (канон / скиллы / программа / примеры / код), волны и приёмка — `staging/concepts/2026-09-22-automaticity-method-concept.md` §8. Формат данных для исполнителей — `staging/handoff/2026-09-22-automaticity-authoring-spec.md`; структурный чекер — `tools/check_authoring.py`.

## Отложенное

- Численные пороги `automaticity@1` (точность, коэффициент latency) — авторские дефолты, калибровка по эксплуатации → OPEN (заводит канон-патч).
- Bulk-импорт авторских упражнений в банк (OPEN-34) не запускается: дрилл-предложения генерирует тьютор из фреймов.

## Ход выполнения (обновляется по мере приёмки)

**Волна 1 принята**: канон (13 спек, OPEN-37/38, фаза 3 в roadmap); скиллы `pedagogy.md`, `correct-learner-output` v3, `run-spaced-review` v3, `run-english-session` v7 (архивы версий, sync без дрейфа); 8 артикльных тем A1–B2 + контрасты в 7 глагольных темах + `carries` на 45 chunks; **1529 фреймов** (66 тем grammar-engine по 12–29 + 144 артикльных фрейма ярусов 1–2); **150 текстов** для реконструкции (2 на каждую из 75 тем). Пост-обработка `tools/link_frames.py` проставила advisory-links и `topic.lexicon`; `trainer curriculum validate` — 0 ошибок, 0 предупреждений.

**Волна 2–3 принята**: Д1 (validator/loader: `carries`, `frame_of`, полы фреймов, обратная ссылка фрейм ↔ тема в обе стороны, вид данных «тексты»), Д2+Д3 (`response_latency_ms`, `attempt record-block` с per-item `items[]`, `curriculum texts`), Д5 (`control@3`: `drill_block`/`reconstruction`/`timed_writing`, профиль `drill`, saturation по блокам, interleaving с `role: contrast`, `tunables@2`), Д6 (`automaticity@1`, reducer `AutomaticityState`, `AUTOMATICITY_UPDATED`, replay, блок в `trainer status`), Д7 (`scheduler@2`: лестница `[1, 2, 4]` → `[1,2,4,7,14,30,60,120,180]`, per-event pinned resolution через `registry=`).

**Уточнения канона по ходу** (владелец): §2d curriculum — `keywords` 6–14, `target_spans` 4–12, `also_targets` тема или LexicalItem (согласовано с чекером и корпусом); control §4.6 — при недоборе контрастов блок выдаётся blocked с `NO_CONTRAST_CANDIDATE` (не пропускается).

**Интеграционные хвосты (открыты, назначены на волну 4)**:
- evidence: вызывать `build_automaticity_update` внутри UoW `record_block_attempt`/`record_attempt`, чтобы `AUTOMATICITY_UPDATED` эмитился живьём (сейчас ось корректна через replay/status, но факт не пишется).
- call sites `fold_schedules`/`due_backlog`/`sweep_overdue` в `cli/`, `lessons/`, `memory/` — передавать `registry=` (per-event pinned scheduler policy).
- evidence §4.6 — правило «один source-span на пару» **поштучно** для items дрилл-блока: решено применять per item (повтор span'а исключает item из зачёта, блок не отклоняется); реализация ждёт.
- control: saturation считает контрастные пары блока как exposure — оставлено (дистрактор реально предъявляется); пересмотреть при калибровке (OPEN-27).
- evidence: `declared_limit_seconds` копируется из snapshot в attempt/evidence (нужно reducer'у для timed-подтверждения) — принято.

## Д11 — облегчение протокола тьютора [PD-2026-09-22, «да хочу»]

Запрос ученика: облегчить тренажёр за счёт числа обязательных шагов протокола в скиллах, не трогая инварианты evidence. Решение: на один структурированный шаг вместо `peek → next → rendered → show → record → finalize → review close` (до 6 вызовов) — `next` (с `plan_version` из предыдущего ответа) → `exercise rendered` → показать → `attempt record` с observations в том же вводе (оценка в той же UoW) и `--close-review` для review-шага (закрытие в той же UoW). `peek` — только после `resume`/`CONFLICT`; `attempt finalize` и `review close` остаются как fallback/двухшаговый путь восстановления; `exercise prepare`/`render-prepared` — MAY. Rendered-before-show, запись каждого ответа и finish/abandon не ослабляются. `obligations@3` признаёт короткий путь. Скиллы получают новые версии с архивами.

**Принято позже**: Д8 (preferences + briefing + прокидка в composition), Д9 (проекция фреймов/автоматизма, `current/automaticity.md`, registry + permanent-набор в `memory/engine.py`), скиллы Б4–Б6 (`run-drill-block` v1, `teach-english-topic` v5, `maintain-english-curriculum` v2), scheduler `permanent_interleave` (флаг + `permanent_interleave_interval_days: 180`, чистый слой: набор целей инжектируется вызывающим кодом).

**Находка scheduler**: цели и раньше не выбывали из очереди — после последней ступени любая цель бесконечно переназначается на `intervals[-1]`; `permanent_interleave` именует это поведение для артикльных фреймов и делает его видимым (backlog/проекция), а не вводит новое.

**Интеграционные хвосты (дополнение)**:
- helper `permanent_interleave_targets(program)` в curriculum service; передача `registry=` и `permanent_interleave_targets=` в `due_backlog`/`sweep_overdue` из `cli/app.py` (review due, metrics), `lessons/delivery.py`, `lessons/sessions.py` (review_candidates_for, sweep), `lessons/resume.py`.
- per-event классификация permanent-набора по pinned curriculum snapshot — follow-up после эксплуатации.

**Контент принят после fix pass** (ревью `staging/reviews/2026-09-22-frames-content-review.md` → 7 sonnet-проходов по файлам): корпусной аудит владельца — 1529 фреймов, 0 трапов-пустышек, 0 контрастов-дублей трапа, все `*_ru` поля кириллицей (67 пустых `slot_hint_ru` удалены), фрейм присутствует хотя бы в одном примере у всех, кроме намеренных парных фреймов «X / Y» темы present-perfect-past-simple.choice; 150 текстов — word_count/spans пересчитаны; `curriculum validate` 0/0. Ids и `frame_of` не менялись, ссылки не сломаны (`link_frames.py --check` → 0).

**Д11 принят**: 3 вызова на структурированный шаг вместо 6 (`next → exercise rendered → show → attempt record [observations] [--close-review]`); `obligations@3`; интеграционный тест доказывает байт-идентичность scores между коротким и длинным путём; шесть скиллов получили новые версии с архивами. Вопрос ученика «тренажёр получился тяжёлым?» — ответ зафиксирован: лёгкий в работе, тяжёлый в изменении (осознанно); облегчение — в протоколе скиллов, что и сделано.

**Обновлены** `CLAUDE.md`/`AGENTS.md` (состояние репозитория, venv, инструменты авторинга) и `wiki/roadmap.md` (фаза 3 done-with-open: Д12).

**Д12–Д14 приняты**: живой `AUTOMATICITY_UPDATED` в UoW попытки; per-item дедуп span'ов (два разных prompt'а с одинаковым ответом = один span, засчитывается первый); scheduler-входы на всех call sites (`registry=`, `permanent_interleave_targets`, классификатор инжектируется в lessons как callable — слои чисты); идемпотентность `attempt record` внутри движка; rubric-evidence несёт latency-поля; `rubric_step_type` в снапшоте для `timed_writing`/`reconstruction`. Финальная приёмка владельца: **814 passed**, ruff/format/mypy strict чисты, `curriculum validate` 0/0, skills validate без нарушений, зеркала идентичны; smoke на свежей установке (`init → activate → preferences → session start --profile drill → next ×4 → abandon → memory rebuild/check → status/replay`) — успешно. Реконструкция на свежей установке в план не попадает (нет освоенной цели для integration-пары) — по дизайну.

**Осталось на будущее**: симметричный дедуп span'ов для одиночных попыток относительно items блока (не запрошено); per-event классификация permanent-набора по pinned curriculum; калибровка OPEN-37/38; активация версии на рабочей установке пользователя и dogfooding; при необходимости перегенерировать HTML-roadmap.

## Д15 — настоящий плейсмент [PD-2026-09-22, «заверши сессию и исправь»]

При первом реальном запуске урока выяснилось: `placement start` выдаёт встроенный стаб из 6 пунктов A1 (`src/english_trainer/assessments/forms.py`), writing не оценивается, форм как данных нет — канон (`flows/placement.md`, `assessments.md` §3, learning-model §6) не был наполнен (фаза П «состав форм» не выполнялась). Открытый плейсмент закрыт (`ABANDONED`), учебная сессия не открывалась; `curriculum activate` на рабочей установке выполнен.

Решения владельца: формы — данные `curriculum/assessments/placement-<name>.yaml` (≥ 2 параллельные формы, A1–C1, ≈73 пункта, ≈35 мин; виды `choice`/`cloze`/`true_false`/`writing`, passages); writing оценивается рубрикой по observations тьютора (provisional); уровень из плейсмента — `scoring@2` секция `placement`: по навыку высший band, где ≥ 5 разных тем band'а решены полностью верно → `measured_working_level` с `confidence: low`, `basis: placement`; состояния тем и потолок ACTIVE не меняются; выбор формы — младшая непросмотренная, иначе ротация по cooldown. Спека — `staging/handoff/2026-09-22-placement-forms-spec.md`. Исполнители: код (opus), формы A/B (sonnet, одинаковое детерминированное правило выбора тем по нечётным позициям), канон + скилл `run-placement-assessment` v2 (sonnet).

**Д15 принят**: формы `placement-en-core-a@1`/`-b@1` (73 пункта, параллельные по темам/видам, свои тексты), loader/validator/snapshot, выбор формы по exposure, grading (буква/текст, true/false/да/нет), writing по observations через `rubric@1` (provisional), `scoring@2` секция `placement` с порогами по навыкам (grammar 5, vocabulary 4, reading 3) и provisional writing (≥ 700000 ppm, very_low); `provisional_working_estimate` в status/briefing/vault. Сквозной прогон формы B с верными ответами: grammar/vocabulary/reading C1 (low, placement), writing B1 provisional, estimate B1. Приёмка владельца: 936 тестов, ruff/mypy чисты, валидатор 0/0, скиллы валидны. OPEN-39 — калибровка порогов. Скилл `run-placement-assessment` v2.

**Первая живая попытка (вечер 2026-09-22)**: программа `curriculum@2026-09-22-placement` активирована в рабочей базе; плейсмент (форма A) начат, ученик попросил предъявлять вопросы по одному (закреплено в памяти проекта как норма предъявления для всех серий), после трёх ответов попросил завершить — плейсмент `ABANDONED` без записи ответов; учебная сессия не открывалась; база без evidence. Follow-up для скиллов: «один item на сообщение» закрепить в `run-placement-assessment`/`run-drill-block`/`run-spaced-review`.
