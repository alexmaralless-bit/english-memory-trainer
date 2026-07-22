---
name: run-placement-assessment
version: "1"
description: "Провести первичную калибровочную сессию (placement): собрать evidence по нескольким темам без предположений об исходном уровне ученика."
required_inputs:
  - "--provider"
  - "необязательно: --mode (по умолчанию balanced)"
forbidden_actions:
  - "не присваивать CEFR-уровень самому — только measured_working_level из `trainer status`"
  - "не выставлять score/mastery самому"
  - "не завершать сессию в обход `trainer session finish` / `trainer session abandon`"
  - "не редактировать файлы состояния напрямую"
cli_calls:
  - session.start
  - session.peek
  - session.next
  - exercise.rendered
  - attempt.record
  - attempt.finalize
  - session.finish
  - status
outputs:
  - "предварительная картина сильных/слабых сторон (по данным `trainer status`)"
postconditions:
  - "хотя бы одна оценённая (assessed) попытка записана"
  - "сессия FINISHED или ABANDONED"
---

## Steps

1. `session start --provider <id> --format json`.
2. Цикл `session peek` → `exercise rendered` (для структурированных заданий)
   → ответ ученика → `attempt record` → при необходимости `attempt finalize`
   → `session next`.
3. После нескольких шагов свериться с `trainer status`: `measured_working_level`
   и `skills` — единственный источник вывода об уровне, никогда не
   собственная оценка агента.
4. Завершить через `session finish` (или `session abandon`, если прервано).
