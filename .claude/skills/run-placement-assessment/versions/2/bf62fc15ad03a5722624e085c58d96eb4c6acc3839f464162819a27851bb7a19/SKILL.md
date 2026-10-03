---
name: run-placement-assessment
version: "2"
description: "Провести первичную калибровочную диагностику (placement) через выделенный placement-lifecycle: собрать evidence по фиксированной форме без предположений об исходном уровне ученика."
required_inputs:
  - "необязательно: --self-assessment (объект по core-skill ID) при decline — скаляр запрещён"
forbidden_actions:
  - "не присваивать CEFR-уровень самому — только measured_working_level/confidence/basis из `trainer status`"
  - "не выставлять score/mastery/оценку письма самому — placement оценивает движок (origin=placement, потолок ACTIVE, никогда MASTERED; writing — provisional rubric-assessment)"
  - "не подсказывать, не переформулировать, не упрощать и не объяснять items — это диагностика, не обучение"
  - "не пропускать item молча — каждый item либо предъявлен и отвечен, либо явно пропущен самим учеником с фиксацией в ответе"
  - "не раскрывать answer key или rubric-эталон ученику ни до, ни после ответа"
  - "не терминализировать в обход `placement submit` / `placement abandon` / `placement decline`"
  - "не редактировать файлы состояния напрямую"
cli_calls:
  - placement.start
  - placement.answer
  - placement.resume
  - placement.submit
  - placement.abandon
  - placement.decline
  - status
outputs:
  - "предварительная картина по каждому core skill: measured_working_level, confidence (`low`), basis (`placement`) — по данным `trainer status` после `placement submit`"
  - "что уточнит оценку дальше (обычные сессии повышают confidence и переключают basis на `evidence` per-skill)"
postconditions:
  - "placement submitted (scored) — либо abandoned/declined, если ученик прервал или отказался"
---

## Steps

1. `placement start --format json` — движок выбирает фиксированную версионированную форму (`PlacementForm` из активной программы: deterministic seed, версия) и возвращает её целиком: passages и items с `kind`/`prompt`/`choice`-опциями/`min_words`-`max_words` у writing. Answer keys и rubric-эталон остаются на стороне движка — их нет в ответе ни для одного kind, и генерация формы на лету запрещена (сравнимость результатов).
2. Предъявляй items **секция за секцией**, внутри секции — **по возрастанию band** (A1→C1). Дословно: без подсказок, упрощений, переформулировок и объяснений. Инструкции ученику — по-русски, сами items (prompt, опции, passage) — по-английски, без перевода и пересказа.
   - `choice` — показывай все четыре опции буквами **a–d**.
   - reading — показывай passage **один раз** перед всеми его вопросами, не повторяй при каждом вопросе секции.
   - writing — вместе с prompt указывай объявленный диапазон слов (`min_words`–`max_words`).
3. По завершении **каждой** секции — checkpoint `placement answer` с ответами этой секции сразу, не дожидаясь конца формы. При обрыве чата — `placement resume` в пределах resume-окна, чтобы продолжить с сохранённой секции.
   - Для writing-секции передай в этом же вызове `observations`: span-ссылочные rubric-наблюдения по `rubric@1` (конкретный criterion + атомарный finding code + точный span в ответе ученика) — никогда готовый вердикт, level, score или `correct`. Без наблюдений item фиксируется non-contributing, не как ошибка ученика.
4. `placement submit` — терминальный идемпотентный submit: движок скорит objective-секции кодом и считает rubric-assessment письма (`rubric_step_type: spontaneous_production`, provisional — единичный фрагмент не даёт полного writing-уровня). Повторный submit возвращает тот же сохранённый результат.
5. Объявляй результат **только** из `trainer status`: per-skill `measured_working_level`, `confidence` (после placement — `low`) и `basis` (после placement — `placement`). Никогда не формулируй уровень от себя. Скажи ученику, что уточнит картину дальше: обычные сессии повышают confidence и переключают `basis` на `evidence` — по каждому навыку отдельно, по мере накопления evidence.
6. Альтернативы: если ученик отказывается проходить — `placement decline` с `--self-assessment` как объектом по навыкам (`{"schema_version":1,"levels":{...}}`; скаляр запрещён — отсутствующий навык остаётся unknown и перекрывается первым реальным evidence). Чтобы прервать без результата — `placement abandon` (только из STARTED/IN_PROGRESS).
