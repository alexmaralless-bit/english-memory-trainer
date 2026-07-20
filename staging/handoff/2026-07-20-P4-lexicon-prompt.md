# Промпт-делегация: П.4a — учебный лексикон A1–A2 (curated inventory)

Скопировать целиком в Codex, запущенный в корне репозитория AI_trainer_eng.

---

Ты — автор учебного лексикона. Задача — собрать **stable core лексикон A1–A2** (roadmap П.4) как версионируемые данные по принятому контракту. Это **отбор и авторская выписка единиц**, а не импорт чужих таблиц.

## Контекст — читать в этом порядке

1. **`wiki/product/lexical-system.md`** — модель лексики: три слоя, `LexicalItem`, lexeme с формами, informal-слой §3b (`usage_policy`, `register`, `volatility`/`currency`, `neutral_equivalent`, `cultural_context`). ГЛАВНАЯ МОДЕЛЬ.
2. **`wiki/modules/curriculum.md` §2, §3.1–§3.2, §5** — формат `LexicalItem`, **правовая позиция**, состав данных, provenance, правила валидации. ГЛАВНЫЙ ФОРМАТ И ГРАНИЦЫ.
3. `curriculum/topics/a1.yaml`, `a2.yaml` — 91 тема A1–A2: лексикон отбирается **под них** (что нужно, чтобы выполнять эти can-do).
4. `curriculum/README.md`, `curriculum/tracks.yaml` — раскладка; трек `vocabulary-chunks` реализуется **только лексиконом**, без topic'ов [PD-2026-07-20].
5. `wiki/glossary.md` — термины (LexicalItem, lexeme, usage_policy, currency, frequency_band).

## Ключевое разделение проходов (читать внимательно)

`frequency_score`/`frequency_band` — **корпусная** величина. Её **нельзя** проставить «на глаз».

- **Этот проход (П.4a)** — курируемый инвентарь: сами единицы, тип, значение, примеры, регистр, формы lexeme, informal-поля, **`curriculum_priority_band`** (это наша педагогическая оценка, её ставить можно и нужно).
- **`frequency_score`/`frequency_band` НЕ проставлять**, если у тебя нет реального доступа к источникам (CEFR-J / NGSL / wordfreq). Оставь поля отсутствующими.
- Если источники **реально доступны** (сеть/пакеты) — можешь выполнить и корпусный проход: зафиксируй `SourceArtifact` (exact_version, url, retrieved_at, sha256, license) и проставь наши **собственные производные** band'ы. Сырые датасеты в репо **не коммитить**.
- **Категорически нельзя**: выдумывать частотные числа, «примерные» Zipf-значения или band'ы по ощущению. Лучше отсутствующее поле, чем правдоподобная выдумка. В отчёте честно укажи, был ли корпусный проход выполнен.

## Что произвести

`curriculum/lexicon/` (YAML, по формату из контракта):

1. **`core-a1.yaml` / `core-a2.yaml`** — слова и chunks под темы соответствующего уровня.
2. **`lexemes-irregular.yaml`** — неправильные глаголы как `type: lexeme` с `forms: {base, past, participle}` (**один** lexeme, не три записи).
3. **`phrasal-verbs.yaml`** — базовые phrasal verbs уровня A1–A2.
4. **`informal-core.yaml`** — stable-core informal единицы под 8 тем informal-трека: casual-подтверждения (Sounds good, My bad, No worries), сокращения (IMO, FYI, TL;DR, AFAIK), рабочие chunks. **У каждой** — `usage_policy` (`safe_to_use` / `context_dependent` / `recognition_only` / `avoid`), `register`, `neutral_equivalent`, `allowed_contexts` для `context_dependent`.
5. **`README.md`** — раскладка, объём, что отложено, выполнен ли корпусный проход.
6. *(опционально)* **`_suggested-topic-links.yaml`** — подсказка «единица → тема» для будущего П.2. Пометить как **advisory, не источник истины**: авторитетное поле `topic.lexicon` заполняет П.2.

**Объём-ориентир**: 150–250 единиц суммарно (примерно: A1 ~60–80, A2 ~60–80, irregular ~25–35, phrasal ~15–25, informal ~25–35). Качество и покрытие тем важнее количества.

## Обязательные поля единицы

```yaml
id: chunk.follow-up-on          # dotted, стабильный, уникальный
type: chunk                     # word | chunk | phrasal-verb | lexeme | informal_chunk | abbreviation
title: follow up on
cefr: A2
curriculum_priority_band: HIGH  # CORE | HIGH | USEFUL | SPECIALIZED | INCIDENTAL (наша оценка)
register: neutral               # formal | neutral | casual | slang | potentially-offensive
domains: [work, project-management]
meaning_ru: уточнить или вернуться к вопросу
examples:
  - I'll follow up on this tomorrow.   # СОБСТВЕННЫЕ примеры, не скопированные
transformations: [authored]     # authored — выписано нами; identity/… — при импорте
```

## Границы (нарушение = отклонение)

1. **Никаких сторонних excerpts.** Примеры пишешь сам; чужой текст (форумы, статьи, датасеты) не копируется — постоянное правило (curriculum §3.1/§5).
2. **`mastery_criteria` и `LexicalMasteryProfile` НЕ создавать** — профиль задаётся scoring policy по `type`/`usage_policy` (контракт 0.4), не на единице.
3. **`topic.lexicon` в темах НЕ трогать** — это поле П.2. Файлы `curriculum/topics/*` и `curriculum/modules/*` **не менять**.
4. Менять/создавать только под `curriculum/lexicon/`. `wiki/`, `docs/`, `staging/` (кроме отчёта) — не трогать. Пустой `Irregular Verbs.md` в корне не трогать.
5. Informal-единица без `usage_policy` — ошибка. `meme_template` в этом проходе **не создавать** (living layer, отдельный процесс).
6. Продуктовые развилки не решай — `# TODO(review)`.

## Самопроверка

- ID уникальны и dotted; типы из разрешённого списка; `cefr` ∈ {A1, A2}.
- У каждой единицы есть `curriculum_priority_band`, `register`, `meaning_ru`, минимум один собственный пример.
- Lexeme: ровно один item на глагол, формы заполнены; `go/went/gone` — одна запись.
- Informal: у всех `usage_policy`; у `context_dependent` — `allowed_contexts`.
- Нет `frequency_*` без реального источника; нет `mastery_criteria`; нет изменений в topics/modules.
- Покрытие: для каждого из 20 модулей A1–A2 есть релевантные единицы (проверь по темам).

## Отчёт

`staging/handoff/2026-07-20-P4-lexicon-report.md`: счётчики по файлам/типам/уровням; **выполнен ли корпусный проход** (если нет — почему, что нужно для П.4b); покрытие модулей; `TODO(review)`; что осознанно отложено.
