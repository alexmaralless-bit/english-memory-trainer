---
name: assess-english-gate
version: "1"
description: "Провести gate-проверку (контрольную точку) по предъявленному gate_item шагу и честно сообщить результат по данным движка."
required_inputs:
  - "активная сессия с предъявленным gate_item шагом"
forbidden_actions:
  - "не выставлять исход gate самому"
  - "не пропускать `exercise rendered` для структурированного gate-задания"
  - "не сообщать про уровень/прохождение без вызова `trainer status`"
cli_calls:
  - session.peek
  - session.next
  - exercise.rendered
  - attempt.record
  - attempt.finalize
  - status
outputs:
  - "сообщение ученику о результате gate-проверки"
postconditions:
  - "попытка по gate_item доведена до assessed"
---

## Steps

1. `session peek` — подтвердить, что предъявлен шаг типа `gate_item`.
2. `exercise rendered` перед показом задания ученику (structured check).
3. Получить ответ → `attempt record` (объективная проверка выставит статус
   `assessed` автоматически, если есть `answer_key`) → при открытом ответе
   `attempt finalize`.
4. Сообщить результат ученику ровно так, как вернул движок; для общей
   картины свериться с `trainer status`.
