---
name: maintain-english-curriculum
version: "2"
description: "Изменить авторские материалы curriculum/ (включая фреймы и тексты реконструкции), прогнать структурные проверки и синхронизировать/провалидировать agent skills, не трогая рантайм-состояние ученика."
required_inputs:
  - "изменение в curriculum/ (тема, лексика, фрейм, текст реконструкции, политика)"
forbidden_actions:
  - "не активировать невалидированную версию curriculum"
  - "не править `.agents/skills/` или `.claude/skills/` руками — только `trainer skills sync`"
  - "не трогать learner state (SQLite/JSONL/memory/) при работе с curriculum"
  - "не пропускать `tools/check_authoring.py` и обязательный `tools/link_frames.py` перед `curriculum validate`, если менялись фреймы (`frame_of`/`carries`) или тексты реконструкции"
  - "не вводить тег `carries` или домен текста вне закрытых словарей — пополнение словаря есть правка самой спеки/чекера, а не разовое исключение"
cli_calls:
  - curriculum.validate
  - curriculum.show
  - curriculum.lexicon
  - curriculum.activate
  - skills.validate
  - skills.sync
outputs:
  - "отчёт `tools/check_authoring.py` по изменённым файлам фреймов и текстов реконструкции"
  - "отчёт `tools/link_frames.py` о добавленных advisory-ссылках и `topic.lexicon`"
  - "отчёт валидации curriculum и skills"
postconditions:
  - "tools/check_authoring.py возвращает OK по каждому изменённому файлу frames-*.yaml / texts/reconstruction/*.yaml"
  - "tools/link_frames.py прогнан без --check после чистого check_authoring.py (для правок с frame_of); повторный прогон не меняет байт"
  - "curriculum.validate чист перед curriculum.activate"
  - "skills.validate не сообщает о drift после skills.sync"
---

## Steps

1. Внести изменения в `curriculum/` через отдельный workflow
   (`maintain-english-curriculum` не описывает сам процесс редактирования
   YAML, только правила, проверку и раскладку).
2. **Фреймы** (`curriculum/lexicon/frames-*.yaml`, тип `chunk` c полями
   `frame_of`+`carries`, `wiki/product/lexical-system.md` §1c): `frame_of` —
   id существующей грамматической темы; владелец связи темы и фрейма —
   `topic.lexicon` темы (см. шаг 5 — `link_frames.py` это гарантирует, ручные
   правки `topic.lexicon` не нужны). `carries` — 1–3 тега из закрытого
   словаря трёх семейств (`tense:`/`article:`/`structure:`, та же спека);
   незнакомый тег — ошибка, а не повод расширить список на лету. Тема трека
   Grammar Engine с `frequency_tier: big-five`/`core` несёт **≥ 12** фреймов,
   `tail` — **≥ 8** (`wiki/modules/curriculum.md` §2c; недобор — ошибка
   валидации, не предупреждение). Фрейм артикльной темы (`frames-articles.yaml`)
   дополнительно несёт `tier: 1 | 2`. `contrast` (`frame`+`note_ru`) и `trap`
   (`learner_form`+`correction`+`cause_ru`) необязательны, но если заданы —
   все их подполя обязательны. `curriculum_priority_band` держит CORE-долю
   файла в 20–40% при ≥10 единицах.
3. **Тексты для реконструкции** (`curriculum/texts/reconstruction/<topic-id>.yaml`,
   один файл на тему, схема — `wiki/modules/curriculum.md` §2d): `schema_version: 1`;
   `word_count` равен фактическому числу слов `text` по пробелам (45–150);
   `target_spans` (4–12) — дословные подстроки `text`; `keywords` (6–14);
   `carries` — теги из того же закрытого словаря §2c; `domain: work | everyday
   | academic`; `context` — kebab-id; `topic` разрешается в существующую
   тему, `also_targets` — в тему или LexicalItem; `transformations: [authored]`;
   текст написан для проекта, сторонние excerpts запрещены тем же постоянным
   правилом, что и для остального лексикона.
4. Структурный чекер до валидатора: `python3 tools/check_authoring.py <новые
   или изменённые frames-*.yaml и texts/reconstruction/*.yaml>` —
   исправлять до `OK` по каждому файлу. Валидатор `curriculum validate`
   проверяет целостность со всей программой, но не эти авторские правила
   формата — чекер обязателен именно для них.
5. Обязательный пост-пасс связывания (только если менялись/добавлялись
   `frame_of`): `python3 tools/link_frames.py` без `--check`, после того как
   шаг 4 чист. Идемпотентно дописывает advisory-ссылки в
   `curriculum/lexicon/_suggested-topic-links.yaml` и id фреймов в
   `topic.lexicon` соответствующих тем `curriculum/topics/<level>.yaml`.
   Прогнать повторно и убедиться, что второй прогон ничего не меняет.
6. `curriculum validate` — исправлять ошибки до чистого результата.
7. `curriculum activate --version <id>` — только после чистой валидации.
8. При изменении `agent-skills/`: `skills validate` → если найден drift →
   `skills sync` → `skills validate` снова, до чистого результата.
