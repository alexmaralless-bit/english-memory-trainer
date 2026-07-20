# Content-review каркаса П.1 (перед П.2)

Дата: 2026-07-20. Ревьювер: Claude (независимо от Codex-автора). Метод: чтение всех 85 тем A1–A2, 20 модулей, levels/tracks против одобренного концепта (`staging/journal/2026-07-19-codex-curriculum-concept.md`), learning-model, curriculum-контракта и целей ученика. Это **педагогический/полнотный** review, не correctness (циклы/dangling/format уже проверены: 0 dangling, DAG корректен).

## Вердикт: каркас годен как основа П.2, с двумя решениями и одной правкой-расширением

Грамматический/письменный/tech-хребет A1–A2 **педагогически крепкий и верен концепту**. Основные вопросы — недопредставленность двух треков, которые пользователь явно хотел (vocabulary/chunks и informal), и порядок П.2↔П.4.

## Распределение

- По уровням: A1 — 44 темы, A2 — 41. Модули сбалансированы (4–8 тем).
- По трекам: grammar-engine 43, us-tech-english 13, written-interaction 12, written-production-mediation 11, reading 4, everyday-online-informal 2, **vocabulary-chunks 0**, toefl 0 (корректно — с B1).

## Что хорошо (подтверждено)

- **Фидельность концепту**: грамматическая прогрессия точно повторяет модули A1.1–A2.8 (be→pronouns→word-order→articles; present simple→do/frequency; there is/have; present continuous; can; past simple→irregular; going to/will; A2: past continuous, present perfect + choice, future forms, modals/comparatives, conditionals/passive, collaboration, reading/mediation, интегрированные capstones).
- **Prerequisites педагогически верны**: `present-perfect.result` ← strong[have-has, past-participle] soft[past-simple] (точно как в контракте); `passive.basic-process` ← [be, past-participle]; capstone-темы (A1.8/A2.8) зависят от компонентов. Глубина 10 адекватна.
- **can_do наблюдаемы и action-oriented**; привязаны к рабочим задачам (tickets, status updates, bug reports, deployment).
- **US Tech и письменные треки** хорошо покрыты (36 тем на writing+tech) — прямо под цели ученика (работа, переписка).
- **Единый паттерн**: `us-tech.*` темы — per-module capstones, применяющие письменный навык в tech-контексте (consistent).

## Находки

### C-1. Vocabulary & Chunks — 0 тем A1–A2 — РЕШЕНИЕ
Концепт делал chunks центральными (I work as…, follow up on, we've deployed…). Codex вынес весь трек в П.4/лексикон (заблокирован OPEN-15). Архитектурно это **может быть корректно**: по lexical-system chunks — это `LexicalItem`, привязываемые к темам через `topic.lexicon`, а не отдельные topic'и. Тогда пустой topic-трек — намеренно, а vocabulary «живёт» в лексиконе. Нужно подтверждение модели (см. вопрос).

### C-2. Everyday/Online & Informal — 2 темы против концепта — ПРАВКА
Концепт: A1 — contractions, casual replies, chat chunks; A2 — сокращения (IMO/FYI), неформальные просьбы, простые форумные ответы, распознавание тона. В каркасе только `basic-chat-response` (A1) и `casual-neutral-request` (A2). Недостаёт: contractions, abbreviations, forum-reply/tone-recognition. Трек, который пользователь явно хотел, недопредставлен.

### C-3. П.2 ↔ П.4 порядок (lexicon refs) — РЕШЕНИЕ
Тела тем П.2 захотят `topic.lexicon` refs (chunks на тему), но лексикон — П.4, заблокирован OPEN-15 (лицензии). Нужен порядок: П.2 без lexicon-refs (backfill в П.4) / сначала OPEN-15+П.4 / П.2 с inline-парафразными chunk-списками (без импортных данных), П.4 формализует.

### C-4. B1–C2 — по одному module-sketch — OK для скелета
Не для наполнения сейчас; декомпозиция — отдельная работа. Помечено TODO(review) корректно.

### C-5 (minor). `TODO(review)` в topic YAML
Оба topic-файла начинаются с `# TODO(review)`; advisory-граф — авторская интерпретация. После content-review их можно снять/подтвердить в П.2.

## Рекомендация

Каркас принять как основу. До П.2: (1) подтвердить vocabulary-модель (C-1), (2) расширить informal-трек (C-2, небольшой патч каркаса — можно тем же Codex), (3) выбрать порядок П.2↔П.4 (C-3).
