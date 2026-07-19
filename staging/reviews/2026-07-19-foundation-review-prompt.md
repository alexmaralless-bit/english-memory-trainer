# Промпт red-team ревью 0.2 Application Foundation (kernel)

Скопировать целиком в Codex (или другой агент), запущенный в корне репозитория AI_trainer_eng.

---

Ты — внешний семантический ревьювер (red team) проекта English Memory Trainer. Ты НЕ автор спек. Проверяется **новый контракт kernel** (roadmap 0.2) и его согласованность с уже принятым каноном. Системная ошибка в фундаменте = системный баг во всех модулях, которые на нём построят. Хвалить не нужно; нужно ломать. Кода ещё нет — ревью только документов, фактов о коде не выдумывать.

## Контекст — читать в этом порядке

1. `wiki/README.md` — конституция вики (в т.ч. «platform без бизнес-логики»).
2. `docs/design-direction.md` §4 — заданный состав kernel и принцип kernel-first.
3. **Предмет ревью (основной):** `wiki/platform/foundation.md`.
4. **Сверка-контекст (уже принято, не переписывать):** `wiki/OPEN.md` (особенно **owner-матрица** и OPEN-7…18), `wiki/glossary.md`, `wiki/product/learning-model.md`, `wiki/product/lexical-system.md`, `wiki/modules/curriculum.md`, `wiki/flows/session.md`, `wiki/flows/continuation.md`, `wiki/flows/placement.md`, `wiki/roadmap.md`.
5. Provenance (не канон, для понимания «почему»): `staging/journal/*.md`, `staging/reviews/2026-07-19-concept-review-codex.md` и `…-rereview-codex.md`.

Приоритет источников: принятые спеки → design-direction → бриф. Расхождение, помеченное `[PD-…]`, дефектом не считается. Расхождение спек между собой — дефект всегда.

## Что искать — по каждому пункту явный вердикт «чисто» или находки

- **A. Гибридная граница источника истины.** foundation.md §2 делит состояние на event-sourced (learning) и SQLite-authoritative (операционное). Найди любое поле/сущность, которая фактически имеет **два источника истины** или чья принадлежность к классу неоднозначна (напр. XP-ledger, review outcome, exposure history, self_reported_level, streak `practice_day`, prior_steady_state). Может ли `scoring replay` разойтись с SQLite-проекцией из-за такого дрейфа?
- **B. Детерминизм.** Полон ли контроль недетерминизма? Clock/RandomSource — да; но проверь: порядок итерации/сортировки, hash-seed, порядок применения событий с равным timestamp, плавающая точка в scoring, порядок outbox-доставки. Может ли replay при тех же событиях+pinned-версиях дать другой результат?
- **C. Инварианты, делегированные kernel, действительно предоставлены.** Пройди по спекам: каждый раз, где спека пишет «kernel даёт X / OPEN-9/10/11», проверь, что foundation.md реально даёт механизм X, а не просто повторяет OPEN. Особо: pinned-vs-active резолв (safety-overlay hook), CAS, idempotency (same-key/different-payload, cached response, **compound-команда** `abandon+start`), UoW-атомарность, correction-события.
- **D. Owner-граница (platform без бизнес-логики).** Не просочилась ли бизнес-логика в kernel? И наоборот — нет ли механизма, который **ни один** контракт не назвал своим (сверить с owner-матрицей в OPEN.md)? Согласована ли owner-матрица с тем, что реально пишет foundation.md (напр. «uniqueness терминального outcome» — 0.5, не kernel; «transition table» — 0.4).
- **E. Атомарность и crash-recovery.** §2/§3.7: ACID коммитит state+events+outbox, проекции post-commit. Проверь дыры: crash между commit и outbox-доставкой; повторная доставка outbox (идемпотентность проекции); rebuild проекции при частично применённых событиях; snapshot операционного (не rebuildable) состояния vs event-sourced.
- **F. Pinning и safety-overlay.** §3.6: pinned для replay, active для доставки production. Нет ли противоречия с G-R1 (rereview) в формулировке kernel? Что происходит при replay события, созданного под policy, которой уже нет (retired)? Кто резолвит `pinned_versions`, если версия отсутствует в реестре?
- **G. Идемпотентность/конкурентность на стыке.** §3.4/§3.5 + continuation (два агента): достаточно ли CAS + idempotency, чтобы два агента не создали конфликтующие терминальные исходы? Есть ли неохваченные мутации (placement submit, XP award, curriculum activate)?
- **H. Пустые/непроверяемые MUST.** Найди MUST без механизма или проверки, слова-уклонения, скрытые «потом». Напр. «projection boundary документирована» — где именно, проверяемо ли; «архитектурные чеки» — конкретны ли настолько, чтобы их можно было реализовать как CI-гейт.
- **I. Глоссарий-дрейф.** Новые kernel-термины (Command/DomainEvent envelope, pinned_versions, Unit of Work, transactional outbox, Policy registry, Snapshot) — определены один раз, используются согласованно, не конфликтуют с прежними (Event log, SourceArtifact).
- **J. Полнота OPEN/roadmap.** Всё нерешённое из foundation.md имеет строку в OPEN.md с владельцем? Корректен ли статус 0.2 `done-with-open` и зависимость 1.2 от него? Не появилось ли нового нерешённого вопроса без OPEN.
- **K. Регрессия триажа.** Я только что переписал шесть спек (коммиты dba6448, 2bb7caf, c9e49c1). Проверь, что эти правки **не внесли новых межспековых противоречий** (термины состояний, review outcome timing, safety-overlay формулировки, owner-матрица) — короткий проход, отдельно от ревью самого 0.2.

## Правила ревью

1. НЕ редактируй файлы и ничего не чини — только отчёт.
2. Каждая находка: **файл и раздел → точная цитата → почему дефект → предлагаемая правка (кратко) → severity** (`BLOCKER` / `MAJOR` / `MINOR` / `QUESTION`).
3. Продуктовые/архитектурные развилки не решай — оформляй как QUESTION.
4. Сомневаешься — включай как QUESTION. Молчание хуже ложной тревоги.
5. Не переписывай архитектуру: ревью против принятых [PD]-решений (гибрид event-sourcing, тонкий sqlite3, safety-overlay), а не вместо них.

## Формат результата

Сохрани отчёт на русском в `staging/reviews/2026-07-19-foundation-review-codex.md` (другие файлы не трогай):

1. Резюме: топ-5 находок.
2. Находки по разделам A–K (формат из правила 2), отсортированы по severity.
3. Вердикт по `wiki/platform/foundation.md`: `PASS` / `PASS-with-findings` / `FAIL` (FAIL = есть BLOCKER).
4. Отдельная строка по K: внесла ли триаж-правка новые противоречия в шесть спек (да/нет + перечень).
5. «Проверено, ок»: что выглядело подозрительно, но корректно.
