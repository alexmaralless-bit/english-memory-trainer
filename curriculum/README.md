# Curriculum skeleton A1–C2 (П.1)

Это candidate data-каркас программы: уровни, треки, модули и A1–A2 Topic-инвентарь. Он следует `wiki/modules/curriculum.md`; это не activation и не готовое наполнение программы.

## Раскладка

- `levels.yaml` — шесть CEFR уровней с главным can-do.
- `tracks.yaml` — **десять** сквозных треков; `everyday-life` — доменный (быт), `everyday-online-informal` — регистровый (онлайн), `word-formation` — морфология (продуктивные аффиксы); `toefl-reading-writing` начинается с B1 (тем ниже B1 не порождает) — полноценная часть программы [PD-2026-07-21].
- `modules/` — один YAML на module. A1.1–A2.8 (работа) и A1.9–A2.13 (быт) содержат список Topic ID; B1–C2 — только module-level sketches без тем.
- `topics/a1.yaml`, `topics/a2.yaml`, `topics/b1.yaml` — минимальные Topic skeletons (b1.yaml: первые детальные B1-темы — трек `word-formation`): ID, CEFR, track, module, can-do и advisory prerequisites.

Все prerequisite-связи — рекомендации графа, не замки. Используются только `strong` и `soft`.

## Осознанно отложено

- `mastery_criteria`, skill dimensions, пороги и численные правила — **→ 0.4 / П.2**. В Topic YAML их нет.
- `LexicalItem`, лексикон, `frequency_band`, `usage_policy` и `topic.lexicon` — **→ П.4 после OPEN-15**. Ни одной лексической единицы и поля `lexicon` здесь нет.
- `typical_errors`, examples, contexts, explanation_language и другое богатое тело Topic — **→ П.2**. В P.1 они намеренно отсутствуют.
- Topic decomposition B1–C2 — **→ последующий curriculum review / П.2+**. Там есть только module sketches.
- Формальная candidate validation/activation и versioned `CurriculumVersion` lifecycle — **→ 0.3 implementation / OPEN-9**; этот каталог является входными данными candidate snapshot.

## TODO(review)

- A1.5 topic split и весь минимальный A1–A2 inventory/порядок advisory edges — рабочая интерпретация конкретных описаний одобренного концепта; требует человеческого content review до П.2.
- B1–C2 получили по одному module-level sketch на уровень, потому что концепт задаёт только level sketch. Количество и границы этих modules не являются принятым продуктовым решением.
- Vocabulary & Chunks остаётся зарегистрированным треком без LexicalItem/Topic inventory до П.4; это не означает отсутствие будущей связи topics с лексиконом.
