# Content-review лексикона П.4a

Дата: 2026-07-20. Ревьювер: Claude (независимо от Codex-автора). Метод: чтение всех 204 единиц + сверка с одобренным концептом, Curriculum Contract и целями ученика.

## Вердикт

Качество отдельных записей хорошее (свои примеры, meaning_ru, register, domains, честное отсутствие частот). Но **chunks недобраны и по количеству, и по составу**, а соотношение типов инвертировано относительно продуктовой цели. Нужен добор П.4a-bis до наполнения П.2.

## 1. 33 chunks — мало, и треть из них не chunks

Из 33 примерно **10–12 — грамматические паттерны, дублирующие существующие темы**, а не лексические единицы:

| «Chunk» | Уже покрыто темой |
|---|---|
| `there is` / `there are` | `grammar.there-is-are.systems` |
| `have finished` | `grammar.present-perfect.result` |
| `better than` | `grammar.comparatives.options` |
| `if ... then ...` | `grammar.first-conditional.troubleshooting` |
| `must have` | `grammar.modals.requirements` |
| `working on` | дублирует phrasal `work on` |

Плюс наречные обороты времени (`after that`, `right now`, `at the time`, `every day`, `by Friday`) — ближе к словам/коллокациям.

**Остаётся ~20 настоящих рабочих фраз-фреймов на 16 модулей** — примерно по одной на модуль.

## 2. Все 9 chunks, названных в одобренном концепте, отсутствуют

Проверено поиском: `we-have-completed`, `we-have-run-into`, `i-have-already-checked`, `im-working-on`, `were-testing`, `the-main-advantage`, `we-should-consider`, `i-usually-start-by`, `how-often-do-you` — **ни одного нет**.

Два из них (`chunk.we-have-completed`, `chunk.we-have-run-into-an-issue`) — это **канонический пример Topic-формата в самом Curriculum Contract** (§2). Контракт ссылается на единицы, которых в лексиконе нет. Это самое наглядное доказательство недобора.

## 3. Соотношение типов инвертировано под цель продукта

- Single-word: **134** (95 words + 28 lexemes + 11) · Multi-word: **70** (33 chunks + 23 informal + 18 phrasal + …).
- Цель продукта — «довести построение фраз до автоматизма» (бриф, design-direction). Для strong-beginner IT-профессионала большинство одиночных слов (`company`, `team`, `day`, `file`, `data`, `system`) уже пассивно известны; дефицит — в **готовых фразовых фреймах** рабочей коммуникации.
- Плотность пользы у chunks здесь заметно выше, чем у слов; сейчас пропорция обратная.

## 4. Перекос priority bands

`CORE` 121 · `HIGH` 76 · `USEFUL` 7 · `SPECIALIZED`/`INCIDENTAL` — 0. 59% единиц помечены CORE: band почти не различает приоритет. Нужна перекалибровка при доборе.

## 5. Реальный пробел схемы (не вина автора)

`lexeme.be` содержит `forms: {base: be, past: [was, were], participle: been}` — **список** в слоте, тогда как [[../../wiki/product/lexical-system]] §2 подразумевает одно значение (`base/past/participle`). Затрагивает и агрегацию required forms (OPEN-14): что значит «знать past» у `be`. Codex честно вынес в TODO(review). **Требует правки контракта**, а не данных.

## 6. Что не выполнено (корректно)

- **Корпусный проход не делался** — `frequency_score`/`frequency_band`/`source_refs` отсутствуют, выдуманных значений нет. Это ровно то поведение, которое требовалось. Для П.4b нужны: pin версий источников, `SourceArtifact` (url/retrieved_at/sha256/license), versioned thresholds score→band, воспроизводимый enrichment.
- **Advisory topic-links — 60 на 204 единицы**: ~144 единицы пока без связи с темами; П.2 потребует более полного маппинга.
- В промпте я ошибочно написал «20 модулей A1–A2» — фактически 16 A1–A2 + 4 sketch B1–C2. Codex это заметил и поступил правильно.

## Рекомендация

1. **П.4a-bis**: добрать chunks до ~90–120 настоящих рабочих фреймов по модулям (status/progress, incidents, results-present-perfect, planning, requirements/options, collaboration, mediation), включая все названные в концепте; переклассифицировать грамматические псевдо-chunks; перекалибровать bands.
2. **Правка контракта**: разрешить несколько поверхностных форм в слоте lexeme (`past: [was, were]`) и определить, что значит «знать форму» при агрегации.
3. П.4b (корпус) — после этого, отдельно.
