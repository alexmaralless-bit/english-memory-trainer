---
name: audit-english-tutor
version: "1"
description: "Только для чтения: сверить, что происходило в сессии, с тем, что предписывали skill'ы, и с тем, что видно в детерминированном состоянии движка."
required_inputs:
  - "session_id или диапазон для аудита"
forbidden_actions:
  - "не мутировать состояние — весь аудит read-only"
  - "не подтверждать соответствие (compliance) со слов агента — только по наблюдаемым CLI-вызовам и доменным событиям"
cli_calls:
  - session.status
  - scoring.replay
  - status
  - review.due
  - memory.check
  - adapters.compare
outputs:
  - "список расхождений между предписанным skill'ом и наблюдаемыми эффектами"
postconditions:
  - "ни один вызов в этом skill'е не изменил learner state"
---

## Steps

1. `session status` / `scoring replay` / `status` — снять фактическое
   состояние сессии и оценок.
2. `adapters compare` — свериться с фикстурами паритета адаптеров.
3. `memory check` — убедиться, что проекция не разошлась с состоянием.
4. Сравнить наблюдаемые CLI-вызовы и доменные события с тем, что предписывал
   исходный skill; самоотчёты агента (`SKILL_COMPLETED` и т.п.) не являются
   доказательством — они лишь диагностический сигнал (adapters §3 [P0-Q3]).
