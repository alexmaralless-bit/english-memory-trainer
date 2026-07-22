---
name: correct-learner-output
version: "1"
description: "Дать обратную связь по уже записанной попытке ученика: указать на ошибку, подсказать верную форму, довести открытую попытку до оценки движком."
required_inputs:
  - "attempt_id записанной (recorded) попытки"
forbidden_actions:
  - "не выставлять score/verdict самому — это делает `attempt finalize`"
  - "не изменять raw_answer ученика задним числом"
  - "не закрывать review самому, вне `review close`"
cli_calls:
  - attempt.record
  - attempt.finalize
  - review.close
outputs:
  - "объяснение ошибки и правильный вариант на человеческом языке"
postconditions:
  - "открытая попытка доведена до assessed (или честно осталась recorded, если рубрика не покрывает случай)"
---

## Steps

1. Дождаться `attempt record` (статус `recorded` для открытых заданий).
2. `attempt finalize --attempt <id>` — движок прогоняет rubric pipeline и
   возвращает `disposition`/`score_ppm`.
3. Объяснить ученику результат: что верно, что нет, как лучше сформулировать
   — опираясь на вернувшийся `disposition`, а не на собственное мнение.
4. Если попытка была ответом на review-шаг — `review close` для этого
   review_assignment_id.
