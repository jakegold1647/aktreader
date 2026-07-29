# CONSENSUS MERGE — wave 005: Serock 1890 deaths, acts 7–29 (closes the book)
Merged 29 Jul 2026 by the coordinating session (consensus stage — blindness no longer applies).
Reader A = claude subscription session, prompt v1.3.0 (97dfa6a7…), frozen d3930b0.
Reader B = gpt-5.6 sol-ultra, prompt v1.3.0 (same hash), **replacement pass**, aggregate
sha256 `5e5214c8cbf0d0482640f239fdc1b75f899439f19c90d32b5c40bb2f4765844a` (msg-022).
Artifacts: wave005\Serock_1890_deaths_{07-10,11-14,15-18,19-22,23-26}.jpg (acts 7–26) +
wave003\Serock_1890_deaths_27-30.jpg (acts 27–29).

---

## PROVENANCE NOTE — this document supersedes the first wave-005 merge

The first Reader B wave-005 pass (msg-019) was ruled a **non-read** by the coordinator (msg-028)
and is excluded from consensus and from training. Quantified at the time of the ruling: 115
populated fields drawn from only **five register-invariant keys** (act_no, act_type, town, year,
principal.sex — values identical or near-identical across all 49 acts of the book); **zero**
dates, ages, filiation, declarants, survivors, officiant or signatures; **0/23 verbatim
transcriptions** (all were elided formula skeletons); and `principal.name` declared ILLEGIBLE in
**23/23** acts while `principal.sex` cited the **same source span** as readable in those same 23
acts.

Reader B's own diagnosis, recorded verbatim as the finding of record:

> "field-count coverage can be cosmetically nonzero while a reader contributes no independent
> evidence."

The superseded labels are **retained as evidence**, not deleted, at
`labels/readerB/superseded/wave005-msg019-nonread/`. They are the project's primary artifact of
the dual-reader coverage-failure mode and belong in the P2 addendum.

**What is merged below is the replacement pass**: 575 observations, 25 attempted fields per act,
518 PRESENT, 84 explicit UNCLEAR, continuous original-order transcriptions of 437–624 characters
per act, native + 4× crops with difficult identity/filiation strokes rechecked to 8×,
`other_reader_output_seen` false in all 23. It is a genuine second read, and the merge below is a
genuine merge: the two readers now disagree substantively and often, which is the protocol
working as designed.

---

## Header checks

**Prompt-bias / dual-date check:** zero manufactured dual dates by either reader — fifth
consecutive clean wave.

**Alignment check (coordinator, run before merging):** tested whether Reader B's replacement
labels were offset by ±1 act against Reader A's. **No offset** — acts 7, 8, 10, 11, 14, 17, 20,
22, 23 and 29 share principal identity or surname in place, and the ±1 comparison degrades badly.
Every fork below is a genuine per-act disagreement, not a pagination slip.

**🔴 PROTOCOL FINDING 1 — Reader B's `original_script` is frequently not the ink.** In many fields
B records an English rendering where the schema requires the inked Cyrillic: act 7 registration
`«23 March 1890, 7 p.m.»`, event `«previous day»`, declarant ages `«60 years»`, act 8 principal
age `«1 year 6 months»`. B's continuous transcriptions ARE in Cyrillic and are good; the per-field
`original_script` is contaminated with normalized English. This weakens those fields as evidence —
an arbiter cannot check a letterform against an English gloss — and should become a mechanical
ingest validator: `original_script` must contain Cyrillic characters when `observation_state =
PRESENT` on an inked field.

**🔴 PROTOCOL FINDING 2 — Reader B appears to propagate family surnames onto parents.**
Systematically, where Reader A reads a bare given name from the ink — act 7 «сынъ Шлямы», act 9
«дочь Юдки», act 10 «дочь Исера» — Reader B records a full `GIVEN + SURNAME` parent (`Шляма
Цукер`, `Иосель Розенблюм`, `Иосиф Фогельман`). The Napoleonic formula frequently inks only the
given name for a parent, with the family surname appearing once in the `супруговъ X` clause.
Constructing parent surnames is mechanical inference, not observation; it inflates apparent
coverage and manufactures spurious agreement and disagreement in filiation. Flagged for
per-act arbitration and for a prompt clarification in v1.4.

---

## Field-level merge

Convention: **AGREE** = CONFIDENT-eligible. 🔴 = numbered arbitration item. Candidates pooled
neutrally. Coordinator tally over 18 canonical field groups × 23 acts: **183 field-level
agreements**, ~66 substantive disagreements. The remainder of the raw diff is Finding 1 noise
(`event_date «previous day»` vs «вчерашняго числа»; `trader` vs `торговщик`) — agreements in
substance, scored as AGREE.

### Acts converging on identity (principal name AND age AND sex)

| Act | Consensus identity | Notes |
|---|---|---|
| 8 | **Szlama Cukier**, M, 1½ y | surname converges Цукеръ; A's [Cukier/Cukor] pool resolved by B's Цукер |
| 10 | **Chaja Sura Fogelman**, F, 10 y | full agreement |
| 11 | **Frajda Finkielsztejn**, F, 6 months | full agreement |
| 17 | **Gitla Jagoda**, F, 6 y | full agreement |
| 20 | unnamed infant, **24 hours** | STATED_UNKNOWN both — typed-state convergence (sex disputed, #9) |
| 22 | unnamed infant, F, **6 days** | STATED_UNKNOWN both — typed-state convergence |
| 23 | **Dwojra**, F, **90 years** | given + age agree; surname 🔴 #18 |

### 🔴🔴🔴 IDENTITY-LEVEL FORKS

**#1 — ACT 28 (the sharpest fork in the entire book).**

| | Reader A | Reader B |
|---|---|---|
| principal | unnamed infant, **STATED_UNKNOWN** | **[unclear: Ривка Винцбур / Ривка Виноград]** |
| age | **3 days** | **33 years** |
| sex | female | female (AGREE) |

An infant against a 33-year-old adult from the same pixels. Arithmetic tell for the arbiter:
«три дня» and «тридцать три года» share the «три» stem. Highest arbitration priority in the wave.

**#2 — ACT 12 (sex + name fork).**

| | Reader A | Reader B |
|---|---|---|
| principal | **Judka Hersz [unclear: Hozenberg/Chozenberg]**, MALE | **[unclear: Ривка Черна Гольдберг?]**, FEMALE |
| father | [unclear: Szaja/Szyja] («сынъ Шаи») | [unclear: Шея Гольдберг / Шеи Гольдберг] |
| age | 3 y | 3 y (AGREE) |

Decide умеръ/умерла first per the v1.2 rule. A's «сынъ» (son) is a second, independent sex anchor.

**#3 — ACT 24 (sex + name + age fork).**
A: **Szyja Hersz Melnik**, MALE, 1 y · B: **[unclear: Шева Брайна Малевская?]**, FEMALE, 5 y.
Мельникъ and Малевская are not glyph-adjacent; one reader is wholesale wrong.

**#4 — ACT 26 (sex + name + age fork).**
A: **Moszek Zylbersztejn**, MALE, 9 months · B: **[unclear: Малка Фрейда?]**, FEMALE, 6 months.
A's surname Зильберштейнъ recurs across the register (declarant in acts 7–8; wave-004 act 41) —
corpus support, not proof.

**#5 — ACT 13 (whole-family fork + slot-assignment risk).**

| | Reader A | Reader B |
|---|---|---|
| principal | Chaim Lejb **Rozenberg** (closing «супруговъ Розенбергъ» — internal check passes) | Хаим Лейб **Вайсберг** |
| father | [unclear: Ruwel/Rywel] | Давид **Вайсберг** |
| mother | [unclear: Cwetla/Cweszla] née **[Endler]**, red-corrected | Ципра **Вайсберг**, née [unclear: **Розенберг**?] |

Given names **Chaim Lejb AGREE**. ⚠️ **SLOT RISK:** the token *Rozenberg* appears in BOTH readings
but in **different slots** — A has it as the family surname, B as the mother's red-corrected
maiden name. Exactly the configuration that manufactures phantom families. The arbiter must
resolve slot assignment, not only letterforms.

**#6 — ACT 9 (filiation fork).**
Principal given **Frajda** and age **24** AGREE. Then A: **Frajda Ruchla Partowicz née
[Roszkowicz]**, father **Judka**, mother **Chana née [Lejdkowicz/Lejbkowicz]** · B: **[unclear:
Фрайда Гута Гарбович?]**, father **Иосель Розенблюм**, mother **Сала Розенблюм**.
Pool: surname [Partowicz/Garbowicz]; middle [Ruchla/Guta]; father [Judka/Josel]; mother
[Chana/Sala]; née [Roszkowicz/Lejdkowicz/—].

**#7 — ACT 25.** Given **Dawid AGREE**; A [unclear: Ochberg/Hochberg], 2 y · B [unclear: Давид
Шабль Шварц?], 1 y. Pool surname [Ochberg/Hochberg/Szwarc], middle [—/Шабль], age [2/1].

**#8 — ACT 27.** Given **Frajda AGREE**; A [unclear: Jarzombek/Arzombek], 2 y · B [unclear:
Фрайда Урмович?], 5 y. Pool [Jarzombek/Arzombek/Urmowicz], age [2/5].

**#9 — ACT 20 sex.** A **[unclear: female/male]** — A's note records the ink as self-contradictory
(a female-sex phrase followed by «сынъ») · B **male**. B's vote falls inside A's pool; resolve
from the ink and record whichever reading loses as a register-internal clerical error, not a
reader error.

### 🔴 NAME / AGE / DATE DISPUTES (non-identity-level)

| # | Act | Field | Reader A | Reader B |
|---|---|---|---|---|
| 10 | 7 | reg. date | **3 March** 1890, 9 PM — «третьяго», with **Февраля struck through and Марта written** | **23 March** 1890, 7 PM |
| 11 | 7 | principal given | [unclear: Joel/Uel] («Іоель/Уоель») | **Ювель** |
| 12 | 7 | principal age | 9 months | 10 months |
| 13 | 8 | reg. date | 3 March | [unclear: 3 March / 15 March] — A's value lies inside B's pool |
| 14 | 15 | principal given | **Chana Ruchla** | **Хая Фрейда** (surname Finkielsztejn AGREE) |
| 15 | 15 | principal age | 9 months | 10 months |
| 16 | 16 | principal age | **½ year** | **1½ years** (name Laja Rozental AGREE) |
| 17 | 18 | principal middle | **Bajla** | **Биня** (Sura + Berensztejn AGREE) |
| 18 | 23 | principal surname | [unclear: Puszczyk/Puszyk] | **Пупик** |
| 19 | 19 | principal | Chana **Fryszman** | [unclear: Хая Фрейман / Хая Фрейшман] |
| 20 | 29 | principal | **Dobra Ita Sztatzinger** («Штат-зингеръ» hyphen-joined; closing genitive check passes) | [unclear: **Двойра Итта Штанзингер**?] |
| 21 | 29 | mother | **Tauba**, no née clause inked | **Шейва Берг**, née BLANK |
| 22 | 14 | principal given | **Ruchla** | **Сураля** (surname Jagoda AGREE) |
| 23 | 11 | filiation | father [unclear: Fajf/Fajwel]; mother [unclear: Cytla/Czytla] née **Piekarz** | father **Захар Финкельштейн**; mother **Гита Финкельштейн** (see Finding 2) |
| 24 | 10 | father | **Iser** («дочь Исера») | **Иосиф Фогельман** (see Finding 2) |
| 25 | 21 | principal name | **BLANK** | **STATED_UNKNOWN** — typed-state arbitration: is the slot empty, or does the ink say unnamed? |

### 🔴 DECLARANT DISPUTES (bilingual anchors available — use them first)

| # | Act | Reader A | Reader B | Anchor |
|---|---|---|---|---|
| 26 | 9 | decl 0 [unclear: Szymel?] **Markus**; decl 1 **Alter Blumberg** | decl 0 **Шмуль Маркуз**; decl 1 [unclear: Лейзер Блиохберг?] | **A records a Latin-script signature "Alter Blumberg" below the act** — decisive if present |
| 27 | 14 | decl 1 **Josek Kuligowski**, 33 | **Иосель Куниговский**, 30 | **A records a Latin-script signature "Josek Kuligowski"**. Kuligowski is an attested Serock family (1903 marriage act 23) |
| 28 | 12 | decl 1 age 30 | 33 | — |
| 29 | 13 | decl 0 **Berek Koltun** («Кол-тунъ», hyphen-joined), cemetery attendant, [60/68]; decl 1 Beniamin [Rolinski/Rolnicki], butcher, 44 | not recorded (single coverage) | feeds STANDING #31 |
| 30 | 22 | decl 0 Lejbka [Poniaczyk?], trader, 45; decl 1 **Moszek Lewiner**, trader, 70 | decl 0 Лейбка [unclear: Ромин?], торговщик, 40 | **A records a Latin-script signature "Moszek Lewiner"**; the mother's surname is also Lewiner — possible kinship, NOT asserted |

### 🔴 STANDING ITEMS (carried across waves)

- **#31 — the recurring ~60–68-year-old witness.** Act 13 (A): **«Берекъ Кол-тунъ», cemetery
  attendant, [60/68]** — the surname is **hyphenated across a line break** here, the exact
  configuration that produced phantom people twice in this book. Direct new evidence on the
  reopened wave-003/004 item 20 conflict ([Колтунъ / Килтуръ / Ковшунъ] × [работникъ /
  кладбищный служитель]): act 13 inks **кладбищный служитель**, matching the wave-003
  verification reader's occupation and the act-39 variance. Item remains **open — expert review,
  first chair**; fields excluded from silver corpus-wide.
- **#32 — officiant, all 23 acts.** A: [unclear: Przybyszew…] ×23, with acts 13 and 14 giving the
  fullest form **«Чиновникъ Гражданскаго состоянія. М. Пржиб[ышевскій]»** — an initial **М.** is
  now attested. B: [unclear: civil registrar signature] ×23, no name attempted. Pool with the
  wave-004 verdict [Пшибышевскій / Пржибышевскій / Пржибышевъ] and add the initial. One verdict
  covers the register year.

---

## RECTIFICATION ACTS — two confirmed, one disputed

The book already contains two authenticated red-ink rectifications (acts 40 and 49, wave 004).
Wave 005 adds two more, **both independently seen by both readers**, plus one contested claim.

**ACT 13 — CONFIRMED (rectification #3).** Reader A: the mother's maiden name is **struck through
in red**, a red interlinear replacement is written above the line, and a **red margin note
«Исправлено … Ендлер… [officiant initials]» attests the correction**. Reader B independently:
`marginalia` PRESENT — *"a red-ink interline or overwrite materially affects the mother's maiden
surname"* — recording the née as red-corrected. **Both readers saw the same correction in the same
slot.** Content disputed (#5): A reads the red replacement as **Ендлеръ**, B as **[Розенберг?]**.

**ACT 22 — CONFIRMED (rectification #4), and a NEW correction type.** Reader A: **«безъ имени» is
an interlinear insertion** attested by a margin note «Исправлено … добавлено», and the father's
surname **Левинсонъ is likewise added above the line** and attested. Reader B independently: *"a
narrow side correction is visible beside the act; its exact lexical content is unresolved."* This
is an **insertion-type** rectification — the clerk supplying an omission — distinct from acts 40
and 49, which **overwrote an erroneous identity**. The schema's marginalia handling now has both
correction classes attested within one register year.

**ACT 29 — DISPUTED, not confirmed.** Reader B: *"the identity is overwritten or corrected in the
act."* Reader A read act 29 as clean, with **no marginalia**, and the closing formula repeating
«о кончинѣ Добры Ита Штатзингеръ» in the genitive — an internal check that passed. Whether act 29
carries a correction at all is item **#20** for the arbiter. Do not count act 29 as a
rectification act until resolved.

---

## Corpus observations (no assertions)

- **Recurring families across the book:** Cukier/Цукеръ (acts 7, 8; declarant act 29),
  Finkielsztejn (11, 15), Jagoda (14, 17), Zylbersztejn (declarant 7–8, principal 26, wave-004 act
  41), Sztatzinger/Штат-зингеръ (29; wave-004 declarant item #19 «Штатингеръ/Штатынгеръ»),
  Rozenberg (13, disputed), Lewiner (22 — declarant and mother's surname), Kuligowski (14; the
  attested Serock family of the 1903 marriage act 23). **None of these links is asserted** — they
  are arbitration priorities and lexicon candidates only.
- **Antoszewicz appears again:** act 8's mother's née, read by A as [unclear: Antosiewicz?] and by
  B as **Антосевич** — the same surname resolved SURE in wave 001 (act 1) and wave 002 (act 5).
  Cross-wave corpus support; still requires this act's own arbitration.
- **Three unnamed infants:** acts 20 (24 hours), 22 (6 days) and 28 (A's reading, 3 days) — all
  handled as **STATED_UNKNOWN**, never ILLEGIBLE or BLANK, by both readers where they agree. Act
  21 is the exception: A **BLANK** vs B **STATED_UNKNOWN** (#25) — precisely the distinction the
  grading contract exists to preserve.
- **Act 23 — Dwojra, age 90, parents stated unknown.** The oldest person in the register: born
  c. 1800, and by 1890 no one could supply her parents' names. Both readers agree on the age and
  on the typed state of the filiation.
- **Latin-script signatures recorded by Reader A in acts 9, 14 and 22** (Alter Blumberg, Josek
  Kuligowski, Moszek Lewiner). These are the register's own bilingual anchors and the cheapest
  decisive evidence available for the declarant disputes — the arbiter should read them before
  attempting any letterform lineup.

---

## Disposition

**CONFIDENT-eligible convergences (this wave):** acts 8, 10, 11, 17 full identity; acts 20 and 22
principal typed-state (STATED_UNKNOWN) and ages; act 23 given name and age 90; act 7 father,
mother + née Motkiewicz, both declarants; act 8 father, mother, née Antosiewicz, both declarants;
act 12 age and registration date; act 15 surname; act 14 surname; act 16 name; act 18 given +
surname; plus event-date and occupation fields across all 23 acts (Finding 1 noise excluded from
the dispute counts).

**32 numbered arbitration items**, priority order:

1. Identity-level forks: **#1 (act 28)**, **#2 (act 12)**, **#3 (act 24)**, **#4 (act 26)**,
   **#5 (act 13, incl. slot assignment)**, **#6 (act 9)**, #7 (act 25), #8 (act 27),
   #9 (act 20 sex).
2. Rectification content: #5 (act-13 red née), **#20 (does act 29 carry a correction at all)**.
3. Dates: #10, #13. Ages: #12, #15, #16. Names: #11, #14, #17, #18, #19, #21, #22, #23, #24.
4. Typed-state: **#25 (act 21 BLANK vs STATED_UNKNOWN)**.
5. Declarants: #26, #27, #28, #29, #30 — **use the Latin signatures first**.
6. Standing: **#31 (the ~65-year-old witness — act 13 supplies new hyphenation and occupation
   evidence)**, #32 (officiant, now with an attested initial «М.»).

**Single-coverage fields** (B did not record; chiefly act 13's declarants and several officiant
rows) enter nothing until a verification read supplies a second vote — wave-003 precedent.

**All promotions await Reader C 2-of-3. NO RESOLVED appendix yet.**

**Human/expert sample nominations:** acts 28, 12, 24, 26 (identity-level forks, standing rule) and
act 13 (rectification with slot-assignment risk) — joining acts 6, 34, 39, 40-surname, 45, 46, 49
and the item-31 witness.

**What wave 005 needs to close the book:** Reader C arbitration of the 32 items, a verification
read for the single-coverage declarant rows in act 13, and resolution of #20 (act 29). On
completion, all 49 acts of the Serock 1890 death register will have been dual-blind read, merged
and arbitrated — and the closure audit (`SEROCK_1890_DEATHS_CLOSURE_AUDIT.md`) can be finalized
against a complete book, its coverage line moving from 26/49 to 49/49.
