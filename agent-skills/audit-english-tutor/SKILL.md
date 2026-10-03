---
name: audit-english-tutor
version: "2"
description: "Только для чтения: сверить урок в чате с сохранённым lesson_report (items, дословные ответы, вердикты тьютора), с тем, что предписывали skill'ы, и с обязательствами obligations@4 в детерминированном состоянии."
required_inputs:
  - "session_id или диапазон для аудита"
  - "по возможности — транскрипт чата урока"
forbidden_actions:
  - "не мутировать состояние — весь аудит read-only"
  - "не подтверждать соответствие (compliance) со слов агента — только по наблюдаемым CLI-вызовам, доменным событиям и транскрипту"
  - "не перегрейдить урок задним числом и не править отчёт — только перечислить расхождения"
cli_calls:
  - session.status
  - audit.session
  - audit.target
  - audit.correlation
  - scoring.replay
  - status
  - review.due
  - memory.check
  - adapters.compare
outputs:
  - "список расхождений между чатом, сохранённым отчётом, предписаниями skill'ов и obligations@4"
  - "список сомнительных вердиктов тьютора с дословными ответами"
postconditions:
  - "ни один вызов в этом skill'е не изменил learner state"
---

## Steps

1. `audit session <session_id> --format json` — полный след сессии:
   `lesson.reported` (items, prompts, дословные ответы, вердикты, ошибки,
   `validation`: предупреждения, `reviews_unaddressed`, requirements) и
   производные события, плюс оценка обязательств.
2. Обязательства obligations@4: `lesson_preflight` (у старта есть профиль),
   `report_committed` (FINISHED только после `lesson.reported`),
   `reviews_addressed` (у каждого назначенного повторения есть
   `review.outcome` или `INSUFFICIENT_EVIDENCE` с причиной),
   `required_skill_effect`, `forbidden_action_absence`. Старые сессии
   оцениваются своей закреплённой версией обязательств.
3. Если есть транскрипт — сверить отчёт с чатом по каждому item: задание
   действительно было показано; `raw_answer` дословно совпадает с первым
   ответом ученика; `learner_form` — фрагмент этого ответа; `hints`
   соответствуют подсказкам; вердикт защитим по правилам pedagogy.md «Tutor
   verdict» (в том числе `partial` — смысл верный, форма споткнулась);
   нет выдуманных items и нет latency. Пропущенные в отчёте задания,
   выдуманные ответы и завышенные вердикты — расхождения.
4. `scoring replay` / `status` / `review due` — детерминированное состояние
   сходится с событиями; `memory check` — проекция не разошлась.
5. `adapters compare` — фикстуры паритета адаптеров (report-протокол).
6. Самоотчёты агента (`SKILL_COMPLETED` и т.п.) не являются доказательством —
   лишь диагностический сигнал (adapters §3 [P0-Q3]).
