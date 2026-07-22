---
name: coach-english-conversation
version: "1"
description: "Вести свободный разговорный шаг сессии (free conversation) без структурированного задания и answer_key."
required_inputs:
  - "активная сессия с предъявленным free-conversation шагом"
forbidden_actions:
  - "не выставлять score/mastery самому"
  - "не придумывать exercise_instance для шага, у которого его нет"
  - "не завершать сессию в обход `trainer session finish` / `trainer session abandon`"
cli_calls:
  - session.peek
  - session.next
  - attempt.record
  - session.status
outputs:
  - "реплики диалога с учеником на английском"
postconditions:
  - "содержательная реплика ученика зафиксирована через `attempt record` (без exercise-instance)"
---

## Steps

1. `session peek` — убедиться, что текущий шаг это free conversation
   (`target_ref` пуст).
2. Вести разговор на английском в контексте темы шага.
3. Каждый содержательный ответ ученика зафиксировать `attempt record`
   (без `--exercise-instance`; движок примет его как conversation evidence).
4. `session next`, когда шаг исчерпан.
