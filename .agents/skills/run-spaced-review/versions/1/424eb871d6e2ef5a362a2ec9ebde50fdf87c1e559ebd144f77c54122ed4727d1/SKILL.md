---
name: run-spaced-review
version: "1"
description: "Провести сессию, сфокусированную на повторении просроченных и близких к забыванию целей (due backlog), а не на новом материале."
required_inputs:
  - "--provider"
forbidden_actions:
  - "не выставлять исход повторения самому — `review close` вычисляет его из оценённых попыток"
  - "не завершать сессию в обход `trainer session finish` / `trainer session abandon`"
  - "не редактировать файлы состояния напрямую"
cli_calls:
  - review.due
  - session.start
  - session.peek
  - session.next
  - exercise.rendered
  - attempt.record
  - attempt.finalize
  - review.close
  - session.finish
outputs:
  - "список закрытых review и их исходов"
postconditions:
  - "каждое предъявленное review-задание имеет попытку и закрыто через `review close`"
  - "сессия FINISHED (pending-набор пуст) или ABANDONED"
---

## Steps

1. `review due --format json` — посмотреть, что просрочено, до старта сессии.
2. `session start --provider <id> --mode maintenance` (или `re_entry`, по
   продуктовому контексту) — режимы для занятия без нового материала.
3. Цикл `session peek`/`session next` → `attempt record` → `attempt finalize`
   → `review close` для каждого review-шага.
4. `session finish`, когда pending-набор пуст.
