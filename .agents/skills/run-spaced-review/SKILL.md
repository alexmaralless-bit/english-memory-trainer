---
name: run-spaced-review
version: "6"
description: "Провести объявленный spaced-review урок по протоколу «задание → отчёт»: due-повторения из brief — припоминание по смыслу (RU→EN), протокол по стадии, retry и перенос; каждое повторение в отчёте — item с review_id или пропуск с причиной."
required_inputs:
  - "--provider"
  - "прямой запрос ученика на повторение либо подтверждённая рекомендация `session propose`"
forbidden_actions:
  - "не вводить новую центральную грамматическую тему под видом повторения"
  - "не показывать ответ или форму до первой попытки припоминания"
  - "не объяснять правило до попытки припоминания и самоисправления"
  - "не вызывать команды системы между `session start` и сборкой отчёта"
  - "не предъявлять несколько items одним сообщением (learner feedback, 2026-09-22)"
  - "не привязывать item к `review_id` другой цели или другого dimension и не закрывать одно повторение двумя items"
  - "не молчать о неадресованном повторении: либо item, либо `reviews_skipped` с причиной"
  - "не придумывать ответы и не приукрашивать вердикт; raw_answer — дословно"
  - "не редактировать состояние напрямую"
cli_calls:
  - review.due
  - session.propose
  - session.start
  - session.resume
  - session.status
  - session.check-report
  - session.report
  - session.abandon
  - status
outputs:
  - "объявление причины повторения и списка навыков без показа ответов"
  - "припоминание по одному item в сообщении, retry и перенос"
  - "принятый `lesson_report@1`: по item на каждое пройденное повторение, остальные — в `reviews_skipped`"
postconditions:
  - "каждое повторение из `brief.reviews_due` адресовано: item с его `review_id` (та же цель и dimension) или `reviews_skipped` с причиной"
  - "сессия FINISHED через принятый `session report` либо ABANDONED"
---

## Required references

- `../run-english-session/references/pedagogy.md` — «Due reviews», «Feedback
  by stage», «Tutor verdict», темп «одно задание — одно сообщение».
- `../run-english-session/references/lesson-report.md` — журнал и отчёт.

## Steps

1. До старта можно прочитать `review due` (только чтение). Предложить/
   запустить профиль `spaced_review` (`session start --profile spaced_review
   --provider … --format json --idempotency-key …`) и объяснить, что материал
   выбран по сроку повторения, а не как наказание.
2. Прочитать `brief.reviews_due`: `review_id`, `target_ref`, `dimension`,
   `urgency`, русская подсказка смысла `hint`. Это и есть список урока —
   вызывать систему по ходу не нужно.
3. Для каждого повторения — retrieval prompt по смыслу: русская реплика или
   ситуация, которую ученик превращает в полную английскую фразу/предложение;
   форму первой не показывать. **Один item в одном сообщении**, ответ
   ученика — в журнал дословно. Вердикт тьютора: `correct` / `partial`
   (смысл верный, форма споткнулась — повторение подтверждается) /
   `incorrect` (повторение уходит в regression). Item отчёта:
   `kind: "review"`, `review_id`, `target_ref` и `dimension` ровно как в
   `reviews_due`.
4. При ошибке — протокол дрилла: один ход на самоисправление (засчитывается
   как подсказка, вердикт не выше `partial`); не исправил — показать
   корректную фразу и попросить перепечатать целиком. Объяснение — только в
   итоговом дебрифе. При успехе — сразу короткий перенос в новый контекст
   (отдельный item без `review_id`, если он был).
5. Не успели или ученик отказался — `reviews_skipped: [{"review_id": …,
   "reason": "no_time" | "learner_declined"}]`; такое повторение закроется
   `INSUFFICIENT_EVIDENCE` — честно сказать об этом ученику.
6. Отчёт: `session check-report` → исправить отклонённое (`review_mismatch`
   — сверить review_id/target/dimension) → `session report`; процедура —
   skill `finish-english-session`. Итог — по `trainer status`. При
   прерывании без полезных ответов — `session abandon`.
