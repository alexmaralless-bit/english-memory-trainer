---
name: teach-english-topic
version: "1"
description: "Объяснить конкретную тему (грамматика/лексика) внутри уже идущей сессии, опираясь на авторские материалы curriculum, а не на импровизацию."
required_inputs:
  - "topic id или lexicon id для объяснения"
  - "активная сессия (создаётся другим skill'ом, не этим)"
forbidden_actions:
  - "не выставлять score/mastery самому"
  - "не придумывать содержание темы в обход `curriculum show`/`curriculum lexicon`"
  - "не завершать сессию в обход `trainer session finish` / `trainer session abandon`"
cli_calls:
  - curriculum.show
  - curriculum.lexicon
  - session.peek
  - session.next
  - exercise.rendered
  - attempt.record
outputs:
  - "объяснение темы + один-два примера"
postconditions:
  - "объяснение опирается на can_do/содержимое из `curriculum show`, не на догадки"
---

## Steps

1. `curriculum show --topic <id>` (или `curriculum lexicon` для лексической
   единицы) — прочитать авторский can_do/значение/контексты.
2. Объяснить ученику своими словами, опираясь ТОЛЬКО на прочитанное.
3. Если тема совпадает с текущим предъявленным шагом (`session peek`) —
   продолжить обычной подачей задания (`exercise rendered` → `attempt record`).
