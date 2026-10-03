---
name: run-drill-block
version: "2"
description: "Провести занятие профиля drill: разминка, ввод фреймов, раунды дрилла (blocked → interleaved), реконструкция текста, timed writing и дебриф с evidence по каждому шагу."
required_inputs:
  - "--provider (идентификатор тьютора)"
  - "прямой запрос ученика на профиль drill либо подтверждённая системная рекомендация"
forbidden_actions:
  - "не показывать ни один item блока до `exercise rendered`"
  - "не объяснять правило внутри раунда без прямого запроса ученика или повтора той же ошибки дважды (кроме `feedback_mode: always_explain` — см. `references/drill-protocol.md`)"
  - "не давать исправление раньше одного хода самоисправления ученика"
  - "не встраивать ответ или целевую форму (фрейм, слово) в формулировку prompt"
  - "не фиксировать блок как отдельные попытки по item — только один `attempt record-block` на блок, unanswered items не включать"
  - "не изобретать `latency_ms`: указывать только время, реально наблюдаемое по меткам чата; иначе поле не передавать"
  - "не показывать ученику JSON, id, generation directive или служебный статус"
  - "не называть систему «движком» в разговоре с учеником"
  - "не выставлять исход блока/попытки/review самому — оценку и disposition вычисляет движок"
  - "не завершать сессию в обход `session finish`/`session abandon`"
  - "не вызывать `session peek` перед каждым шагом: только после `session resume` или конфликта"
cli_calls:
  - session.propose
  - session.start
  - session.peek
  - session.next
  - curriculum.texts
  - exercise.rendered
  - attempt.record-block
  - attempt.record
  - attempt.finalize
  - review.close
  - session.finish
  - session.abandon
outputs:
  - "объявление профиля drill, центрального паттерна, плана и правила ОДНОЙ строкой"
  - "фреймы темы с meaning_ru перед раундами"
  - "раунды дрилла blocked → interleaved без утечки ответа в prompt"
  - "реконструкция текста по ключевым словам"
  - "timed writing под объявленным лимитом без штрафа за превышение"
  - "дебриф: полное «почему», контрасты, правило, итог по очереди повторений"
postconditions:
  - "каждый drill_block/reconstruction/timed_writing имеет immutable exercise snapshot до показа"
  - "один блок = один `attempt record-block`; per-item попыток нет"
  - "review-происхождение блока (`kind: review`) закрыто движком через `--close-review` (или fallback `review close`)"
  - "сессия FINISHED с пустым pending-набором либо явно ABANDONED"
---

## Required references

Перед действием полностью прочитать:

- `references/drill-protocol.md` — как читать `generation_directive`, строить
  `items[]`/`rounds[]` из фреймов пятью формами item, и что писать в
  `attempt record-block`.
- `../run-english-session/references/pedagogy.md`, разделы «Feedback by
  stage» и «Drill rounds» — протокол обратной связи по стадии; этот skill его
  не дублирует, только применяет.

## Steps

1. **Preflight.** Прямой запрос ученика на профиль `drill` — уже согласие;
   иначе `session propose` → объявить `title`, профиль `drill`, центральный
   паттерн, план (retrieval-разминка по due-материалу → ввод фреймов → раунд 1
   blocked → раунд 2 interleaved → реконструкция текста → timed writing →
   дебриф) и получить подтверждение. `session start --profile drill`
   (или `session resume`). Прочитать `briefing.preferences`: `round_size`
   (дефолт 6), `explanation_language` (дефолт ru), `timed_limit_seconds`
   (дефолт 240), `preferred_drill_forms[]`, `feedback_mode`. Сказать целевую
   форму темы ОДНОЙ строкой — полное объяснение только в дебрифе (learning-model
   §9.1).
2. **Для каждого шага плана:** `session next` (с `plan_version` из
   предыдущего ответа; `session peek` — только после `session resume` или
   конфликта ревизии/плана). Прочитать
   `generation_directive`: `form`, `mode` (`blocked`|`interleaved`),
   `round_size`, `rounds`, `primary_target`, `contrast_targets[]` и `frames[]`
   (для `drill_block`); `text`/`text_id` (для `reconstruction` — если пусто,
   запросить `curriculum texts --topic <id> [--domain ...]`); `declared_limit_seconds`
   и `expected_targets[]` (для `timed_writing`). Построить материал по
   `references/drill-protocol.md`, никогда не показывая ответ или целевую
   форму в prompt. Сохранить снапшот через `exercise rendered` ДО показа хоть
   одного item: `form: drill_block` несёт `items[]`+`rounds[]`; `form:
   reconstruction` несёт авторский текст, `keywords`, `target_spans` и
   `rubric_ref`; `form: timed_writing` несёт `declared_limit_seconds` внутри
   снапшота — именно это число тьютор обязан назвать ученику до начала.
3. **Раунд дрилла** — один item за раз. Отмечать время ответа по меткам чата,
   когда оно наблюдаемо; иначе `latency_ms` не указывать. Внутри раунда
   работает протокол «Feedback by stage» / «Drill rounds» из pedagogy.md:
   flag фрагмента → один ход самоисправления → корректный фрейм целиком (не
   правило) → ученик перепечатывает предложение целиком. `self_repaired: true`
   только если ученик исправился сам после подсказки, не увидев ответ. После
   раунда — ровно один `attempt record-block` со всеми items (неотвеченные
   пропустить), затем следующий шаг плана. Если у блока есть
   `review_assignment_id` (шаг доставлен как `kind: review`) — добавить
   `--close-review` к тому же вызову; отдельный `review close` остаётся
   fallback.
4. **Реконструкция.** Показать текст один раз, скрыть, дать `keywords`,
   ученик восстанавливает текст по памяти целиком. `exercise rendered` — до
   показа. Оценить одной фиксацией: `attempt record` с `observations` в том же
   входном файле (без утечки ответа); `attempt finalize` — fallback, если
   попытка вернулась `recorded`. В обратной связи указать целевые
   `target_spans`.
5. **Timed writing.** Объявить лимит (то же число, что в снапшоте) до начала;
   не штрафовать и не комментировать негативно превышение лимита — это
   измерение оси automaticity, а не критерий оценки (learning-model §2/§4a).
   `attempt record --latency-ms` (когда время наблюдаемо) с `observations` в
   том же входном файле; `attempt finalize` — только fallback.
6. **Дебриф** — единственное место для полного «почему», контрастов и
   формулировки правила по каждой ошибке раунда/реконструкции/timed writing.
   Назвать, что ушло в очередь повторений. `session finish` только при пустом
   pending-наборе; иначе явный `session abandon`.
