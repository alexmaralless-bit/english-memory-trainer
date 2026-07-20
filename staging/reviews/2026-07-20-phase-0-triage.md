# Триаж сквозного ревью фазы 0

Дата: 2026-07-20 · Вход: `2026-07-20-phase-0-review-codex.md` (FAIL: 4 BLOCKER, 7 MAJOR, 3 MINOR, 3 QUESTION) · Исполнитель: Claude

## Итог

**Принято и исправлено — 17 из 17** в первом прогоне и **10 из 10** в повторном (§ ниже). Отклонённых находок нет. Ревью точное: почти все цитаты подтвердились на первоисточниках дословно, и **большая часть дефектов — следствие моих же правок последних суток**, когда новая ось `transparency` и трек `everyday-life` дошли не до всех владельцев.

## BLOCKER

### P0-1 — REGRESSION → AT_RISK

Тотальная таблица переходов не содержала ни одной ветки в `AT_RISK` по REGRESSION, а MUST пятью строками ниже утверждал обратное. Enum исходов содержит один `REGRESSION`; поля «тяжесть», которое требовалось глоссарию («лёгкий опускает в LEARNING»), не существует.

**Решение:** побеждает таблица. `AT_RISK` возникает **только** из `OVERDUE_AT_RISK_TRIGGERED`; REGRESSION всегда понижает состояние. Разделение смысловое: `AT_RISK` — «знал, рискует забыть от простоя», REGRESSION — «продемонстрировал, что не владеет». Синхронизированы scoring §3, learning-model §4, glossary.

Это выбор семантики, а не только правка текста: если считаешь, что провал на MASTERED-теме должен помечать её «под угрозой», а не понижать, — скажи, разверну обратно и добавлю поле тяжести.

### P0-2 — ReviewAssignment нельзя закрыть

Три спеки противоречили друг другу: evidence говорил «finish/abandon закрывает все pending», lessons — «finish отклоняется, если pending непуст, это **не** авто-закрытие», а CLI не имел команды закрытия вовсе. Сессия с назначенным review оказывалась штатно незавершаемой.

**Решение:** добавлена `trainer review close` (владелец evidence, идемпотентна). `finish` **требует** пустой pending-set, `abandon` преобразует остаток в `INSUFFICIENT_EVIDENCE(reason=abandoned)`. Формулировка evidence исправлена: прежняя позволяла завершить сессию без исходов, то есть обойти персистентность evidence — ровно то, что finish обязан не допускать.

### P0-3 — `transparency` не дошла до scoring

Вчера я довёл новую ось до lexical-system, curriculum и glossary, но **не до scoring**, который владеет `LexicalMasteryProfile`. Для `opaque + safe_to_use` curriculum запрещал требовать production, а scoring его добавлял.

**Решение:** lookup стал тотальным по `(type, transparency, usage_policy)` с явной таблицей и правилом precedence — **ограничение сильнее разрешения**: `controlled_production` попадает в required, только если разрешают обе оси. Ключевая клетка `opaque + safe_to_use`: производить идиому безопасно, но требовать нельзя.

### P0-4 — нет контрактов `learner`, `audit`, `gates`

Конституция требует одну спеку на модуль; CLI уже назначил этим модулям MVP-команды (`status`, `audit session`, `gate begin/submit/evaluate`), то есть CLI создавал бизнес-контракт вместо владельца. Плюс `session next` числится за lessons, но в её public API отсутствует, и алгоритм композиции curriculum+scheduler+learner не описан.

**Решение:** заведён **OPEN-25**, четыре строки в owner-матрицу и новый этап **0.11** в roadmap. Фаза 0 закрывала восемь контрактов из `design-direction` §5 — эти три туда никогда не входили, но дыра реальна, и честнее её зарегистрировать, чем считать фазу завершённой.

## MAJOR

| # | Что было | Что стало |
|---|---|---|
| P0-5 | flow continuation требовал `AGENT_ATTACHED` и session notes, которых нет ни у одного владельца | `AGENT_ATTACHED` + `attach_agent` → lessons (событие сессионное); `SessionNote` → evidence, явно **untrusted** и не evidence для scoring |
| P0-6 | `placement decline` отсутствовал в реестре команд | добавлена в CLI с пометкой **per-skill** self-report |
| P0-7 | memory обещал полный rebuild из event-store, но foundation запрещает считать operational state event-sourced | источник объявлен постранично: learning-страницы — replay событий, operational — render из authoritative SQLite/snapshot. Drift сверяется с объявленным источником |
| P0-8 | нормативная таблица треков содержала 8 и не знала `everyday-life`, а данные и scoring — знали | девять треков, `everyday-life` (домен) отделён от `everyday-online-informal` (регистр); SHOULD «рабочий контекст» расширен до «рабочий **или** бытовой» |
| P0-9 | living layer одновременно `[mvp]` и «в MVP не строится» | workflow и `LEXICAL_ITEM_ADDED` помечены `[post-mvp]`; поля и запрет excerpts остаются в target |
| P0-10 | «отклоняется **или** помечается» вверху, «единственная ветка `rejected`» внизу | одна ветка везде |
| P0-11 | adapters переиспользовал `3`/`5` с чужой семантикой: drift ≠ CAS-конфликт | drift → `6 PRECONDITION_FAILED` + `next_action: skills.sync`; `3` только за сломанную структуру |

## MINOR

- **P0-12** — roadmap ссылался на закрытые OPEN-13/15, lexical-system на закрытый OPEN-8 вместо OPEN-22. Синхронизировано. Заодно починены две настоящие битые wiki-ссылки (`[[README]]`, `[[glossary]]` из `modules/` без `../`).
- **P0-13** — `Last updated: 2026-07-19` в файлах, содержащих `[PD-2026-07-20]`. Обновлено, добавлены записи истории с перечнем новых полей.
- **P0-14** — glossary держал ссылку на «ordinal/sublevel» через закрытый OPEN-8. Working level определён прямо: целые bands, не выше слабейшего core-навыка, `measured` vs `provisional`.

## QUESTION

- **Q1** — порядок проверки skills. Зафиксирован строго: `resolve` всех версий → UoW → commit → `SESSION_STARTED`. Потребитель события в adapters переопределён как пост-фактум аудит, а не сама проверка.
- **Q2** — `REVIEW_DUE`. Объявлен **идемпотентным уведомлением, не источником истины**: `due` вычисляется из расписания и Clock, событие несёт `boundary_at` и ключ `(target_id, dimension_id, schedule_epoch)`. Противопоставлено `OVERDUE_AT_RISK_TRIGGERED`, который фактом **является**, потому что меняет состояние.
- **Q3** — доверие Tutor Compliance. Обязательства вычисляются из **наблюдаемых движком** эффектов (вызовы CLI + доменные события), а не из самоотчёта. `SKILL_COMPLETED` сам по себе obligation не закрывает; его расхождение с эффектами — само по себе диагностический сигнал.

## Что ревью подтвердило как корректное

Атомарность event-store, честно открытый kernel-долг (OPEN-19/20/21), safety-overlay, placement exposure в evidence, CAS и uniqueness, ordering scheduler, numeric-детерминизм, отсутствие висячих OPEN-ID. Эти места переживают уже четвёртый прогон ревью без замечаний.

## Повторное ревью (`2026-07-20-phase-0-rereview-codex.md`)

Вердикт FAIL: 1 BLOCKER, 6 MAJOR, 2 MINOR, 1 QUESTION. **Принято полностью.**

**R-1 — мой over-claim.** «Все четыре BLOCKER сняты» неверно: сняты три, а P0-4 **зарегистрирован как долг**, что не равно исправлению. Это третий случай той же ошибки за проект (`mastery_criteria`, `learner_priority`, теперь этот). Roadmap исправлен: фаза 0 **не завершена**, 0.10 переведён в `done-with-open`, вертикальный срез не начинается до 0.11.

Остальные шесть MAJOR — один и тот же класс: правило исправлено у одного владельца и осталось устаревшим у соседнего.

| # | Что осталось несинхронным | Исправлено |
|---|---|---|
| R-2 | `RECOVERED` объявлен «после AT_RISK/REGRESSION», но после P0-1 regression в AT_RISK не ведёт → outcome стал недостижимым | `RECOVERED` только из `AT_RISK`; рост после regression — обычные `PROGRESS`/`CONFIRMED` |
| R-3 | flow continuation по-прежнему назначал `AGENT_ATTACHED` модулю audit, а cold resume не мог передать провайдера | владелец — lessons; `resume --provider` фиксирует подключение атомарно |
| R-4 | lessons включал `finish` в closure triggers рядом с MUST, который это запрещает; evidence звал несуществующую `review record` | триггер — только `abandon`; точные имена команд |
| R-5 | команда `placement decline` появилась, а payload остался скаляром `A2` на четыре навыка | versioned schema-объект по core-skill ID; скаляр и broadcast запрещены |
| R-6 | §5 описал гибридный источник страниц, а public API девятью строками ниже снова обещал rebuild только из событий | `rebuild()` описан как гибридный по page-source manifest |
| R-7 | flow требовал сохранения observed-фактов и явного отказа от re-entry, а команд для них не существовало | `trainer observed record`, `trainer reentry decline` |

MINOR R-8/R-9: закрытые OPEN-13 и OPEN-8 всё ещё стояли в разделах «Открытые вопросы» своих спек — перенесены. QUESTION R-Q1: ось `type` не переопределяет required dimensions, а управляет пост-обработкой (агрегация форм lexeme); порядок разрешения записан явно.

## Осталось

**OPEN-25 / этап 0.11** — контракты `learner`, `audit`, `gates` и владелец `session next`. Реализацию вертикального среза (фаза 2) начинать до него нельзя: три модуля без API, событий и инвариантов.
