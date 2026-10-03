---
name: run-spaced-review
version: "2"
description: "Провести объявленный spaced-review урок: сначала самостоятельное припоминание due-материала, затем объяснение, retry и перенос."
required_inputs:
  - "--provider"
  - "due backlog из `review due`"
forbidden_actions:
  - "не вводить новую центральную грамматическую тему под видом повторения"
  - "не показывать ответ до первой попытки припоминания"
  - "не выставлять исход review самому"
  - "не показывать structured prompt до `session next` и `exercise rendered`"
  - "не редактировать состояние напрямую"
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
  - "каждое предъявленное review имеет попытку и закрыто через `review close`"
  - "сессия FINISHED с пустым pending-набором либо ABANDONED"
---

## Steps

1. Прочитать `review due`. Предложить/запустить профиль `spaced_review` и
   объяснить, что материал выбран по сроку повторения, а не как наказание.
2. Для каждого due item соблюдать порядок `session peek` → `session next` →
   создать retrieval prompt без ответа → `exercise rendered` → показать →
   `attempt record` → `attempt finalize` → `review close`.
3. При ошибке кратко объяснить причину, затем дать retry и один fresh-context
   перенос. При успешном припоминании не перегружать повторным объяснением.
4. Закрыть сессию через `session finish` только при пустом pending-наборе;
   при прерывании использовать `session abandon`.
