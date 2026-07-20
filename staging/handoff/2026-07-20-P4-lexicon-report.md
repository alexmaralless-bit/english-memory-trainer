# П.4a: stable core лексикон A1–A2

## Что создано

Под `curriculum/lexicon/` создан авторский stable core из **204 LexicalItem** и отдельный advisory-файл будущих Topic-связей.

### По файлам

| Файл | Единиц |
|---|---:|
| `core-a1.yaml` | 64 |
| `core-a2.yaml` | 64 |
| `lexemes-irregular.yaml` | 28 |
| `phrasal-verbs.yaml` | 18 |
| `informal-core.yaml` | 30 |
| **Итого** | **204** |

Дополнительно созданы `README.md` и `_suggested-topic-links.yaml` с 60 advisory-связями «единица → Topic». Авторитетные `topic.lexicon` не изменялись.

### По типам

| Type | Число |
|---|---:|
| `word` | 95 |
| `chunk` | 33 |
| `lexeme` | 28 |
| `phrasal-verb` | 18 |
| `informal_chunk` | 23 |
| `abbreviation` | 7 |

### По уровням

| CEFR | Число |
|---|---:|
| A1 | 98 |
| A2 | 106 |

Педагогические priority bands: `CORE` — 121, `HIGH` — 76, `USEFUL` — 7.

## Корпусный проход

**Не выполнен.** В П.4a не использовались CEFR-J, NGSL или wordfreq и не импортировались сторонние таблицы. Поэтому у единиц отсутствуют `frequency_score`, `frequency_band` и `source_refs`; вымышленные значения не ставились.

Для П.4b нужны:

1. Получить и pin-нуть exact version каждого выбранного источника.
2. Зафиксировать `SourceArtifact`: URL, retrieved_at, sha256, license, attribution и notices.
3. Зафиксировать версию build-процедуры и собственные versioned thresholds преобразования score → band.
4. Выполнить воспроизводимый enrichment, сохранив только производные значения и `source_refs`, без сырых датасетов в репозитории.

## Покрытие модулей

Advisory links резолвятся в существующие Topic и дают покрытие **16 из 16** модулей A1–A2.

| Module | Advisory-единиц | Основные области |
|---|---:|---|
| `a1.1-identity-and-role` | 3 | role, self-introduction, responsibilities |
| `a1.2-daily-work` | 3 | routines, frequency, schedule |
| `a1.3-systems-objects-and-data` | 3 | system descriptions, fields, data |
| `a1.4-work-in-progress` | 3 | current status, progress, contractions |
| `a1.5-requests-and-clarification` | 4 | requests, clarification, casual responses |
| `a1.6-past-work` | 4 | past events, sequence, irregular forms, issues |
| `a1.7-plans-and-next-steps` | 3 | plans, deadlines, next steps |
| `a1.8-integrated-work-scenario` | 3 | tickets, status, handoff |
| `a2.1-events-and-incidents` | 4 | incident timeline and past context |
| `a2.2-results-and-experience` | 4 | current results and participles |
| `a2.3-planning-and-delivery` | 4 | delivery, scope, deadlines, status |
| `a2.4-requirements-and-options` | 4 | requirements, comparison, recommendation |
| `a2.5-processes-and-troubleshooting` | 4 | causes, conditions, backup and rollback |
| `a2.6-collaboration` | 5 | requests, disagreement, follow-up, register |
| `a2.7-reading-and-mediation` | 5 | documentation, summary, forum tone/replies |
| `a2.8-integrated-project-update` | 4 | project update, bug report, recommendation |

В repository 20 module-файлов всего; четыре оставшихся — module-level sketches B1–C2, не входящие в scope stable core A1–A2.

## Самопроверка

Пройдено:

- 204 уникальных dotted ID; типы и CEFR входят в разрешённые enum;
- у каждой единицы есть priority band, register, domains, русское значение, собственный пример и `transformations: [authored]`;
- все 28 неправильных глаголов представлены одним lexeme с `base`/`past`/`participle`; `go/went/gone` — одна запись;
- все 30 informal-единиц имеют `usage_policy`, `neutral_equivalent`, `volatility: stable`, `currency: current`; у всех 15 `context_dependent` есть `allowed_contexts`; одна саркастическая единица — `recognition_only`;
- `frequency_*`, `mastery_criteria`, `LexicalMasteryProfile`, learner-state и сторонние excerpts отсутствуют;
- все 60 advisory links резолвятся; покрытие A1–A2 — 16/16 модулей;
- Topic и Module не редактировались в рамках П.4a.

Ошибок самопроверки не найдено.

## TODO(review)

- CEFR и `curriculum_priority_band` — авторская педагогическая классификация П.4a; до активации требуется human content review и затем отдельная корпусная аттестация П.4b.
- Нужно подтвердить sense-гранулярность многозначных `issue`, `field`, `run`, `set`: сейчас выбраны минимальные senses под текущие can-do.
- `lexeme.be.forms.past` представлен списком `[was, were]`; schema form aggregation должна подтвердить множественное значение формы.
- В задании сказано «20 модулей A1–A2», тогда как текущие данные содержат 16 A1–A2 modules и четыре B1–C2 sketches. Выбран минимальный вариант: проверены именно 16 модулей заявленных уровней.
- `_suggested-topic-links.yaml` требует П.2 content review; автоматически переносить его в `topic.lexicon` нельзя.

## Осознанно отложено

- Корпусные score/band и provenance — П.4b.
- Авторитетные `topic.lexicon` — П.2.
- Mastery profiles — scoring policy 0.4.
- Living layer, изменчивый сленг, meme templates и currency lifecycle — отдельный maintain-workflow.
- LearnerLexicalState, evidence и агрегация форм lexeme — runtime/scoring.
