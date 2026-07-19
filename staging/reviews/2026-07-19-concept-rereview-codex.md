# Повторное red-team ревью после триажа 66 находок

> **Checkout**: `dba6448` (`Triage red-team concept review: fix specs, rebuild OPEN registry`)  
> **Scope**: шесть принятых спек + `wiki/README.md`, `glossary.md`, `OPEN.md`, `roadmap.md`; frozen docs и journal использованы только как lower-priority provenance  
> **Режим**: docs-only; старый отчёт и канон не изменялись

## Резюме

Триаж существенно улучшил канон: прежние блокеры вокруг клиентской классификации, replay одного evidence, CEFR coverage, ABANDONED, placement recovery, XP exactly-once и Informal→CEFR получили явные инварианты и владельцев. П.1 остаётся разблокированной; П.2 корректно ждёт schema `mastery_criteria` из 0.4.

Повторное ревью, однако, нашло один новый `BLOCKER`: абсолютная не-ретроактивность pinned policy противоречит обязательной stale-safety проверке по active policy. При смене `safe_to_use → avoid` живая сессия одновременно обязана продолжить по старой версии и запретить ещё не предъявленный production-контент. Это нужно разрешить до финализации pinning в 0.2/0.3/0.5.

Топ-5:

1. **G-R1 — BLOCKER:** pinned resume/replay конфликтует с active safety-policy.
2. **D-R1/D-R2 — MAJOR:** `knowledge_state` всё ещё смешан с enrollment/scheduling, а `AT_RISK` определён не так, как в диаграмме.
3. **E-R1 — MAJOR:** «атомарная» терминализация включает файловую Obsidian-проекцию, хотя summary/projection выполняются после commit.
4. **D-R3 — MAJOR:** placement объявляет `ABANDONED`, но переход, CLI и audit-event для abandon отсутствуют.
5. **J-R1/J-R2 — MAJOR:** owner/dependency matrix OPEN-7…17 расходится между спеками, реестром и roadmap; особенно OPEN-10/14/16/17 и зависимости П.3/П.4.

Практический gate после rereview:

- П.1 — можно продолжать.
- 0.4 — можно начинать, но в его scope надо вернуть полную таблицу LearningTarget transitions и lexical mastery/aggregation.
- 0.2 — можно проектировать параллельно, но нельзя закрывать pinning contract до решения G-R1.
- П.3 и П.4 — roadmap пока преждевременно считает зависимости полными; нужны OPEN-14/16 и OPEN-15 соответственно.

## A. Внутренние противоречия — НАХОДКИ

### A-R1. Review outcome вычисляется в два разных момента — `MAJOR`

**Файл и раздел → точная цитата**

- `wiki/flows/session.md`, «Сценарий»: `T->>T: движок вычисляет review outcome по versioned policy` сразу после `attempt record`.
- Там же, «Выведенные контракты»: `scoring (0.4) | вычисление review outcome и пересчёт на терминализации`.
- `wiki/glossary.md`, `ReviewAssignment`: «Имеет ровно один терминальный outcome.»

**Дефект:** непонятно, является ли результат отдельного attempt уже терминальным либо только предварительной оценкой. При нескольких attempts на один `review_id`, crash/recover и correction две реализации законно выберут разные моменты фиксации outcome.

**Минимальная правка:** развести `AttemptAssessment` и единственный terminal `ReviewOutcome`; явно выбрать момент закрытия ReviewAssignment и внести это в OPEN-10/0.4.

### A-R2. Общая терминализация «закрывает pending», но finish обязан их не иметь — `MAJOR`

**Цитаты:** `wiki/flows/session.md`, «Состояния сессии»: «Терминализация — единая атомарная транзакция для `FINISHED` и `ABANDONED`: закрывает все pending attempts и review-цели явными исходами»; «Правила»: «finish отклоняется … [при] нефинализированном attempt, review-цели без исхода».

**Дефект:** для FINISHED pending либо автоматически закрываются транзакцией, либо являются precondition failure. Обе нормы одновременно выполнить нельзя.

**Минимальная правка:** написать раздельно: FINISHED требует нулевой pending-set; ABANDONED атомарно преобразует pending в явные abandoned outcomes. Общей оставить только последующую UoW обработки.

### A-R3. Scope замещения `self_reported_level` не определён — `QUESTION`

**Цитаты:** `wiki/product/learning-model.md` §5: «Непроверенная область трактуется как unknown» и «Самооценка … полностью перекрывается первым допустимым evidence»; `wiki/flows/placement.md`, решение 4 повторяет «полностью перекрываемый первым допустимым evidence».

**Дефект:** один grammar attempt может быть прочитан как глобальное удаление provisional estimate по четырём core skills, что конфликтует с coverage/unknown-as-unknown. Альтернативное прочтение — замещение только соответствующего skill — не записано.

**Минимальная правка:** человек должен подтвердить scope. Безопасная формулировка: self-report перестаёт влиять отдельно по skill после evidence/confidence floor для этого skill; provenance сохраняется.

## B. Замки-безбилетники — ЧИСТО

Finish-postconditions защищают честность фиксации и обходятся явным `session abandon`, а не запирают обучение. Placement, re-entry и gates допускают отказ; prerequisites, backlog и `early` остаются рекомендациями. `recognition_only/avoid` — content-safety ограничение production, не learner lock.

## C. Дыры evidence-модели — НАХОДКИ

### C-R1. Engine-owned outcome всё ещё может полностью определяться клиентскими rubric-observations — `MAJOR`

**Цитата:** `wiki/product/learning-model.md` §3: «агент передаёт только проверяемые наблюдения … rubric-observations; итоговый review outcome вычисляет движок».

**Атака:** если observation schema допускает готовые семантические флаги вроде `criterion_satisfied=true`, агент дважды передаёт все флаги как true для слабого raw answer. Backend формально сам вычисляет outcome, но фактически получает готовую оценку другим именем. Cap и две сессии лишь замедляют накрутку.

**Минимальная правка:** расширить OPEN-7: observation обязан ссылаться на rubric criterion и конкретный source span/error; определить machine-checkable часть, subjective trust/cap, consistency validation и реакцию на observation, не подтверждаемое raw answer.

### C-R2. Целенаправленное объяснение агента всё ещё разрешено читать как learner evidence — `MAJOR`

**Цитаты:** `wiki/product/lexical-system.md` §3: «критерии 1–4 могут порождать evidence»; критерий 4 — «агент целенаправленно её объяснил». `wiki/product/learning-model.md` §3 требует для оценки «исходный текст ученика».

**Атака:** агент объясняет слово и регистрирует положительное evidence без learner attempt. Это не нарушает буквальную lexical-норму, но нарушает evidence-only модель.

**Минимальная правка:** все критерии входа сами по себе дают только enrollment. Evidence появляется лишь при отдельном сохранённом learner response; объяснение агента никогда не является evidence знания.

### C-R3. Не определена доверенная граница исходного learner text — `QUESTION`

**Цитаты:** `wiki/glossary.md`: агент — «не источник истины о прогрессе»; `wiki/flows/session.md`: именно агент передаёт `raw answer`; семантическая идентичность строится из `source-span`.

**Дефект:** hash доказывает повтор текста, но не то, что текст действительно пришёл от ученика. Если агент входит в threat model, он может создать уникальные вымышленные raw answers, которые проходят dedup/coverage.

**Минимальная правка:** явно выбрать trust model. Для untrusted agent — source reference на сообщение роли user, захваченное adapter boundary (`provider_message_id`, content hash, span); для trusted reporter — записать это допущение и границы Tutor Compliance.

## D. Целостность state machines — НАХОДКИ

### D-R1. `knowledge_state` всё ещё смешивает три оси — `MAJOR`

**Цитаты:** `wiki/product/learning-model.md` §4: «knowledge state — меняется только движком по evidence»; «review status (`due`/`overdue`) — служебный scheduling-слой»; затем «`REVIEW_DUE` … — knowledge state темы, к которой scheduler выставил review status `due`»; `INTRODUCED` создаётся enrollment без evidence.

**Дефект:** один enum кодирует tracking (`NEW/INTRODUCED`), знание и scheduling (`REVIEW_DUE`), хотя текст объявляет слои раздельными. `REVIEW_DUE` дублирует `review_status=due` и требует скрытого `prior_steady_state`; у review status нет нормального `not_due/scheduled` и reset-перехода.

**Минимальная правка:** оставить стабильное `knowledge_state`, вынести tracking и `review_status: not_due | due | overdue`; убрать `REVIEW_DUE` из knowledge enum. Если сохраняется composite state, отменить утверждение о раздельных слоях и формализовать `prior_steady_state`.

### D-R2. Нормативный `AT_RISK` расходится с диаграммой — `MAJOR`

**Цитаты:** `wiki/glossary.md`: «`AT_RISK` — зафиксирован REGRESSION либо просрочка вышла за порог»; `wiki/product/learning-model.md` §4: `REVIEW_DUE --> LEARNING: REGRESSION`, `ACTIVE --> LEARNING: REGRESSION`, а вход в AT_RISK показан только как `REVIEW_DUE --> AT_RISK: overdue сверх порога`.

**Дефект:** glossary отправляет regression в AT_RISK, диаграмма — в LEARNING.

**Минимальная правка:** синхронизировать glossary, диаграмму и будущую таблицу OPEN-10; если только тяжёлый/подтверждённый regression даёт AT_RISK, определить условие явно.

### D-R3. `ABANDONED` placement объявлен, но недостижим из нужных состояний — `MAJOR`

**Цитаты:** `wiki/flows/placement.md`, lifecycle: `STARTED → IN_PROGRESS → SUBMITTED → SCORED | ABANDONED`; CLI-контракт: `start/answer/submit/decline/resume`; audit: `STARTED/SUBMITTED/SCORED/DECLINED/RESUMED`.

**Дефект:** запись читается как переход `SUBMITTED → ABANDONED`, хотя abandon нужен из STARTED/IN_PROGRESS. Команды `placement abandon` и события `PLACEMENT_ABANDONED` нет; checkpoint-event тоже не назван.

**Минимальная правка:** формальная state diagram с `STARTED|IN_PROGRESS → ABANDONED`, запретом abandon после SCORED, CLI-командой и audit events для checkpoint/abandon. Уточнить OPEN-17.

## E. Невыполнимые или пустые MUST — НАХОДКИ

### E-R1. Файловая Obsidian-проекция ошибочно включена в ACID-терминализацию — `MAJOR`

**Цитаты:** `wiki/flows/session.md`: «единая атомарная транзакция … обновляет … Obsidian-проекцию» и «summary создаётся движком после commit терминализации»; диаграмма ставит `summary → projection` после terminalization.

**Дефект:** canonical DB/event log и файловую projection нельзя обновить одной ACID-транзакцией. Crash после commit оставит FINISHED/ABANDONED без summary/projection, вопреки обещанию атомарности.

**Минимальная правка:** атомарно коммитить authoritative state + events + outbox. Summary сохранить в той же UoW либо сделать идемпотентной derived projection; Obsidian обновлять post-commit с retry/catch-up и rebuild.

### E-R2. Новую CurriculumVersion нельзя провалидировать и активировать через заявленный API — `MAJOR`

**Цитаты:** `wiki/modules/curriculum.md` §4: `validate()` — «полная валидация активной версии»; §5: «невалидная версия не активируется». В API есть событие `CURRICULUM_VERSION_ACTIVATED`, но нет candidate validation/activation operation.

**Дефект:** проверить candidate до активации невозможно; проверка только active версии циклична, а emitter события не определён.

**Минимальная правка:** `validate(version_or_candidate)` + `activate(version, expected_active_version)`; activation атомарно требует успешный validation result и публикует событие.

### E-R3. Обычный LexicalItem не имеет mastery profile — `MAJOR`

**Цитаты:** `wiki/product/lexical-system.md` §3: «состояния — та же машина, что у тем» и «recognition и production evidence раздельно»; канонические dimensions в learning-model — `recognition`, `controlled_production`, `spontaneous_production`, `transfer`; Topic имеет `dimensions/mastery_criteria`, LexicalItem — нет.

**Дефект:** `production` не является machine-ID, а для обычного word/chunk не определены required dimensions и mastery criteria. OPEN-13 покрывает informal-policy, OPEN-14 — формы lexeme, но не generic LexicalItem.

**Минимальная правка:** versioned `LexicalMasteryProfile` по type/usage policy в 0.4, разрешимый из curriculum; validator проверяет наличие профиля. Добавить его в OPEN owner matrix.

### E-R4. «Полступени CEFR» не представима текущим Level schema — `MAJOR`

**Цитаты:** `wiki/product/learning-model.md` §5: общий estimate «не выше самого слабого core-навыка более чем на полступени»; `wiki/modules/curriculum.md` §2: Level id — `A1…C2`.

**Дефект:** ни sublevels (`A2+`, `B1-`), ни численная шкала полступени не определены; одинаковые данные дадут разные working estimate.

**Минимальная правка:** определить ordinal/sublevel representation и aggregation в OPEN-8/0.4 либо заменить правило на вычислимое по целым CEFR bands.

### E-R5. `frequency_band` по-прежнему содержит нечастотные категории — `MAJOR`

**Цитата:** `wiki/product/lexical-system.md` §1: `frequency_band` — «только corpus statistic», enum `core | high | useful | specialized | incidental`.

**Дефект:** `useful`, `specialized`, `incidental` — педагогические/доменные категории, а не интервалы численной частоты. Старое смешение частоты и приоритета частично сохранилось под двумя полями; импорт П.4 невоспроизводим без thresholds.

**Минимальная правка:** хранить numeric Zipf/source score и нейтральные bands с versioned thresholds (`very_high/high/mid/low/...`); utility/domain оставить в `curriculum_priority_band`/domains.

## F. Глоссарий-дрейф — НАХОДКИ

### F-R1. Confidence machine values и `self_reported_level` не нормализованы — `MINOR`

**Цитаты:** `wiki/glossary.md`: Confidence — «`low` / `very-low`»; learning-model использует `low-confidence`; placement — `very-low-confidence`. `self_reported_level` используется в learning/placement, но отдельного glossary-entry нет.

**Дефект:** code-font задаёт разные enum values, а важное provisional поле не имеет scope/lifecycle определения.

**Минимальная правка:** единый enum (`very_low | low | ...`) отдельно от UI labels; glossary-entry для `self_reported_level` и его per-skill/global scope.

## G. Пропущенные сценарии — НАХОДКИ

### G-R1. Pinned resume/replay конфликтует с active stale-safety — `BLOCKER`

**Цитаты:**

- `wiki/modules/curriculum.md` §5: «replay и resume используют pinned-версию, не current active».
- `wiki/product/lexical-system.md` §3b: несовместимые items «ре-валидируются против active version перед повторным использованием в production».
- `wiki/modules/curriculum.md` §5: «банк/формы ре-валидируются против active policy».
- `wiki/flows/session.md`: Session Manifest содержит pinned versions.

**Дефект:** после `safe_to_use → avoid` или сужения allowed context живая сессия/placement обязаны одновременно продолжить старую policy и запретить ещё не предъявленный production item. OPEN-9 и OPEN-14 не задают precedence; live manifests/review assignments не входят в stale-safety scope.

**Минимальная правка:** принять явный safety-overlay invariant. Historical evaluation/replay остаются pinned; будущая delivery из live manifest проверяется active safety-policy, несовместимое задание отменяется/заменяется append-only event с обеими версиями. Расширить OPEN-14 на live manifests и владельцев 0.2/0.5.

### G-R2. Finish отклоняется не только из-за «нечестной фиксации» — `MAJOR`

**Цитаты:** `wiki/flows/session.md`: «finish отклоняется только из-за нечестной фиксации»; `wiki/flows/continuation.md`: stale session revision отклоняется; session states FINISHED/ABANDONED терминальны; OPEN-11 требует same-key/different-payload semantics.

**Дефект:** finish также обязан отклонить stale revision, wrong/nonexistent session, invalid/terminal state и key collision; identical retry должен вернуть cached result, а не ошибку.

**Минимальная правка:** ограничить «только» бизнес-postconditions для валидной команды к текущей ревизии активной сессии; отдельно перечислить общие lifecycle/concurrency/idempotency errors.

### G-R3. Streak не определён на midnight/DST/timezone-change — `MAJOR`

**Цитаты:** `wiki/product/learning-model.md` §7–§8: «настраиваемая IANA-таймзона» и streak «по локальной календарной дате»; OPEN-12 описывает XP ledger, но не day attribution.

**Дефект/атака:** смена timezone может ретроактивно пересчитать practice days или дать два локальных дня за короткий интервал; неясны сессия через полночь, retry после полуночи и DST.

**Минимальная правка:** расширить OPEN-12: immutable `practice_day` из `occurred_at` + snapshot/effective timezone, day dedup, cross-midnight rule; прошлые дни при смене зоны не пересчитывать.

## H. Informal-слой — НАХОДКИ

### H-R1. Safety validator не закрывает currency и полный informal schema — `MAJOR`

**Цитаты:**

- `wiki/product/lexical-system.md`: `obsolete` — значение currency, но stale-safety приводит псевдопереход `safe_to_use → recognition_only/avoid/obsolete`.
- `wiki/modules/curriculum.md` §5 исключает из production только `avoid/recognition_only`.
- Lexical-system требует у `meme_template` культурный контекст; validator проверяет только нейтральное объяснение.
- Generic LexicalItem schema не задаёт machine-predicate informal, а validator требует usage_policy только у «informal-единицы».

**Дефект:** `usage_policy: safe_to_use + currency: obsolete` проходит свежую generation/scheduler; meme без cultural context активируется; рискованный `type: word`/register может обойти policy из-за неопределённого predicate.

**Минимальная правка:** вычисляемый `production_eligible` из active usage_policy+currency; `obsolete` исключает production и новые assignments. Определить `requires_usage_policy` по type/register; добавить `cultural_context` и обе проверки в validator.

## I. Данные и лицензии — НАХОДКИ

### I-R1. Таблица всё ещё занижает обязанности CC BY-SA — `MAJOR`

**Цитаты:** `wiki/modules/curriculum.md` §3: объединённая CEFR-J/Octanove строка имеет obligations только «цитирование»; для wordfreq data CC BY-SA указано только `attribution`; build-time описан как минимизация ShareAlike boundary.

**Дефект:** Octanove C1/C2 и wordfreq data имеют CC BY-SA obligations, а отсутствие raw dataset само по себе не решает, является ли распространяемый отобранный лексикон Adapted Material. OPEN-15 признаёт вопрос, но текущая таблица уже даёт более слабую норму.

**Минимальная правка:** разделить CEFR-J A1–B2 и Octanove C1/C2; для каждого CC-source указать conditional notices/change marking/ShareAlike; первый publish/import commit блокировать OPEN-15. Первичные источники: [CEFR-J/Octanove terms](https://github.com/openlanguageprofiles/olp-en-cefrj#terms-of-use), [wordfreq license](https://github.com/rspeer/wordfreq#license), [CC BY-SA 4.0 §3](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en#s3a).

### I-R2. Принятый safe default для living layer остался только в journal — `MAJOR`

**Цитаты:** `staging/journal/2026-07-19-concept-review-triage.md`, «Дефолты»: «living layer хранит короткую единицу + свой парафраз, без сторонних excerpts, до rights_basis»; `wiki/README.md`: journal «никогда не является источником истины»; канон лишь ссылается на OPEN-15.

**Дефект:** принятая защита не стала нормативной; provenance не даёт право копировать forum post/example, а канон не запрещает ingestion до решения.

**Минимальная правка:** canonical `MUST NOT` на сторонние excerpts до закрытия OPEN-15; разрешены source metadata, короткая единица и собственный neutral paraphrase.

### I-R3. `transformations` обязателен, но validator его не проверяет — `MAJOR`

**Цитаты:** `wiki/modules/curriculum.md` §3: «каждая импортированная запись несёт `source_refs` + `transformations`»; §5 validator проверяет только `source_refs`/SourceArtifact.

**Дефект:** импорт без журнала изменений проходит activation, ломая reproducibility и CC change marking.

**Минимальная правка:** поле в imported LexicalItem schema и validation; для неизменённой записи явное `transformations: [identity]`.

## J. Полнота OPEN и roadmap — НАХОДКИ

### J-R1. Owner/carrier matrix OPEN-7/10/14/16/17 противоречива — `MAJOR`

**Точные расхождения:**

- OPEN-7: `OPEN.md` назначает `0.4 + 0.2`, roadmap 0.2 его не перечисляет.
- OPEN-10: learning-model отдаёт полную state-transition table в 0.4, а OPEN/roadmap — только 0.5 + 0.2.
- OPEN-14: lexical contract относит scoring/агрегацию форм к 0.4, OPEN — к curriculum detail + П.3.
- OPEN-16: learning-model и OPEN назначают П.3, roadmap объявляет carrier 0.4.
- OPEN-17: владелец `0.5 + assessments`, но отдельного `assessments.md` deliverable в roadmap нет.
- Continuation отдаёт kernel «уникальный terminal outcome ReviewAssignment», хотя README запрещает business logic в platform.

**Дефект:** соседние контракты могут каждый считать механизм чужой обязанностью.

**Минимальная правка:** единая component→owner matrix: kernel — envelopes/CAS/UoW; 0.4 — evidence admissibility, LearningTarget transitions и lexical scoring; 0.5 — Session/Attempt lifecycle; assessments — отдельный named artifact; П.3 — bank/policy lifecycle.

### J-R2. Roadmap не проводит OPEN-14/15/16 как реальные зависимости — `MAJOR`

**Цитаты:** OPEN-14/16 назначены П.3, но строка П.3 их не упоминает; OPEN-15 блокирует 0.3 detail + П.4, но П.4 зависит только от П.1/0.3. Roadmap разрешает статусы `planned/next/in-progress/done/blocked`, но использует неопределённый `done-with-open`.

**Дефект:** П.3/П.4 могут стартовать и считаться завершёнными без механизмов, которые реестр назначил им как blocking owners; статус нельзя интерпретировать однозначно.

**Минимальная правка:** П.3 зависит от/закрывает OPEN-14/16; П.4 сначала закрывает OPEN-15, затем импортирует. Определить `done-with-open` либо использовать объявленные статусы.

### J-R3. Re-entry thresholds ошибочно направлены в суженный OPEN-1 — `MAJOR`

**Цитаты:** `wiki/flows/session.md`: «Численные пороги re-entry — OPEN-1»; `wiki/OPEN.md`: OPEN-1 — пороги Mastery/Stability/Retrievability «только они»; learning-model требует ещё порог длины перерыва.

**Дефект:** Retrievability threshold можно считать частью OPEN-1, но gap-duration и scheduler-policy не имеют владельца.

**Минимальная правка:** расширить/разделить OPEN с владельцем `0.4 scheduler`; синхронизировать session и roadmap.

## Вердикт по шести документам

| Документ | Вердикт | Причина |
|---|---|---|
| `wiki/product/learning-model.md` | `PASS-with-findings` | state axes, outcome timing, self-report/half-step и trust boundary |
| `wiki/product/lexical-system.md` | `FAIL` | участвует в G-R1; generic lexical mastery и currency safety неполны |
| `wiki/modules/curriculum.md` | `FAIL` | участвует в G-R1; candidate activation, validator и license table |
| `wiki/flows/session.md` | `FAIL` | участвует в G-R1; terminalization/outcome/atomic projection |
| `wiki/flows/continuation.md` | `PASS-with-findings` | finish/concurrency wording и domain-owner boundary |
| `wiki/flows/placement.md` | `PASS-with-findings` | lifecycle/abandon, pin scope и schema drift |

`FAIL` возвращён не из-за отсутствия будущего механизма как такового, а из-за одновременных противоположных MUST в G-R1. После одного precedence-решения этот blocker снимается; остальные находки — contract work, не запрет на П.1.

## Проверено, ок

- Клиентская готовая review-classification действительно запрещена; outcome принадлежит движку. C-R1 — более узкий trust-boundary вопрос, не повтор старого A-1/C-1.
- Semantic identity, source-span/item-exposure, independence и multi-credit имеют несущий MUST и честный OPEN-7.
- CEFR coverage, confidence floor и unknown-as-unknown закреплены в OPEN-8.
- ABANDONED сохраняет evidence, закрывает недостигнутые цели как `INSUFFICIENT_EVIDENCE(reason=abandoned)` и не создаёт fake independence.
- Restore `MASTERED → REVIEW_DUE → CONFIRMED → MASTERED` записан явно.
- XP award-once/ABANDONED eligibility вынесены в OPEN-12; штрафов и списаний нет.
- Placement получил incremental checkpoint/resume, terminal submit, exposure history и потолок ACTIVE; дефект D-R3 касается только формальной ветки abandon.
- Informal recognition исключён из CEFR; production допускается через `contribution_scope` с dedup/cap carrier OPEN-13.
- `context_dependent`, volatility/currency и form aggregation получили инварианты; H-R1 касается оставшихся validation paths.
- Заявленные source licenses и snapshot wordfreq ~2021 подтверждаются upstream; проблема I-R1 — неполная таблица obligations, не неверный выбор источников.
- Все OPEN-ID, упомянутые в каноне, существуют в `OPEN.md`; дефект J — owners/dependencies, не orphan IDs.
- П.2 действительно зависит от 0.4; П.1 не зависит от scoring и остаётся разблокированной.
