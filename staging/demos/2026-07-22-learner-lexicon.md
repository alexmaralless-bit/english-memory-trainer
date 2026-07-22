# Демо: личный словарь и встреча слова (2026-07-22)

Читаемый транскрипт **реального** детерминированного прогона
(`tests/integration/test_learner_lexicon.py`, `FixedClock(2026-07-22T09:00Z)` +
`SeededRandomSource(20260722)`). Все ID, хеши, числа и события — из прогона, не
выдуманы.

Сценарий отвечает на главный вопрос приёмки: **вопрос о переводе надёжно
переживает смену чата, но сам по себе никогда не превращается в доказательство
знания.**

---

## 0. Программа

Активна тестовая программа `learner-lexicon@1`: тема `grammar.be.identity` (A1)
и одна лексическая единица `word.feasible` (`feasible`, CORE, safe_to_use,
current), **привязанная к лексикону темы**. Из-за привязки micro-lane по
умолчанию её не берёт — до встречи она не появляется ни в одном плане.

## 1. Старт сессии — слова ещё нет в плане

```
provider = codex
session_id      = 01KY4GV8M0Y1D8E3BVRJ63X6ZX
session_revision = 1
plan targets    = ['grammar.be.identity']        # word.feasible ОТСУТСТВУЕТ
```

## 2. Ученик спрашивает перевод

Агент СНАЧАЛА фиксирует реплику ученика по adapter-протоколу (untrusted, не
evidence):

```
adapters capture-turn  "What does feasible mean?"
  → USER_TURN_CAPTURED  content_hash=sha256:d13ffb6115fdd…  trust=untrusted_user_input
  → session_revision = 2
```

Снимок scoring ДО встречи:

```
scores_before = {}          # ни одной оценённой цели
```

## 3. Агент вызывает структурированную команду (движок принимает факты)

Агент понимает естественную фразу, движок принимает структурированную команду —
NLP-парсера фраз внутри Python нет.

```
trainer lexicon encounter
  --surface "feasible" --note-ru "осуществимый; выполнимый"
  --session 01KY4GV8M0Y1D8E3BVRJ63X6ZX --linked-item word.feasible
  --provider codex --expected-session-revision 2

  → LEARNER_LEXICON_ENTRY_ADDED
       entry_id      = 01KY4GV8M0K69M29B5T5XNRHV1
       source        = encountered
       linked_item_id = word.feasible
       added_at      = 2026-07-22T09:00:00+00:00
     session_revision = 3
```

Единица сохранена как `encountered` в личном словаре и связана с её
`LexicalItem`. `relevant_targets = {word.feasible}` — приоритет будущей проверки
повышен.

## 4. Объяснение и добавление НЕ считаются evidence

Снимок scoring ПОСЛЕ встречи побайтово равен снимку ДО:

```
scores_after_encounter = {}          # IDENTICAL to scores_before → True
```

Нет `EVIDENCE_ADDED`, нет изменения Mastery/XP/уровня, нет `ReviewSchedule`,
нет фиктивного ReviewOutcome. Встреча — enrollment, не оценка.

## 5. Повтор той же встречи не создаёт второй записи

```
lexicon encounter (снова feasible → word.feasible)  → cached = True
LEARNER_LEXICON_ENTRY_ADDED events:  1  →  1         # второго события нет
```

## 6. Смена агента: следующий провайдер видит слово в briefing

```
trainer session resume --provider claude-code       # другой тьютор
  → AGENT_ATTACHED (claude-code),  session_revision = 4
  briefing.personal_lexicon.recent_encounters = [
    { entry_id: 01KY4GV8M0K69M29B5T5XNRHV1,
      surface: "feasible",
      note_ru: "осуществимый; выполнимый",
      linked_item_id: "word.feasible",
      added_at: "2026-07-22T09:00:00+00:00" }
  ]
```

Блок вычислен из состояния, отделён от untrusted-заметок и **не объявляет запись
изученной**. Вопрос о переводе пережил смену чата.

## 7. Слово попадает в практику отдельной проверкой

Т.к. единица есть в активном curriculum, `learner_relevance` подтягивает её в
lexicon-first практику при пересборке плана:

```
trainer session replan
  → plan targets = ['grammar.be.identity', 'word.feasible']   # теперь есть!

trainer session next … (до нужного шага)
  → STEP_PRESENTED  step_id=01KY4GV8M0231TCXGJKC96GWYV
     kind=growth  step_type=new_material_intro  target=word.feasible
```

## 8. Только отдельный оценённый ответ меняет знание

```
exercise rendered (answer_key=["feasible"])  →  exercise_instance_id
attempt record  raw_answer="feasible"
  → ATTEMPT_RECORDED  status=assessed  origin=session
    primary_target = { target_ref: word.feasible, dimension: recognition }
  → EVIDENCE_ADDED

scores_after_graded = {
  "word.feasible": {
    "mastery": { "recognition": "4.800" },
    "stability_days": "2.0",
    "knowledge_state": "NEW",
    "evidence_count": 1
  }
}
```

Только теперь у цели появилось scoring-состояние: Mastery `recognition=4.800`,
Stability `2.0` дн., `evidence_count=1` — там, где встреча не создавала ничего.
`knowledge_state` остаётся `NEW`: переход `NEW → LEARNING → ACTIVE → MASTERED`
идёт по ReviewOutcome последующих оценённых ответов, не по одной первой попытке
и тем более не по встрече.

## 9. Слово вне curriculum остаётся личной записью

```
trainer lexicon add --surface "blorptastic" --note-ru "выдуманное"
  → entry  linked_item_id = null   (unlinked)
  "blorptastic" in relevant_targets(control) : False
  "blorptastic" in scores                    : False
```

Непривязанная запись есть в словаре и в briefing/memory, но не участвует в
scoring и не становится целью обычного упражнения — до отдельной living-layer
операции.

## 10. Итоговый личный словарь

```
[ { surface: "blorptastic", source: learner,     linked_item_id: null },
  { surface: "feasible",    source: encountered,  linked_item_id: word.feasible } ]
```

---

## Матрица эффектов

| Сценарий | Personal lexicon | Scoring | Scheduler / control |
|---|---|---|---|
| Ученик спросил перевод | added / `encountered` | **unchanged** (byte-identical) | relevance only (не due) |
| Агент объяснил слово | unchanged | unchanged | unchanged |
| Оценённый ответ | unchanged | **updated** (evidence, Mastery) | schedule may open |
| Слово отсутствует в curriculum | unlinked | unchanged | not a target |

Прогон детерминирован: тот же сценарий на второй БД даёт побайтово равный
canonical_json (`test_scenario_is_byte_identical_across_databases`).
