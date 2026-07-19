# Повторное red-team ревью: Application Foundation (0.2)

Дата: 2026-07-19  
Предмет: `wiki/platform/foundation.md` и его стыки с принятым каноном.  
Метод: только документы; факты об отсутствующем коде не предполагаются. Принятые `[PD-…]` (гибридная модель, тонкий `sqlite3`, safety-overlay) не оспариваются.

## 1. Резюме: топ-5

1. **BLOCKER — JSONL назван event-source-of-truth, но UoW обещает ACID-коммит с ним без атомарного носителя.** SQLite-транзакция не делает append в файл JSONL частью своего commit. Crash оставляет либо state без event, либо event без state; это прямо ломает replay и заявленную границу источников истины.
2. **MAJOR — «bit-for-bit replay» не имеет детерминированного порядка и числового контракта.** Нет log sequence/порядка равных timestamps, канонического `payload_hash`/сериализации, правил сортировки и numeric/rounding policy. Инъекция clock/random этого не исправляет.
3. **MAJOR — exposure history отнесена к non-rebuildable SQLite, хотя определяет вес повторного placement-evidence.** Следовательно, replay learning-части может получить иной результат после потери/восстановления operational state.
4. **MAJOR — outbox обещает retry/catch-up, но не определяет идентичность, дедупликацию и порядок consumer-доставки.** Повторная или переупорядоченная доставка может оставить projection в неверном состоянии; полный rebuild — ручная компенсация, не crash-recovery protocol.
5. **MAJOR — kernel лишь называет idempotency для compound-команд и correction events.** Нет атомарной семантики `abandon+start` и нет способа применить correction при replay. Это не предоставленный механизм, а ссылка на OPEN-11.

## 2. Находки A–K

## A. Гибридная граница источника истины — НАХОДКИ

### A-1. Authoritative JSONL не входит в заявленную ACID-транзакцию — BLOCKER

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: «**event-sourced** — append-only DomainEvents = источник истины | JSONL event log + SQLite как rebuildable read-model»; там же: «одна ACID-транзакция коммитит authoritative state + соответствующие DomainEvents + outbox-записи».

**Почему дефект:** JSONL — файловый append, а SQLite ACID-транзакция — другой ресурс. Контракт не выбирает ни transactional event-table с JSONL как derived export, ни журналируемый recovery protocol для двух ресурсов. После crash возможны SQLite-state без authoritative event либо JSONL-event без SQLite-state. В первом случае replay теряет learning-факт, во втором rebuild/read-model получает незафиксированный факт. Это не вопрос реализации: одновременно выполнить оба MUST в пределах описанного механизма невозможно.

**Предлагаемая правка:** назначить один транзакционный event-store внутри SQLite источником commit (event rows + state + outbox в одной UoW), а JSONL определить как проверяемый/rebuildable export; либо описать эквивалентный crash-safe write-ahead/recovery protocol и его canonical ordering.

### A-2. Exposure history имеет неясную принадлежность и может менять replay-результат — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: «Операционное: … exposure history … | **SQLite-authoritative**»; `wiki/flows/placement.md`, «Правило форм и exposure»: «вес повторно увиденных items понижается или обнуляется»; `wiki/product/learning-model.md`, §6: «exposure-history и cooldown повторных прохождений».

**Почему дефект:** exposure определяет допустимый вклад placement-ответа в evidence, а значит потенциально Mastery/working level. При SQLite-only exposure history replay из learning-event log не может доказуемо воспроизвести этот вес. Если вес записывается как факт в evidence, это надо явно требовать; если вычисляется при replay, history должна быть event-sourced/pinned. Сейчас возможны два результата при одинаковых learning-events.

**Предлагаемая правка:** в projection boundary явно выбрать: (а) event-source exposure для scoring, либо (б) immutable `exposure_decision`/вес в событии evidence с версией policy и source item; operational cooldown оставить отдельным, не влияющим на replay.

### A-3. Граница не классифицирует `self_reported_level`, `practice_day`/streak и `prior_steady_state` — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: список learning-state — «evidence, review outcomes, scores … XP-ledger, knowledge state»; список operational-state — «сессии, Attempt-lifecycle, review-очереди, exposure history, черновики»; там же: «projection boundary документирована: какие read-models rebuildable … а какие — SQLite-authoritative».

**Почему дефект:** канон требует отдельный `self_reported_level` с per-skill provenance, immutable `practice_day` для streak и явный `prior_steady_state`. Ни одно поле не попало в исчерпывающую классификацию. В частности, `practice_day` должен быть replayable рядом с XP-ledger; `prior_steady_state` влияет на restore; `self_reported_level` влияет на working estimate и briefing. Таблица с примерами не отвечает, где их truth и можно ли их восстановить.

**Предлагаемая правка:** добавить нормативную field/aggregate boundary-таблицу: truth class, canonical event/state, rebuildability и snapshot requirement для этих полей, ReviewAssignment/queue и всех данных, влияющих на scoring/recommendations.

### A-4. ReviewAssignment разделён между operational queue и event-sourced ReviewOutcome без link/reconciliation contract — QUESTION

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: «review outcomes» — learning event-sourced, но «review-очереди» — SQLite-authoritative; `wiki/glossary.md`: «ReviewAssignment … Имеет ровно один ReviewOutcome».

**Почему дефект:** не задано, хранится ли идентичность/содержимое assignment в самом outcome-event и как queue при терминализации согласуется с ним. Потерянная/восстановленная operational queue способна оставить replayable outcome без assignment либо assignment без terminal outcome. Это может быть допустимой моделью, но контракт её не выбирает.

**Предлагаемая правка:** явно определить `ReviewAssignment` как operational aggregate с неизменяемой event-reference и reconciliation/recovery rule либо перенести минимальный assignment snapshot в event payload.

## B. Детерминизм — НАХОДКИ

### B-1. Bit-for-bit claim не закрывает порядок, hash и числа — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.3 задаёт поля event: «`id`, `type`, `occurred_at` … `payload_hash`»; §5: «одинаковые события + timestamps + pinned policy-версии ⇒ одинаковое learning-состояние (bit-for-bit по значимым полям)».

**Почему дефект:** timestamp не задаёт total order для равных instants; ULID-like ID также не объявлен canonical event order. Не определены canonical JSON/Unicode/decimal representation и алгоритм `payload_hash`, порядок обхода map/set и aggregation, запрет/rounding IEEE float. Разные process hash-seed, SQLite query order, Python iteration или порядок равновременных событий способны дать разные hash, sequence transitions и итог scores при тех же входных facts.

**Предлагаемая правка:** в kernel определить monotonic append sequence (и tie-breaker replay), canonical encoding + hash algorithm, sorted collection/query rules; в 0.4 потребовать deterministic numeric representation/rounding в pinned scoring policy. Проверки replay должны включать shuffled insertion/equal-timestamp cases и разные hash-seed.

### B-2. Outbox не имеет детерминированного порядка доставки — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.7: «outbox — надёжная доставка post-commit эффектов … с retry/catch-up и полным rebuild»; §5 требует crash-test, при котором «не теряет и не дублирует данные».

**Почему дефект:** retry означает at-least-once. Без immutable message ID, consumer inbox/dedup key, acknowledgement, ordering key и правила late delivery consumer может применить один event дважды или применить старый после нового. Для non-commutative Obsidian/SQLite projection это именно дублирование/откат, которое §5 запрещает.

**Предлагаемая правка:** описать outbox record ID, delivery/ack state, per-projection idempotency/inbox и ordering (global sequence либо aggregate partition); задать обязательные duplicate/out-of-order crash tests.

## C. Делегированные kernel-инварианты — НАХОДКИ

### C-1. «Compound-команда» названа, но не имеет atomic/CAS semantics — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.4: «Покрывает attempt/review/finish/placement submit и **compound-команды**»; `wiki/flows/session.md`, «Сценарий»: «`session resume | session abandon + session start`».

**Почему дефект:** cached response для одного ключа не говорит, какие subcommands входят в итог, проверяются ли все expected revisions до записи, что возвращать при частичном выполнении или как восстанавливаться после crash. Два отдельных вызова `abandon`, затем `start` не эквивалентны одной идемпотентной операции: crash между ними меняет observable session state. UoW обещана для state/events/outbox, но не связывает command composition с единой decision point.

**Предлагаемая правка:** в kernel задать compound-command envelope/result, one-UoW all-or-nothing, набор expected revisions и один idempotency record; либо flow должен нормативно сказать, что это две независимые команды и описать recovery. Выбор — вопрос владельца, но механизм обязан быть один.

### C-2. Correction event не имеет replay-правила — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.6: «append-only correction-события с обеими версиями»; §9: «OPEN-11: … CAS/**correction protocol**».

**Почему дефект:** не определено, что correction адресует (event/effect/projection), отменяет ли исходный эффект, допускается ли цепочка corrections, какой порядок и idempotency key применяет replay. Наличие имени события не даёт корректной семантики: replay может повторно засчитать и исходный, и исправленный effect. OPEN-11 тоже не формулирует protocol, хотя owner-матрица отдаёт его kernel.

**Предлагаемая правка:** определить generic correction envelope (`corrects_event_id`, replacement/effect semantics, sequence, idempotency) и reducer contract; конкретное бизнес-решение оставить 0.4/0.5. Добавить duplicate/correction-chain replay tests.

### C-3. Scope idempotency заявлен обязательным, но остаётся не задан — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.4: «`idempotency_key` имеет **определённый scope**»; §9: «OPEN-11: **idempotency scope** …».

**Почему дефект:** scope (per learner, aggregate, command type, provider или global) определяет, являются ли две команды collision либо повтором. Здесь одновременно MUST «определён» и указано, что он ещё открыт; cached result также не имеет schema/retention. Это не может быть проверено или одинаково реализовано modules до 1.2.

**Предлагаемая правка:** минимум зафиксировать generic key namespace и retention/result schema в 0.2; если выбор продуктово зависит от контекста — зарегистрировать отдельный QUESTION, но не называть механизм уже предоставленным.

## D. Owner-граница — НАХОДКИ

### D-1. Kernel сам приводит не принадлежащие ему business event types — MINOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §4: «Примеры сквозных: `SKILL_REQUIRED/STARTED/COMPLETED/FAILED`, `AGENT_ATTACHED`, `CURRICULUM_VERSION_ACTIVATED`»; там же: «конкретные типы принадлежат модулям».

**Почему дефект:** `AGENT_ATTACHED` имеет audit/continuation owner, `CURRICULUM_VERSION_ACTIVATED` — curriculum owner, а семейство `SKILL_*` не названо owner-матрицей вообще. Kernel одновременно заявляет, что не определяет types, и закрепляет их перечнем. Это создаёт неучтённую domain surface и риск business leakage в platform.

**Предлагаемая правка:** убрать типы из kernel либо рядом указывать module-owner и ссылку на его контракт; не вводить `SKILL_*`, пока владелец/канон не определены.

### D-2. «Kernel-часть Attempt/Session lifecycle» пересекает матрицу владельцев — QUESTION

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §9: «OPEN-10: **kernel-часть Attempt/Session lifecycle** (finalize/recover, crash между attempt↔review); сами машины — 0.5»; `wiki/OPEN.md`, owner-матрица: «Session + Attempt lifecycle, терминализация … | **0.5 lessons**».

**Почему дефект:** возможно, под «kernel-частью» имеются в виду лишь UoW/CAS primitives, но слова `finalize/recover` уже выглядят lifecycle-поведением. Матрица требует одного contract-owner, поэтому граница пока не проверяема.

**Предлагаемая правка:** заменить на «kernel предоставляет UoW/CAS/idempotency для lifecycle-команд» и оставить `finalize/recover` только в 0.5, либо дополнить matrix точным mechanism split.

## E. Атомарность и crash-recovery — НАХОДКИ

### E-1. Crash между SQLite commit и authoritative JSONL append не покрыт — BLOCKER

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: «event log … JSONL» и «одна ACID-транзакция коммитит … DomainEvents»; §5: «crash между commit и projection не теряет и не дублирует данные».

**Почему дефект:** это тот же корневой дефект, что A-1, но здесь он нарушает прямой crash-recovery MUST. Outbox может восстановить только post-commit projections; он не делает atomic append authoritative JSONL и SQLite.

**Предлагаемая правка:** применить правку A-1 и добавить crash cases до/после durable event-store commit, before/after JSONL export и recovery verification.

### E-2. Rebuild описан без протокола частично применённых delivery/projection — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.7: «retry/catch-up и полным rebuild»; §3.8: «есть команда полного rebuild».

**Почему дефект:** не определены checkpoint/version projection, атомарный swap rebuilt view и поведение concurrent outbox delivery во время rebuild. После crash midway можно смешать старую частичную проекцию с новым replay, а поздний outbox message снова испортит результат. Statement «есть команда» не является recovery protocol.

**Предлагаемая правка:** задать projection offset/checkpoint, isolate-and-swap rebuild, replay up to high-water mark и затем ordered catch-up; фиксировать applied offsets atomically с consumer state.

## F. Pinning и safety-overlay — НАХОДКИ

### F-1. Старый pinned policy snapshot может исчезнуть — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.6: «Каждая версия — иммутабельный snapshot, адресуемый по id» и «Replay и resume резолвят policy по pinned-версии»; `wiki/modules/curriculum.md`, §5: «исходная версия сохраняется в snapshot» и «tombstones сохраняются».

**Почему дефект:** immutability/addressability не устанавливают retention: registry может перестать содержать retired version или snapshot. Тогда deterministic replay/resume не может выполнить MUST и не определено, fail ли операция, использует ли alias либо восстанавливает архив. Curriculum требует сохранения, foundation обязан предоставить capability/ошибку для отсутствующей версии.

**Предлагаемая правка:** требовать immutable retention всех pinned snapshots/tombstones либо durable embedded policy artifact; задать `PinnedPolicyUnavailable` как hard error, recovery/export protocol и compatibility with retired IDs. Safety-overlay оставить отдельным active resolver, как уже принято.

### F-2. Safety precedence сформулирован согласованно — ЧИСТО

Проверено: `foundation` §3.6, curriculum §5, lexical §3b, session и resolved OPEN формулируют одно правило: historical evaluation/replay использует pinned scoring, а live production delivery проверяет active `production_eligible`; отмена/замена — append-only event с обеими версиями. Это не повтор старого G-R1.

## G. Идемпотентность и конкурентность на стыке — НАХОДКИ

### G-1. CAS per aggregate не задаёт atomic concurrency для cross-aggregate операции — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.5: «сессии и другие изменяемые агрегаты имеют `revision`; запись — compare-and-set по ожидаемой ревизии»; §3.7: «атомарный commit state + events + outbox».

**Почему дефект:** не сказано, может ли одна UoW conditional-commit проверить и изменить несколько aggregates (Session, ReviewAssignment, Attempt/queue, XP award) без частичного success и как она сообщает stale revision. Для двух агентов это важнее одиночного CAS: один может закрыть session, другой — terminal review/XP на прежнем state. Уникальность outcome верно оставлена 0.5, но kernel не описывает техническую возможность её атомарно проверить вместе с session revision.

**Предлагаемая правка:** описать multi-aggregate expected-revisions/conditional writes как kernel mechanism; 0.5 добавит unique business constraint и выбирает aggregate boundaries.

### G-2. Мутации placement/curriculum/XP формально охвачены, но без проверяемого coverage register — MINOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.3: «каждая мутация — `Command`»; §3.4 явно перечисляет «attempt/review/finish/placement submit», но не curriculum activate и XP award.

**Почему дефект:** общий MUST логически распространяется на них, поэтому это не отсутствие правила. Однако перечень выглядит как исчерпывающий acceptance scope и не даёт CI/contract test способ доказать, что activate/award и другие commands проходят idempotency/CAS/UoW.

**Предлагаемая правка:** добавить command registry/contract-test requirement: каждый published mutation endpoint объявляет idempotency/CAS/UoW class; явно включить `curriculum activate`, placement checkpoints/abandon и XP awards.

## H. Пустые или непроверяемые MUST — НАХОДКИ

### H-1. «Projection boundary документирована» не имеет проверяемого артефакта — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2: «**MUST**: projection boundary документирована».

**Почему дефект:** текущая двухстрочная таблица не исчерпывает state fields/aggregates и уже пропускает A-3/A-4. Нет требуемого файла, schema, owner или теста, который сверяет Repository/read-model с классификацией. Формулировка не делает MUST проверяемым.

**Предлагаемая правка:** требовать versioned boundary manifest (aggregate/field → truth store → event/read model → rebuild/snapshot policy) и CI check, что каждая persisted model зарегистрирована.

### H-2. Архитектурные checks названы, но не специфицированы как CI-gate — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §8: «прямой импорт внутренностей чужого модуля запрещён (import-boundary чек в CI)»; «доменный код не обращается к системным часам/random/IO напрямую — … (чек)».

**Почему дефект:** не названы directory/layer map, разрешённые adapter exceptions, собственно инструмент/правило AST, список запрещённых APIs и условия fail. Особенно «IO» включает легитимные persistence/adapters; без boundary checker он либо неизбежно false-positive, либо не ловит обход. Нельзя написать воспроизводимый CI-gate по этой норме.

**Предлагаемая правка:** добавить machine-readable dependency/layer allowlist и AST/lint rules (включая exceptions только в adapters/kernel), команды CI и минимальные violation fixtures.

## I. Глоссарий-дрейф — ЧИСТО

Проверено: `Command / DomainEvent envelope`, `pinned_versions`, `Unit of Work`, `Transactional outbox`, `Policy registry`, `Snapshot` и `Event log` определены в `wiki/glossary.md` один раз и соответствуют `foundation` §§2–3. Термин `SourceArtifact` не подменён kernel-термином. Найденная в A-3 неполнота — граница состояния, а не расхождение определений терминов.

## J. Полнота OPEN и roadmap — НАХОДКИ

### J-1. Новые незакрытые механизмы kernel не имеют OPEN-владельца — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §5: «bit-for-bit» и «crash-recovery»; §3.7: «retry/catch-up»; §9 перечисляет только «OPEN-9», «OPEN-10», «OPEN-11».

**Почему дефект:** atomic event-store/JSONL, deterministic ordering+encoding+numeric interface, outbox consumer idempotency/order и pinned-policy retention — самостоятельные нерешённые mechanisms из A/B/E/F. Их нет в `wiki/OPEN.md`, значит нет owner, blocking relation и acceptance criteria. Нельзя считать, что OPEN-9/11 покрывают всё: их формулировки не содержат JSONL atomicity/outbox delivery semantics, а owner-матрица требует один контракт-владелец.

**Предлагаемая правка:** завести отдельные OPEN либо расширить OPEN-9/11 с явными подпунктами и acceptance tests; owner — 0.2 kernel/1.2–1.3. После этого `done-with-open` для 0.2 может остаться корректным, но roadmap должен перечислить дополнительные open mechanisms.

### J-2. Статус и зависимость сами по себе согласованы — ЧИСТО

`wiki/roadmap.md` определяет `done-with-open`; 0.2 отмечен им, 1.2 зависит от «0.2 done», П.2 — от П.1 и 0.4. Это согласуется с текущими принятыми OPEN. Недостаток — только J-1: перечень residual OPEN неполон.

## K. Регрессия триажа шести спек — ЧИСТО

**Отдельная строка K:** **нет**, правки триажа в `dba6448` и `2bb7caf` не внесли новых межспековых противоречий в шесть проверенных спек; `c9e49c1` их не менял.

Короткий проход подтвердил: три оси состояний и отсутствие `REVIEW_DUE` согласованы в glossary/learning/lexical; `AttemptAssessment` отделён от единственного terminal `ReviewOutcome`; safety-overlay одинаково сформулирован в curriculum/lexical/session; owner-матрица верно оставляет uniqueness terminal outcome за 0.5, а CAS — за kernel. Это не отменяет новые kernel-находки A–J выше.

## 3. Вердикт по `wiki/platform/foundation.md`

**FAIL** — есть BLOCKER A-1/E-1: контракт одновременно требует authoritative JSONL и общую ACID-транзакцию, не задавая возможного атомарного носителя/recovery protocol.

## 4. Проверено, ок

- Гибрид event-sourcing сам по себе не является дефектом: learning и operational state разделены явно, Obsidian вынесен post-commit.
- Safety-overlay не конфликтует с pinning: active policy применяется только к live delivery, не к historical replay/scoring.
- Kernel не присваивает себе business-правило уникальности terminal ReviewOutcome: §3.5 корректно оставляет его 0.5.
- `same-key/same-hash → cached result` и `same-key/different-payload → stable error` сформулированы явно; дефект C-3 — отсутствие scope/retention, а не отсутствие самих двух веток.
- `0.2 done-with-open`, разблокировка П.1 и зависимость П.2 от 0.4 в roadmap согласованы с принятым триажем.
