# Handoff: каркас программы П.1

Дата: 2026-07-20

## Что создано

- `curriculum/levels.yaml` — 6 уровней A1–C2.
- `curriculum/tracks.yaml` — 8 треков.
- `curriculum/README.md` — структура и границы П.1.
- `curriculum/topics/a1.yaml`, `curriculum/topics/a2.yaml` — 85 Topic skeletons A1–A2.
- `curriculum/modules/a1.1-identity-and-role.yaml`, `a1.2-daily-work.yaml`, `a1.3-systems-objects-and-data.yaml`, `a1.4-work-in-progress.yaml`.
- `curriculum/modules/a1.5-requests-and-clarification.yaml`, `a1.6-past-work.yaml`, `a1.7-plans-and-next-steps.yaml`, `a1.8-integrated-work-scenario.yaml`.
- `curriculum/modules/a2.1-events-and-incidents.yaml`, `a2.2-results-and-experience.yaml`, `a2.3-planning-and-delivery.yaml`, `a2.4-requirements-and-options.yaml`.
- `curriculum/modules/a2.5-processes-and-troubleshooting.yaml`, `a2.6-collaboration.yaml`, `a2.7-reading-and-mediation.yaml`, `a2.8-integrated-project-update.yaml`.
- `curriculum/modules/b1.1-systems-and-project-reports.yaml`, `b2.1-technical-argumentation-and-synthesis.yaml`, `c1.1-professional-register-and-decision-memos.yaml`, `c2.1-editorial-precision-and-audience-adaptation.yaml`.

Всего под `curriculum/`: 25 файлов (5 корневых/data-файлов и 20 module files; Topic YAML — два из пяти data-файлов).

## Форма графа

- Тем: 85 (A1: 44; A2: 41).
- Рёбер prerequisites: strong — 111; soft — 16.
- Максимальная глубина strong-цепочки: 10 тем (9 рёбер).

## Осознанно отложено

- `mastery_criteria`, dimensions, пороги и числа → 0.4 / П.2.
- LexicalItem, лексикон, frequency/usage policy и `topic.lexicon` → П.4 после OPEN-15.
- `typical_errors`, examples, contexts, explanation_language и другое тело Topic → П.2.
- B1–C2 Topic inventory → последующий content review / П.2+.

## Самопроверка инвариантов

- Пройдена: 6 уникальных level IDs и ровно 8 уникальных track IDs; TOEFL начинается с B1.
- Пройдена: каждый A1–A2 Topic содержит `id`, `cefr`, `track`, `module`, однострочный `can_do`; Topic IDs и module IDs уникальны.
- Пройдена: все module/track/prerequisite references резолвятся; prerequisites используют только `strong`/`soft`; CEFR prerequisite не выше CEFR Topic; циклов нет.
- Пройдена: у A1.1–A2.8 есть can-do, tracks и полный список Topic IDs; B1–C2 не содержат Topic IDs.
- Пройдена: нет `mastery_criteria`, LexicalItem, `topic.lexicon`, численных порогов и богатого Topic body.

## Открытые вопросы и домыслы (`TODO(review)`)

1. A1.5 и точная гранулярность всего A1–A2 Topic inventory не перечислены в концепте буквально; применён минимальный функциональный split, помеченный в YAML.
2. Advisory prerequisite edges и их сила — минимальная авторская интерпретация, не продуктовые замки; требуется content review перед П.2.
3. Концепт даёт B1–C2 только level sketch. Созданы по одному module sketch на B1, B2, C1, C2; их будущая декомпозиция оставлена человеку.
4. Трек Vocabulary & Chunks намеренно не имеет A1–A2 Topic/LexicalItem data до П.4 и OPEN-15.
