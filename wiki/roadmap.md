# Roadmap

> **Status**: living
> **Last updated**: 2026-07-20

Единственное место, где живёт «где мы сейчас». Статусы: `planned / next / in-progress / done / done-with-open / blocked`. **`done-with-open`** = спека принята и не FAIL, но несёт остаточные OPEN, которые закрывает контракт-исполнитель (не блокирует зависимые работы, кроме явно указанных). Правится руками при каждом существенном сдвиге. Состав фаз — из `docs/design-direction.md` §5; при конфликте главнее этот файл. Owner-матрица OPEN → контракт — в [[OPEN]].

HTML-версия (пересобирается по запросу из этого файла): <https://claude.ai/code/artifact/b2afa615-2340-417b-8aed-89efceb89bfa>
> **Внимание**: HTML собран до П.4a и сильно устарел — фаза 0 там ещё не закрыта, треков восемь, П.1c/П.4b отсутствуют. Источник истины — этот файл.

## Фаза 0 — дизайн-контракты (текущая)

> **Фаза не завершена.** Восемь исходных контрактов написаны, но повторное ревью (R-1) справедливо указало: `learner`, `audit` и `gates` имеют MVP-команды в CLI и не имеют контрактов, а у `session next` нет владельца и алгоритма. Вертикальный срез (2.x) не начинается до 0.11; kernel (1.2) может идти параллельно.

Каждый контракт пишется как спека в вики (концепт → «ок» → пишем, Принцип 6).

| # | Артефакт | Куда ложится | Статус | Зависимости |
|---|---|---|---|---|
| 0.1 | Learning Model Requirements | `wiki/product/learning-model.md` | done | OPEN-4/5 решены; после триажа — остаточные OPEN-1/7/8/10/12/13 → 0.4 |
| 0.2 | Application Foundation Contract (kernel) | `wiki/platform/foundation.md` | done-with-open | event-store: SQLite-таблица authoritative + JSONL export [PD-2026-07-20]; 2 прогона ревью пройдены (PASS-with-findings, все сняты); остаточные OPEN-9/10/11/19/20/21 → 1.2/1.3 |
| 0.3 | Curriculum Contract | `wiki/modules/curriculum.md` | done-with-open | can-do граф, **9 треков** (добавлен `everyday-life`); остаточные OPEN-9/14 (OPEN-15 закрыт) |
| 0.4 | Evidence, Scoring & Review Contract | `wiki/modules/evidence.md` + `scoring.md` + `scheduler.md` | done-with-open | две оси + целые bands + Learning Score [PD-2026-07-20]; 2 прогона ревью (FAIL→PASS-with-findings, все находки сняты); остаётся калибровка констант + триггер терминализации в 0.5 (OPEN-10) |
| 0.5 | Lesson Lifecycle & Completion Contract (+ assessments) | `wiki/modules/lessons.md` + `assessments.md` | done-with-open | Attempt `draft→recorded→assessed`, stale/expiry как replayable события, closure trigger, uniqueness [PD-2026-07-20]; закрыл OPEN-10/17 + бизнес-часть OPEN-11; остаётся калибровка порогов |
| 0.6 | Obsidian Vault Contract | `wiki/modules/memory.md` | done | две зоны `memory/`+`notes/`, обычные файлы, страница-на-сущность + дашборды [PD-2026-07-20]; закрыл OPEN-2/OPEN-3 |
| 0.7 | CLI и Agent Skills contracts | `wiki/modules/cli.md` + `adapters.md` | done-with-open | Тотальный envelope, закрытые exit codes, обязательный idempotency-key, паритет над эффектами. Заведены OPEN-23/24 |
| 0.8 | Сквозные flows (сессия, продолжение другим агентом, placement) | `wiki/flows/` | done | session · continuation · placement приняты [PD-2026-07-19] |
| 0.9 | Lexical System Requirements | `wiki/product/lexical-system.md` | done-with-open | дизайн пользователя + ось `transparency`/`idiom`; остаточные OPEN-14/22 (OPEN-13/15 закрыты) |
| 0.11 | Контракты `learner`, `audit`, `gates` + владелец и алгоритм `session next` | `wiki/modules/learner.md`, `audit.md`, `gates.md` | **next** | P0-4/OPEN-25: конституция требует спеку на модуль, а CLI уже назначает им MVP-команды |
| 0.12 | Learning Control & Calibration | `wiki/modules/control.md` | done-with-open | Concept Gate пройден, 6 развилок решены [PD-2026-07-20]. Бюджет в минутах, защищённый минимум нового, классы срочности с конъюнкцией риск∧ставка, каталог tunables, decision trace. Закрыл владельца `session next`; остаточный OPEN-27 (калибровка) |
| 0.10 | Red-team ревью (4 прогона) + триаж | `staging/reviews/` | done-with-open | 66 находок + rereview + сквозное ревью фазы 0 + повторное. **Из 4 BLOCKER сняты 3**; P0-4 (нет контрактов learner/audit/gates) **не снят**, а вынесен в блокирующий 0.11 — регистрация долга не равна его закрытию |

## Фаза П — учебная программа (после 0.3, параллельно фазе 1)

Программа проектируется заранее целиком — уроки генерятся агентом по ней, поэтому без спроектированной программы корректная генерация невозможна [PD-2026-07-19]. Упражнения при этом НЕ создаются заранее: банк растёт из сессий (гибридная контент-модель).

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| П.1 | Каркас программы A1–C2: уровни, треки, модули | done | Codex: 6 уровней, 8 треков, 20 модулей, 85 тем A1–A2, 0 dangling. Content-review пройден. `curriculum/` |
| П.1b | Патч каркаса: расширение informal-трека | done | Codex: +6 тем (informal 2→8, всего 91); проверено — 0 dangling/инверсий/циклов, модули согласованы |
| П.4a | Учебный лексикон A1–A2: авторский stable core | done-with-open | Codex: 204 единицы, 16/16 модулей; корпусный проход не делался (без выдумок). Content-review: chunks недобраны → П.4a-bis |
| П.4a-bis | Добор chunks, чистка псевдо-chunks, перекалибровка bands | done | 290 единиц, chunks 33→116, multi-word 55%, CORE 59%→29%, ≥7 фреймов на каждый из 16 модулей, advisory-links 60→254. Отчёт `staging/handoff/2026-07-20-P4a-bis-report.md` |
| П.4b | Корпусный проход: pin источников, SourceArtifact, score→band | done-with-open | wordfreq@3.1.1 + NGSL/BSL@1.2 pinned по sha256, thresholds v1, `tools/enrich_lexicon.py --check`. Покрыто 129/290 (44%): корпус не измеряет фразы. Заведён **OPEN-22**. Отчёт `staging/handoff/2026-07-20-P4b-corpus-report.md` |
| П.1c | Каркас трека `everyday-life`: 45 тем A1–A2 | done-with-open | Codex: 136 тем, 30 модулей, **0 новых grammar-тем**, 36 грамматических targets переиспользовано; проверено независимо — 0 dangling/инверсий/циклов, старые темы побайтово. Content-review: нет тем не-дословного понимания → П.1c-bis |
| П.1c-bis | Темы не-дословного понимания (phrasal verbs, идиомы, разговорные реакции, сленг) + бытовое чтение | next | content-review П.1c. Делает не-дословное понимание учебной целью — иначе ~220 непрозрачных единиц П.4c некому планировать в занятия |
| П.4c | Лексикон быта и непрозрачных выражений: phrasal verbs 18→~100, идиомы 0→~120, casual chunks 0→~70, устойчивый сленг 0→~50, бытовые слова →~250. Разметка `transparency` по всему лексикону | next | **не блокируется П.1c-bis**: разные файлы (`lexicon/` против `topics/`), можно параллельно. П.1c-bis нужен, чтобы advisory-links непрозрачных единиц были осмысленными, а не чтобы единицы существовали. [PD-2026-07-20] ось прозрачности + тип `idiom` |
| П.2 | Программа A1–A2: тела тем (mastery_criteria, typical_errors, examples, contexts, lexicon-refs) | planned | **после П.1c-bis и П.4c** — иначе тела 91 темы придётся переписывать под выросший каркас; 0.4 schema готова |
| П.3 | Policies генерации уроков + lifecycle банка | planned | после П.2; informed by 0.1; **закрывает OPEN-14/OPEN-16** |

## Фаза 1 — kernel и каркас

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 1.1 | Пересоздать .venv на Python 3.12+, pyproject, ruff, pytest | in-progress | — (venv 3.12.10 готов, tooling при scaffold) |
| 1.2 | Kernel по контракту 0.2 (envelopes, Clock/Random, UoW, outbox, policy registry, event log) | planned | 0.2 done; закрывает механизм OPEN-9/10/11 |
| 1.3 | Storage: SQLite + миграции + event log + Unit of Work | planned | 1.2 |

## Фаза 2 — вертикальный срез A1–A2

| # | Работа | Статус | Зависимости |
|---|---|---|---|
| 2.1 | Загрузка программы A1–A2 в движок + валидация графа | planned | П.2, 1.3 |
| 2.2 | Сессия end-to-end: start → attempts/evidence → finish | planned | 0.5, П.3, 1.3 |
| 2.3 | Scoring + scheduler + replay | planned | 0.4, 2.2 |
| 2.4 | Obsidian-проекция | planned | 0.6, 2.2 |
| 2.5 | Agent skills + sync для Codex/Claude | planned | 0.7, 2.2 |
| 2.6 | Placement (текстовый) | planned | 0.1, 2.3 |
| 2.7 | Демо: сессия провайдером A → продолжение провайдером B без контекста | planned | 2.2–2.5 |

## За горизонтом (не планируется сейчас)

Listening/speaking модальности · полный TOEFL-симулятор · FSRS вместо базовой формулы · web UI · машинные гейты вики (см. [[README]] §Что не переняли).

## История изменений

- **2026-07-20 (34)**: **0.12 Learning Control & Calibration принят**. Развилки [PD-2026-07-20]: бюджет занятия в ожидаемых минутах (короткая проверка и письменная задача стоят разного); переполнение critical **переносится**, а защищённый минимум нового материала не занимается — исключение при рождении срабатывало бы всё чаще по мере роста программы; доступность объявленная с коррекцией; decision trace доступен по `trainer why`; потолок автономии калибровки — предложение с подтверждением (при n=1 шум неотличим от сигнала, а чисто ручной режим требует, чтобы ученик сам заметил); tuple приоритета исправлен немедленно. Закрыт владелец алгоритма `session next` — часть OPEN-25. Заведён OPEN-27.
- **2026-07-20 (33)**: повторное сквозное ревью после триажа — FAIL: 1 BLOCKER, 6 MAJOR, 2 MINOR, 1 QUESTION, принято полностью. **BLOCKER R-1 — мой over-claim**: «все четыре BLOCKER сняты» неверно, сняты три, а P0-4 зарегистрирован как долг, что не равно исправлению. Фаза 0 помечена **незавершённой**, 0.10 → `done-with-open`, вертикальный срез не начинается до 0.11. Остальные шесть MAJOR — один класс: правило исправлено у владельца и осталось устаревшим у соседа (`RECOVERED after REGRESSION` стал недостижим; flow всё ещё назначал `AGENT_ATTACHED` модулю audit; `finish` снова попал в closure triggers; самооценка placement осталась скаляром на четыре навыка; `rebuild()` в API снова обещал только события; observed-факты и отказ от re-entry не имели команд). Добавлены `trainer observed record` и `trainer reentry decline`.
- **2026-07-20 (32)**: бриф о числовых показателях настройки обучения. Принято: детерминизм гарантирует воспроизводимость, но не качество политики — этого слоя в фазе 0 нет вообще. Найдены два **живых** дефекта канона (**OPEN-26**): приоритет повторений возглавляет `overdue_days`, из-за чего просроченная периферия обгоняет критичный навык; бюджета занятия не существует, и с ростом программы занятия вырождаются в сплошное повторение — что противоречит исходной установке «разговор, а не уроки». Заведён этап **0.12**, написан концепт с 7 инвариантами и 6 развилками. Из брифа отклонено: восемь семейств политик с наследованием (difficulty/evidence/mastery уже имеют владельцев в 0.4), сумма из 11 слагаемых как приоритет (неотлаживаема — заменена классами срочности), метрики времени ответа и усталости (в нашей архитектуре не наблюдаемы), отдельный «протокол безопасного изменения» (пиннинг политик уже есть).
- **2026-07-20 (31)**: сквозное red-team ревью фазы 0 — вердикт FAIL, 17 находок. Триаж выполнен полностью. **BLOCKER**: (1) REGRESSION заявлялся как вход в AT_RISK, но тотальная таблица такой ветки не содержит и поля «тяжесть regression» не существует — AT_RISK теперь только из overdue-события; (2) терминальный ReviewOutcome нельзя было записать через CLI, а evidence и lessons описывали finish взаимоисключающе — добавлен `trainer review close`, finish требует пустой pending-set, abandon преобразует; (3) ось `transparency` не дошла до scoring, который владеет `LexicalMasteryProfile` — lookup стал тотальным по `(type, transparency, usage_policy)` с precedence «ограничение сильнее разрешения»; (4) у `learner`/`audit`/`gates` нет контрактов → OPEN-25 и новый этап **0.11**. **MAJOR**: владельцы `AGENT_ATTACHED` и session notes, `placement decline` в реестре, гибридный источник memory-страниц, девятый трек в контракте, living layer помечен post-mvp, единственная ветка `rejected`, exit codes в adapters. **QUESTION**: preflight resolve до commit, `REVIEW_DUE` как идемпотентное уведомление, Tutor Compliance по наблюдаемым эффектам, а не самоотчёту.
- **2026-07-20 (30)**: правка зависимостей — П.4c ошибочно значилась заблокированной П.1c-bis. Зависимости нет: проходы трогают разные каталоги и идут параллельно; П.1c-bis нужен для осмысленных advisory-links и планирования, а не для существования единиц. Помечен устаревший HTML-роадмап.
- **2026-07-20 (29)**: П.1c принят (Codex) — трек `everyday-life`, 45 тем, всего 136 тем и 30 модулей. Требование «не плодить грамматику» выполнено буквально: 0 новых grammar-тем, 36 существующих targets переиспользованы через advisory-граф. Все заявления автора подтверждены независимой проверкой. Content-review нашёл дыру в главном приоритете ученика: **ни одна из 136 тем не делает не-дословное понимание учебной целью** — все бытовые can-do продуктивные, а контракт запрещает требовать производство `opaque`-единиц. Заведена **П.1c-bis** перед П.4c. Исправлены work-centric can-do уровней A1/A2 и счёт треков в README.
- **2026-07-20 (28)**: 0.7 CLI + Agent Skills принят (`wiki/modules/cli.md`, `adapters.md`) — **фаза 0 закрыта, все восемь контрактов написаны**. Тотальный envelope (успех и отказ одной формы), закрытый набор из 7 exit codes с различением `CONFLICT`/`PRECONDITION_FAILED`, обязательный `--idempotency-key` у мутирующих команд (мотив — падение между commit и печатью ответа), запрет команды, принимающей оценку. Skills объявлены подсказкой, а не принуждением: их события не evidence, версия иммутабельна и пинится манифестом, паритет адаптеров определён над наблюдаемыми эффектами, а не над текстом. Попутно закрыт разрыв — `required_skills` в Session Manifest требовался брифом, но не был объявлен нигде ([[modules/lessons]] §4b). Заведены OPEN-23/24.
- **2026-07-20 (27)**: замер после П.4b показал перекос: `register` casual 24 из 290, домены `work` 139 / `technology` 47, **бытовой лексики ноль**, сленга ноль, а в каркасе informal — 8 тем из 91. Корень не в лексиконе: П.4 отбирал слова под темы, а темы спроектированы вокруг работы. 4 PD [PD-2026-07-20]: (1) отдельный трек `everyday-life` — домен, отдельно от `everyday-online-informal` — регистра; (2) **паритет** бытового и рабочего пласта; (3) новая ось **`transparency`** + тип `idiom` + `literal_trap_ru` — «не тупить, переводя дословно» стало явной учебной целью; (4) living layer в MVP не строится, поля остаются. Заведены **П.1c** и **П.4c**; **П.2 сдвинута** за них.
- **2026-07-20 (26)**: П.4b done-with-open — частоты выведены из трёх pinned-артефактов (wordfreq@3.1.1, NGSL/BSL@1.2, sha256 сверяются), thresholds v1, воспроизводимость через `tools/enrich_lexicon.py --check`, заведён `ATTRIBUTIONS.md`. **Покрыто только 44%**: корпус слов не измеряет фразы, а композитная оценка по токенам не зависит от порядка слов — присвоение её chunks было бы фабрикацией. Корпус подтвердил ручную разметку (0 конфликтов CORE/HIGH) и поймал 5 занижённых лексем. Вскрыт over-claim: `learner_priority` числился закрытым в OPEN-8, но в 0.4 отсутствует → **OPEN-22**. Словарь `transformations` закрыт в контракте. **П.4 закрыта, открывается П.2.**
- **2026-07-20 (25)**: П.4a-bis done — лексикон 204→290 единиц, chunks 33→116. Удалены 7 грамматических псевдо-chunks (дублировали темы → двойной scoring-таргет) и 2 малополезных; 3 наречных оборота → `type: word`. Добавлены 95 рабочих фреймов, включая все 9 из концепта. Multi-word 34%→55%, CORE 59%→29%, задействованы SPECIALIZED/INCIDENTAL. Advisory-links 60→254 (все chunks + все CORE/HIGH). Следующий — П.4b (корпус), затем открывается П.2. Новый TODO: стяжения внутри фреймов пересекаются с `informal.contraction-*` — риск того же двойного учёта.
- **2026-07-20 (24)**: П.4a принят с оговорками — 204 авторских единицы, корпусный проход честно не делался. Content-review нашёл перекос: 33 chunks (треть — грамматика, дублирующая темы), **все 9 фраз из концепта отсутствуют**, соотношение single/multi-word обратное цели, перекос bands (59% CORE). Решения [PD-2026-07-20]: добор до ~100 фреймов, удаление псевдо-chunks. Заведены П.4a-bis и П.4b. Схема форм lexeme уточнена (слот-список).
- **2026-07-20 (23)**: 0.6 Obsidian Vault принят (`wiki/modules/memory.md`) — две зоны (`memory/` генерится, `notes/` твоя), обычные markdown-файлы без зависимости от Obsidian CLI, страница-на-сущность + дашборды [PD-2026-07-20]. Закрыты OPEN-2/OPEN-3. В фазе 0 остался только **0.7**.
- **2026-07-20 (22)**: 0.5 Lesson Lifecycle + assessments принят (`wiki/modules/lessons.md`, `assessments.md`) — Attempt `draft→recorded→assessed`, авто-abandon stale-сессии и истечение placement как **replayable события** (`SESSION_STALE_ABANDONED`, `PLACEMENT_EXPIRED`), closure trigger, uniqueness поверх CAS [PD-2026-07-20]. Закрыты OPEN-10/17 + бизнес-часть OPEN-11. В фазе 0 остались 0.6 и 0.7. П.4a передан Codex.
- **2026-07-20 (21)**: П.1b done — informal-трек расширен (Codex, +6 тем: contractions, casual acknowledgements, abbreviations, casual↔neutral rephrasing, tone-recognition, forum-reply). Каркас: 91 тема, informal 8. Проверено независимо. Каркас готов под П.2.
- **2026-07-20 (20)**: **OPEN-15 закрыт** [PD-2026-07-20] — репо приватный/личный, без публикации и продажи: обязательства CC BY-SA срабатывают на распространении и не наступают; provenance оставлен по технической мотивации; publication trigger зафиксирован как условие. **П.4 разблокирована**, критический путь свободен. П.1b передан Codex.
- **2026-07-20 (19)**: 0.4-rereview — PASS-with-findings, новых BLOCKER нет; 5 MAJOR + 2 MINOR (schedule_epoch/policy-pin, tie-break по dimension, transfer в core-skill map, primary-target precedence, граница закрытия ReviewOutcome, schema_version, measured Learning Score) сняты. 0.4 подтверждён.
- **2026-07-20 (18)**: content-review каркаса П.1 пройден (`staging/reviews/2026-07-20-P1-content-review.md`) — хребет верен концепту; 3 PD: vocab = lexicon-layer (пустой topic-трек намеренно), informal расширяется патчем П.1b, **порядок изменён на OPEN-15 → П.4 → П.2**. OPEN-15 на критическом пути.
- **2026-07-20 (17)**: 0.4-review (FAIL) обработан — 2 BLOCKER (Topic.mastery_criteria schema; overdue→AT_RISK replayable-событие) + 9 MAJOR сняты в спеках; схемы/протоколы определены, не отложены. FAIL снят с 0.4. П.2 теперь genuinely разблокирована (schema есть).
- **2026-07-20 (16)**: П.1 каркас программы принят (Codex, `curriculum/`) — 6 уровней, 8 треков, 20 модулей, 85 тем A1–A2; независимая проверка: 0 dangling refs, формат по контракту, отложенное (mastery_criteria/лексикон/тела) корректно отсутствует. П.1 → done; П.2 разблокирована (сначала content-review каркаса).
- **2026-07-20 (15)**: 0.4 Evidence/Scoring/Review принят (`wiki/modules/evidence.md`+`scoring.md`+`scheduler.md`) — две оси, целые CEFR-bands, Learning Score = владение текущим уровнем [PD-2026-07-20]; закрыты OPEN-1/7/8/12/13/18 (модель), OPEN-10/20 сужены. 0.4 → done-with-open; П.2 разблокирована по 0.4 (ждёт только П.1 от Codex). Next → 0.5.
- **2026-07-20 (14)**: foundation-rereview — PASS-with-findings, новых BLOCKER нет; 4 MAJOR + 2 MINOR (JSONL lag, boundary-поля, safety-correction, replay-тесты, `sequence`) сняты в тексте. 0.2 подтверждён. Next → 0.4.
- **2026-07-20 (13)**: foundation-review (BLOCKER A-1/E-1 + ~13 MAJOR, регрессия триажа чистая) — event-store переопределён: SQLite-таблица authoritative, JSONL derived export [PD-2026-07-20]; заведены OPEN-19/20/21; FAIL снят с 0.2. Next → 0.4.
- **2026-07-19 (12)**: 0.2 Application Foundation Contract принят (`wiki/platform/foundation.md`) — гибрид event-sourcing + тонкий sqlite3 [PD-2026-07-19]; 0.2 → done-with-open (механизм OPEN-9/10/11 в 1.2/1.3); next → 0.4.
- **2026-07-19 (11)**: rereview-триаж (BLOCKER G-R1 + 21 MAJOR) — safety-overlay «safety не пинится» разрешил единственный BLOCKER; добавлены owner-матрица OPEN→контракт и OPEN-18; расширены OPEN-7…17; определён статус `done-with-open`; П.3 закрывает OPEN-14/16, П.4 сначала OPEN-15; assessments.md добавлен к 0.5. FAIL повторно снят со всех спек.
- **2026-07-19 (10)**: red-team триаж 66 находок (`staging/reviews/`) — 0.10 done, FAIL снят; правки шести спек + перестройка OPEN (OPEN-7…17); 0.3/0.9 → done-with-open; П.2 теперь зависит от 0.4 (schema mastery_criteria); П.1 разблокирована; 0.2 и 0.4 подняты в next (носители отложенных BLOCKER).
- **2026-07-19 (9)**: добавлен гейт 0.10 — red-team ревью шести концептов (промпт в `staging/reviews/`); П.1 ждёт итогов ревью.
- **2026-07-19 (8)**: 0.3 done — Curriculum Contract по одобренному концепту Codex (can-do граф, 8 треков с informal, OPEN-6 закрыт: CEFR-J + NGSL + wordfreq); next → П.1.
- **2026-07-19 (7)**: flow «placement» принят — 0.8 done (все три flows); next → 0.3 Curriculum Contract.
- **2026-07-19 (6)**: 0.9 Lexical System Requirements done (дизайн пользователя); добавлена П.4 — отбор лексикона A1–A2; OPEN-6 (frequency source).
- **2026-07-19 (5)**: flow «continuation» (`wiki/flows/continuation.md`) принят; в 0.8 остался placement.
- **2026-07-19 (4)**: 0.8 in-progress — flow «сессия» (`wiki/flows/session.md`) принят; остались continuation и placement.
- **2026-07-19 (3)**: 0.1 done — спека `wiki/product/learning-model.md` принята; next → 0.8 flows (flow-first).
- **2026-07-19 (2)**: добавлена фаза П — учебная программа проектируется заранее [PD-2026-07-19]; 2.1 переориентирована на загрузку готовой программы; ссылка на HTML-версию.
- **2026-07-19**: создан; фазы 0–2 из design-direction §5 и build-prompt.
