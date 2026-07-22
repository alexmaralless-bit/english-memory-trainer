# П.5 — задание для Codex: `rubric@1` — критерии оценки открытых ответов

> Дата постановки: 2026-07-22. Заказчик: владелец (через Claude).
> Роадмап: `wiki/roadmap.md` строка П.5, запись 74. Схема — двухфазная, как П.3.

## Зачем

Движок уже оценивает закрытые задания objective-проверкой по `answer_key` (2.3 инкремент 1).
Открытые ответы (controlled/spontaneous production, writing, free conversation) остаются
`recorded` и **блокируют finish разговорных сессий**, потому что policy-kind `rubric` пуст:
упражнение может нести `rubric_ref`, но резолвить его не во что. П.5 создаёт `rubric@1` —
данные, по которым движок (не агент!) вычисляет AttemptAssessment открытого ответа.

## Фаза 1 — концепт (сначала ТОЛЬКО это)

Файл `staging/concepts/2026-07-22-P5-rubric-concept.md`. Канон (`wiki/`) НЕ редактировать.
Изучи и обопрись на:

- `wiki/modules/evidence.md` §4.1 — schema observation: ссылка на `rubric_criterion` и span в
  raw_answer (не булев `criterion_satisfied`), разделение machine-checkable / subjective,
  неподтверждаемая observation → rejected (единственная ветка);
- `wiki/modules/scoring.md` §2.1 (rubric_cap, независимость ≥2 сессий для повышения состояния,
  Decimal-детерминизм), §3b (mastery_criteria тем — rubric их интерпретирует, не переопределяет);
- `curriculum/policies/generation-v1.yaml` — evidence_mode (`rubric_observation_*`),
  `answer_key_or_rubric_ref`;
- `wiki/product/learning-model.md` §3 (trust model: агент — trusted reporter raw_answer,
  но классификацию считает движок);
- `src/english_trainer/evidence/attempts.py` и `src/english_trainer/scoring/engine.py` —
  как objective-оценка уже течёт в `EVIDENCE_ADDED` и свёртку (читать, не менять).

Концепт обязан явно поставить **развилки (PD) владельцу**, минимум:

1. **Гранулярность рубрик**: универсальные по dimension (одна rubric на
   controlled_production и т.д.) vs специализация по треку/step_type (writing-essay отдельно
   от chat-reply). Рекомендация с обоснованием.
2. **Шкала критерия**: бинарные критерии vs градуированные уровни; как счёт становится
   `score_ppm` (целые, float-запрет; формула агрегации веса×уровни).
3. **Machine-checkable часть**: закрытый список проверок, которые движок выполняет кодом
   (мин. длина/структура, присутствие target-формы/лексемы в ответе, запрещённые кальки...) —
   что реализуемо детерминированно уже сейчас; всё остальное — subjective под trust+cap.
4. **Связь с typical_errors тем**: как observation ссылается на тип ошибки
   (severity-таксономия? влияние на счёт?).
5. **Namespace `rubric_ref`**: формат ссылки (`rubric:<id>` внутри `rubric@1`), резолв при
   рендере и при оценке.
6. **Дефолтная rubric per step_type**: что берёт `free_conversation`/`spontaneous_production`,
   когда упражнение не указало `rubric_ref` явно.

## Фаза 2 — только после «ок» владельца по развилкам

- Payload **`curriculum/policies/rubric-v1.yaml`** (`policy_id: "rubric@1"`, `status:
  "accepted"` после решений): критерии с целыми весами/уровнями (числа — int или
  decimal-строки; YAML-float запрещён), canonical-encodable, регистрируется на
  `curriculum activate` как kind `rubric` (хук валидации добавит владелец).
- Канон-патчи — **только предложениями** в отчёте (OLD/NEW), применяет владелец.
- Отчёт `staging/handoff/2026-07-22-P5-report.md` с воспроизводимыми проверками.

## Жёсткие ограничения

- `wiki/`, `src/`, `tests/` — read-only (движковое потребление rubric@1 — работа владельца в 2.3).
- Никаких фазовых маркеров [PD-2026-07-22]; никаких float в decision-полях.
- Все тексты критериев/примеров — свои (own_text_rule).
- A1–A2 контент, лексикон, root `Irregular Verbs.md` — не трогать.
