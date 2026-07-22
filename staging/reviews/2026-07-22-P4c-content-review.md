# P.4c content review — idiom CEFR spread & casual/slang boundary (OPEN-31)

Date: 2026-07-22
Reviewer role: EFL lexicographer (content review, read-only)
Scope: `curriculum/lexicon/*.yaml` (excluding `_`-prefixed). Two defects flagged at P.4c acceptance.
Status: **PROPOSAL** — advisory only. Nothing edited. The owner decides and applies via the `maintain-english-curriculum` workflow, then re-runs validators.

> CEFR here is **authored pedagogical metadata**, not a corpus certificate. Every level below is a teaching-difficulty judgement grounded in **opacity + frequency + register + cultural specificity** (per `wiki/product/lexical-system.md` §1a). Where I am genuinely unsure I write "keep / low confidence" rather than invent a level. No frequencies are fabricated — none of these units carries corpus frequency by design (multi-word units are uncovered, §1 "частота есть не у всех единиц").

---

## 1. Summary & distributions

**Defect 1 — idiom CEFR.** All **120** `type: idiom` units are authored `cefr: A2`; the field stopped differentiating. I propose moving **88** off A2: **42 → B1**, **43 → B2**, **3 → C1**. **32 stay A2.** So 74 remain A2/B1 (the transparent/functional core) and 46 rise to B2/C1 (the vivid, figurative, or culturally specific idioms). C1 is deliberately sparse: this is an *everyday* idiom inventory, so truly advanced/literary idioms are largely absent — inflating C1 would be mechanical, not honest.

| CEFR | Current | Proposed |
|---|---:|---:|
| A2 | 120 | 32 |
| B1 | 0 | 42 |
| B2 | 0 | 43 |
| C1 | 0 | 3 |
| **Total** | **120** | **120** |

**Defect 2 — casual/slang boundary.** **50** units carry `register: slang`. I propose **re-registering all 50** off `slang`: **42 → casual**, **8 → neutral**, **0 kept**. Under the reserved definition (`slang` = genuinely slangy / in-group / **volatile**), none of the current 50 qualifies — they live in `slang-stable.yaml` and the everyday phrasal-verb / idiom files, i.e. they were *selected for stability*, which is precisely the opposite of what makes something slang. The category legitimately empties. See §3 note on the resulting content gap.

Register across the **whole 1112-unit inventory** (current → proposed, applying only the 50 changes):

| Register | Current | Proposed |
|---|---:|---:|
| formal | 209 | 209 |
| neutral | 715 | 723 |
| casual | 138 | 180 |
| slang | 50 | 0 |
| **Total** | **1112** | **1112** |

**Overall confidence:** high on the *direction* of both moves and on the slang→casual/neutral split; medium on exact CEFR band for the ~15 B1/B2 borderline idioms (flagged inline). The A2 keepers and the clearly-figurative B2 set are high-confidence.

---

## 2. Idiom CEFR reclassification (all 120)

Ordered as authored (`idioms-everyday-1.yaml` then `idioms-everyday-2.yaml`). All rows are `type: idiom`, current `cefr: A2`.

### idioms-everyday-1.yaml

| id | current | proposed | rationale |
|---|---|---|---|
| idiom.call-it-a-day | A2 | B1 | opaque but very high-freq work/casual idiom; standard intermediate teaching |
| idiom.no-big-deal | A2 | B1 | ubiquitous reassurance; opaque yet meaning quickly graspable |
| idiom.off-the-top-of-my-head | A2 | B2 | long, fully figurative phrase; decoding is non-trivial |
| idiom.keep-an-eye-on | A2 | B1 | very common; partly decodable via "eye = attention" |
| idiom.cut-corners | A2 | B2 | figurative (quality/ethics); not recoverable from the words |
| idiom.piece-of-cake | A2 | B1 | iconic idiom taught early despite opacity; very high-freq |
| idiom.hit-the-road | A2 | B1 | common casual "leave" idiom; frequent, short |
| idiom.get-the-hang-of | A2 | B1 | common learner-facing idiom; high-freq casual |
| idiom.touch-base | A2 | B2 | business-register figurative idiom; register-marked |
| idiom.on-the-same-page | A2 | B1 | very common collaboration idiom; semi-graspable metaphor |
| idiom.under-the-weather | A2 | B2 | classic non-decodable health idiom (canonically upper-int.) |
| idiom.a-heads-up | A2 | B1 | short, high-freq casual/business idiom |
| idiom.for-the-time-being | A2 | B1 | formal connective; opaque but decodable with effort |
| idiom.on-the-fly | A2 | B2 | figurative, register-marked (tech/casual); mid-freq |
| idiom.make-ends-meet | A2 | B2 | fixed financial idiom; fully figurative |
| idiom.bite-the-bullet | A2 | B2 | vivid opaque idiom, obscure origin; mid everyday freq |
| idiom.once-in-a-blue-moon | A2 | C1 | culturally specific ("blue moon"), low everyday freq, fully figurative |
| idiom.break-the-ice | A2 | B2 | figurative social idiom; canonically upper-intermediate |
| idiom.cost-an-arm-and-a-leg | A2 | B2 | hyperbolic figurative idiom; not decodable |
| idiom.better-late-than-never | A2 | B1 | common proverb; semi-transparent |
| idiom.easier-said-than-done | A2 | B1 | common proverb; semi-transparent |
| idiom.so-far-so-good | A2 | B1 | high-freq fixed casual phrase; mildly opaque |
| idiom.fingers-crossed | A2 | B1 | common casual gesture-idiom; frequent |
| idiom.out-of-the-blue | A2 | B2 | figurative "suddenly"; not decodable |
| idiom.in-hot-water | A2 | B2 | figurative "in trouble"; mid-freq |
| idiom.not-my-cup-of-tea | A2 | B2 | figurative, culturally British-origin; register-marked |
| idiom.the-last-straw | A2 | B2 | figurative (proverb origin); not recoverable |
| idiom.go-the-extra-mile | A2 | B2 | figurative motivational idiom; mid-freq |
| idiom.miss-the-boat | A2 | B2 | figurative "miss the opportunity" |
| idiom.take-it-easy | A2 | B1 | very common casual formula; opaque but high-freq |
| idiom.hang-in-there | A2 | B1 | common casual encouragement |
| idiom.give-me-a-break | A2 | B2 | idiomatic/sarcastic "stop it" sense is tone-loaded & opaque |
| idiom.take-your-time | A2 | A2 | near-transparent core politeness formula; very high-freq |
| idiom.its-up-to-you | A2 | A2 | elementary, high-freq; meaning largely recoverable |
| idiom.long-story-short | A2 | B1 | common discourse marker; opaque-ish |
| idiom.to-be-honest | A2 | A2 | high-freq discourse marker; largely transparent |
| idiom.by-the-way | A2 | A2 | core A2 discourse marker |
| idiom.in-the-long-run | A2 | B1 | common connective; mild opacity |
| idiom.sooner-or-later | A2 | A2 | semi-transparent, high-freq (already `semi_opaque`) |
| idiom.first-things-first | A2 | B1 | common fixed phrase; mildly opaque |
| idiom.one-step-at-a-time | A2 | B1 | semi-transparent; common (medium confidence, could be A2) |
| idiom.out-of-order | A2 | A2 | high-freq practical sign-phrase; elementary (low conf, could be B1) |
| idiom.in-a-hurry | A2 | A2 | semi-transparent, high-freq |
| idiom.in-no-time | A2 | B1 | figurative "very fast"; mildly opaque |
| idiom.right-away | A2 | A2 | semi-transparent, core |
| idiom.around-the-corner | A2 | B1 | figurative "soon/near"; common |
| idiom.on-the-way | A2 | A2 | semi-transparent, core |
| idiom.in-the-middle-of-nowhere | A2 | B2 | figurative, register-marked casual |
| idiom.all-of-a-sudden | A2 | B1 | common connective; mildly opaque |
| idiom.in-the-same-boat | A2 | B2 | figurative "same situation" |

### idioms-everyday-2.yaml

| id | current | proposed | rationale |
|---|---|---|---|
| idiom.a-change-of-heart | A2 | B2 | figurative; lower everyday freq |
| idiom.have-second-thoughts | A2 | B1 | common; semi-decodable |
| idiom.learn-the-hard-way | A2 | B1 | common; largely decodable |
| idiom.sleep-on-it | A2 | B2 | figurative "decide later"; opaque |
| idiom.take-it-or-leave-it | A2 | B2 | idiomatic ultimatum; tone-loaded |
| idiom.you-name-it | A2 | B2 | idiomatic "anything"; opaque |
| idiom.that-rings-a-bell | A2 | B2 | figurative "sounds familiar" |
| idiom.it-slipped-my-mind | A2 | B1 | common; semi-decodable figurative |
| idiom.my-hands-are-tied | A2 | B2 | figurative "unable to act" |
| idiom.i-have-no-clue | A2 | B1 | common casual; "clue" aids decoding |
| idiom.beats-me | A2 | B2 | opaque casual exclamation; tone-marked (also re-register, §3) |
| idiom.fair-and-square | A2 | B2 | fixed idiom; culturally flavored, non-decodable |
| idiom.by-accident | A2 | A2 | semi-transparent, core |
| idiom.on-purpose | A2 | A2 | semi-transparent, core |
| idiom.out-of-luck | A2 | B1 | figurative but decodable-ish; common |
| idiom.a-waste-of-time | A2 | A2 | semi-transparent, high-freq |
| idiom.worth-a-try | A2 | A2 | semi-transparent, common |
| idiom.safe-and-sound | A2 | B1 | fixed binomial; common but idiomatic |
| idiom.back-to-square-one | A2 | B2 | figurative (board-game origin) |
| idiom.from-scratch | A2 | B1 | opaque but high-freq; standard intermediate |
| idiom.the-sooner-the-better | A2 | A2 | semi-transparent, common |
| idiom.no-wonder | A2 | A2 | common discourse phrase; semi-transparent |
| idiom.thats-the-point | A2 | A2 | semi-transparent discourse phrase |
| idiom.thats-not-the-point | A2 | A2 | semi-transparent discourse phrase |
| idiom.when-it-comes-to | A2 | B1 | common connective; mildly opaque |
| idiom.as-far-as-i-know | A2 | B1 | common hedging connective |
| idiom.for-good | A2 | B2 | opaque "permanently"; non-obvious (medium confidence) |
| idiom.in-advance | A2 | A2 | semi-transparent, core |
| idiom.at-least | A2 | A2 | core A2 |
| idiom.at-first | A2 | A2 | core A2 |
| idiom.at-last | A2 | A2 | core A2/B1; common (low conf, could be B1) |
| idiom.in-charge-of | A2 | B1 | complex preposition; semi-decodable, common in work talk |
| idiom.in-favor-of | A2 | B1 | formal complex preposition |
| idiom.in-common | A2 | A2 | semi-transparent, common |
| idiom.on-my-own | A2 | A2 | very common; largely recoverable |
| idiom.in-person | A2 | A2 | semi-transparent, common |
| idiom.in-a-nutshell | A2 | B2 | figurative, register-marked discourse idiom |
| idiom.word-for-word | A2 | B1 | semi-transparent; mid-freq |
| idiom.face-to-face | A2 | A2 | semi-transparent, common |
| idiom.side-by-side | A2 | A2 | semi-transparent, common |
| idiom.little-by-little | A2 | B1 | semi-transparent; lower freq than step-by-step |
| idiom.step-by-step | A2 | A2 | semi-transparent, common |
| idiom.day-by-day | A2 | B1 | semi-transparent; less frequent variant |
| idiom.all-over-the-place | A2 | B2 | figurative casual; register-marked |
| idiom.up-in-the-air | A2 | B2 | figurative "undecided" |
| idiom.out-of-hand | A2 | B2 | figurative, two opaque senses |
| idiom.on-edge | A2 | B2 | figurative "tense"; not decodable |
| idiom.at-ease | A2 | B2 | opaque, register-marked (formal/military echo) |
| idiom.in-a-bad-mood | A2 | A2 | semi-transparent, common |
| idiom.in-a-good-mood | A2 | A2 | semi-transparent, common |
| idiom.fed-up-with | A2 | B1 | common casual; opaque but high-freq |
| idiom.sick-and-tired-of | A2 | B1 | common casual emphatic; opaque but high-freq |
| idiom.over-the-moon | A2 | B2 | figurative "delighted"; British-origin, register-marked |
| idiom.down-in-the-dumps | A2 | C1 | opaque, lower-freq, mildly dated register |
| idiom.a-pain-in-the-neck | A2 | B2 | figurative "annoyance" |
| idiom.have-a-sweet-tooth | A2 | B2 | figurative; fully non-decodable |
| idiom.grab-a-bite | A2 | B1 | common casual; semi-decodable |
| idiom.help-yourself | A2 | A2 | very common hospitality formula; elementary |
| idiom.feel-at-home | A2 | A2 | common; largely recoverable |
| idiom.make-yourself-at-home | A2 | B1 | common hospitality idiom; slightly opaque |
| idiom.be-my-guest | A2 | B2 | idiomatic "go ahead" permission sense is tone-marked & opaque |
| idiom.after-you | A2 | B1 | polite formula; non-obvious to decode ("you go first") |
| idiom.here-you-go | A2 | A2 | extremely common service formula; elementary |
| idiom.there-you-go | A2 | B1 | multi-sense casual (agreement / handing over); opaque |
| idiom.that-will-do | A2 | B2 | idiomatic "that's enough"; opaque, register-marked |
| idiom.suit-yourself | A2 | B2 | tone-loaded dismissive idiom; opaque |
| idiom.the-more-the-merrier | A2 | C1 | proverb-like, culturally specific, lower dialogue freq |
| idiom.get-cold-feet | A2 | B2 | figurative "lose one's nerve"; classic upper-int idiom |
| idiom.spill-the-beans | A2 | B2 | figurative "reveal a secret"; classic upper-int idiom |
| idiom.pull-someones-leg | A2 | B2 | figurative "tease"; classic upper-int idiom |

**Idiom move totals:** A2→B1 = 42, A2→B2 = 43, A2→C1 = 3, stay A2 = 32.

---

## 3. `register: slang` re-registration (all 50)

Reserved definition applied: keep `slang` only for genuinely slangy / in-group / **volatile** items; ordinary informal → `casual`; register-neutral → `neutral`.

### Register-neutral phrasal verbs & one adjective → `neutral` (8)

| id | title | current | proposed | rationale |
|---|---|---|---|---|
| phrasal-verb.show-up | show up | slang | neutral | register-neutral; appears unremarkably in journalism/formal writing |
| phrasal-verb.catch-up | catch up | slang | neutral | register-neutral ("catch up on work / with a friend") |
| phrasal-verb.come-over | come over | slang | neutral | register-neutral ("come over for dinner") |
| phrasal-verb.sleep-in | sleep in | slang | neutral | register-neutral; plain everyday phrasal verb |
| phrasal-verb.hold-on | hold on | slang | neutral | register-neutral ("hold on a second") |
| phrasal-verb.pull-off | pull off | slang | neutral | register-neutral; standard in sports/business reporting (low conf, could be casual) |
| phrasal-verb.bump-into | bump into | slang | neutral | mildly informal but standard everyday; not slangy (low conf, could be casual) |
| slang.weird | weird | slang | neutral | clearest single mismatch: a plain standard adjective, not informal at all |

### Ordinary informal → `casual` (42)

| id | title | current | proposed | rationale |
|---|---|---|---|---|
| phrasal-verb.hang-out | hang out | slang | casual | mainstream informal "spend time together"; not in-group |
| phrasal-verb.mess-up | mess up | slang | casual | ordinary informal "make an error"; universally understood |
| phrasal-verb.screw-up | screw up | slang | casual | informal, mildly crude but mainstream; keep `context_dependent` policy |
| phrasal-verb.freak-out | freak out | slang | casual | expressive informal "panic"; standard colloquial |
| phrasal-verb.chill-out | chill out | slang | casual | colloquial "relax"; widely understood, stable |
| phrasal-verb.splash-out | splash out | slang | casual | informal "spend freely"; (BrE-leaning) not slang |
| phrasal-verb.tag-along | tag along | slang | casual | friendly informal "accompany"; not in-group |
| idiom.beats-me | beats me | slang | casual | informal fixed exclamation; stable, cross-generational — not slang (also CEFR B2, §2) |
| slang.stuff | stuff | slang | casual | ubiquitous informal "things"; mildly colloquial, not slang |
| slang.guys | guys | slang | casual | ordinary informal address to a group |
| slang.cool | cool | slang | casual | decades-stable informal "good"; no longer in-group |
| slang.awesome | awesome | slang | casual | mainstream informal intensifier |
| slang.broke | broke | slang | casual | informal "without money"; universal, stable |
| slang.chill | chill | slang | casual | colloquial "relax/calm"; mainstream (adj. sense slightly slangier — low conf) |
| slang.pretty-degree | pretty | slang | casual | colloquial downtoner ("pretty good"); standard informal, not slang |
| slang.bucks | bucks | slang | casual | entrenched informal "dollars"; stable, mainstream |
| slang.buddy | buddy | slang | casual | informal term of address; stable |
| slang.kiddo | kiddo | slang | casual | affectionate informal address; stable |
| slang.creepy | creepy | slang | casual | informal adjective, near-neutral ("a creepy movie") (low conf, could be neutral) |
| slang.gross | gross | slang | casual | informal "disgusting"; universal |
| slang.cheesy | cheesy | slang | casual | informal "overly sentimental"; mainstream |
| slang.lame | lame | slang | casual | informal "poor/unconvincing"; mainstream (note: some sensitivity around origin) |
| slang.nuts | nuts | slang | casual | informal "unreasonable/crazy"; mainstream |
| slang.cop | cop | slang | casual | informal "police officer"; mainstream, stable |
| slang.comfy | comfy | slang | casual | informal diminutive of comfortable |
| slang.gonna | gonna | slang | casual | casual reduction of "going to"; phonetic, not slang |
| slang.wanna | wanna | slang | casual | casual reduction of "want to" |
| slang.gotta | gotta | slang | casual | casual reduction of "have got to" |
| slang.kinda | kinda | slang | casual | casual reduction of "kind of" |
| slang.sorta | sorta | slang | casual | casual reduction of "sort of" |
| slang.ripped-off | ripped off | slang | casual | informal "overcharged"; stable idiom |
| slang.a-bunch-of | a bunch of | slang | casual | informal "many"; near-neutral quantifier (low conf, could be neutral) |
| slang.dunno | dunno | slang | casual | casual reduction of "don't know" |
| slang.lemme | lemme | slang | casual | casual reduction of "let me" |
| slang.gimme | gimme | slang | casual | casual reduction of "give me" |
| slang.gotta-go | gotta go | slang | casual | casual closing formula "I have to leave" |
| slang.no-biggie | no biggie | slang | casual | informal "not a problem"; stable |
| slang.couch-potato | couch potato | slang | casual | informal idiom; stable, well-established |
| slang.my-folks | my folks | slang | casual | informal "my parents/family"; stable |
| slang.hang-on | hang on | slang | casual | informal "please wait"; near-neutral |
| slang.come-on | come on | slang | casual | informal interjection; universal |
| slang.not-gonna-lie | not gonna lie | slang | casual | most current/register-marked of the set, but now mainstream casual — not in-group |

**Note on the emptied category.** Recommending 0 keeps is not mechanical: the inventory lives in `slang-stable.yaml` and everyday phrasal-verb files, deliberately chosen for stability. By the reserved definition, "stable + mainstream" = `casual`, so the whole set moves. The consequence is that **the current lexicon has no genuine `slang`** — items a real slang tier would hold (volatile/in-group, e.g. *sus, rizz, no cap, lowkey, ghost (someone), flex, based*) are simply absent. If the owner wants a live `slang` register, that is a **content gap to fill** (through the maintain-workflow, with `volatility: changing` + currency lifecycle per lexical-system §3b), not something to satisfy by leaving mislabeled stable items in place. The nearest slang-adjacent items in the current set are the lexical substitutions (`bucks, cop, buddy, lame, nuts, no-biggie, not-gonna-lie`); if the owner prefers a non-empty tier, those are the only defensible candidates — but I still lean `casual` because all are stable and mainstream.

---

## 4. Incidental mismatches noticed in passing

1. **`slang.weird` is the single clearest error** — a fully standard neutral adjective marked `slang`. Recommended `neutral` above; called out separately because it is not merely over-strong (slang vs casual) but categorically wrong.
2. **Idiom `register` is applied inconsistently** across the 119 non-slang idioms. Semantically parallel opaque idioms are split arbitrarily between `casual` and `neutral` — e.g. `piece-of-cake`/`no-big-deal` are `casual` while `cut-corners`/`keep-an-eye-on`/`touch-base` are `neutral`; `hit-the-road` `casual` vs `make-ends-meet` `neutral`. This is not a hard validation error (both are legal), but a consistency pass would help: reserve `casual` for idioms that actually signal relaxed register (`hit the road`, `not my cup of tea`, `no big deal`) and `neutral` for register-neutral ones (`make ends meet`, `keep an eye on`, `in charge of`). Out of scope to enumerate fully here; flag for a follow-up.
3. **`phrasal-verb.hurry-up` marked `casual`** is arguably `neutral` ("please hurry up" is unremarkable in neutral register). Minor; `stay-over` (`casual`) is fine. The 84 `register: neutral` phrasal verbs were spot-checked and show **no** reverse mismatches — none is secretly casual/slang.
4. **`usage_policy` follows register.** If the owner accepts the 42 slang→casual moves, note that `casual`/`context_dependent` pairing stays valid, but several new-`neutral` phrasal verbs (`show-up`, `catch-up`, `come-over`, `sleep-in`, `hold-on`, `bump-into`, `pull-off`) currently carry `usage_policy: safe_to_use` + `communities`/`neutral_equivalent` informal metadata that reads oddly on a `neutral` unit. Not blocking — but the maintain-workflow should decide whether to drop the informal-only fields when demoting register to `neutral`. (`weird` likewise carries `communities`/`neutral_equivalent` that a neutral adjective does not need.)
5. **File naming.** With the category emptied, `slang-stable.yaml` is really a *stable-colloquial* file. Renaming is out of scope and not recommended as part of this review, but worth noting for coherence.

---

## 5. Reproducible counting snippet

Run from repo root with the project venv (`.venv/Scripts/python.exe`). It (a) regenerates the current distributions and (b) applies the proposal maps below to print the proposed distributions, so the owner can verify every number in §1–§3 without trusting this document.

```python
import yaml, glob, os
from collections import Counter

FILES = [f for f in glob.glob("curriculum/lexicon/*.yaml")
         if not os.path.basename(f).startswith("_")]

# --- Proposal maps (this review) ---
IDIOM_CEFR = {
    # A2 -> B1
    "idiom.call-it-a-day":"B1","idiom.no-big-deal":"B1","idiom.keep-an-eye-on":"B1",
    "idiom.piece-of-cake":"B1","idiom.hit-the-road":"B1","idiom.get-the-hang-of":"B1",
    "idiom.on-the-same-page":"B1","idiom.a-heads-up":"B1","idiom.for-the-time-being":"B1",
    "idiom.better-late-than-never":"B1","idiom.easier-said-than-done":"B1","idiom.so-far-so-good":"B1",
    "idiom.fingers-crossed":"B1","idiom.take-it-easy":"B1","idiom.hang-in-there":"B1",
    "idiom.long-story-short":"B1","idiom.in-the-long-run":"B1","idiom.first-things-first":"B1",
    "idiom.one-step-at-a-time":"B1","idiom.in-no-time":"B1","idiom.around-the-corner":"B1",
    "idiom.all-of-a-sudden":"B1","idiom.have-second-thoughts":"B1","idiom.learn-the-hard-way":"B1",
    "idiom.it-slipped-my-mind":"B1","idiom.i-have-no-clue":"B1","idiom.out-of-luck":"B1",
    "idiom.safe-and-sound":"B1","idiom.from-scratch":"B1","idiom.when-it-comes-to":"B1",
    "idiom.as-far-as-i-know":"B1","idiom.in-charge-of":"B1","idiom.in-favor-of":"B1",
    "idiom.word-for-word":"B1","idiom.little-by-little":"B1","idiom.day-by-day":"B1",
    "idiom.fed-up-with":"B1","idiom.sick-and-tired-of":"B1","idiom.grab-a-bite":"B1",
    "idiom.make-yourself-at-home":"B1","idiom.after-you":"B1","idiom.there-you-go":"B1",
    # A2 -> B2
    "idiom.off-the-top-of-my-head":"B2","idiom.cut-corners":"B2","idiom.touch-base":"B2",
    "idiom.under-the-weather":"B2","idiom.on-the-fly":"B2","idiom.make-ends-meet":"B2",
    "idiom.bite-the-bullet":"B2","idiom.break-the-ice":"B2","idiom.cost-an-arm-and-a-leg":"B2",
    "idiom.out-of-the-blue":"B2","idiom.in-hot-water":"B2","idiom.not-my-cup-of-tea":"B2",
    "idiom.the-last-straw":"B2","idiom.go-the-extra-mile":"B2","idiom.miss-the-boat":"B2",
    "idiom.give-me-a-break":"B2","idiom.in-the-middle-of-nowhere":"B2","idiom.in-the-same-boat":"B2",
    "idiom.a-change-of-heart":"B2","idiom.sleep-on-it":"B2","idiom.take-it-or-leave-it":"B2",
    "idiom.you-name-it":"B2","idiom.that-rings-a-bell":"B2","idiom.my-hands-are-tied":"B2",
    "idiom.beats-me":"B2","idiom.fair-and-square":"B2","idiom.back-to-square-one":"B2",
    "idiom.for-good":"B2","idiom.in-a-nutshell":"B2","idiom.all-over-the-place":"B2",
    "idiom.up-in-the-air":"B2","idiom.out-of-hand":"B2","idiom.on-edge":"B2","idiom.at-ease":"B2",
    "idiom.over-the-moon":"B2","idiom.a-pain-in-the-neck":"B2","idiom.have-a-sweet-tooth":"B2",
    "idiom.be-my-guest":"B2","idiom.that-will-do":"B2","idiom.suit-yourself":"B2",
    "idiom.get-cold-feet":"B2","idiom.spill-the-beans":"B2","idiom.pull-someones-leg":"B2",
    # A2 -> C1
    "idiom.once-in-a-blue-moon":"C1","idiom.down-in-the-dumps":"C1","idiom.the-more-the-merrier":"C1",
    # (every other idiom stays A2)
}
SLANG_REGISTER = {
    # -> neutral
    "phrasal-verb.show-up":"neutral","phrasal-verb.catch-up":"neutral","phrasal-verb.come-over":"neutral",
    "phrasal-verb.sleep-in":"neutral","phrasal-verb.hold-on":"neutral","phrasal-verb.pull-off":"neutral",
    "phrasal-verb.bump-into":"neutral","slang.weird":"neutral",
    # -> casual (everything else currently register: slang)
    "phrasal-verb.hang-out":"casual","phrasal-verb.mess-up":"casual","phrasal-verb.screw-up":"casual",
    "phrasal-verb.freak-out":"casual","phrasal-verb.chill-out":"casual","phrasal-verb.splash-out":"casual",
    "phrasal-verb.tag-along":"casual","idiom.beats-me":"casual",
    "slang.stuff":"casual","slang.guys":"casual","slang.cool":"casual","slang.awesome":"casual",
    "slang.broke":"casual","slang.chill":"casual","slang.pretty-degree":"casual","slang.bucks":"casual",
    "slang.buddy":"casual","slang.kiddo":"casual","slang.creepy":"casual","slang.gross":"casual",
    "slang.cheesy":"casual","slang.lame":"casual","slang.nuts":"casual","slang.cop":"casual",
    "slang.comfy":"casual","slang.gonna":"casual","slang.wanna":"casual","slang.gotta":"casual",
    "slang.kinda":"casual","slang.sorta":"casual","slang.ripped-off":"casual","slang.a-bunch-of":"casual",
    "slang.dunno":"casual","slang.lemme":"casual","slang.gimme":"casual","slang.gotta-go":"casual",
    "slang.no-biggie":"casual","slang.couch-potato":"casual","slang.my-folks":"casual",
    "slang.hang-on":"casual","slang.come-on":"casual","slang.not-gonna-lie":"casual",
}

items = []
for f in FILES:
    data = yaml.safe_load(open(f, encoding="utf-8")) or {}
    items += (data.get("lexical_items") or [])

idioms = [it for it in items if it.get("type") == "idiom"]
slang  = [it for it in items if it.get("register") == "slang"]

print("total units:", len(items))
print("idioms:", len(idioms), "| register:slang units:", len(slang))
print("idiom CEFR current :", dict(Counter(it["cefr"] for it in idioms)))
print("idiom CEFR proposed:", dict(Counter(IDIOM_CEFR.get(it["id"], it["cefr"]) for it in idioms)))
print("global register current :", dict(Counter(it.get("register") for it in items)))
print("global register proposed:",
      dict(Counter(SLANG_REGISTER.get(it["id"], it.get("register")) for it in items)))
print("slang->neutral:", sum(v=="neutral" for v in SLANG_REGISTER.values()),
      "| slang->casual:", sum(v=="casual" for v in SLANG_REGISTER.values()))

# sanity: every proposal id must exist in the lexicon
ids = {it["id"] for it in items}
missing = [k for k in list(IDIOM_CEFR)+list(SLANG_REGISTER) if k not in ids]
print("unknown proposal ids (should be []):", missing)
```

Expected output: `idioms: 120`, `register:slang units: 50`; idiom CEFR proposed `{A2:32, B1:42, B2:43, C1:3}`; global register proposed `{formal:209, neutral:723, casual:180, slang:0}`; `slang->neutral: 8`, `slang->casual: 42`; `unknown proposal ids: []`.

---

## 6. Apply order (for the owner)

This is advisory; apply through `maintain-english-curriculum`, then re-validate. Suggested order:

1. **Decide the two policy questions first**, since they change the mechanical edits:
   - Keep a genuine `slang` tier? If yes, it means *adding* volatile/in-group items (§3 note), not retaining any of the current 50. If no, accept the empty category.
   - Accept sparse C1 (3) for an everyday inventory, or push a few more B2 idioms up? I recommend accepting 3.
2. **Apply Defect 2 (register)** — the 50 edits in §3 (8→`neutral`, 42→`casual`). Mechanically simplest, lowest risk. While doing so, resolve the informal-metadata cleanup for the 8 new-`neutral` units (§4 item 4).
3. **Apply Defect 1 (CEFR)** — the 88 idiom level edits in §2. Pure metadata; no schema change.
4. **Re-run validators** after each batch: `trainer curriculum validate` (once wired) plus `pytest` (lexicon invariants) and the §5 snippet to confirm the target distributions. Confirm `curriculum_priority_band` ↔ frequency consistency is unaffected (these edits touch neither band nor frequency).
5. **Log** the change in `transformations` on each edited unit (append `content-reviewed` or equivalent per the transformations journal convention) so provenance is preserved.
6. **Defer** the idiom `casual`/`neutral` consistency pass (§4 item 2) to a separate follow-up — it is a larger, lower-priority sweep and should not block OPEN-31.
