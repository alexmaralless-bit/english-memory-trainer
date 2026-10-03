---
name: finish-english-session
version: "1"
description: "Корректно завершить или прервать текущую сессию: закрыть весь pending-набор перед session finish, либо явно перейти в session abandon."
required_inputs:
  - "активная сессия"
forbidden_actions:
  - "не сообщать ученику, что сессия завершена, если `session finish` не был вызван и не вернул успех"
  - "не закрывать review/attempt в обход `review close`/`attempt finalize`"
  - "не выставлять score/mastery самому"
cli_calls:
  - session.status
  - review.close
  - attempt.finalize
  - session.finish
  - session.abandon
outputs:
  - "краткое резюме сессии для ученика"
postconditions:
  - "сессия в терминальном статусе FINISHED или ABANDONED"
  - "при FINISHED — pending-набор пуст (проверено движком)"
---

## Steps

1. `session status --format json` — прочитать pending attempts/review из
   сообщения об ошибке `session finish`, если он был вызван раньше и отказал.
2. Довести каждую открытую попытку до оценки (`attempt finalize`) и каждое
   открытое review — до `review close`.
3. `session finish`. Если движок снова отказал по precondition — повторить
   шаг 2 для оставшихся целей; никогда не объявлять сессию завершённой
   без успешного ответа `session finish`.
4. Если довести pending-набор до пустоты невозможно (сессия обрывается) —
   `session abandon` вместо имитации finish.
