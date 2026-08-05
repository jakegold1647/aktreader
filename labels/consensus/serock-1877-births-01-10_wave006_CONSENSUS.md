# CONSENSUS MERGE — wave 006: Serock 1877 births, acts 1–10

Merged 4 Aug 2026 by the coordinating session (consensus stage — blindness no longer applies).
Reader A = claude subscription session, prompt v1.4.0 (5d14dcb8…):
acts 1–8 frozen `0f02480` (29–30 Jul, reader_id `claude-reader-a-wave006`);
acts 9–10 completed by a fresh instance `readerA-w006-20260804`, frozen `f7391fc` (4 Aug).
Reader B = fresh instance `readerB-w006-20260804`, prompt v1.4.0 (same hash), frozen `c05c091`
(4 Aug) — first wave run under protocol v1.1 (per-wave fresh blind instances, msg-046).
Artifacts: Serock_1877_births_{01-02,03-06,07-10}.jpg, hashes verified against the frozen
brief at merge time.

---

## PROVENANCE NOTES

**Split Reader A pass.** The July session froze acts 1–8 and stopped; the 4 Aug fresh instance
completed 9–10. The fresh instance also independently read acts 1–8; those labels are retained
as **supplementary evidence only** at `labels/readerA/supplementary/wave006-readerA2-20260804/`
— they are never a vote in this merge, and are cited below only where they illuminate a dispute.

**Envelope variance.** The 4 Aug labels (both readers) use `record_id serock-1877-b-0NN` and
flat key names (`witness1.name`); the July pass uses `serock-1877-birth-N` and underscored
names (`witness_1.name`). Mapping is by act number. Files are frozen verbatim; no envelope was
edited.

**🔴 WAVE-LEVEL FINDING — the brief's language pin is wrong.** The frozen brief declares
`target.language = "pl"` with a note that the Cyrillic gate must not apply. All ten acts are
Russian chancery Cyrillic in pre-reform orthography, as expected for 1877 (Russification window
1868–1915). **Both readers independently contradicted the brief from the ink** and labeled
`language: "ru"` — the language-conditional guard read the page, not the metadata, which is the
guard working as designed. ERRATUM required on `wave006_artifacts.json` metadata (registers as
brief-authoring error, charged to the retired builder role; the corpus_gap_note re acts 23–26
of the year is unaffected).

---

## Header checks

**Dual-date check:** Reader A records both calendar sides with the inked day-words; Reader B
normalises to single Gregorian values. Zero manufactured duals by either reader — where both
sides are checkable the 12-day gap holds throughout. Convention difference only; scored on the
Gregorian value.

**Alignment check (run before merging):** the ±1 offset hypothesis was tested for the 03-06
spread because act 6 forks wholesale (below). No clean offset exists: B's act 6 matches neither
A's act 6 nor A's act 7 (different families in all three readings). The forks in acts 2, 6, 7
are genuine per-act disagreements or a region-assignment error inside the four-act spread —
for the arbiter, not a pagination slip that consensus can undo.

**🔴 PROTOCOL FINDING 3 — Reader B occupation glossing.** Where A reads the inked trade
(сапожникъ shoemaker, мясникъ butcher, чернорабочій laborer), B repeatedly records
"shopkeeper" (acts 1, 2, 4, 5, 6, 7, 8). The pattern is too systematic to be independent
letterform reads; it resembles wave-005 Finding 1 (normalised gloss displacing the ink).
Arbiter must resolve occupations from the ink, and the mechanical-validator recommendation
from wave 005 extends to trade words.

**🔴 PROTOCOL FINDING 4 — Fiszman/Fiszbin is one systematic fork, not five.** The recurring
butcher-witness is A: Мортка Фишманъ, B: Мортка Фишбинъ across acts 1, 3, 4, 5, 8 (and as
B's father-of-record in its act-6 reading). One letterform decision (м/б before the terminal
cluster) settles all instances at once; arbitrate once, apply per-act.

**Fresh-instance convergence note.** Acts 9–10, where BOTH passes are same-day fresh
instances, agree on essentially every core field (two minor items below). Acts 1–8, July
session vs fresh instance, carry all the substance. Worth carrying into the P2 addendum as a
protocol observation; the supplementary A′ pass gives a third leg for the arbiter on 1–8.

---

## Field-level merge

Coordinator tally over the mapped canonical fields: **~89 field-level agreements** across the
ten acts (67 on acts 1–8, 22 on acts 9–10), ~20 gloss-noise differences scored AGREE in
substance (hour formatting, officiant-title translation variants), and the substantive
disagreements pooled into the numbered items below.

### Acts converging on identity

| Act | Consensus identity | Notes |
|---|---|---|
| 3 | **Abram Szyja**, M, b. Serock 1/13 Jan 1877; father Haskel Nejman, mother Sura Itta née Moszkowna | cleanest act of the wave; née pool [Moszkowna/Moskowna] resolves on the shared candidate |
| 4 | **Golda**, F, b. Popowo 8/20 May **1872** — five-year late registration | identity + late-reg agree; mother disputed #6 |
| 8 | **Brucha**, F, b. Serock 2/14 Mar 1877; father Fajwel/Fajbisz Rozenberg | mother née fork #9 |
| 9 | **Elka Fajga**, F, b. Dembe 4/16 Mar 1877; father Abram Dawid Rozenfeld, private scribe, 28; mother Ruchla | full agreement both fresh passes; née initial К/В → human queue |
| 10 | **Pejsach**, M, b. Popowo 1/13 Apr 1877; father Pinkus Rokita, laborer, 22; mother Frajda née Kania | Rokita resolves on shared candidate; birth hour #12 |
| 1 | child pool intersection **Ankiel** (A [Ankiel/Ancel/Anszel] × B [Jankiel/Ankiel]) | intersection recorded, NOT promoted — the initial letter is the identity; #4 and human queue |
| 5 | **Rojza/Rejza**, F, late registration, same couple as act 4 | name variants glyph-adjacent; birth-year fork #8 |

### 🔴🔴🔴 IDENTITY-LEVEL FORKS

**#1 — ACT 6 (the sharpest fork of the wave; whole-act divergence).**

| | Reader A (July) | Reader B (fresh) |
|---|---|---|
| child | [unclear: Mendel/Mendla/Szmul] | **Icek** |
| reg. date | 16/28 Jan 1877 | 22 Feb (Greg) 1877 |
| birth | 3/15 Jan 1877 | 14 Feb (Greg) 1877, Serock |
| father | declarant age [28/26], name not carried to father slot | **Mortka Fiszbin**, 44, the recurring butcher-witness |
| mother | [Bejla Chana/Bejla Chaja] née [Golbarekowna/Goldbarekowna/Kolbarekowna], [30/36] | **Bejla Fajga** née **Lewkowiczowna**, 34 |
| witness 2 | [Mortka Fiszman/Icek Fiszman], butcher | [Josek Pieniek/Josek Pianek], 44 |

Different families, dates a month apart, from the same declared act region. The supplementary
A′ pass reads act 6 as **Icek, father Mortka [Fiszbin/Friszbin]** — siding with B — which
suggests the July pass may have mis-bounded the act region on the four-act spread. Arbiter
must first fix WHICH ink belongs to act 6, then read it. Highest priority.

**#2 — ACT 2 (child + mother fork; surname agrees).**
A: child **Lejb**; mother **Chawa Ruchla** née [Zofersztejn/Safersztejn/Zafersztejn], 25;
declarant Szmul Majer Cytronowicz, [28/26].
B: child **Berek**; mother **Malka Ruchla** née **Borensztejn**, 22; declarant [Szmul/Szendel]
Majer Cytrynowicz, 25. Family surname AGREES (Cytr-nowicz vowel variance only). Supplementary
A′ reads Berek and Borensztejn — again siding with B. Full-family arbitration.

**#3 — ACT 7 (child + mother fork).**
A: child **Malka**; mother née [Pruch/Prus/Bruch], 27; birth 6/18 Feb.
B: child **Ruchla Laja**; mother née **Kon**, [19?]; birth 15 Feb (Greg).
Father Haskel/Chackel Solarz of Popowo AGREES. A′ reads Ruchla Laja née Kon. Arbitrate.

**#4 — ACT 1 (identity pool + filiation fork).**
Child: intersection Ankiel stands, but A′ introduces **[Jankiel/Chankiel]** — the initial
(А/Я/Ха) remains a three-way letterform question; both readers + merge nominate for human
review. Mother: A née [Buchman/Bukman/Bukszman] 45 vs B née **Bursztyn** 42 — no candidate
overlap; filiation-critical. Declarant surname pool [Szachcer/Szechter/Solarz] vs [Soliarz]
— the Latin signature (read by both as ~"dawid Solarz") anchors toward Solarz; arbiter to
weigh signature against Cyrillic body per the bilingual-anchor rule.

### 🔴 FIELD DISPUTES

| # | Act | Field | Reader A | Reader B |
|---|---|---|---|---|
| 5 | 1 | reg. date (Greg) | [16/17 Jan] | **15 Jan** — three-way, no overlap |
| 6 | 4 | mother | **[Frejdela/Frejda Lea]**, 30, née [Meernowa/Meersonowa/Meerowna] | **Frymeta**, 37, née [Meszkowiczowna/Moszkowiczowna] |
| 7 | 2 | ages | declarant [28/26]; mother 25; reg. hour 11:00 | declarant 25; mother 22; reg. hour [12:00?] |
| 8 | 5 | birth year + residence | born **1876**; declarant residing **Serock** | born **1875**; residing **Popowo** — late-reg year fork changes the child's age by one year |
| 9 | 8 | mother née | [Wananka/Chananka/Bananka] | **[Mielnik?]** — zero overlap; filiation-critical |
| 10 | 1,4,5,6 | witness-1 (Rozenberg) age | [39/29], [40/39], [39/49], 37 | **31 in every act** — B's cross-act consistency argument vs A's per-act letterforms; resolve once |
| 11 | 3,7 | witness Wajnberg/Wajngard/Wajngrod | pools | **Wajngrod** — single letterform cluster, arbitrate once |
| 12 | 10 | birth hour | [4:00 morning?] | [06:00 morning?] — both UNCLEAR, both fresh instances |
| 13 | 7 | birth date | 6/18 Feb | 15 Feb (Greg) |
| 14 | 8 | witness-2 age | 40 | 45 |

### Human-review queue (nominated by readers and merge)

1. **Act 6 region assignment + full re-read** (fork #1) — before anything else on that spread.
2. **Act 1** child-name initial (А/Я/Ха) and mother née (Buchman-pool vs Bursztyn).
3. **Act 2** child Lejb/Berek + mother.
4. **Acts 4/5 side-by-side** — same couple, two late registrations: one review of both acts
   should settle mother's name/age and the act-5 year fork jointly.
5. **Act 9** mother's maiden initial К/В (Kacnerowska/Waznerowska) — both fresh passes pool it.
6. **Act 7** child + mother (fork #3).

### Tier consequence

No act promotes to silver from this merge alone. Acts 3, 9, 10 are one arbitration pass from
promotion; acts 1, 2, 6, 7 carry identity-level forks and are gated on Reader C + human queue.

---

## ADDENDUM — ARBITRATION APPLIED AND JULY PASS RULED (4 Aug 2026, late evening)

Reader C (`readerC-w006-20260804`, frozen `b940c44`) arbitrated all 18 items:
**17 to Reader B, 1 BOTH-UNCLEAR (act-9 née К/В), plus act-1 child initial
BOTH-UNCLEAR within its ruling.** Act 6 was not a region error: both readers
boxed the true №6 quadrant; the July Reader A body wraps a family that is not
on the page.

**Coordinator ruling (msg-048, wave-005 precedent):** the July Reader A pass
(`0f02480`, acts 1–8) is **COMPROMISED** — one confabulated act body, three
unlisted registration-date errors, trades not in the ink, 17/18 arbitrated
against. It is superseded verbatim at
`labels/readerA/superseded/wave006-july-pass-ruled-compromised/`. The fresh
instance pass `readerA-w006-20260804` is promoted to canonical Reader A
(promotion `dfd85b2`, envelope normalization follows the 3e8fce2 pattern).

**Post-promotion comparison (canonical A′ vs B):** acts 3–9 carry **zero**
value conflicts; residual value conflicts are act-1 witness1.age /
witness1.name / witness2.name (C items 1/10 cover the substance: ages read 31
per the year-constant witness; names per B) and act-10 mother.maiden_name +
witness1.name (minor, post-swap residuals, optional human).

**Adopted values:** per Reader C's 18 rulings — B's reading stands on every
ruled item; arbiter-flagged act-6 = Icek / Fiszbin household; Finding 3 is
REVERSED (B's «лавочникъ» 'shopkeeper' was the correct letterform; the July
pass carried trades not in the ink).

**Tier outcomes (2-of-3 gating):**
| Act | Outcome |
|---|---|
| 1 | silver EXCEPT child.given_name (А/Я/Ха initial) → HUMAN queue |
| 2 | SILVER (Berek, Cytrynowicz, Malka Ruchla née Borensztejn) |
| 3 | SILVER |
| 4 | SILVER (child initial noted resolved by C to B's Golda reading context) |
| 5 | SILVER |
| 6 | SILVER (Icek, father Mortka Fiszbin — B wholesale per C) |
| 7 | SILVER (Ruchla Laja, née Kon) |
| 8 | SILVER (née Mielnik per line-break split) |
| 9 | silver EXCEPT mother.maiden_name (К/В initial) → HUMAN queue |
| 10 | silver EXCEPT mother.maiden_name + witness1.name (minor residuals, optional human) |

**Human gold-sample queue additions:** act-1 child initial (identity-critical),
act-9 née initial — joining the standing acts 6/34/39 (1890) package.
