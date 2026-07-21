# Модуль: curriculum

> **Status**: current
> **Last updated**: 2026-07-21
> **Sources**: концепт Codex (одобрен, `staging/journal/2026-07-19-codex-curriculum-concept.md`) · red-team триаж (`staging/journal/2026-07-19-concept-review-triage.md`) · [[../product/learning-model]] §9 · [[../product/lexical-system]] · flows [[../flows/session]], [[../flows/placement]] · лицензии проверены 2026-07-19 ([PD-2026-07-19])
> **Bounded context**: `src/english_trainer/curriculum/`

> Спека — **target**. Фазы — тегами `[mvp]` / `[post-mvp]`. Термины — из [[../glossary]]; поведение — полностью inline. Это контракт формата и правил программы (roadmap 0.3); само наполнение — фаза П.

---

## 1. Назначение

Модуль владеет учебной программой: графом can-do тем, треками, уровнями и учебным лексиконом. Отдаёт остальным модулям адресуемые темы, рекомендации («что стоит взять сейчас») и лексикон. Программа — карта, не система замков: модуль никогда ничего не блокирует.

## 2. Сущности и состояния

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| `CurriculumVersion` | иммутабельный версионируемый снимок программы | version, activated_at, changelog |
| `Level` | CEFR-уровень с главным результатом | id (A1…C2), outcome |
| `Track` | сквозной трек через уровни | id, title, from_level |
| `Module` | группа тем уровня вокруг рабочей задачи | id (`a2.2-results-and-experience`), can_do, topics |
| `Topic` | единица изучения | см. формат ниже |
| `LexicalItem` | единица лексикона ([[../product/lexical-system]]) | id, type, `frequency_band`, `curriculum_priority_band`, register, usage_policy, source_refs… |
| `SourceArtifact` | внешний источник данных (provenance) | id, exact_version, url, retrieved_at, sha256, license, attribution, notices |

**Программа — граф can-do умений, не линейный учебник** [PD-2026-07-19]. Каждая тема отвечает на вопрос «что ученик сможет сделать», грамматика привязана к рабочей задаче (Present Perfect ← «сообщить о готовом результате»).

### Формат Topic

```yaml
id: grammar.present-perfect.result
cefr: A2
track: grammar-engine
module: a2.2-results-and-experience
can_do: Report a completed action that matters now
dimensions: [recognition, controlled_production, spontaneous_production, transfer]
advisory_prerequisites:
  strong: [grammar.have-has, grammar.past-participle]   # сильная рекомендация
  soft: [grammar.past-simple]                            # мягкая
lexicon: [chunk.we-have-completed, chunk.we-have-run-into-an-issue]
contexts: [project-update, deployment, aec-model-review]
typical_errors:
  - using Past Simple without a finished-time context
  - incorrect past participle
  - omitting have/has
mastery_criteria: {...}        # по versioned schema из 0.4, критерий на каждую required dimension
explanation_language: ru-allowed   # когда допустим русский
```

- **Единый enum prerequisites — `strong`/`soft`** [ревью A-4]: сила рекомендации, не замок. `hard/soft` из брифа — **superseded**, в текущей schema не используется.
- **`mastery_criteria`** — по versioned schema контракта 0.4 ([[../product/learning-model]] §9, ревью E-1); валидатор (§5) проверяет наличие критерия на каждую required dimension. До 0.4 полноценное авторское наполнение критериев не финализируется (см. roadmap: П.2 зависит от 0.4).

### Треки

| # | Track | С уровня |
|---|---|---|
| 1 | Grammar Engine | A1 |
| 2 | Vocabulary & Chunks | A1 |
| 3 | Reading | A1 |
| 4 | Written Interaction (чат, email, переписка) | A1 |
| 5 | Written Production & Mediation | A1 |
| 6 | US Tech English (AI/AEC/SaaS) | A1 |
| 7 | Everyday Life (`everyday-life`) — **домен**: быт, еда, дом, транспорт, здоровье, деньги, досуг | A1 |
| 8 | Online & Informal Register (`everyday-online-informal`) — **регистр и канал**: чат, форумы, сокращения, распознавание тона | A1 |
| 9 | TOEFL Reading & Writing | B1 |
| 10 | Word Formation (`word-formation`) — морфология как отдельная ось: продуктивные аффиксы (un-, re-, mis-, over-, out-, -er, -tion…) | A1 |

- **Десять треков; `everyday-life` отделён от `everyday-online-informal`** [PD-2026-07-20, P0-8]: первый задаёт **домен** (о чём речь), второй — **регистр и канал** (как пишут онлайн). Смешение домена с регистром повторило бы склейку, уже распутанную для частоты и педагогического приоритета. Бытовой пласт паритетен рабочему. Трек `word-formation` добавлен П.1d [PD-2026-07-21]: тема-паттерн и слово — разные targets, паттерн — помощь узнаванию, не генератор.
- **TOEFL-трек — в продукте, без отложек** [PD-2026-07-21]: тег `[post-mvp]` снят — пользователь готовится к TOEFL, трек полноценная часть программы (с B1; тем ниже B1 не порождает, §5). Прежняя пометка отражала фазировку MVP-продукта, которой у личного тренажёра нет.
- **Vocabulary & Chunks — lexicon-layer трек** [PD-2026-07-20, content-review C-1]: не несёт отдельных Topic'ов; реализуется как `LexicalItem` (chunks/слова), привязанные к темам через `topic.lexicon`, и отслеживается через LearnerLexicalState ([[../product/lexical-system]]). Пустой topic-инвентарь этого трека — намеренно, не пробел.

### Частотное взвешивание грамматики [PD-2026-07-21]

Корпусная основа: пять форм — Present Simple, Past Simple, Future Simple, Present Perfect, Present Continuous — покрывают ≈95%+ употреблений финитного глагола (Krámský 1969, воспроизводится по форме в Biber et al. 1999; точные доли зависят от регистра: научный текст — present simple, нарратив — past simple). Отсюда правило авторинга и приоритезации грамматических тем:

- **MUST — «большая пятёрка» = production-mastery**: темы пяти форм несут полный набор dimensions (recognition → controlled_production → spontaneous_production, transfer) на своём домашнем уровне (A1–A2) и получают высший рекомендательный приоритет. Цель — автоматизм («вызубрить»).
- **MUST — хвост полностью в продукте, приоритет ≠ включение**: редкие формы (past perfect, conditionals, past continuous, пассивные комбинации, будущее в прошедшем…) **не вырезаются и не откладываются** — TOEFL Reading/Writing без них не сдать, а «понять, а не перевести дословно» без них недостижимо. Последовательность: на уровне появления темы обязательны recognition (+ transfer понимания); controlled/spontaneous production обязательны к B1–B2. Частотный вес управляет **порядком и интенсивностью** практики, никогда — составом программы.
- **MUST — вес advisory**: взвешивание — рекомендация (карта, не замки, §5); scheduler/control потребляют его как обычный приоритет и ничего не блокируют.
- **MUST — разметка при авторинге (П.2)**: каждая тема трека Grammar Engine несёт `frequency_tier: big-five | tail`; валидатор требует поле только у тем этого трека.

### Каталоги лексикона

- **stable core** — проектируется заранее (П.4) из источников ниже;
- **living layer** [PD-2026-07-21, supersedes P0-9] — мемы, сленг и форумные единицы, встреченные во время обучения; добавляются через `maintain-english-curriculum` workflow с provenance (`first_observed_at`, источник, `currency`). **В продукте целиком**: workflow-пополнение, currency-lifecycle и авто-устаревание строятся — работа ложится в П.3 вместе с currency/usage-policy lifecycle (OPEN-14). Прежняя отложка «механизм в MVP не строится» снята: у личного тренажёра нет MVP-фазировки контента. Поля `volatility`/`currency`/`first_observed_at` обязательны, как и были; постоянный запрет сторонних excerpts (§3.1) не меняется;
- **learner lexicon** — личный словарь; живёт в модуле learner, не здесь.

## 3. Данные и лицензии [PD-2026-07-19]

Источники и режим использования выбраны (OPEN-6). Правовая позиция и схема provenance — решены [PD-2026-07-20], см. §3.1 (закрывает OPEN-15).

### 3.1 Правовая позиция: приватное личное использование [PD-2026-07-20]

- **Контекст**: репозиторий **приватный, для личного обучения одного ученика; не публикуется, не распространяется, не продаётся**. Обязательства CC BY-SA (attribution, license/notices, indication of changes, ShareAlike на Adapted Material) и требования цитирования срабатывают при **распространении** — при его отсутствии они не наступают. Поэтому **блокирующего лицензионного гейта перед первым импортом нет**.
- **MUST — provenance сохраняется по технической причине**: `SourceArtifact`, `source_refs` и `transformations` остаются обязательными **не** ради лицензий, а ради воспроизводимости, повторного импорта, replay и аудита (§3.2). Их отмена лицензионной позицией не оправдана.
- **MUST — publication trigger**: если репозиторий когда-либо публикуется/передаётся третьим лицам, **до** публикации обязана быть проведена ревизия: per-source notices (Octanove C1/C2, NGSL/NAWL/BSL, wordfreq data — все CC BY-SA), indication of changes, оценка «является ли отобранный лексикон Adapted Material» и граница ShareAlike. Это **условие**, а не открытый вопрос: пока распространения нет, работа не блокируется.
- **MUST NOT**: сторонние excerpts в living layer (см. §5) — правило постоянное, мотивировано ToS площадок и персональными данными, а не только лицензиями.
- Автор — не юрист; позиция задокументирована как продуктовое решение с явным триггером пересмотра.

| Источник | Роль | Лицензия | Обязательства |
|---|---|---|---|
| CEFR-J Vocab/Grammar Profiles A1–B2 (olp-en-cefrj) | CEFR-разметка | free research+commercial (Tono Lab) | цитирование + disclaimer |
| Octanove Vocabulary Profile C1/C2 | CEFR-разметка C1/C2 | **CC BY-SA 4.0** | attribution + license/notices + change-marking + ShareAlike на производное |
| NGSL / NAWL / Business Service List (BSL) | frequency band, рабочая лексика | **CC BY-SA 4.0** | attribution + notices + change-marking + ShareAlike на производное |
| wordfreq (rspeer) | численные частоты (агрегированный корпусный score) | код Apache-2.0, **данные CC BY-SA 4.0** | attribution + notices + change-marking; snapshot ~2021 |

- **MUST — режим build-time** [PD-2026-07-19/Q3, ревью I-1]: частотные данные используются pinned на build-time/этапе отбора; **сырые частотные датасеты в репо не коммитятся**. В репо — только отобранный лексикон с `source_refs`.
### 3.2 Состав данных и provenance

- **MUST — состав** [PD-2026-07-20]: в репо кладутся **собственные поля** единицы (id, title, meaning_ru, примеры, can_do-привязки) + **наш собственный** производный `frequency_score`/`frequency_band` (вычислен build-time из pinned-версий источников) + `source_refs`. Сырые датасеты источников не коммитятся (OPEN-6, build-time режим). Дословное копирование чужих таблиц не требуется и не делается.
- **MUST — provenance schema** [ревью I-2/I-3]: каждый импорт фиксирует `SourceArtifact {id, exact_version, url, retrieved_at, sha256, license, attribution, notices}`; каждая импортированная запись несёт `source_refs` + `transformations` (для неизменённой — явное `transformations: [identity]`). Оба поля **проверяются валидатором** (rereview I-R3). Основание — воспроизводимость импорта, не лицензия.
- **MUST — манифест provenance** [П.4b]: `SourceArtifact`-записи и versioned score→band thresholds живут в `curriculum/lexicon/_provenance.yaml`; `source_refs` ссылается только на объявленные там `id`. Сам расчёт выполняет `tools/enrich_lexicon.py`: он скачивает артефакт во внешний кэш, **сверяет sha256 и отказывается работать при расхождении**, и в режиме `--check` заново выводит каждое значение, падая при дрейфе. Ключевое требование — «частоты воспроизводимы из pinned-артефактов», а не «частоты кем-то проставлены».
- **MUST — закрытый словарь `transformations`** [П.4b, закрывает TODO П.4a-bis]: допустимы `identity` (импортирована без изменений), `authored` (выписана вручную для проекта), `corpus-enriched` (добавлены производные частотные поля из pinned-источников), `lemma-form-sum` (частота лексемы получена суммированием частот её поверхностных форм), `reclassified-from-chunk` (сменила type/ID при content-review). Пополнение словаря — правка этого контракта; валидатор отвергает незнакомый токен.
- **MUST — членство в списках проверяется по семье форм** [П.4b]: принадлежность к NGSL/BSL определяется по lemma-family файлам, а не по headword-рангам. На поверхностных формах `completed` и `meeting` ложно читались бы как отсутствующие, потому что списки содержат `complete` и `meet`; это исказило бы `source_refs`.
- **MUST — `formation` валидируется** [PD-2026-07-21]: если у единицы есть `formation`, поле несёт `affix`, `base` и `affix_type ∈ {prefix, suffix}`; `base` — существующая словоформа. Наличие `formation` не создаёт LexicalItem для `base` и не переопределяет его. Валидатор не требует `formation` у не-аффиксных единиц ([[../product/lexical-system]] §1b).
- **MUST — прозрачность валидируется** [PD-2026-07-20, П.4c]: у каждой многословной единицы (`chunk`, `idiom`, `phrasal-verb`, `informal_chunk`) обязан быть `transparency`; у `opaque` обязан быть `literal_trap_ru`; `opaque` не может иметь `controlled_production` среди required dimensions своего `LexicalMasteryProfile`. Профиль разрешается по `(type, transparency, usage_policy)` ([[../product/lexical-system]] §1a).
- **MUST — частотные поля не обязательны** [П.4b]: валидатор не требует `frequency_score`/`frequency_band` и не считает их отсутствие ошибкой — корпус слов не покрывает многословные единицы ([[../product/lexical-system]] §1). Но наличие частоты **без** `source_refs` — ошибка, равно как и `source_refs` на необъявленный артефакт.
- Список per-source notices (для будущей публикации, §3.1 trigger) хранится вместе с `SourceArtifact`, чтобы ревизия перед публикацией была механической, а не археологической.
- **Уточнение по wordfreq** [ревью I-5]: wordfreq даёт **агрегированную корпусную частоту** (домены, включая Reddit/Twitter, слиты в один score) — per-domain «присутствие в Reddit/Twitter» из API не запрашивается, а snapshot ~2021 не доказывает текущую currency. Источник informal-currency — отдельно, OPEN-14.
- **SHOULD**: `ATTRIBUTIONS.md` ведётся с первого импорта — как готовая заготовка под publication trigger (§3.1), не как блокирующее условие приватного использования.
- **MUST NOT**: импортировать данные CEFR-SP (лицензия не указана) и данные OpenVLT (лицензия данных не заявлена; только архитектурный reference).

## 4. Публичный API и события

| Операция / Событие | Тип | Что делает | Фаза |
|---|---|---|---|
| `get_topic(id)` | API | тема с полным содержимым | `[mvp]` |
| `recommendations(learner_state)` | API | темы с флагом `recommended / early` по advisory-графу и уровням | `[mvp]` |
| `lexicon_query(filter)` | API | выборка LexicalItem (frequency_band, curriculum_priority_band, track, usage_policy, currency) | `[mvp]` |
| `get_version(v)` | API | иммутабельный snapshot указанной версии (для replay/pin) | `[mvp]` |
| `validate(version_or_candidate)` | API | валидация **кандидата или версии** до активации (rereview E-R2) | `[mvp]` |
| `activate(version, expected_active)` | API | атомарная активация: требует успешный validate + CAS по expected_active, публикует событие | `[mvp]` |
| `CURRICULUM_VERSION_ACTIVATED` | publishes | активация новой версии (эмитится `activate`) | `[mvp]` |
| `LEXICAL_ITEM_ADDED` | publishes | пополнение living layer | `[mvp]` [PD-2026-07-21] |

## 5. Поведение

- **MUST**: у каждой темы есть `can_do`; тема без наблюдаемого умения не проходит валидацию.
- **MUST**: граф advisory — модуль выдаёт рекомендации, никогда не запрещает ([[../product/learning-model]] §1, §4).
- **MUST — pinning и не-ретроактивность** [PD-2026-07-19, ревью G-2/G-3]: `CurriculumVersion` иммутабелен. Evidence, session и Session Manifest **pin-ят** версию curriculum (и scoring/scheduler/generation/rubric policy), под которой созданы. Активация новой версии **никогда не ретроактивна**: replay и resume используют pinned-версию, не current active. «Движок работает с активной версией» относится только к формированию *новых* манифестов.
- **MUST — deprecation и replay** [ревью G-3]: изменение ID — только deprecation через append-only alias/migration events с явной семантикой `1:1 | split | merge | retired`; исходная версия сохраняется в snapshot, historical evidence не перепривязывается. Перезапись event log запрещена (append-only). Механизм — [[../OPEN]] OPEN-9.
- **MUST — бессмертие ссылок** [ревью G-5]: стабильный ID бессмертен, если на него ссылается **любой** persistent reference (evidence, manifest, review queue, банк, assessment), не только evidence; tombstones сохраняются; cross-validator проверяет разрешимость ссылок в learner state, манифестах, очереди, банке и assessments.
- **MUST — safety не пинится (safety-overlay)** [PD-2026-07-19, rereview G-R1]: пинятся только scoring/структура/rubric. `production_eligible` (из active usage_policy+currency) проверяется по **active** policy в момент доставки, не по pinned-версии. Прошлое evaluation/replay детерминировано по pinned; но live manifest / review assignment / банк / placement-форма перед доставкой production сверяются с active safety, и ставший `avoid`/`obsolete`/вне-контекста item отменяется/заменяется append-only event с обеими версиями. Scope stale-safety **включает live manifests**, владельцы — [[../OPEN]] OPEN-14 (+0.5 live delivery).
- **MUST — enforcement активации** [ревью E-5]: `validate`/`activate` энфорсят schema, provenance и целостность **независимо от способа правки файла**; невалидная версия не активируется. (Отдельный attestation-протокол в MVP не вводится — осознанный отказ от gate-машинерии, [[../README]].)
- **MUST**: изменения программы проходят `maintain-english-curriculum` workflow с последующей валидацией.
- **MUST — `production_eligible` и predicate** [rereview H-R1]: production/scheduler используют вычисляемый `production_eligible`; `obsolete` исключает production и новые assignments. `requires_usage_policy` — predicate по type/register, а не только по «informal-единица»: рискованный `type: word`/register тоже обязан иметь usage_policy.
- **MUST**: валидация ловит: циклы advisory-графа; битые ссылки prerequisites/lexicon/module/track/source_refs; дубли ID; prerequisite с CEFR выше уровня темы; пустые dimensions или отсутствие `mastery_criteria`/`LexicalMasteryProfile` на required dimension; отсутствие can_do; тему трека Grammar Engine без `frequency_tier` [PD-2026-07-21]; единицу, для которой `requires_usage_policy=true`, без `usage_policy`; `context_dependent` без `allowed_contexts`; `volatility: changing` без полного набора (`first_observed_at`/`last_verified_at`/`currency`/источник); `meme_template` без нейтрального объяснения **или `cultural_context`** (rereview H-R1); импортированную единицу без `source_refs`/SourceArtifact **или без `transformations`** (rereview I-R3); сторонние excerpts в living layer (постоянное правило).
- **MUST NOT — living layer excerpts** [PD-2026-07-20, rereview I-R2]: **постоянно** запрещено хранить сторонние excerpts (текст forum post/example) — мотив ToS площадок и персональные данные, независимо от лицензий. Разрешены: source-метаданные, короткая сама единица (выражение/сокращение) и **собственный** нейтральный парафраз/объяснение.
- **MUST**: informal-единицы с `usage_policy: avoid`/`recognition_only`/`currency: obsolete` не попадают в production и не рекомендуются — только на понимание; банк/формы/live manifests ре-валидируются против active policy ([[../product/lexical-system]] §3b, [[../OPEN]] OPEN-14).
- **MUST**: TOEFL-трек не порождает тем ниже B1.
- **SHOULD** [P0-8]: каждая тема связана хотя бы с одним реальным контекстом — **рабочим** (AI/AEC/SaaS/переписка/форум) **или бытовым** (быт, здоровье, поездки, досуг). Требование «только рабочий» противоречило принятому паритету бытового домена.

## 6. CLI-поверхность

| Команда | Что делает | Ответ |
|---|---|---|
| `trainer curriculum validate [--candidate PATH]` | валидация кандидата или активной версии | exit 0 / список ошибок с адресами |
| `trainer curriculum activate --version V --expected-active W` | атомарная активация валидной версии | результат + событие |
| `trainer curriculum show --topic ID --format json` | содержимое темы | Topic JSON |
| `trainer curriculum lexicon --filter ... --format json` | выборка лексикона | список LexicalItem |

## 7. Границы

- **depends on**: kernel (policy registry, IDs), storage
- **events published**: `CURRICULUM_VERSION_ACTIVATED`, `LEXICAL_ITEM_ADDED`
- **consumed by**: scheduler, lessons, assessments, learner, memory (через API рекомендаций/тем/лексикона)

## 8. Открытые вопросы

OPEN-6 решён (источники + build-time режим). Остаточные механизмы, зафиксированные инвариантами выше ([[../OPEN]]):

- **OPEN-9**: version pinning, deterministic replay, deprecation split/merge/retired, бессмертие ссылок → 0.3 (+0.2 CAS/snapshot).
- **OPEN-14**: currency/usage-policy lifecycle, `production_eligible`, safety-overlay для live manifests, stale-safety → П.3 (+0.4/+0.5).
- ~~OPEN-15~~ **закрыт** [PD-2026-07-20]: правовая позиция (приватное использование + publication trigger), состав данных и provenance-схема — §3.1/§3.2; living-layer rights — постоянное правило.

## История изменений

- **2026-07-21 (3)**: **living layer — в продукте [PD-2026-07-21]**, supersedes P0-9: workflow-пополнение, currency-lifecycle и авто-устаревание строятся (работа — П.3, вместе с OPEN-14); `LEXICAL_ITEM_ADDED` → `[mvp]`. Provenance-поля и постоянный запрет сторонних excerpts не меняются.
- **2026-07-21 (2)**: **TOEFL-трек — в продукте [PD-2026-07-21]**: тег `[post-mvp]` снят по решению пользователя (готовится к TOEFL; у личного тренажёра нет MVP-фазировки контента). Таблица треков синхронизирована с фактическим состоянием: добавлен ряд 10 `word-formation` (заведён П.1d, [PD-2026-07-21]), счёт «девять» → «десять» здесь и в glossary.
- **2026-07-21**: **частотное взвешивание грамматики [PD-2026-07-21]** — «большая пятёрка» времён (≈95%+ финитных употреблений: present/past/future simple, present perfect, present continuous) получает production-mastery и высший приоритет на A1–A2; хвост (past perfect, conditionals, пассив…) **полностью в продукте** — recognition на уровне появления, production обязательна к B1–B2 (TOEFL). Приоритет управляет порядком и интенсивностью, никогда — составом. Новое поле `frequency_tier: big-five | tail` обязательно для тем Grammar Engine (валидатор). Инициировано пользователем (Krámský 1969 / Biber et al. 1999).
- **2026-07-20 (P0-триаж)**: добавлен трек `everyday-life` в нормативную таблицу (девять треков, P0-8); living layer и `LEXICAL_ITEM_ADDED` помечены `[post-mvp]` согласно принятому PD (P0-9); SHOULD «рабочий контекст» расширен до «рабочий или бытовой»; ранее в этот же день — манифест provenance, закрытый словарь `transformations`, валидация `transparency` (П.4b/П.4c).
- **2026-07-20**: OPEN-15 закрыт [PD-2026-07-20] — правовая позиция «приватное личное использование, без распространения/продажи» + publication trigger (§3.1); состав данных (свои поля + собственный производный band + source_refs) и provenance по технической мотивации (§3.2); living-layer excerpts запрещены постоянно; ATTRIBUTIONS.md → SHOULD (заготовка). П.4 разблокирована. Также добавлен Vocabulary&Chunks как lexicon-layer трек (content-review C-1).
- **2026-07-19 (3)**: rereview — safety-overlay «safety не пинится» + live manifests в scope stale-safety (G-R1); candidate `validate`/`activate` API (E-R2); license-таблица разделена CEFR-J/Octanove + полные CC BY-SA obligations (I-R1); валидатор проверяет `transformations` (I-R3), `cultural_context` и `production_eligible`/`requires_usage_policy` (H-R1); living layer без сторонних excerpts до OPEN-15 (I-R2).
- **2026-07-19 (2)**: red-team триаж — единый enum `strong/soft` (A-4); pinning/не-ретроактивность и deprecation replay (G-2/G-3); бессмертие любого persistent reference (G-5); build-time режим данных (I-1/Q3); SourceArtifact provenance (I-2/I-3); полное имя BSL (I-4); исправлено утверждение о wordfreq Reddit/Twitter (I-5); enforcement активации без attestation (E-5); `mastery_criteria` → 0.4; расширена валидация. Механизмы → OPEN-9/14/15.
- **2026-07-19**: создан по одобренному концепту Codex (can-do граф, 8 треков, формат темы) + решение OPEN-6. Все решения [PD-2026-07-19].
