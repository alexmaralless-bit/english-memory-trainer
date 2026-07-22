---
name: run-placement-assessment
version: "1"
description: "Провести первичную калибровочную диагностику (placement) через выделенный placement-lifecycle: собрать evidence по фиксированной форме без предположений об исходном уровне ученика."
required_inputs:
  - "необязательно: --self-assessment (объект по core-skill ID) при decline — скаляр запрещён"
forbidden_actions:
  - "не присваивать CEFR-уровень самому — только measured_working_level из `trainer status`"
  - "не выставлять score/mastery самому — placement оценивает движок (origin=placement, потолок ACTIVE, никогда MASTERED)"
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
  - "предварительная картина сильных/слабых сторон (по данным `trainer status` после `placement submit`)"
postconditions:
  - "placement submitted (scored) — либо abandoned/declined, если ученик прервал или отказался"
---

## Steps

1. `placement start --format json` — движок выбирает фиксированную версионированную форму и возвращает секции и items (answer keys остаются на стороне движка; генерация формы на лету запрещена — сравнимость результатов).
2. Предъявляй items ученику по секциям; собирай ответы; фиксируй инкрементально через `placement answer` (checkpoint) по каждой секции. При обрыве чата — `placement resume` в пределах resume-окна, чтобы продолжить с сохранённой секции.
3. `placement submit` — терминальный идемпотентный submit: движок оценивает форму (evidence с `origin=placement`, потолок ACTIVE — placement никогда не даёт MASTERED). Повторный submit возвращает тот же сохранённый результат.
4. Сверься с `trainer status`: `measured_working_level` и `lexicon_progress`/`skills` — единственный источник вывода об уровне; никогда не собственная оценка агента.
5. Альтернативы: если ученик отказывается проходить — `placement decline` с `--self-assessment` как объектом по навыкам (`{"schema_version":1,"levels":{...}}`; скаляр запрещён — отсутствующий навык остаётся unknown и перекрывается первым реальным evidence). Чтобы прервать без результата — `placement abandon` (только из STARTED/IN_PROGRESS).
