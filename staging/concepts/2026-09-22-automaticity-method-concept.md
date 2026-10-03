# Концепт: контур автоматизации — фразы вперёд правил

> Phase: concept only. Date: 2026-09-22.
> Canon status: **не канон**. `wiki/`, `src/`, `tests/`, `curriculum/`, `agent-skills/` не менялись.
> Триггер: запрос ученика 2026-09-22 — «учить методом заучивания целых фраз и предложений, чтобы артикли, порядок слов и глагольные формы вылетали на автомате, без вспоминания правил в момент речи; правила тоже нужны, но как поддержка».
> Основа: аудит канона (learning-model, curriculum, control, lessons, scoring, scheduler, generation@1/@2, skills) + исследовательская сводка (раздел 6).

---

## 1. Диагноз: как тренажёр учит сейчас

Канон описывает **честную систему измерения точности** поверх гибкого разговора. Она хорошо построена, но её единица обучения, состав занятия и обратная связь заточены под «понял правило → применил правильно», а не под «выдаёт форму быстро и без раздумий». Конкретно:

| Аспект | Как сейчас (канон) | Почему это мешает автоматизму |
|---|---|---|
| Единица обучения | `Topic` (can-do) с rule-first TeachingSegment: ситуация → ментальная модель → форма → контраст → примеры → ловушки → граница → retrieval bridge | Центр урока — объяснение. Chunks (≈136 из 1142 единиц лексикона) привязаны к темам как иллюстрации, а не как то, что заучивается |
| Что измеряется | 4 dimension по **точности**: recognition → controlled → spontaneous → transfer; Mastery 0–100, пороги 70/75, 2 независимых попытки | Нет ни одной меры **скорости**. Evidence не хранит время ответа. Система не отличает «знает правило и применяет медленно» от «выдаёт автоматически» |
| Состав занятия | 30 мин ≈ 8–12 шагов; `saturation` ≤ 3 показа цели за 5 сессий; ≤ 2 шага на тему за занятие; ≤ 1 growth-шаг на цель | Это **анти-дрилл**: серию из 12–20 быстрых предъявлений одного паттерна собрать нельзя. Правила защищают от перепоказа, но именно массированные повторения с вариацией нужны для процедурализации |
| Формы упражнений (`generation@1/@2`) | slot_fill, sentence_transformation, word_order, guided_reply, cloze_recognition, short_free_reply, status_update, new_context_rewrite… | Нет RU→EN перевода предложений, нет recall фразы по смыслу, нет заданий на время, нет реконструкции текста, нет минимальных пар a/the/∅ |
| Обратная связь | Всегда «объясни причину, не только исправленную строку»; skill `correct-learner-output` это **запрещает** | Каждая ошибка возвращает ученика к правилу. Для стадии автоматизации нужен другой протокол: подсказка → самоисправление → правильный chunk → повтор целиком |
| Интервалы | `1 → 3 → 7 → 14 → 30…` дней на пару (target, dimension) | Для морфосинтаксиса исследования показывают: сначала 3–4 продуктивных сессии с интервалом 1–4 дня, потом длинная очередь. Прыжок к 7 дням после двух проверок — рано |
| Артикли | **1 тема из 275** (`grammar.articles.identity`, A1, с явными `scope_limits`); 45 chunks содержат артикль, но никак не помечены | Главная цель русскоязычного ученика представлена одной вводной темой. Нет тем на zero article, generic, the с superlative/ordinal, институциональные `go to work / the office`, фиксированные обороты `in the morning, once a week, a lot of` |
| Предпочтения ученика | Заметка от 2026-07-27 (раунды по 6 артиклей, объяснения по-русски) лежит только в journal; в `learner` нет механизма preferences | Тьютор каждый раз начинает с нуля |

Что **уже правильно и остаётся основой**: evidence-only scoring и детерминизм; dimensions `spontaneous_production`/`transfer`; тип `chunk` = «заготовка со слотом»; known-language envelope свободного разговора; error clinic по recurring error; versioned policies (новую ось можно добавить без ломки replay); сигналы/probe; exercise bank; ось transparency и `production_eligible`.

Вывод: **менять нужно не архитектуру, а педагогическую модель поверх неё** — единицу заучивания, формы практики, протокол обратной связи, ритм повторений и измерение скорости.

## 2. Что говорит исследование (по силе доказательств)

Полная сводка с источниками — раздел 6. Краткий ранжированный список:

1. **Печатное припоминание с обратной связью вместо перечитывания** — очень сильно (Karpicke & Roediger 2008; Nakata 2016; Serfaty & Serrano 2024).
2. **Практика в целевой модальности**: письменная цель = письменная продукция; распознавание и cloze-узнавание продукцию не строят (DeKeyser 1997; Shintani et al. 2013).
3. **3–4 продуктивные сессии с интервалом 1–4 дня** до передачи в длинную очередь; недельные интервалы для морфосинтаксиса слишком велики (Suzuki 2017; Serfaty & Serrano 2024; Kim & Webb 2022).
4. **Сфокусированная письменная коррекция с повтором** держится месяцами; прямая правка chunk'а работает не хуже металингвистического объяснения (Bitchener & Knoch 2010 — именно на a/the; Brown et al. 2023).
5. **Interleaving контрастных структур после короткого blocked-ввода**: больше ошибок в тренировке, лучше отложенная точность (Nakata & Suzuki 2019; Pan et al. 2019).
6. **Правило — коротко и вторично**, в дебрифе; знание правил артиклей без постоянной практики распадается за год (Goo et al. 2015; Umeda et al. 2019).
7. **Подсказка раньше правки**: вызвать самоисправление, потом дать правильный chunk и потребовать воспроизвести (Lyster & Saito 2010).
8. **Chunks как инвентарь фреймов со слотами, заучиваемых намеренно и продуцируемых**; постоянный «артикльный» ярус (Yi & Zhong 2024 — мета-анализ processing advantage, g ≈ 0.43; Pastushenkov & Cornell 2019 — для русскоязычных: учить bundles с фиксированными артиклями).
9. **Короткий structured-input шаг для неверно парсимых контрастов** (русский perfective ≠ perfect; колебание a/the), затем продукция (Shintani 2015).
10. **Timed writing, реконструкция текста, sentence combining, контрастный RU→EN перевод** как наполнители на беглость — слабо-умеренно (Laufer & Girsai 2008 поддерживают контрастный перевод).

**Не подтверждено**: input flood / выделение форм в тексте само по себе (d ≈ 0.2); «productive failure»; Glossika/Refold/sentence mining как таковые (нет контролируемых исследований, но компоненты — retrieval + spacing — сильные); LLM-тьюторы для автоматизма (никто не измеряет).

Ключевая рамка — **Skill Acquisition Theory** (DeKeyser; Suzuki & DeKeyser 2017): декларативное знание (правило) → процедурализация через практику → автоматизация. Правило нужно в начале, но объём практики должен многократно превышать объём объяснения, а прогресс измеряется **скоростью и точностью под нагрузкой**, а не устной способностью правило пересказать. Это ровно то, что просит ученик.

## 3. Предлагаемая модель: «правило коротко → фразы → дрилл → речь → перенос»

### 3.1 Инвентарь фреймов (grammar-carrying chunks)

- Для каждой темы `big-five` и `core` — авторский набор **15–40 фреймов со слотами**, несущих целевую форму: `I've already ___`, `We haven't ___ yet`, `It's been ___ since ___`, `I was ___ when ___`, `at the end of the ___`, `a couple of ___`, `she's a ___` (профессия).
- Фрейм — существующий тип `chunk`, но с новым полем `carries: [article:definite, tense:present-perfect, …]` и обязательной привязкой к теме. Фрейм — это то, что **заучивается**; правило темы — то, что объясняет.
- Отдельный **артикльный инвентарь в три яруса** (по исследованию §7): (1) фиксированные обороты как целое (`in the morning`, `have a look`, `on the other hand`, `the same`, `a lot of`); (2) низкоуровневые схемы (`a + first mention … the + second mention`, `the N of N`, `a/an + роль`); (3) дискурсивное правило — коротко и последним.
- **Глагольные инвентари по L1-разрыву**: present perfect result/experience, past simple с законченным временем, past continuous «фон + прерывание», согласование времён; каждый с одним контрастом (`since Monday` vs `on Monday`) и одной «ловушкой» из русского вида (`*I have read it yesterday`).

### 3.2 Дрилл-блок как новый step_type

- `drill_block`: серия из **2–3 раундов по 6 предъявлений** (соответствует предпочтению ученика от 2026-07-27) одного паттерна с разным лексическим наполнением; один evidence-объект на блок с per-item наблюдениями.
- Формы внутри блока, все — печатная продукция: `ru_to_en_sentence` (русская реплика → полное английское предложение 8–12 слов), `frame_recall` (смысл/ситуация → фраза целиком; удаление покрывает **весь** фрейм, а не только `the`), `cue_to_sentence` (ключевые слова → предложение), `transformation` (`yesterday → since Monday`), `minimal_pair` (a/the/∅ в одинаковом контексте), `error_spotting` (найти и исправить).
- Порядок: первое занятие по паттерну — blocked; со второго — **interleaved** с 2–4 контрастными паттернами (a/the/∅; past simple/present perfect/past continuous).
- Внутри блока `saturation` и `max_steps_per_topic` не применяются к элементам; они считают **блоки**.

### 3.3 Измерение автоматизма

- Attempt получает `response_latency_ms` (время от показа prompt до ответа; агент — trusted reporter, как и для raw_answer). Измерение шумное, но сравнивается с **собственной базой ученика**, не с абсолютом.
- Timed-формы: `timed_writing` (5 минут, N предложений на тему, форсирующую цель), `timed_drill` (раунд с объявленным лимитом).
- Новая **ось `automaticity`** per (target): `not_measured → deliberate → proceduralized → automatic`. Условие `automatic` (черновые значения, tunable): точность ≥ 95 % в ≥ 3 дрилл-блоках в ≥ 2 сессиях **и** медианная latency ≤ k × базовой latency ученика на известном материале **и** ≥ 1 подтверждение в spontaneous/timed-форме. Ось отдельна от Mastery и Stability и не меняет формулу scoring; вводится новой версией policy.

### 3.4 Ритм повторений

- Новый набор фреймов проходит **короткую лестницу**: продуктивные проверки на день 1, 2–3, 5–7 (до критерия), и только потом попадает в основную `1 → 3 → 7 → 14…`. Реализуется как `scheduler@2` с параметром `relearning_ladder_days: [1, 2, 4]` перед основной; доменная модель не меняется.
- Артикльный ярус остаётся в interleaved-очереди **постоянно** (знание артиклей распадается без практики).

### 3.5 Обратная связь по стадиям

| Стадия | Протокол |
|---|---|
| Дрилл / фреймы | (1) подсказка: отметить фрагмент, один ход на самоисправление; (2) не исправил — показать правильный **chunk**, не правило; (3) потребовать перепечатать предложение целиком; (4) ошибка → новая карточка в очередь. Объяснение — только по запросу или при повторе ошибки ×2 (одна строка + ссылка на тему) |
| Свободная речь | focus-ошибка сразу в форме recast + retry; остальное — пакетом в дебрифе |
| Дебриф занятия | здесь и только здесь — «почему», контрасты, правило |

Требует изменить `correct-learner-output` (снять запрет «только исправленная строка») и `pedagogy.md` («explain the cause» → зависит от стадии).

### 3.6 Беглость текста и чтение

- `reconstruction`: авторский текст 60–80 слов, насыщенный целевыми фреймами → скрыть → восстановить по ключевым словам → сравнить (retrieval в маске; Yu, Boers & Tremblay 2025).
- `sentence_combining`; `bidirectional_translation` (EN-модель → RU → через день обратно в EN, сравнить).
- Чтение: авторские тексты с «предскажи форму» (cloze-reading на артикли/времена) как structured-input шаг **только** для неверно парсимых контрастов; input flood сам по себе не полагается.
- Всё — собственный текст проекта (own-text rule сохраняется).

### 3.7 Состав занятия «программный урок» после изменения

Ориентир 25–30 мин: 3–5 мин retrieval due-карточек → 8–10 мин ввод фрейм-набора с 6–10 печатными продукциями (правило — одной строкой до, полноценно — в дебрифе) → 5 мин реконструкция → 5 мин timed writing → 3 мин дебриф с retry; из ошибок генерируются карточки. Профили `practice` и `spaced_review` получают вариант «дрилл».

### 3.8 Предпочтения ученика

`LearnerProfile.preferences` (versioned): размер раунда, язык объяснений, предпочитаемые формы дрилла, лимит времени. Читаются в briefing; меняются командой `trainer learner preferences set`.

## 4. Что придётся менять в каноне (после «ок»)

| Спека | Изменение |
|---|---|
| `product/learning-model.md` | ось `automaticity` (§4), стадийная обратная связь (§9.1), короткая лестница (§7) |
| `product/lexical-system.md` | поле `carries` у chunk; артикльный ярус; фрейм = единица заучивания |
| `modules/curriculum.md` | `carries`, минимальный инвентарь фреймов на big-five/core тему (валидатор), артикльные micro-topics по уровням |
| `modules/evidence.md` | `response_latency_ms`, per-item observations в блоке |
| `modules/scoring.md` | ось automaticity (отдельный reducer, свой policy kind), timed-формы |
| `modules/scheduler.md` | `relearning_ladder_days` |
| `modules/control.md` | `drill_block`/`timed_writing`/`reconstruction` в матрице `kind → step_type`, expected_seconds, saturation по блокам, квота interleaving |
| `generation@3` | новые формы (§3.2, §3.6), правила минимальных пар и RU→EN |
| `modules/learner.md` | preferences |
| skills: `correct-learner-output`, `run-english-session/references/pedagogy.md`, `run-spaced-review`, новый `run-drill-block` | протокол §3.5, раунды, timed-режим |
| `glossary.md` | frame, drill block, automaticity, relearning ladder |

## 5. Развилки для решения ученика (кандидаты PD)

- **PD-A. Автоматизм как отдельная ось состояния** (рекомендуется: не трогает Mastery и таблицу переходов, replay-безопасно) **или** пятый dimension `fluency` внутри Mastery.
- **PD-B. Latency**: доверять агентскому `response_latency_ms` как trusted-reporter полю (рекомендуется, с оговоркой «относительно базы ученика») **или** измерять только timed-формы с объявленным лимитом.
- **PD-C. Фреймы**: тип `chunk` + поле `carries` (рекомендуется: без нового типа и новой mastery-таблицы) **или** новый тип `pattern`.
- **PD-D. Короткая лестница**: отдельная relearning-фаза перед основной (рекомендуется) **или** замена основной лестницы на `1 → 2 → 4 → 7 → 14…`.
- **PD-E. Обратная связь**: стадийный протокол §3.5 (рекомендуется) **или** сохранить «всегда объясняй причину» и добавить только retry.
- **PD-F. Артикли**: расширить программу до 6–8 артикльных тем по уровням + постоянный interleaved-ярус (рекомендуется) **или** оставить одну тему и покрыть остальное только фреймами.

## 6. Источники исследовательской сводки

Chunks / формульные последовательности: Yi & Zhong 2024 (SSLA, мета-анализ) — <https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/abs/processing-advantage-of-multiword-sequences-a-metaanalysis/64D9BFF2B458422C8CCE202A520F914A>; Frontiers 2024 (stimulated recall) — <https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1281926/full>; Boers et al. 2006 — <https://journals.sagepub.com/doi/abs/10.1191/1362168806lr195oa>; Pellicer-Sánchez & Boers 2019 — <https://ir.lib.uwo.ca/edupub/283/>; N. Ellis 2006 (learned attention) — <https://academic.oup.com/applij/article-abstract/27/2/164/185787>; Swan — <https://mikeswan.net/wp-content/uploads/2017/08/Chunks-in-the-classroom.pdf>.

Skill Acquisition / практика: DeKeyser 1997 — <https://eric.ed.gov/?id=EJ547482>; Suzuki & DeKeyser 2017 (LL) — <https://onlinelibrary.wiley.com/doi/abs/10.1111/lang.12241>; R. Ellis 2005 (измерение implicit/explicit) — <https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/measuring-implicit-and-explicit-knowledge-of-a-second-language-a-psychometric-study/0708428E45AEA716C06E47ED37785D4E>; Suzuki 2017 (3.3 vs 7 дней) — <https://onlinelibrary.wiley.com/doi/abs/10.1111/lang.12236>; Suzuki 2024 (SSLA) — <https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/effects-of-distributed-practice-on-second-language-fluency-development/4F6787916C198376CAD222934D3B37E4>; Kim & Webb 2022 — <https://onlinelibrary.wiley.com/doi/abs/10.1111/lang.12479>; Serfaty & Serrano 2024 — <https://onlinelibrary.wiley.com/doi/10.1111/lang.12585>; Nakata & Suzuki 2019 — <https://onlinelibrary.wiley.com/doi/abs/10.1111/modl.12581>; Pan et al. 2019 — <http://stevencpan.bol.ucla.edu/pdf/PTLOR_2019.pdf>; Suzuki (ed.) 2023 — <https://www.routledge.com/Practice-and-Automatization-in-Second-Language-Research-Perspectives-from-Skill-Acquisition-Theory-and-Cognitive-Psychology/Suzuki/p/book/9780367644390>.

Retrieval / SRS: Karpicke & Roediger 2008 — <https://pubmed.ncbi.nlm.nih.gov/18276894/>; Nakata 2016 — <https://www.degruyterbrill.com/document/doi/10.1515/iral-2015-0022/html>; Laufer & Shmueli 1997 — <https://files.eric.ed.gov/fulltext/EJ1324878.pdf>; Settles & Meeder 2016 (Duolingo HLR) — <https://research.duolingo.com/papers/settles.acl16.pdf>; FSRS — <https://github.com/open-spaced-repetition/fsrs4anki/wiki/>; Refold sentence mining — <https://refold.la/simplified/stage-2/a/sentence-mining/>.

Input vs output: Shintani, Li & Ellis 2013 — <https://onlinelibrary.wiley.com/doi/abs/10.1111/lang.12001>; Shintani 2015 — <https://academic.oup.com/applij/article-abstract/36/3/306/2422461>; Lee & Huang 2008 (enhancement) — <https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/abs/visual-input-enhancement-and-grammar-learning-a-metaanalytic-review/B9D0C50B09928C20C94548B37B29A042>; Goo et al. 2015 — <https://benjamins.com/catalog/sibil.48.18goo>; Kang, Sok & Han 2019 — <https://journals.sagepub.com/doi/10.1177/1362168818776671>; Muranoi 2000 (артикли) — <https://onlinelibrary.wiley.com/doi/pdf/10.1111/0023-8333.00142>.

Беглость текста: Graham & Perin 2007 — <https://bridgestolearning2009.pbworks.com/f/graham&perin07.pdf>; Yu, Boers & Tremblay 2025 (реконструкция) — <https://journals.sagepub.com/doi/full/10.1177/13621688221117242>; Laufer & Girsai 2008 — <https://academic.oup.com/applij/article-abstract/29/4/694/183330>; Bjork & Bjork 2011 — <https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf>.

Обратная связь: Lyster & Saito 2010 — <http://kazuyasaito.net/SSLA2010.pdf>; Brown, Liu & Norouzian 2023 — <https://journals.sagepub.com/doi/abs/10.1177/13621688221147374>; Bitchener & Knoch 2010 — <https://www.researchgate.net/publication/249237898_The_Contribution_of_Written_Corrective_Feedback_to_Language_Development_A_Ten_Month_Investigation>; Kamelabad et al. 2025 (LLM, timing) — <https://erctpapers.com/papers/152-kamelabad-personalized-language-learning-with-an-llm-chatbot-effects-of-immediate-vs-delay.html>.

Артикли и времена у русскоязычных: Ionin, Ko & Wexler 2004 — <http://www.lingref.com/cpp/gasla/9/paper1626.pdf>; Pastushenkov & Cornell 2019 — <https://works.hcommons.org/records/pw04e-w0y27>; Umeda et al. 2019 — <https://journals.sagepub.com/doi/abs/10.1177/1362168817739648>; Master 1997 — <https://www.sciencedirect.com/science/article/abs/pii/S0346251X97000109>; Frontiers 2026 (Slavic aspect, eye-tracking) — <https://www.frontiersin.org/journals/language-sciences/articles/10.3389/flang.2026.1756472/full>; Bardovi-Harlig 2000 — <https://www.wiley.com/en-us/Tense+and+Aspect+in+Second+Language+Acquisition:+Form,+Meaning,+and+Use-p-9780631221494>.

LLM-тьюторы: scoping review 2026 — <https://doi.org/10.3390/educsci16081196>; arXiv 2025 (gains d = 0.28–0.33) — <https://arxiv.org/abs/2506.17006>.

## 7. Предлагаемый порядок внедрения (после решений по §5)

1. **Данные без кода**: инвентарь фреймов для big-five/core тем + `carries` + артикльные ярусы; расширение артикльных тем. Валидатор — новые проверки.
2. **Skills без кода**: стадийная обратная связь в `pedagogy.md` и `correct-learner-output`; раунды по 6 и RU→EN формы в `run-spaced-review`/`practice` в рамках существующих `controlled_production`-форм (guided_reply уже допускает это частично).
3. **`generation@3`**: формальные `drill_block`, `frame_recall`, `ru_to_en_sentence`, `minimal_pair`, `reconstruction`, `timed_writing`.
4. **Evidence + scoring**: `response_latency_ms`, ось `automaticity` отдельной policy.
5. **`scheduler@2`**: короткая лестница.
6. **`learner`**: preferences.

Шаги 1–2 дают ученику ощутимую смену метода уже на следующих занятиях; 3–6 делают её измеримой и детерминированной.

## 8. Разбиение работ и волны [PD-2026-09-22, «ок» ученика]

Типы: **Канон** (`wiki/`), **Скиллы** (`agent-skills/`), **Программа** (структура `curriculum/`), **Примеры** (авторский контент), **Код** (`src/`, `tests/`). Формат данных — `staging/handoff/2026-09-22-automaticity-authoring-spec.md`.

### А. Канон — opus-субагент, ревью владельца

| № | Что | Где |
|---|---|---|
| А1 | Термины frame, `carries`, drill block, ось automaticity, relearning ladder | `wiki/glossary.md` |
| А2 | Ось `automaticity` (§4), короткая лестница (§7), обратная связь по стадиям и timed-формы (§9.1) | `wiki/product/learning-model.md` |
| А3 | Фрейм как единица заучивания, `carries`, три яруса артиклей | `wiki/product/lexical-system.md` |
| А4 | Минимум фреймов на big-five/core тему, артикльные темы, вид данных «тексты для реконструкции» | `wiki/modules/curriculum.md` |
| А5 | `response_latency_ms`, drill-block attempt с per-item наблюдениями | `wiki/modules/evidence.md` |
| А6 | Reducer `automaticity@1` как отдельный policy kind | `wiki/modules/scoring.md` |
| А7 | `relearning_ladder_days` | `wiki/modules/scheduler.md` |
| А8 | Новые `step_type`, saturation по блокам, квота interleaving, профиль `drill` | `wiki/modules/control.md` |
| А9 | Preferences ученика | `wiki/modules/learner.md` |
| А10 | Команды CLI, PD-записи, фаза 3 в roadmap, OPEN на калибровку | `wiki/modules/cli.md`, `wiki/OPEN.md`, `wiki/roadmap.md` |

### Б. Скиллы — sonnet-субагент

| № | Что | Где |
|---|---|---|
| Б1 | Правило одной строкой до практики, объяснение в дебрифе; протокол подсказка → самоисправление → фраза → повтор; раунды по 6 | `run-english-session/references/pedagogy.md` |
| Б2 | Снять запрет «только исправленная строка»; объяснение по запросу или при повторе ×2 | `correct-learner-output` v3 |
| Б3 | Повторение начинается с RU→EN припоминания | `run-spaced-review` v3 |
| Б4 | Новый скилл дрилл-блока | `agent-skills/run-drill-block/` |
| Б5 | Фреймы раньше формы при вводе темы | `teach-english-topic` v5 |
| Б6 | Правила авторинга фреймов, `carries`, текстов | `maintain-english-curriculum` v2 |
| Б7 | Синхронизация и архив версий | `trainer skills sync` |

### В. Программа — sonnet-субагент (темы), владелец (policies)

| № | Что | Где |
|---|---|---|
| В1 | Восемь новых артикльных тем A1–B2 с полными телами и ≥ 6 минимальными парами | `curriculum/topics/*.yaml`, `curriculum/modules/*.yaml`, `tests/test_curriculum_topic_bodies.py` |
| В2 | `carries` на 45 существующих chunks с артиклями | `curriculum/lexicon/*.yaml` |
| В3 | Policies `scheduler-v2`, `generation-v3`, `control-v3`, `automaticity-v1`, `tunables-v2` | `curriculum/policies/` |
| В4 | Новая версия curriculum: validate → activate | CLI |

### Г. Примеры — рой haiku-субагентов (один файл на тему, без пересечений)

| № | Что | Объём | Где |
|---|---|---|---|
| Г1 | Фреймы для всех 66 тем grammar-engine (кроме артиклей): 20–30 на big-five/core, 12–20 на tail; каждый с meaning_ru, 2 примерами, контрастом и ловушкой | ≈ 1300 единиц | `curriculum/lexicon/frames-<topic-code>.yaml` |
| Г2 | Артикльные фреймы ярусов 1–2 для девяти артикльных тем | 120–150 единиц | `curriculum/lexicon/frames-articles.yaml` |
| Г3 | Минимальные пары как `contrasts` в артикльных и семи глагольных темах | ≥ 6 на тему | внутри тем |
| Г4 | Тексты для реконструкции: 2 на каждую из 75 grammar-тем | ≈ 150 текстов | `curriculum/texts/reconstruction/<topic-id>.yaml` |
| Г5 | Дрилл-предложения RU→EN заранее не пишутся: тьютор генерирует их из фреймов по `generation-v3`; банк растёт из сессий | — | exercise bank |

Пост-обработка владельца: advisory-links и `topic.lexicon` для всех фреймов из `frame_of` (детерминированный скрипт).

### Д. Код — opus/sonnet-субагенты, приёмка владельца

| № | Что | Где |
|---|---|---|
| Д1 | Validator/loader: `carries`, `frame_of`, минимум фреймов, вид данных «тексты» | `curriculum/validate.py`, `loader.py`, `tests/curriculum/` |
| Д2 | Evidence: `response_latency_ms`, drill-block attempt `items[]` с per-item objective check | `evidence/attempts.py`, `assessment.py` |
| Д3 | CLI: `attempt record --latency-ms`, `attempt record-block`, `learner preferences show/set` | `cli/app.py`, `cli/registry.py` |
| Д4 | Генерация/рендер форм `drill_block`, `frame_recall`, `ru_to_en_sentence`, `minimal_pair`, `reconstruction`, `timed_writing`; dedup банка | `lessons/rendering.py`, `policy.py`, `bank.py`, `preparation.py` |
| Д5 | Control: step_types в матрице, стоимость, saturation по блокам, interleaving со 2-го показа, профиль `drill` | `control/policy.py`, `compose.py`, `saturation.py`, `lesson_profiles.py` |
| Д6 | Scoring: reducer `automaticity@1`, `trainer status`, replay | `scoring/automaticity.py`, `engine.py`, `replay.py` |
| Д7 | Scheduler: короткая лестница | `scheduler/engine.py`, `policy.py` |
| Д8 | Learner: preferences как события, выдача в briefing | `learner/preferences.py`, `lessons/resume.py` |
| Д9 | Obsidian-проекция фреймов и оси автоматизма | `memory/` |
| Д10 | Obligations для нового скилла; арх-гейт, паритет registry | `curriculum/policies/obligations-v3.yaml`, `tests/architecture/` |

### Волны

1. **Волна 1 (без кода)**: А ∥ Б1–Б3 ∥ В1–В2 + Г3 ∥ Г1 (22 haiku) ∥ Г2 ∥ Г4 (10 haiku).
2. **Волна 2 (код, без пересечений)**: Д1 ∥ Д2+Д3 ∥ Д7.
3. **Волна 3**: Д4 ∥ Д5 ∥ Д6 ∥ Д8 (CLI-правки только у Д8).
4. **Волна 4**: В3–В4, Б4–Б7, Д9–Д10, пост-обработка ссылок, roadmap/journal.

Приёмка каждой волны владельцем: полный pytest, ruff, mypy strict, `trainer curriculum validate`, drift-check скиллов, `trainer scoring replay`, живой smoke-урок с дрилл-блоком.

### Д11. Облегчение протокола тьютора [PD-2026-09-22]

| № | Что | Где |
|---|---|---|
| Д11.1 | `attempt record` с observations оценивает в той же UoW; `--close-review` закрывает review-шаг в той же UoW; `finalize`/`review close` — fallback | `evidence/attempts.py`, `evidence/reviews.py`, `cli/app.py`, `cli/registry.py` |
| Д11.2 | Нормативный порядок шага: `next → rendered → show → record [--close-review]`; `peek` только после resume/conflict | `wiki/modules/lessons.md`, `evidence.md`, `cli.md`, `flows/session.md` |
| Д11.3 | `obligations@3`: delivery/correction protocol признают короткий путь | `curriculum/policies/obligations-v3.yaml`, `tests/audit` |
| Д11.4 | Скиллы: минимальный протокол, prepare как MAY, новые версии с архивами | `run-english-session`, `run-spaced-review`, `run-drill-block`, `teach-english-topic`, `coach-english-conversation`, `correct-learner-output` |
