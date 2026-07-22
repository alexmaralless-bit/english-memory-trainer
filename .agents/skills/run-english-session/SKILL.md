---
name: run-english-session
version: "1"
description: "Провести полноценную сессию английского от старта до завершения: прогнать шаги плана, зафиксировать попытки ученика и корректно закрыть сессию через движок."
required_inputs:
  - "--provider (идентификатор тьютора: claude-code | codex | ...)"
  - "session_id активной сессии (создаётся этим же skill'ом при старте, либо берётся из `session status`)"
forbidden_actions:
  - "не выставлять score/mastery самому — оценку всегда вычисляет движок"
  - "не завершать сессию в обход `trainer session finish` / `trainer session abandon`"
  - "не редактировать файлы состояния (SQLite, JSONL export, memory/) напрямую"
  - "не изобретать target_ref/dimension/origin попытки — их определяет движок из STEP_PRESENTED"
  - "не сообщать ученику про уровень/прогресс без реального вызова `trainer status`"
  - "не сообщать движку, что слово освоено: `lexicon encounter` — это enrollment, а не evidence; знание переводит только отдельная оценённая попытка"
  - "не создавать curriculum-единицу напрямую: при неизвестном слове оставлять `--linked-item` пустым (personal-запись, не программа)"
cli_calls:
  - session.start
  - session.peek
  - session.next
  - session.replan
  - exercise.rendered
  - attempt.record
  - attempt.finalize
  - review.close
  - session.finish
  - session.abandon
  - session.status
  - adapters.capture-turn
  - lexicon.encounter
outputs:
  - "краткое резюме сессии для ученика (что прошли, что осталось)"
postconditions:
  - "сессия в статусе FINISHED или ABANDONED"
  - "pending-набор (незавершённые attempts и review) пуст при FINISHED"
---

## Steps

1. `trainer session start --provider <id> --format json` (или `session status`,
   если сессия уже активна) — прочитать `pinned_versions` и `required_skills`.
2. Цикл: `session peek` → показать шаг ученику → при структурированном
   задании `exercise rendered` ДО показа промпта → получить ответ →
   `attempt record` (по потребности `attempt finalize`) → `session next`
   с актуальным `--expected-plan-version`.
2a. Если ученик просит перевод или говорит «не знаю это слово»: сначала
   зафиксировать реплику ученика через `adapters capture-turn`, затем вызвать
   `trainer lexicon encounter --surface "<слово>" --note-ru "<перевод>"
   --session <ID> --provider <id> --expected-session-revision <R>`. Если слово
   есть в активном curriculum — передать `--linked-item <ID>`; если нет —
   оставить пустым. После этого объяснить слово и ПРОДОЛЖИТЬ урок. Добавление
   и объяснение НЕ считаются знанием: проверку планирует штатный
   control/session-flow, отдельной оценённой попыткой.
3. Если план исчерпан или контекст изменился — `session replan`.
4. Due review из `session peek`/плана закрывать через `review close`
   (движок сам вычисляет исход, skill только сообщает о завершении шага).
5. Перед `session finish` убедиться, что pending-набор пуст
   (`session status`); если движок отказал по precondition — закрыть
   недостающие attempts/review и повторить.
6. Если сессию нужно прервать без результата — `session abandon`
   (никогда не оставлять сессию открытой без явного действия).
