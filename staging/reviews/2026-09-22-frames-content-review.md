# Content review — frames + reconstruction texts (2026-09-22)

> Ревью языкового качества контента, написанного роем 2026-09-22 (`curriculum/lexicon/frames-*.yaml`, `curriculum/texts/reconstruction/*.yaml`). Только чтение; структурная проверка `tools/check_authoring.py` уже пройдена и здесь не повторяется. Provenance: staging, не канон.

## Метод

- Выборка детерминированная: в каждом frames-файле позиции 1, 7, 13, 19 (если есть) → 171 фрейм A1–A2 (44 файла), 41 фрейм B1–B2 (14 файлов), 29 фреймов C1–C2 (8 файлов); `frames-articles.yaml` прочитан целиком (144 единицы). Итого проверено вручную ~385 фреймов из 1529 плюс 144/144 article-фреймов. Тексты: первый текст 12 A1–A2-файлов по алфавиту + оба текста `present-perfect-past-simple.choice`, `articles.second-mention`, `articles.fixed-time-expressions`, `hedging-stance.control` → 18 текстов из 14 файлов.
- Denominator-счётчики ниже (171/41/29) перепроверены отдельным скриптом после того, как параллельные проходы независимо насчитали близкие, но не идентичные числа (172/32/32) — расхождение было в подсчёте, не в самой выборке: почти все затронутые B1–B2/C1–C2 файлы фигурируют в списке дефектов ниже.
- Пять параллельных проходов (по одному на группу), каждое существенное утверждение выборочно сверено с исходными файлами; `frames-articles.yaml` дополнительно прочитан владельцем ревью полностью. Сверх выборки — корпусные подсчёты скриптом по всем 1529 фреймам (см. «Системные паттерны»).

## Вердикт

| Категория | Дефектных в выборке | Нужен fix pass |
|---|---|---|
| Frames A1–A2 | 35/171 (~20 %); ~30 из 44 файлов чистые, дефекты сконцентрированы в 5–6 файлах | Да — точечный + два файла целиком (транслит) |
| Frames B1–B2 | ~16/41 (~39 %) с реальными дефектами, ещё ~8 с мягкими (подмена подлежащего в примерах) | Да |
| Frames C1–C2 | 21/29 (~72 %) | Да — самый слабый блок: неверные `carries` по всему файлу, trap-пары не минимальные, примеры не содержат фрейм |
| Article frames (144) | 6/144 (~4 %) на уровне единиц; ни одного неверного правила про артикли; но `contrast.frame` в ~70/144 (~49 %) — не конкурирующий валидный фрейм, а дубль ошибочной формы из trap | Лёгкий: 6 точечных правок + переработка `contrast` в четырёх кластерах |
| Texts | 13/18 (~72 %), в основном средней тяжести (summary_ru, «приклеенные» наречия, одно PP+past marker) | Да |

Самое опасное (учит неверному правилу): B1–B2 `it-is-expected-that` (неграмматичная correction), `must-have` (meaning_ru «должны были» для must have + V3), `if-had-would-have` (contrast «If we had ___, we are now ___»), A1 `be-identity.i-am-a` (правило a/an перевёрнуто), `past-irregular-events.the-error-began` («third form began»), demonstratives ×4 и `quantifiers-basic.all-of-the` (валидный английский помечен ошибкой), C2 `so-did` / `nor-would` (trap чинит несуществующую ошибку).

## Дефекты

Формат: `file:item_id — проблема — правка`. Группы: (a) неверное грамматическое утверждение в trap/contrast/cause_ru; (b) неестественный/неверный английский; (c) неверные carries/frame_of/tier; (d) ошибки в русском; (e) тексты.

### (a) Неверные грамматические утверждения — 30

**B1–B2**
- frames-passive-reporting-structures.yaml:chunk.passive-reporting-structures.it-is-expected-that — correction сама неграмматична: `"It is expected that will improve."` (нет подлежащего) — `"It is expected that the response time will improve."`
- frames-modals-deduction-obligation.yaml:chunk.modals-deduction-obligation.must-have — meaning_ru `"мы должны были ..., вероятно ..."` смешивает долженствование и дедукцию; must have + V3 = только вывод о прошлом — `"мы, наверное/вероятно, … (вывод о прошлом)"`
- frames-third-conditional-retrospective.yaml:chunk.third-conditional-retrospective.if-had-would-have — contrast.frame `"If we had ___, we are now ___"` неграмматичен как mixed conditional — `"If we had ___, we would ___ now"`
- frames-third-conditional-retrospective.yaml:chunk.third-conditional-retrospective.if-not-past-perfect — contrast `"If we did not ___, ___"` + note `"это прошлый факт, не условный"`: форма условная (real past / 2nd), не «факт»; trap correction меняет глагол (`miss` → `failed`) и не объясняет вторую ошибку (`would restore` → `would have restored`) — сделать пару минимальной: `"If the backup had not failed, we would restore."` → `"…we would have restored."`, cause_ru про обе части
- frames-mixed-conditionals-consequences.yaml:chunk.mixed-conditionals-consequences.would-understand-if-had — trap объявляет ошибкой валидное `"We would better understand if they had provided."`; cause_ru `"word order: would + verb + adverb"` — ложное правило (наречие может стоять перед глаголом) — заменить trap на реальную ошибку (например `"We would understand better if they provided."` → `"…if they had provided."`, cause_ru про Past Perfect в if-части)
- frames-cleft-sentences-focus.yaml:chunk.cleft-sentences-focus.it-was-the-token — cause_ru `"после people используется 'who' или 'that', не 'which'; после things — 'that' или 'which'"` противоречит самому trap (token — thing, а which помечен ошибкой) — `"в cleft-конструкции It was X that … стандартно that; which здесь звучит неестественно"`
- frames-cleft-sentences-focus.yaml:chunk.cleft-sentences-focus.it-was-the-timeout — cause_ru `"'that' используется для things, не people"` неверно (that нормально и для людей) — `"who — для людей, that — для предметов и людей, which — только для предметов"`
- frames-modal-perfect-speculation.yaml:chunk.modal-perfect-speculation.must-have-sent — contrast note_ru `"less certain; expresses what ideally should have happened"` (английский + неверно: should have — не «менее уверенная» дедукция, а невыполненное ожидание) — `"should have — не предположение, а ожидание/упрёк: так должно было быть, но не случилось"`
- frames-second-conditional-hypothetical.yaml:chunk.second-conditional-hypothetical.if-she-were — cause_ru `"с she/he/it во втором условном пишется were, не was"` слишком абсолютно — `"формально were (subjunctive); was встречается в разговорной речи, но в письме лучше were"`
- frames-reported-speech-work-updates.yaml:said-that-would / agreed-would — cause_ru называет would `"условным"`; это backshift (future-in-the-past), не conditional — `"will → would при сдвиге времён (будущее в прошедшем)"`
- frames-reported-speech-work-updates.yaml:chunk.reported-speech-work-updates.asked-when-would — note_ru `"в reported speech используется when вместо прямого вопроса"` неточно (when есть и в прямом вопросе; суть — прямой порядок слов, без will/инверсии) — переписать

**A1–A2**
- frames-be-identity.yaml:chunk.be-identity.i-am-a — cause_ru `"перед согласным звуком нужен артикль a/an"` — правило перевёрнуто (engineer начинается с гласного) — `"перед гласным звуком нужен an (an engineer), перед согласным — a"`
- frames-past-irregular-events.yaml:chunk.past-irregular-events.the-error-began — slot_hint_ru `"begin — неправильный глагол, third form began"`; began — 2-я форма — `"2-я форма began (3-я — begun)"`
- frames-demonstratives-references.yaml:this-is / this-field-contains / this-type-of / this-document — trap объявляет ошибкой валидные `"It is the main issue"`, `"That field contains the ID"`, `"That type of error is common"`, `"That document explains the policy"` — убрать эти trap или заменить на реальную кальку (например пропуск глагола-связки `"This the main issue."`)
- frames-quantifiers-basic.yaml:chunk.quantifiers-basic.all-of-the — trap помечает верное `"all the data"` ошибкой, cause_ru сам признаёт `"both … возможны"` — заменить learner_form на `"all of data"`
- frames-time-dates.yaml:chunk.time-dates.today — trap-пустышка: learner_form == correction `"I will do it today."`, cause_ru `"правильная форма, но можно ошибиться…"` — удалить или дать реальную ошибку (`"I will do it in today."`)

**C1–C2**
- frames-ellipsis-substitution.yaml:chunk.ellipsis-substitution.so-did — learner_form `"The team adopted, and so to did partners."` не реальная ошибка; cause_ru `"после so did пропускаем частицу to"` про несуществующий инфинитив — trap `"…and partners so did."` → `"…and so did partners."`, cause_ru про инверсию вспомогательного после so
- frames-ellipsis-substitution.yaml:chunk.ellipsis-substitution.nor-would — trap ничего не чинит: `"nor would we be able to proceed"` → `"nor would we be able"` обе грамматичны; cause_ru `"упрощаем глагол после nor would"` — реальная ошибка: `"and we would not be able"` → `"nor would we be able"` (нет инверсии)
- frames-ellipsis-substitution.yaml:chunk.ellipsis-substitution.had-not-yet — meaning_ru `"… (past perfect с элизисом)"` — эллипсиса нет, обычный Past Perfect — убрать «с элизисом» (и см. (c))
- frames-hedging-stance-control.yaml:chunk.hedging-stance-control.it-seems-likely — cause_ru `"after 'seems likely' не нужно 'like' — то для 'seem like'…"` невнятно — `"не смешивать seem like (выглядеть как) и seems likely that (похоже, что): после likely сразу that"`
- frames-marked-word-order-rhetoric.yaml:chunk.marked-word-order-rhetoric.what-clause-was — correction меняет содержание вместо ошибки: `"...was unclear."` → `"...was the cause."` — `"What the inquiry did not establish was unclear."`
- frames-marked-word-order-rhetoric.yaml:chunk.marked-word-order-rhetoric.among-the-most — correction меняет число: `"...the correlation was."` → `"...were the correlations."` — `"Among the most significant findings was the correlation."`
- frames-participle-clauses-precision.yaml:chunk.participle-clauses-precision.having-completed — cause_ru `"добавь article перед существительным"`, но ни в learner_form, ни в correction артикль не появляется — переписать cause_ru под реальную разницу
- frames-syntactic-ambiguity-control.yaml:chunk.syntactic-ambiguity-control.that-vs-which — correction меняет смысл: `"the report which contained is out of date"` → `"the report that contained outdated data"` (потеряно сказуемое) — `"the report that contained outdated data is out of date."`
- frames-syntactic-ambiguity-control.yaml:chunk.syntactic-ambiguity-control.as-intended — trap не парный: `"as we expecting the results"` → `"as expected"` — `"as we are expecting"` → `"as expected"`

**Article frames**
- frames-articles.yaml:chunk.articles-the-unique-superlative-ordinal.the-only-x — note_ru `"only всегда идёт с the"` — есть `an only child`; trap верен, но формулировку смягчить: `"only в значении «единственный из набора» — с the; исключение: an only child"`
- frames-articles.yaml:the-first-time / the-last-time / the-weather / the-impact-of-x-on-x — «всегда the» слишком абсолютно (`a first draft`, `last week`, `weather permitting`, `an impact of…`); правила верны для контекста фрейма, но «всегда» → «в этом значении»
- frames-articles.yaml:chunk.articles-identity.i-have-a-question — contrast note_ru `"the почти не встречается: question как класс требует a, не конкретный предмет"` — невнятное объяснение — `"the — только если вопрос уже известен собеседнику (the question we discussed); при первом упоминании — a"`
- frames-articles.yaml:chunk.articles-generic-statements.a-x-should-always-x — trap не минимальный: `"Manager should always give clear feedback."` → `"A good manager should…"` (добавлено good) — correction `"A manager should always give clear feedback."`
- frames-articles.yaml:chunk.articles-fixed-time-expressions.twice-a-month — contrast.frame `"two times the month"` смешивает лексическую замену с ошибкой артикля — `"twice the month"`

### (b) Неестественный или неверный английский — 24

**B1–B2**
- frames-present-perfect-duration.yaml:chunk.present-perfect-duration.ive-not-seen — title `"I've not seen ___ since ___"` — в AmE естественно `"I haven't seen ___ since ___"` (собственный trap так и пишет); contrast `"I don't see since"` — обрывок
- frames-present-perfect-duration.yaml:chunk.present-perfect-duration.ive-worked-for — title `"I've worked on ___ for"` обрывается на предлоге, длительность не выделена слотом — `"I've worked on ___ for ___"`; contrast `"I work on this for"` — то же
- frames-present-perfect-duration.yaml:chunk.present-perfect-duration.weve-had-the-opportunity — фрейм и примеры неидиоматичны: `"We've had the opportunity for quite a while to fix this…"` — заменить фрейм на `"We've had ___ for ___"` / `"We've had the chance to ___ for ___"`
- frames-participle-clauses-compression.yaml:chunk.participle-clauses-compression.having-verified — contrast `"After the engineer verified the ___, the engineer ___"` — повтор подлежащего неестествен — `"After the engineer verified the ___, he ___"`; ex.2 `"Having reviewed the code, the developer…"` не содержит фрейм
- frames-participle-clauses-compression.yaml:chunk.participle-clauses-compression.considering-the-budget — ex.2 `"Considering the timeline, the simplified approach…"` не содержит фрейм; trap меняет `"the best option"` на `"the option"` помимо времени
- frames-cleft-sentences-focus.yaml:it-was-the-timeout, frames-passive-expanded-process.yaml:was-being-reviewed, frames-relative-clauses-specification.yaml:team-built, frames-modal-perfect-speculation.yaml:may-have-retried — второй пример подменяет фиксированное слово фрейма (`timeout` → `server overload`, `reviewed` → `executed`, `built` → `designed`, `worker` → `service`)

**A1–A2** (фрейм без слотов не воспроизведён в примерах)
- frames-there-is-are-systems.yaml:chunk.there-is-are-systems.is-theres — сам фрейм неграмматичен: `"Is there's a ___?"`, оба примера `"Is there's a copy…"`, `"Is there's enough time…"` — `"Is there a ___?"`
- frames-basic-word-order.yaml:chunk.basic-word-order.positive-no-do — title `"I write code"`, ex.2 `"I update the documentation regularly."` — `"I write code every single day."`
- frames-past-participle-forms.yaml:chunk.past-participle-forms.its-done — ни один пример не содержит `"It's done"` — ex.1 `"It's done — the report is ready for review."`
- frames-past-participle-forms.yaml:chunk.past-participle-forms.option-has-been-chosen — ex.2 `"This approach has been chosen…"` — `"The option has been chosen for its efficiency."`
- frames-future-forms-planning.yaml:the-meeting-is-tomorrow — ex.2 `"The standup is in an hour."` — `"The meeting is tomorrow, not today."`
- frames-future-forms-planning.yaml:when-does-the-feature-launch — ex.2 `"When does the meeting start?"` — `"When does the feature launch exactly?"`
- frames-do-questions.yaml:chunk.do-questions.what-does-he-need — оба примера без `he` — ex.1 `"What does he need to fix this?"`
- frames-here-is-are-presenting.yaml:chunk.here-is-are-presenting.password — ex.2 `"Here is your login credential…"` — `"Here is your password for the new account."`
- frames-sequencing-delivery.yaml:we-need-to-sequence-our-steps — ex.2 `"…sequence the deployment steps"` — `"We need to sequence our steps properly."`

**C1–C2**
- frames-ellipsis-substitution.yaml:chunk.ellipsis-substitution.nor-would — ex.2 `"The old code does not scale, nor would manual override."` — вспомогательный не согласован — `"…nor does manual override."`
- frames-ellipsis-substitution.yaml:chunk.ellipsis-substitution.as-expected — `"as expected in stress"` — `"as expected under stress"`
- frames-inversion-formal-emphasis.yaml:chunk.inversion-formal-emphasis.only-when — title `"Only when ___, should ___"` с лишней запятой, примеры без неё — `"Only when ___ should ___"`
- frames-hedging-stance-control.yaml:chunk.hedging-stance-control.generally-speaking — contrast.frame `"___"` пустой — `"As a rule, ___"`
- frames-nominalization-information-flow.yaml:chunk.nominalization-information-flow.the-introduction-of — ex.2 `"The new policy led to confusion among employees."` без фрейма — `"The introduction of the new policy led to confusion among employees."`
- frames-marked-word-order-rhetoric.yaml:chunk.marked-word-order-rhetoric.direct-object-fronting — ex.2 `"Such arguments we have already addressed."` теряет `we cannot` — `"Such arguments we cannot accept."`
- frames-participle-clauses-precision.yaml:chunk.participle-clauses-precision.adjusted-to — ex.2 `"…the roadmap shifted away."` (подмена `the plan`, нет дополнения) — `"…the plan shifted direction."`; `"the plan delayed rollout."` → `"the plan delayed the rollout."`, `"the plan delayed."` → `"the plan was delayed."`
- frames-syntactic-ambiguity-control.yaml:chunk.syntactic-ambiguity-control.the-latter — оба примера без `the former`, двухслотовый фрейм не показан — `"…; the former was riskier, the latter was preferred."`

**Article frames**
- frames-articles.yaml:chunk.articles-proper-nouns-geography.the-eu — ex.2 `"a trip around the EU"` — так не говорят (`around Europe`) — `"We're planning to hire in the EU next spring."`
- frames-articles.yaml:the-average-user-skips-the-tutorial / a-well-designed-interface-needs-no-manual / a-successful-product-solves-a-real-problem — вторые примеры подменяют существительное фрейма без слота (`shopper`, `form`, `recipe`) — либо дать слот в title, либо повторить фрейм

### (c) Неверные carries / frame_of / tier — 19

**B1–B2**
- frames-modals-deduction-obligation.yaml:chunk.modals-deduction-obligation.must-be-deduction — `carries: [structure:modal, tense:modal-perfect]`, но `"It must be ___"` — не modal perfect — убрать `tense:modal-perfect`
- frames-passive-reporting-structures.yaml:chunk.passive-reporting-structures.appears-to-have — `carries: [tense:passive]`, `"The commit appears to have ___"` — не пассив — заменить на `structure:hedging` (или оставить без tense)
- frames-passive-reporting-structures.yaml:chunk.passive-reporting-structures.is-assumed-to — `tense:reported-speech` для `"is assumed to be"` сомнителен — оставить `tense:passive`
- frames-mixed-conditionals-consequences.yaml:chunk.mixed-conditionals-consequences.might-not-have-if-had — чистый третий условный (прошлое → прошлое) в файле mixed — перенести в third-conditional или заменить на настоящий mixed

**A1–A2**
- frames-basic-questions-clarification.yaml:which-file — `structure:question-do`, но ex.2 `"Which file should I send?"` с модальным — оставить только `structure:question-wh`
- frames-here-is-are-presenting.yaml:password / api-key — `article:indefinite-first-mention` при `your password` / `your API key` (артикля нет) — убрать тег (в файле таких 7)
- frames-there-is-are-systems.yaml:are-there — `article:indefinite-first-mention` при `"Are there ___?"` — убрать или `article:zero-plural`
- frames-future-expressions-deadlines.yaml:by-friday — `article:fixed-expression` без артикля (в файле 4 таких) — убрать
- frames-time-dates.yaml:at-nine — `article:fixed-expression` для `"at ___"` (в файле 5 таких) — убрать
- frames-future-forms-planning.yaml:the-meeting-is-tomorrow — `tense:present-continuous` для `"The meeting is tomorrow"` — `tense:present-simple`

**C1–C2**
- frames-nominalization-information-flow.yaml:the-introduction-of / the-shift-to-reflected / the-improvement-in-validates / the-consequence-of-was (и ещё 13 — 17/26 в файле) — `article:definite-second-mention`, хотя the вызвано пост-модификатором of/to/in — `article:of-phrase` (в файле 0 использований)
- frames-ellipsis-substitution.yaml:had-not-yet — `structure:ellipsis` при обычном Past Perfect — `tense:past-perfect`
- frames-marked-word-order-rhetoric.yaml:direct-object-fronting — `structure:inversion` для object fronting (подлежащее перед глаголом) — убрать; ближайший тег отсутствует в словаре
- frames-syntactic-ambiguity-control.yaml:coordinate-parallel — `structure:reference` для сочинения с and — `structure:connector` (в файле все 25 единиц помечены `structure:reference`)
- frames-syntactic-ambiguity-control.yaml:as-intended — `structure:reference` — ближе `structure:ellipsis`

**Article frames**
- frames-articles.yaml:chunk.articles-abstract-and-of-phrases.the-technology-behind-x — `article:generic`, а собственный note_ru объясняет the конкретностью (`behind ___`) — `article:definite-shared-context`
- frames-articles.yaml:chunk.articles-institutional-places.i-need-to-stop-by-the-x — `article:institutional`, slot_hint говорит «конкретное известное место» — `article:definite-shared-context`

### (d) Ошибки в русском — 20

- frames-future-time-expressions.yaml — 3/4 единиц выборки (in-two-weeks, in-afternoon, by-end-day) с note_ru/cause_ru латиницей: `"in — ot segodnya; after — ot drugogo momenta"` — переписать кириллицей (в файле 38 полей без кириллицы)
- frames-prepositions-time.yaml — все 4 единицы выборки латиницей: `"on — dlya dney; at — dlya vremen"`, `"start i beginning — blizkikh znachen"` (ещё и обрывок) — переписать (44 поля)
- frames-here-is-are-presenting.yaml — `cause_ru: "chislo: is — singular, are — plural"` и note_ru целиком по-английски (50 полей без кириллицы — рекорд корпуса)
- frames-superlatives-selection.yaml — `"супелатив"` во всех 4 единицах выборки (21 вхождение в файле) — `"суперлатив"`
- frames-have-has-objects.yaml:i-dont-have — note_ru `"положение и отрицание"` — `"утверждение и отрицание"`
- frames-can-cant-ability-requests.yaml:what-cant-they — note_ru по-английски `"can't describes inability, don't describes absence of habit"` — перевести
- frames-relative-clauses-specification.yaml:solution-found / test-validates — note_ru `"both are equally correct"` / `"both are equally good"` (15 полей в файле)
- frames-third-conditional-retrospective.yaml:but-for-would-have — note_ru `"without is less formal"`
- frames-passive-reporting-structures.yaml:is-assumed-to — cause_ru `"нужна статья перед существительным"` — `"нужен артикль"`
- frames-modals-deduction-obligation.yaml:can-ability — note_ru `"краче"` — `"короче"`
- frames-passive-expanded-process.yaml:has-been-completed — meaning_ru `"___ уже был/была завершена"` — `"… уже завершён(а)"` (и `…` вместо `___` по спеке)
- frames-past-perfect-sequence.yaml:once-had — meaning_ru `"как только мы ___,  начало происходить ___"` — `"как только мы …, …"`
- frames-ellipsis-substitution.yaml:nor-would — meaning_ru `"и не бы …"` — `"и … тоже не (сделал бы)"`
- frames-ellipsis-substitution.yaml:had-not-yet — note_ru `"изненаду"` — `"неожиданность"`
- frames-inversion-formal-emphasis.yaml:nowhere-is-this-more — meaning_ru `"это не явнее, чем в …"` — `"нигде это не проявляется так ярко, как в …"`
- frames-syntactic-ambiguity-control.yaml:as-intended — meaning_ru `"… так как …"` (причина) при примерах с as = «как» — `"…, как и …"`
- frames-articles.yaml:to-the-doctors / to-the-dentists — note_ru `"даже хотя doctor's сама по себе притяжательная форма"` — `"хотя …"`

### (e) Тексты — 15 (13/18 текстов)

- grammar.present-perfect-past-simple.choice.yaml:text.recon.present-perfect-past-simple-choice.travel-plans — Present Perfect с маркером прошлого в файле, который учит именно этому выбору: `"have already booked the hotel for our trip online last week successfully"` — `"already booked the hotel for our trip online last week"` (или убрать `last week`)
- grammar.articles.second-mention.yaml:text.recon.articles-second-mention.morning-discovery — пара a→the не сходится: `"There is also a problem with the door. The door needs repair."` (`a door` в тексте нет) — `"There is also a door with a problem. The door needs repair."`; сбой времени `"The meeting is with my manager."` → `"The meeting was with my manager."`
- grammar.articles.the-unique-superlative-ordinal.yaml:text.recon.articles-the-unique-superlative-ordinal.company-hierarchy — `"The first quarter was the most successful year"` — `"…the most successful quarter"`
- grammar.basic-word-order.yaml:text.recon.basic-word-order.daily-tasks — `"today morning"` — `"this morning"`
- grammar.connectors.cause-contrast.yaml:text.recon.connectors-cause-contrast.production-incident — круговая причина: `"We notified the client because they reported the issue first."` — `"…because we noticed the issue before they did."`
- grammar.articles.institutional-places.yaml:text.recon.articles-institutional-places.weekly-schedule — `"the clinic at the building"` — `"the clinic in the building"`
- grammar.articles.identity.yaml:text.recon.articles-identity.project-roles — `"The goal is clear always."`, `"The team is ready always."` — `"…is always clear/ready"`
- grammar.present-perfect-past-simple.choice.yaml:project-status — `"as planned exactly"`, `"yesterday afternoon specifically"` — `"exactly as planned"`, убрать `specifically`; travel-plans — `"on schedule exactly"` → `"exactly on schedule"`
- grammar.articles.fixed-time-expressions.yaml:daily-schedule — summary_ru `"фокусная работа в пятницу"` при `"once a week on Tuesday"` — `"по вторникам"`
- grammar.articles.fixed-time-expressions.yaml:weekly-routine — summary_ru `"вечер спи дольше"` при `"On the weekend I usually sleep longer"` — `"по выходным сплю дольше"`
- grammar.articles.second-mention.yaml:project-description и morning-discovery; grammar.present-perfect-past-simple.choice.yaml:оба — summary_ru описывает правило, а не содержание: `"Использование неопределенного артикля a при первом упоминании…"`, `"Статус проекта, демонстрирующий выбор между Present Perfect и Past Simple."` — переписать как пересказ содержания
- grammar.hedging-stance.control.yaml:educational-technology — summary_ru начинается с второстепенной детали (`"связь между интерактивным обучением и удержанием знаний"`), а текст открывается `"educational technology and student engagement"` — переставить
- grammar.can-cant.ability-requests.yaml:team-chat — summary_ru `"Может открыть папку, не нашла отчет"` меняет лицо/время/род относительно `"Can you open the shared folder? I can't find…"` — `"Можешь открыть папку? Не могу найти отчёт."`
- Чистые в выборке: word_count совпал во всех 18; все target_spans найдены дословно; артикли в самих текстах верны везде, кроме `at the building`.

## Системные паттерны (для file-wide fix pass)

1. **RU-поля без кириллицы: 257 полей в 29 файлах** (скрипт по всем 1529 фреймам). Два вида: латинская транслитерация (`frames-prepositions-time` 44, `frames-future-time-expressions` 38, частично `frames-here-is-are-presenting`) и note_ru/cause_ru целиком по-английски (`frames-here-is-are-presenting` 50, `frames-present-continuous-status` 22, `frames-reference-cohesion` 15, `frames-relative-clauses-specification` 15, `frames-present-simple-continuous-choice` 14, `frames-time-dates` 8). Нарушает спеку §0.6. Добавить в checker правило «`*_ru` содержит кириллицу».
2. **Пример не содержит фрейм дословно: 497/1529 (32 %)**; checker это не проверяет (только длину и отсутствие кириллицы). Большинство — подмена подлежащего/местоимения (`I went to ___` → `She went to the bank`, мягко), но заметная доля — подмена фиксированного слова или выпадение ядра (`It's done`, `the introduction of`, `we cannot`, `the former`). Худшие файлы: past-irregular-basics 25/25, past-simple-negatives-questions 25/25, past-simple-events 24/25, modals-deduction-obligation 21/22. Правило для checker: title с `___` → `.+?`, оба примера должны матчиться (регистр не важен); для фреймов без слота — как минимум один пример дословно.
3. **`contrast.frame` = ошибочная форма из trap, а не конкурирующий валидный фрейм.** В `frames-articles.yaml` так устроено ~70/144 (49 %): почти весь кластер fixed-time (16/22), proper-nouns (14/14), abstract-of (11/14), institutional (9/16), superlative (10/16). Для tier-1 идиом это отчасти неизбежно, но там, где валидная пара есть, она потеряна: `Germany` vs `the Netherlands`, `education` vs `the education we received`, `the number of` vs `a number of` (последнее сделано правильно — образец). Та же подмена в A1–A2 (`frames-basic-word-order` OSV, `frames-past-simple-negatives-questions` `"Did you have tested"`) и `frames-present-perfect-past-simple-choice`, где `contrast.frame` вообще содержит предложение-объяснение (`"I sent it yesterday is only Past Simple"`, все 19 единиц).
4. **Trap объявляет ошибкой валидный английский** (demonstratives ×4, `all the data`, `would better understand`, `If she was`) или **не чинит ничего**: 5 trap с learner_form == correction (basic-questions-clarification.where-is, mixed-conditionals.would-still-use-if-not-were, past-simple-negatives-questions.where-did-you-put, time-dates.today, time-dates.for-two-days). Это учит, что верное — неверно. Правило для checker: learner_form ≠ correction.
5. **Trap-пары не минимальны**: correction меняет подлежащее, число, глагол или содержание помимо ошибки (C1–C2 what-clause-was, among-the-most, that-vs-which, as-intended; B2 if-not-past-perfect, considering-the-budget; articles a-x-should-always-x). cause_ru тогда описывает не ту разницу, что показана (`having-completed`, `nor-would`).
6. **`carries` проставлены по теме файла, а не по конструкции**: 17/26 nominalization → `article:definite-second-mention` вместо `article:of-phrase` (0 использований); 25/25 syntactic-ambiguity → `structure:reference`; `tense:modal-perfect` на `It must be`, `tense:passive` на `appears to have`, `tense:present-continuous` на `The meeting is tomorrow`. Плюс 21 не-articles единица с `article:*` при отсутствии a/an/the в title (here-is-are-presenting 7, time-dates 5, future-expressions-deadlines 4, nouns-singular-plural 2, there-is-are-systems 2). В `frames-articles.yaml` 24 таких — это нулевой артикль в идиомах (`at night`, `go to work`), допустимо, но стоит зафиксировать конвенцию в спеке.
7. **Абсолютные формулировки «всегда/never»** в note_ru/cause_ru там, где есть известные исключения (`only`, `first`, `last`, `weather`, `were` vs `was`). В article-файле правила верны для контекста фрейма; правка — «в этом значении» вместо «всегда».
8. **Тексты: «приклеенные» наречия в конце предложения** (`exactly`, `specifically`, `always`) — 5 случаев в 3 файлах; regex-проход по корпусу текстов на `\b(exactly|specifically|always)\.` . И **summary_ru как описание правила вместо пересказа** — 4/18; проверить все 150 текстов grep'ом по «артикл|Present Perfect|Past Simple» в summary_ru.
9. **Тексты A1–A2 — чек-лист паттернов без связного сюжета** (articles.identity.project-roles, the-unique-superlative-ordinal.company-hierarchy). Образец нормы в том же наборе: institutional-places.weekly-schedule, be.identity.team-intro, оба hedging-stance.control.
10. **Смешанный алфавит в RU-полях** (`"clause варианта более живой"`, `"word order: would + verb + adverb"`, `"passive более непредвзято"`) — не ошибка, но терминологию (Present Perfect, relative clause и т.п.) стоит либо оставить как имена собственные, либо глоссировать один раз.

## Что не найдено

- Британских написаний нет ни в одной группе (`at the weekend` / `in hospital` встречаются только как помеченные BrE-контрасты).
- В `frames-articles.yaml` ни одного неверного правила про артикли; AmE/BrE, аббревиатуры (NASA / the FBI), реки/горы/океаны, the number of / a number of — всё верно.
- Дубликатов и калек в самих фреймах A1–A2 почти нет: ~30 из 44 файлов в выборке без дефектов.
