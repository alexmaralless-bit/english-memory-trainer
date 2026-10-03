---
name: finish-english-session
version: "2"
description: "Корректно завершить или прервать текущую сессию: собрать lesson_report@1 из журнала урока, проверить `session check-report`, исправить отклонённое и сдать `session report` — либо явно перейти в `session abandon`."
required_inputs:
  - "активная сессия и её brief (`session_id`, `report_contract.brief_hash`)"
  - "журнал урока в контексте тьютора: prompt, дословный ответ, вердикт, подсказки, ошибки по каждому заданию"
forbidden_actions:
  - "не сообщать ученику, что урок завершён, если `session report` не вернул успех (или не выполнен `session abandon`)"
  - "не добавлять в отчёт задания, которых не было, и не менять ответ ученика или вердикт, чтобы пройти проверку"
  - "не отправлять `session report` без предварительного `session check-report` по тому же файлу"
  - "не повторять `session report` с тем же idempotency-key, изменив файл"
  - "не выставлять уровни/mastery самому и не называть уровень, которого нет в `trainer status`"
cli_calls:
  - session.status
  - session.resume
  - session.check-report
  - session.report
  - session.abandon
  - status
outputs:
  - "принятый отчёт и краткое резюме урока для ученика по данным `trainer status`"
postconditions:
  - "сессия в терминальном статусе FINISHED (через `session report`) или ABANDONED"
  - "отчёт прошёл `session check-report` без отклонённых items"
---

## Required references

- `../run-english-session/references/lesson-report.md` — поля отчёта, коды
  отказа, предупреждения.

## Steps

1. Собрать `lesson_report@1` из журнала: `session_id` и `brief_hash` из
   brief (если контекст потерян — `session resume` вернёт тот же brief), items
   в порядке урока, `blocks` для раундов дрилла, `reviews_skipped` с
   причиной для каждого непройденного повторения, `teaching`, `lexicon`,
   `summary` (`text`, `next_focus`). Записать JSON во временный файл вне
   репозитория.
2. `trainer session check-report --file <path> --format json` (только
   чтение). Если `valid: false` — прочитать `errors` и `reasons` каждого
   отклонённого item.
3. Исправить каждое отклонение по таблице из `lesson-report.md` (например,
   `learner_form_not_in_answer` — процитировать фрагмент дословно из
   `raw_answer`; `review_mismatch` — сверить `review_id`, цель и dimension).
   Никогда не «чинить» отклонение правкой ответа ученика или вердикта. Item,
   который честно не восстановить (ответа не было), — удалить. Повторять
   шаг 2, пока отклонённых нет.
4. Прочитать предупреждения и не скрывать их: `duplicate_span` (ответ уже
   засчитан раньше — записан без вклада), `review_unaddressed` (повторение
   закроется `INSUFFICIENT_EVIDENCE`), `requirement_unmet` (например, нет
   items по центральной теме), `brief_changed`. Существенное — сказать
   ученику.
5. `trainer session report --file <path> --provider <id> --format json
   --idempotency-key <key>`.
   Отказ `REPORT_REJECTED` — вернуться к шагу 3. Повтор того же ключа с тем же
   файлом вернёт кэшированный результат.
6. Итог ученику — только из `trainer status --format json`: что практиковали,
   что ушло в повторения, без придуманных уровней.
7. Если ученик ушёл, не дав ни одного полезного ответа, или урок нельзя
   честно описать отчётом — `trainer session abandon` вместо имитации
   завершения.
