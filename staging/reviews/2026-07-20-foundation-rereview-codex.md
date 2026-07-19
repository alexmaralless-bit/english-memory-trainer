# Повторное red-team ревью Foundation после triage `d7b974a`

Дата: 2026-07-20  
Предмет: текущий `wiki/platform/foundation.md`, commit `d7b974a`, и его согласованность с принятым каноном.  
Метод: только документы; о коде выводов нет. Решения `[PD-2026-07-19]` и `[PD-2026-07-20]` принимаются как заданные.

## Резюме

Предыдущий BLOCKER A-1/E-1 действительно закрыт: authoritative event-store перенесён в SQLite event-table и коммитится с state/outbox в одной транзакции; JSONL стал derived export. Это устраняет невозможное требование «ACID SQLite + authoritative file append».

Новых BLOCKER не найдено. Есть четыре MAJOR-регрессии/неполноты: normal async lag JSONL объявлен integrity-error; boundary-таблица противоречит канону для `prior_steady_state` и сужает роль `self_reported_level`; safety correction больше не обязано сохранять обе версии; test-MUST о shuffled insertion не отличает физический порядок чтения от canonical `sequence`. Также glossary не синхронизирован с обязательным полем `sequence`.

## A. Гибридная граница источника истины — НАХОДКИ

### A-1. Boundary-таблица конфликтует с нормативным состоянием `prior_steady_state` и ролью `self_reported_level` — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2.2: «`prior_steady_state` | **производно от событий (детерминированно)**» и «`self_reported_level` … | operational (**не влияет на scoring; влияет на briefing**)»; `wiki/product/learning-model.md`, §4: «`prior_steady_state` — **явное поле**»; §5: «`self_reported_level` … даёт только **provisional working estimate**»; `wiki/flows/placement.md`, §15: «это provisional working estimate».

**Почему дефект:** «производно» не гарантирует наличие явного поля, необходимого для restore-on-confirm; две реализации могут либо materialize его, либо пересчитывать из истории с разной обработкой correction/migration. Для self-report фундамент оставляет только briefing, тогда как канон требует, чтобы оно участвовало в provisional working estimate (а placement выводит старт и policy-определённые рекомендации). Это уже не просто классификация storage: таблица сужает поведение, заданное принятыми спеками.

**Предлагаемая правка:** обозначить `prior_steady_state` как явное rebuildable поле проекции, детерминированно материализуемое из событий; для `self_reported_level` указать «не влияет на scoring, но влияет на provisional working estimate/briefing/recommendations» и его snapshot/recovery policy.

## B. Детерминизм — НАХОДКИ

### B-1. Replay-test про shuffled insertion двусмысленен относительно canonical `sequence` — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.3: «`sequence` — canonical total order» и «replay применяет события строго по `sequence`»; §5: «**shuffled insertion order** и события с равным `occurred_at` дают тот же результат».

**Почему дефект:** если «insertion order» назначает `sequence`, его перестановка по определению меняет canonical order и может легитимно изменить некоммутативный reducer. Если речь о физическом порядке строк/выборки при уже зафиксированных `sequence`, это другой тест. В текущей форме CI может либо требовать невозможной order-independence, либо не проверить основную гарантию — чтение строго по зафиксированному sequence.

**Предлагаемая правка:** заменить на два теста: (1) при неизменных event payload + `sequence` replay инвариантен к физическому storage/query order; (2) concurrent/equal-timestamp append получает детерминированный total order, и этот записанный order воспроизводится.

## C. Делегированные kernel-инварианты — НАХОДКИ

### C-1. Safety correction не обязан хранить обе policy-версии — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.6: «active-резолв (`production_eligible` при доставке) + correction-события»; далее generic envelope содержит «`corrects_event_id`, семантику … позицию в `sequence` и idempotency»; `wiki/modules/curriculum.md`, §5: incompatible item «отменяется/заменяется append-only event **с обеими версиями**».

**Почему дефект:** после triage foundation больше не требует, чтобы safety-correction сохранил pinned/source и active safety version. `pinned_versions` не закрывает это: glossary прямо говорит, что safety не pin-ится, а generic correction payload не задаёт отдельное поле active safety snapshot. В результате live delivery может быть отменена, но audit/replay не объяснит, по какой active policy и вместо какого pinned decision это сделано; это регрессирует согласованную safety-overlay формулировку.

**Предлагаемая правка:** generic correction envelope должен позволять/требовать `original_pinned_versions` и `active_safety_version` для safety corrections; §3.6 явно ссылается на invariant «с обеими версиями». Правило eligibility остаётся у П.3/0.4/0.5.

## D. Owner-граница — ЧИСТО

Kernel больше не перечисляет business event types; `finalize/recover` возвращены 0.5, а kernel оставляет себе UoW/CAS/idempotency. Это согласуется с owner-матрицей и принципом «platform без бизнес-логики».

## E. Атомарность и crash-recovery — НАХОДКИ

### E-1. Нормальный post-commit lag JSONL ошибочно назван расхождением-ошибкой — MAJOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §2.1: «JSONL — derived … export … **только post-commit через outbox**» и «расхождение JSONL ↔ event-таблица = ошибка (`database check`)».

**Почему дефект:** между authoritative commit и успешной outbox delivery JSONL по контракту неизбежно отстаёт; это нормальное recoverable состояние, особенно после crash. Без high-water mark/export offset `database check` будет объявлять healthy catch-up lag corruption. Это противоречит заявленной at-least-once/retry модели и мешает корректному crash recovery.

**Предлагаемая правка:** `database check` сравнивает JSONL только до acknowledged export offset/high-water mark; lag показывает как pending/outbox health, а error — только для divergence после catch-up или невалидного content/hash. Зафиксировать recovery command/ожидаемое состояние.

## F. Pinning и safety-overlay — НАХОДКИ

См. C-1: active-safety correction без обеих сохранённых версий не доказывает precedence safety-overlay. Retention pinned snapshots и hard error `PinnedPolicyUnavailable` сами по себе сформулированы корректно.

## G. Идемпотентность и конкурентность — ЧИСТО

`session abandon` + `session start` теперь явно две независимые идемпотентные команды с benign recovery; multi-aggregate CAS задан как all-or-nothing в одной UoW; uniqueness terminal outcome остаётся бизнес-правилом 0.5. Это устраняет прежнюю неопределённость без переноса lifecycle в kernel.

## H. Пустые или непроверяемые MUST — НАХОДКИ

### H-1. «payload_hash, cached-result schema и retention фиксированы» не содержит самой нормы — MINOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.4: «`payload_hash`, cached-result schema и retention **фиксированы в kernel**»; §9: «OPEN-11: … cached response+retention».

**Почему дефект:** конкретная schema cached response, retention horizon/eviction и fixed hash algorithm в этом контракте не приведены, хотя текст утверждает, что они уже фиксированы. Без них нельзя проверить identical retry после snapshot/cleanup или одинаково реализовать cache persistence. OPEN-11 честно оставляет детали открытыми, но первая фраза это маскирует.

**Предлагаемая правка:** либо назвать точную schema/retention/algorithm и тесты, либо заменить «фиксированы» на «должны быть зафиксированы в 1.2 по OPEN-11/20».

## I. Глоссарий-дрейф — НАХОДКИ

### I-1. Обязательный envelope field `sequence` отсутствует в glossary — MINOR

**Файл и раздел → точная цитата:** `wiki/platform/foundation.md`, §3.3: «Обязательные поля: `id`, **`sequence`**, `type` …»; `wiki/glossary.md`, «Command / DomainEvent envelope»: «`id, type, occurred_at … payload_hash`».

**Почему дефект:** glossary объявлен местом единого определения терминов и сейчас публикует устаревший состав envelope. Потребитель, следующий glossary, не сохранит canonical order и сломает replay-contract.

**Предлагаемая правка:** добавить `sequence` с определением монотонного canonical total order и обновить историю glossary до 2026-07-20.

## J. Полнота OPEN и roadmap — ЧИСТО

OPEN-19/20/21 и расширения OPEN-9/11 покрывают event-store, determinism, outbox/rebuild, correction, multi-CAS и retention; owner-матрица назначает kernel, а roadmap корректно сохраняет 0.2 как `done-with-open` с реализацией в 1.2/1.3.

## K. Регрессия triage — НАХОДКИ

`d7b974a` не возвращает прежний JSONL/ACID BLOCKER и не ломает шесть исходных спек целиком. Но он вносит межспековые регрессии A-1 и C-1, а также асинхронное противоречие E-1; поэтому утверждение «foundation-review пройдено» преждевременно без их уточнения.

## Вердикт по `wiki/platform/foundation.md`

**PASS-with-findings** — BLOCKER A-1/E-1 закрыт, новых BLOCKER нет; остаются 4 MAJOR и 2 MINOR, которые следует снять до реализации 1.2/1.3, чтобы не закрепить неверные invariants в kernel.

## Проверено, ок

- SQLite event-table как authoritative source и JSONL как rebuildable outbox export совместимы с ACID и replay.
- Capture-into-event для exposure weight и snapshot ReviewAssignment закрывают прежнее смешение operational и event-sourced facts.
- `sequence`, canonical encoding, hash-seed/equal-timestamp tests и numeric interface созданы как правильные носители determinism, хотя B-1 нуждается в уточнении формулировки.
- Outbox получил message id, dedup/inbox, ack/order и rebuild с checkpoint/isolate-and-swap; это закрывает прежнюю дыру duplicate/out-of-order delivery.
- Boundary manifest, command registry и machine-readable CI-gate сделали прежние декларативные MUST проверяемыми по направлению.
