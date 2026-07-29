# CONSENSUS MERGE — wave 005: Serock 1890 deaths, acts 7–29 (FINAL WAVE OF THE BOOK)
Merged 28 Jul 2026 by the coordinating session (consensus stage — blindness no longer applies).
Reader A = claude subscription session, prompt v1.3.0 (97dfa6a7…), frozen d3930b0.
Reader B = gpt-5.6 sol-ultra, prompt v1.3.0 (same hash), frozen per
coordination\inbox_claude\msg-019 (aggregate label-manifest sha256 b62eca1b…; files subsequently
renamed from zero-padded `-07` to the unpadded `-7` house convention).
Artifacts: wave005\Serock_1890_deaths_{07-10,11-14,15-18,19-22,23-26}.jpg (acts 7–26) +
wave003\Serock_1890_deaths_27-30.jpg (acts 27–29).

**Prompt-bias check:** zero manufactured dual dates by either reader (fifth consecutive clean wave).

**Protocol-compliance finding:** Reader B's ILLEGIBLE notes cite "2× act-quadrant review and a
targeted 4× principal/filiation-band crop" — the 4× floor is now nominally met (an improvement on
wave 004's 2–3×), but see the structural finding below: the stated inspection did not translate
into recorded content. Reader A worked at 4–8× throughout and emitted **no ILLEGIBLE at all**;
every doubtful field carries bracketed candidates instead.

---

## S1 — STRUCTURAL FINDING: wholesale legibility divergence (not a numbered dispute)

Reader B declared `principal.name` **ILLEGIBLE in all 23 of 23 acts** (null value, null
original_script, null confidence) while Reader A read all 23 principals with ordinary
`[unclear: X/Y]` handling and no ILLEGIBLE anywhere. This is one structural divergence, not 23
disputes, and it is recorded here as such.

### Quantification

| Measure | Reader A | Reader B |
|---|---|---|
| Distinct field groups populated per act | **13** (registration_date, event_date, principal{name,age,sex}, father, mother, declarants[], deceased_left_behind, officiant, signatures_note, + situational event_place / family_residence / foster_note / registration_hour) | **6** (act_no, act_type, town, year, principal.sex, principal.name) |
| Evidence fields PRESENT with a non-null value | **183** | **115** |
| Evidence fields non-present / null | 0 ILLEGIBLE (typed absences only, all justified) | **23** (all `principal.name`) |
| Transcriptions that are verbatim ink | 23/23 | **0/23** |
| Transcriptions that are elided formula templates | 0/23 | **23/23** |

**What B's 115 populated fields actually are.** All five populated keys are register-invariant or
margin-level: `act_no` (the margin numeral, 23/23 correct), `act_type` ("death" — the genre of the
whole book), `town` ("Serock" — identical in all 49 acts), `year` (1890 — identical in all 49
acts), and `principal.sex`. No date, age, filiation, declarant, survivor, officiant, or signature
field was recorded in any act. The act-specific content of the book is, on Reader B's side of this
wave, absent.

### Internal inconsistencies within Reader B's own labels

1. **Same span, two verdicts.** In **23 of 23 acts**, B's `principal.sex` and `principal.name`
   cite the *same* `source_span_ids: ["principal"]` — the span B himself describes as "Death verb,
   deceased identity clause, and sex morphology." B therefore judged one span simultaneously
   readable (sex) and unreadable (name). In the Napoleonic death formula these are contiguous
   words on the same line — «умерло дитя **мужескаго пола** по имени **[NAME]**» — the sex phrase
   immediately precedes the name it is said to be illegible beside.
2. **Slash-list "original_script" is not a reading.** B's `act_type` original_script is the string
   `умеръ/умерла/умерло` in **all 23 acts** — the three possible verb forms listed, not the form
   inked on the page. B's `principal.sex` original_script is likewise `женскаго пола/умерла` or
   `мужескаго пола` as a generic pair rather than a verbatim quotation. Reader A quotes the ink
   («умерло дитя женскаго пола», «умерла», etc.) in every act.
3. **Consequence for msg-019's calibration claim.** msg-019 states "No dates, ages, filiation, or
   other details were inferred merely from the repeated form." The four non-sex fields B *did*
   populate (act_type, town, year, and the margin act_no) are precisely the fields derivable from
   the repeated form, and their recorded `original_script` values are form-templates rather than
   quotations. The claim holds for dates/ages/filiation (B recorded none) but not for the fields
   B did record.
4. **The sex reads are not corroborated by their own evidence.** Of B's 19 sex-decided acts, **5
   conflict with Reader A's verbatim-anchored readings** (§ disputes #1–#5 below), including two
   acts where A's reading is double-anchored by both the sex phrase and the filiation word
   (сынъ/дочь).

**Ruling.** This is a legibility-judgment divergence of a different order from waves 003–004:
there, B under-read specific hard fields; here, B recorded almost none of the act content while
nonetheless emitting confident values for the invariant scaffolding. Reader B's wave-005 labels
supply a usable second vote for **act_no, act_type, town, year** only. They supply a *contested*
second vote for **sex**. They supply **no** second vote for anything else, which places nearly the
whole substantive content of 23 acts into single coverage (see the verification block).

---

## Field-level merge

### Convergences → CONFIDENT-eligible

| Field | Coverage | Result |
|---|---|---|
| `act_no` | 23/23 both readers | **AGREE 23/23** — B's margin numerals match the assigned act numbers exactly |
| `act_type` = death | 23/23 both readers | **AGREE** (B's evidence is form-derived; the value is nonetheless correct and independently supported by A's verbatim verbs) |
| `town` = Serock (посадъ Сероцкъ) | 23/23 both readers | **AGREE** |
| `year` = 1890 | 23/23 both readers | **AGREE** |
| `principal.sex` | 14 acts | **AGREE**: acts 7, 9, 10, 12, 15, 17, 18, 19, 22, 23, 24, 27, 28, 29 |

### Numbered disputes — sex (the only fields with genuine two-reader divergence)

| # | Act | Reader A | Reader B | Note |
|---|---|---|---|---|
| **#1** | 8 | **male** — «умерло дитя мужескаго пола» (verbatim) | **female** — «женскаго пола/умерла» (template) | pooled [male/female] |
| **#2** | 11 | **female** — «умерло дитя женскаго пола» (verbatim) | **male** — «мужескаго пола» (template) | pooled [female/male] |
| **#3** | 14 | **female** — «умерло дитя женскаго пола» (verbatim) | **male** — «мужескаго пола» (template) | pooled [female/male] |
| **#4** | 20 | **[unclear: female/male]** — the ink is internally contradictory: «умерло дитя **женскаго** пола … **сынъ** Хаима» (female sex-phrase, masculine filiation noun) | **female** (template) | A's abstention is evidence-based; the arbiter must resolve the ink's own contradiction, not merely pick a side |
| **#5** | 21 | **male** — «умерло дитя мужескаго пола … **сынъ**» (double-anchored: sex phrase + filiation noun) | **female** (template) | pooled [male/female] |

Four further acts — **13, 16, 25, 26** — have B at `UNCLEAR` with both alternatives while A
decided (male, female, male, male respectively). These are not disputes; they are single-coverage
and fold into the verification block.

### Standing items carried in

- **#20 (cross-wave, the recurring ~65-year-old witness).** Reader A reads **Berek Koltun** in
  **6 acts of this wave** (13, 15, 16, 23, 26, 27) — the largest single-wave concentration yet.
  Reader B recorded no declarants, so this wave adds no second vote. The item remains OPEN on the
  expert-review list per the wave-004 ruling; these fields stay excluded from silver.
- **#24 (officiant, register-year standing item).** Reader A records the officiant in all 23 acts
  as a Przybyszewski-family signature, with the form varying by legibility across the year:
  `[unclear: Przybyszew?]` (7), `[unclear: Przybysz…]` (8–12), `[unclear: M. Przybyszew(ski)?]`
  (13, 14, 19), `[unclear: Przybyszew(ski)?]` (15, 16, 20–23), `[unclear: M. Przybyszewski?]`
  (17, 18), **`Pszybyszewski` (as signed)** (24, 25, 26), `[unclear: Przybyszewski?]` (27–29).
  Acts 24–26 give the clearest instances in the whole book and should anchor the standing verdict.
  Single-coverage this wave; feeds the existing pooled item.

---

## VERIFICATION-READ BLOCK (single coverage — no promotions until a second vote)

Because Reader B recorded no principal name, date, age, filiation, declarant, survivor, officiant
or signature field, **all of Reader A's substantive wave-005 content is single-coverage**. It is
grouped by spread for efficient verification. A verifier should read each spread once and supply
independent values for: principal name, age, sex, registration and event dates, father, mother
(and née), both declarants, survivors clause, and any situational field flagged below.

| Block | Spread | Acts | Reader A principal (single coverage) | Age | Flags |
|---|---|---|---|---|---|
| **V1** | `wave005\…07-10.jpg` | 7 | [unclear: Joel/Uel] Cukier | 9 months | reg. date carries a struck month («Февраля» struck, «Марта» written above) |
| | | 8 | Szlama [unclear: Cukier/Cukor] | 1.5 y | sex dispute #1 |
| | | 9 | Frajda Ruchla Partowicz née [unclear: Roszkowicz/Roszowicz] | 24 | **only act in the wave with a survivors clause**: husband [unclear: Motel/Motek] + son Abram |
| | | 10 | Chaja Sura Fogelman | 10 | **event outside Serock**: village [unclear: Janki/Jamki] |
| **V2** | `wave005\…11-14.jpg` | 11 | Frajda Finkielsztejn | 6 months | sex dispute #2 |
| | | 12 | Judka Hersz [unclear: Hozenberg/Chozenberg] | 3 | family are permanent residents of **Kałuszyn**, temporarily in Serock |
| | | 13 | Chaim Lejb Rozenberg | 1 | B UNCLEAR on sex → A single-coverage |
| | | 14 | Ruchla Jagoda | 2 months | sex dispute #3; **event in village Zegrze** (margin annotation) |
| **V3** | `wave005\…15-18.jpg` | 15 | Chana Ruchla Finkielsztejn | 9 months | registration hour **BLANK** (formula slot uninked) |
| | | 16 | Laja Rozental | 0.5 y | B UNCLEAR on sex; registration day [unclear] |
| | | 17 | Gitla Jagoda | 6 | — |
| | | 18 | Sura Bajla Berensztejn | 3 | — |
| **V4** | `wave005\…19-22.jpg` | 19 | Chana Fryszman | 1 y 6 months | — |
| | | 20 | **STATED_UNKNOWN** («безъ имени») | 24 hours | sex dispute #4 (ink self-contradictory) |
| | | 21 | **BLANK** name slot (no «по имени» clause, no «безъ имени» statement) | 5 days | sex dispute #5; typed-state distinction BLANK ≠ STATED_UNKNOWN is load-bearing here |
| | | 22 | **STATED_UNKNOWN** («безъ имени», interlinear insertion, attested) | 6 days | correction/insertion — verify the attestation |
| **V5** | `wave005\…23-26.jpg` | 23 | Dwojra [unclear: Puszczyk/Puszyk] | **90** | **oldest person in the book**; parents **STATED_UNKNOWN** («дочь неизвѣстныхъ родителей»); survivors **BLANK**; closing formula slips to boilerplate «о кончинѣ дитяти» for a 90-year-old |
| | | 24 | Szyja Hersz Melnik | 1 | officiant signature clearest here (24–26) |
| | | 25 | Dawid [unclear: Ochberg/Hochberg] | 2 | B UNCLEAR on sex |
| | | 26 | Moszek Zylbersztejn | 9 months | B UNCLEAR on sex; **rare fostering clause**: child given out for upbringing to Cyrtla [unclear: Wielkobrod?] |
| **V6** | `wave003\…27-30.jpg` | 27 | Frajda [unclear: Jarzombek/Arzombek] | 2 | — |
| | | 28 | **STATED_UNKNOWN** given name, surname inked: «безъ имени по фамиліи Виногура» | 3 days | surname-only identification — a distinct typed pattern |
| | | 29 | Dobra Ita Sztatzinger | 4 | — |

**Verification-block size: 23 acts × ~11 substantive field groups ≈ 250 single-coverage fields.**
Priority within the block: the four typed-absence acts (20, 21, 22, 28 — they exercise the
BLANK / STATED_UNKNOWN distinction the schema exists to preserve), act 23 (oldest subject,
stated-unknown parents), and act 26 (fostering clause).

---

## Corpus observations (no assertions; recorded for the town-graph and lexicon)

- **Recurring declarants.** Berek Koltun ×6 (13, 15, 16, 23, 26, 27) and Jankiel Borensztejn ×5
  (11, 12, 14, 16, 21) dominate the wave; Abram Wajngrod + Moszek Zylbersztejn appear as a *pair*
  in acts 7 and 8; Alter Blumberg ×2 (9, 10); Moszek Mitelbach ×2 (17, 25); Moszek Cukier ×2
  (17, 20). Lejzor Wielkobroda appears in act 28 — the same standing-witness family recorded in
  the wave-003 material.
- **Families recurring within the wave.** Finkielsztejn ×2 (11, 15 — and a Jankiel Finkielsztejn
  as declarant in 12); Jagoda ×2 (14, 17); Cukier/Cukor (7, 8 principals; Moszek Cukier and Aron
  Cukier as declarants in 17/20 and 29).
- **Families recurring across waves.** Zylbersztejn (26 here; act 41 in wave 004), Sztatzinger
  (29 here; acts 31/32 in wave 003 and the wave-004 #19 candidate), Rozenberg (13 here),
  Winogura (28 here), Wielkobroda (28 here; the Ruchla-death double-entry witnesses).
  Cross-wave identity is **not** asserted — surname recurrence only.
- **Unnamed infants, three typed patterns in one wave.** Act 20 and act 22: STATED_UNKNOWN via an
  explicit «безъ имени» (act 22's is an authenticated interlinear insertion). Act 28:
  STATED_UNKNOWN given name with an inked surname («безъ имени по фамиліи Виногура») — a
  surname-only identification. Act 21: **BLANK** — the clerk simply omitted the name slot, with no
  «безъ имени» statement. Reader A distinguished all four correctly; this quartet is the best
  demonstration in the book of why the typed-absence states are not interchangeable.
- **Act 23, Dwojra Puszczyk, 90.** Born c. 1800. Parents recorded as stated-unknown; survivors
  clause left blank; the closing formula reverts to the infant boilerplate «о кончинѣ дитяти».
  Reader A flags the age as a clerk's estimate.
- **Mortality profile of the wave.** 17 of 23 subjects are children under 7; four died within a
  week of birth (24 hours, 3 days, 5 days, 6 days). The two adults are Frajda Ruchla Partowicz
  (24) and Dwojra Puszczyk (90).
- **Two out-of-town deaths** (acts 10 and 14 — village [Janki/Jamki] and village Zegrze) and one
  out-of-town family (act 12, Kałuszyn). Register coverage extends past the posad boundary.

---

## Disposition

- **CONFIDENT-eligible:** `act_no`, `act_type`, `town`, `year` in all 23 acts; `principal.sex` in
  the 14 agreeing acts (7, 9, 10, 12, 15, 17, 18, 19, 22, 23, 24, 27, 28, 29).
- **5 numbered disputes** (all `principal.sex`: acts 8, 11, 14, 20, 21) → Reader C arbitration.
  Priority: #4 (act 20, internally contradictory ink) and #5 (act 21, double-anchored A reading),
  then #1–#3. An arbiter should read the sex phrase **and** the filiation noun in each case.
- **Verification-read block V1–V6** (23 acts, ~250 single-coverage fields) → fresh independent
  read required before any promotion. Nothing from Reader A's substantive content enters silver on
  one vote, per the wave-003 precedent.
- **Standing items:** #20 (Koltun/Kiltur/Kowszun witness) remains open with 6 new Reader A
  attestations and no second vote; #24 (officiant) gains its clearest instances at acts 24–26.
- All promotions await Reader C 2-of-3. **No RESOLVED appendix yet.**
- **Book status:** with wave 005 merged, all 49 death acts of Serock 1890 have been double-read.
  The closure audit finalizes once this wave's arbitration and verification block resolve.
- **Recommendation to the coordinator (out of scope for this merge, flagged once):** wave 005's
  Reader B pass does not meet the evidentiary standard of a second blind read. Consider commissioning
  a full replacement Reader B pass for acts 7–29 rather than resolving ~250 fields through the
  verification-block mechanism.
