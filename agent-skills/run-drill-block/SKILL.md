---
name: run-drill-block
version: "4"
description: "Провести занятие профиля drill по протоколу «задание → отчёт»: разминка, ввод фреймов, раунды дрилла (blocked → interleaved), реконструкция текста, timed writing и дебриф; раунды уходят в отчёт как blocks, только точность."
required_inputs:
  - "--provider (идентификатор тьютора)"
  - "прямой запрос ученика на профиль drill либо подтверждённая системная рекомендация"
forbidden_actions:
  - "не вызывать команды системы между `session start` и сборкой отчёта — все раунды идут в чате"
  - "не объяснять правило внутри раунда без прямого запроса ученика или повтора той же ошибки дважды (кроме `feedback_mode: always_explain` — см. `references/drill-protocol.md`)"
  - "не давать исправление раньше одного хода самоисправления ученика"
  - "не встраивать ответ или целевую форму (фрейм, слово) в формулировку задания"
  - "не предъявлять несколько items одним сообщением (learner feedback, 2026-09-22)"
  - "не передавать и не оценивать время ответа: автоматизм в чат-уроке — только точность [PD-2026-09-23]"
  - "не включать в блок неотвеченный item и не придумывать ответ; raw_answer — дословно первый ответ"
  - "не показывать ученику JSON, id или служебный статус и не называть систему «движком»"
  - "не выставлять уровни/mastery и не объявлять автоматизм достигнутым"
  - "не завершать сессию в обход `session report`/`session abandon`"
cli_calls:
  - session.propose
  - session.start
  - session.resume
  - session.status
  - curriculum.texts
  - session.check-report
  - session.report
  - session.abandon
  - status
outputs:
  - "объявление профиля drill, центрального паттерна, плана и правила ОДНОЙ строкой"
  - "фреймы темы с meaning_ru перед раундами"
  - "раунды дрилла blocked → interleaved без утечки ответа в prompt, по одному item в сообщении"
  - "реконструкция текста по ключевым словам"
  - "timed writing под объявленным лимитом без штрафа за превышение"
  - "дебриф: полное «почему», контрасты, правило"
  - "принятый `lesson_report@1`: раунды как `blocks` с items, реконструкция и timed writing как items"
postconditions:
  - "каждый раунд — одна запись `blocks[]` и его отвеченные items с тем же `block_id`"
  - "в отчёте нет latency и нет неотвеченных items"
  - "сессия FINISHED через принятый `session report` либо явно ABANDONED"
---

## Required references

Перед действием полностью прочитать:

- `references/drill-protocol.md` — как строить раунды из фреймов пятью
  формами item и как раунды, реконструкция и timed writing ложатся в отчёт.
- `../run-english-session/references/pedagogy.md` — «Feedback by stage»,
  «Drill rounds», «Tutor verdict»; этот skill их не дублирует, только
  применяет.
- `../run-english-session/references/lesson-report.md` — журнал в контексте,
  поля отчёта, check → report.

## Steps

1. **Preflight.** Прямой запрос ученика на `drill` — уже согласие; иначе
   `session propose` → объявить `title`, профиль, центральный паттерн, план
   (retrieval-разминка по due-материалу → ввод фреймов → раунд 1 blocked →
   раунд 2 interleaved → реконструкция → timed writing → дебриф) и получить
   подтверждение. `session start --profile drill --topic … --provider …
   --format json --idempotency-key …`. Из `brief` взять: `central_topic`
   (фреймы с `meaning_ru`/`slot_hint_ru`/`examples`, `reconstruction_text`),
   `plan.steps[].material` drill-шагов (`mode`, `round_size`, `rounds`, `primary_target`,
   `contrast_targets[]`, `frames[]`), `reviews_due`,
   `learner.preferences` (`round_size` по умолчанию 6, `explanation_language`,
   `timed_limit_seconds` по умолчанию 240, `preferred_drill_forms[]`,
   `feedback_mode`). Если текста реконструкции в brief нет — до начала урока
   `curriculum texts --topic <id>`. Сказать целевую форму ОДНОЙ строкой —
   полное объяснение только в дебрифе.
2. **Разминка** по `reviews_due` — припоминание RU→EN, по одному item в
   сообщении; каждое — item отчёта `kind: "review"` с `review_id`.
3. **Раунды** по `references/drill-protocol.md`: один item в одном сообщении,
   без вызовов системы; протокол обратной связи дрилла (flag → один ход
   самоисправления → фрейм целиком → перепечатать). Вердикт по каждому item —
   тьютора (pedagogy.md «Tutor verdict»); в журнале — prompt, дословный первый
   ответ, вердикт, подсказки, ошибки, `block_id` раунда. Время ответа не
   фиксировать.
4. **Реконструкция.** Показать текст один раз, скрыть, дать `keywords`;
   ученик восстанавливает по памяти целиком. В журнал — один item
   (`controlled_production`, центральная тема), `raw_answer` — весь текст
   ученика дословно, ошибки — дословные фрагменты.
5. **Timed writing.** Объявить лимит (`timed_limit_seconds`) до начала; не
   штрафовать превышение. Один item `spontaneous_production`; время не
   передаётся.
6. **Дебриф** — полное «почему», контрасты и правило по каждой ошибке урока.
7. **Отчёт** — по `lesson-report.md` и skill `finish-english-session`:
   `session check-report` → исправить отклонённое → `session report`. Итог
   ученику — по `trainer status`; уровень `automatic` в чат-уроке
   недостижим, не обещать его.
