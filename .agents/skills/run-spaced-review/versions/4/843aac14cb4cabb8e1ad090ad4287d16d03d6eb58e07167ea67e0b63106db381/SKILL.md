---
name: run-spaced-review
version: "4"
description: "Провести объявленный spaced-review урок: сначала припоминание due-материала по смыслу (RU→EN), затем протокол по стадии, retry и перенос."
required_inputs:
  - "--provider"
  - "due backlog из `review due`"
forbidden_actions:
  - "не вводить новую центральную грамматическую тему под видом повторения"
  - "не показывать ответ до первой попытки припоминания"
  - "не выставлять исход review самому"
  - "не показывать structured prompt до `session next` и `exercise rendered`"
  - "не вызывать `session peek` перед каждым шагом: только после `session resume` или конфликта"
  - "не редактировать состояние напрямую"
  - "не объяснять правило до попытки припоминания и самоисправления"
cli_calls:
  - review.due
  - session.propose
  - session.start
  - session.peek
  - session.next
  - exercise.rendered
  - attempt.record
  - attempt.finalize
  - review.close
  - session.finish
  - session.abandon
outputs:
  - "объявление причины повторения и списка навыков без показа ответов"
  - "список закрытых review и их исходов"
postconditions:
  - "каждое предъявленное review имеет попытку и закрыто движком через `attempt record --close-review` (или fallback `review close`)"
  - "сессия FINISHED с пустым pending-набором либо ABANDONED"
---

## Steps

1. Прочитать `review due`. Предложить/запустить профиль `spaced_review` и
   объяснить, что материал выбран по сроку повторения, а не как наказание.
2. Для каждого due item сначала retrieval prompt по смыслу — русская реплика
   или ситуация, которую нужно превратить в полную английскую фразу или
   предложение целиком, — никогда не показывая форму первой. Соблюдать
   порядок `session next` → создать этот prompt без ответа →
   `exercise rendered` → показать → `attempt record` с `observations`
   и `--close-review` (оценка и закрытие review — в той же транзакции).
   `session peek` — только после `session resume` или конфликта; `attempt
   finalize` и `review close` — fallback, если попытка осталась `recorded`
   или review не закрылся.
3. При ошибке — протокол дрилла: один ход на самоисправление; если не
   исправил, показать корректную фразу; потребовать перепечатать целиком.
   Объяснение — только в итоговом дебрифе занятия, не внутри повторения. При
   успешном припоминании не перегружать объяснением и сразу перейти к
   fresh-context переносу.
4. Закрыть сессию через `session finish` только при пустом pending-наборе;
   при прерывании использовать `session abandon`.
