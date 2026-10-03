---
name: assess-english-gate
version: "2"
description: "Педагогическая справка: провести gate-проверку (контрольную точку) из advisory-плана brief в чате без подсказок, честно вынести вердикт тьютора, занести его в отчёт и сообщать результат только по `trainer status`."
required_inputs:
  - "brief активной сессии с шагом `gate_item` в `plan.steps[]`"
forbidden_actions:
  - "не подсказывать и не объяснять ответ до ответа ученика"
  - "не объявлять gate пройденным или уровень достигнутым самому — только по `trainer status` после отчёта"
  - "не завышать вердикт контрольного задания"
  - "не вызывать команды системы между `session start` и отчётом"
cli_calls:
  - status
outputs:
  - "контрольное задание, показанное одним сообщением"
  - "item отчёта с вердиктом тьютора по цели и dimension шага `gate_item`"
  - "сообщение ученику о результате по данным `trainer status`"
postconditions:
  - "ответ по gate_item занесён в журнал урока дословно, с вердиктом тьютора"
---

## References

- `../run-english-session/references/pedagogy.md` — «Gate items», «Tutor
  verdict».

## Steps

1. Найти в `brief.plan.steps[]` шаг `step_type: gate_item`: его `target_ref`
   и `dimension` — цель контрольного задания.
2. Показать задание одним сообщением, без подсказок и без предварительного
   разбора ответа.
3. Принять ответ, вынести вердикт по правилам «Tutor verdict», занести в
   журнал item (`target_ref`/`dimension` шага, дословный ответ, ошибки).
4. После принятого `session report` сообщить ученику результат ровно так, как
   показывает `trainer status`; самому прохождение gate не объявлять.
