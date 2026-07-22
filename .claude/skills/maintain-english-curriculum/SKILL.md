---
name: maintain-english-curriculum
version: "1"
description: "Изменить авторские материалы curriculum/ и синхронизировать/провалидировать agent skills, не трогая рантайм-состояние ученика."
required_inputs:
  - "изменение в curriculum/ (тема, лексика, политика)"
forbidden_actions:
  - "не активировать невалидированную версию curriculum"
  - "не править `.agents/skills/` или `.claude/skills/` руками — только `trainer skills sync`"
  - "не трогать learner state (SQLite/JSONL/memory/) при работе с curriculum"
cli_calls:
  - curriculum.validate
  - curriculum.show
  - curriculum.lexicon
  - curriculum.activate
  - skills.validate
  - skills.sync
outputs:
  - "отчёт валидации curriculum и skills"
postconditions:
  - "curriculum.validate чист перед curriculum.activate"
  - "skills.validate не сообщает о drift после skills.sync"
---

## Steps

1. Внести изменения в `curriculum/` через отдельный workflow
   (`maintain-english-curriculum` не описывает сам процесс редактирования
   YAML, только проверку и раскладку).
2. `curriculum validate` — исправлять ошибки до чистого результата.
3. `curriculum activate --version <id>` — только после чистой валидации.
4. При изменении `agent-skills/`: `skills validate` → если найден drift →
   `skills sync` → `skills validate` снова, до чистого результата.
