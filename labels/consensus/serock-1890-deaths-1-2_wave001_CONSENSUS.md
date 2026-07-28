# CONSENSUS MERGE — wave 001: Serock 1890 deaths, acts 1–2
Merged 28 Jul 2026 by the coordinating session (consensus stage — blindness no longer applies).
Reader A = claude-fable-5 (pilot-#0 labels, ad-hoc prompt — provenance asymmetry noted).
Reader B = gpt-5.6 sol-ultra (prompt v1.0.0, full schema, bboxes, artifact sha256).
**Sol's label format is adopted as the factory standard going forward — it is strictly better
(act-region bboxes, artifact hashes, dual-date objects, typed observation states).**

## ⚠️ PROVENANCE FLAG BEFORE ANYTHING ELSE
Reader B's prompt sha256 (`88e56abd…`) ≠ the sha256 of prompts/reader_prompt.md as hashed later
by the coordinator (`A2E6C50C…`). Either the prompt file was edited between the two hashings or
the hash methods differ (encoding/line endings). **Reconcile before wave 002** — this is the
provenance discipline catching real drift on day one, which is what it is for.

> **RESOLVED 28 Jul 2026:** re-hash of `prompts/reader_prompt.md` (raw AND LF-normalized)
> = `88e56abd…` — **matches Reader B.** Reader A's `A2E6C50C…` was hashed against an
> intermediate state of the file during authoring. Sol's provenance chain is intact;
> Reader A wave-001/002 labels carry a stale hash → `PROVENANCE_ERRATA` at ingest,
> content stands. Details + v1.1 patch: `FOR_SOL_wave002_brief.md`.

## ACT 1 — field-level merge

| Field | Reader A | Reader B | CONSENSUS |
|---|---|---|---|
| act/type/no/year/town | death, №1, 1890, Serock | same | **AGREE → CONFIDENT-eligible** |
| registration date | 1 Jan 1890, 11 AM — "no dual date present" | **dual: 1/13 Jan 1890**, 11 AM | ⚠️ **STRUCTURAL DISAGREEMENT** — is a dual date on the ink? → zoom arbitration #1. Affects acts 3–6 readings too. |
| event date | 30 Dec 1889, 9 AM | same (Julian; Gregorian derived) | **AGREE** (B's dual-calendar handling adopted) |
| deceased given name | Ru[ch]la [unclear] | **Fruma** | 🔴 **[unclear: Ruchla/Fruma]** → zoom arbitration #2 (letter-shapes Ру vs Фру) |
| deceased surname | Malowanczyk | [unclear: Małowiańczyk/Małowalczyk] | **root AGREED (Малован-/Маловян-чикъ)**; middle cluster → [unclear], candidates pooled |
| age / sex | 61, female | 61, female | **AGREE → CONFIDENT-eligible** |
| father | Abram (parents deceased) | Abram | **AGREE → CONFIDENT-eligible** |
| mother given | Rifka | **Cyfra** | 🔴 **[unclear: Rifka/Cyfra]** (Р/Ц cursive confusable) → arbitration #3 |
| parents' surname | [unclear: Litoszewicz/**Antoszewicz**] | **Antonowicz** | **[unclear: Antoszewicz/Antonowicz]** — ⚠️ corpus evidence: act 5/1890 (same clerk) carries a clearly legible «урожденной Антошевичъ» → consensus LEANS Antoszewicz, pending arbitration #4 |
| widowed husband | [unclear: Cuka/Szuka] | **Judka (Юдка)** | **[unclear: Judka/Szuka]** — B's Judka is onomastically plausible (Юдка = Yudel dim.); arbitration #5 |
| declarant 1 | Izrael **Ioskowicz, FELDSHER** (occupation), 55 | Izrael **Ickowicz GOLDFARB** (surname), 55 | 🔴🔴 **THE HEADLINE DISAGREEMENT**: same ink read as «фельдшеръ» (occupation) vs «Гольдфарбъ» (surname). This is the *literal Goldfarb trap* named in skills/cyrillic-paleography.md. Also Іосковичъ vs Ицковичъ. One reader is wrong; both were properly uncertain-shaped. → zoom arbitration #6 (check for occupation slot: if no other occupation word exists for declarant 1, "фельдшеръ" as occupation is structurally favored by the formula, which expects name+occupation+age). |
| declarant 2 | Jankel Borensztejn, szkolnik, 40 | Jankiel Berenstein, [unclear: szkolnik?], 40 | **AGREE** (spelling variants of same name; szkolnik pooled → PROBABLE) |
| signatures | both declarants signed | two non-registrar signatures visible | **AGREE** |

## ACT 2 — field-level merge (abridged; same pattern)
- **AGREE → CONFIDENT-eligible:** act №2, death, Serock 1890; deceased **Chana**, 9 months,
  female; father Lejba/Lajba (е/а variant — same name); mother Laja; same declarant pair with
  identical ages (55/40) — the within-register consistency check passes across BOTH readers.
- **Registration date:** A: 18 Jan single · B: dual 8/20 Jan → ⚠️ arbitration #7 (couples to #1:
  «восемьнадцатаго» vs «восьмаго/двадцатаго» is one pen-stroke cluster apart).
- **Deceased surname:** A: [unclear: Auksztukalska] · B: Auksztuk → root **Аукштук- AGREED**;
  ending → [unclear: -ъ/-альская]; note act 3's declarant «Лейбъ Укштукальскій» (Reader A,
  batch 2) — if the same family, the fuller form gains corpus support. Arbitration #8.
- **Mother's maiden name:** A: [unclear: Konkol/Konkal] · B: [unclear: Korky/Korki] → **all
  candidates pooled: [unclear: Konkol/Konkal/Korki]** (нк vs рк cluster). Arbitration #9.

## WHAT WAVE 001 PROVED
1. **The protocol works on real ink**: structure/dates/ages/sexes/father converge (the
   CONFIDENT-eligible pool exists); names diverge exactly where cursive is genuinely ambiguous
   (the [unclear] pool exists and is honest).
2. **Cross-vendor disagreement caught what same-model-twice never would** — the
   feldsher/Goldfarb split is two different *parses of the formula slot*, not two glyph guesses.
3. **The corpus-level thesis (§9.1) fired twice already**: act 5 arbitrates act 1's surname;
   act 3 may arbitrate act 2's. Same clerk, same year — the register solves itself.
4. **Nine zoom arbitrations** — all human-checkable in ~15 minutes from the two saved scans, or
   by a targeted third read of the specific pixel regions (B's bboxes make this trivial).
5. Provenance discipline caught a prompt-hash drift on day one. Reconcile before wave 002.

## NEXT
- Jake (or a third targeted pass) arbitrates the 9 items; results promote fields to gold.
- Reader B still owed: acts 3–6 (Serock_1890_deaths_03-06.jpg) — Reader A pass already frozen.
- Adopt Sol's schema for all future Reader A labels; regenerate A's wave-001 labels in that
  schema only if P2's ingest requires it (content stands).

---

## WAVE 001 RESOLVED — Reader C arbitration applied (2-of-3 rule, 28 Jul 2026)
Reader C (independent Opus session, blind to reader identities, worked from 4×–22× upscaled
crops of the original pixels): report at readerC_arbitration_wave001.md.

| # | Dispute | Verdict (votes) | Promoted value |
|---|---|---|---|
| 1 | Act 1 dual date? | SINGLE (A+C, C SURE) | reg. 1 Jan 1890 — single date |
| 2 | Рухля/Фрума | Рухля (A+C SURE; closing genitive «Рухли» kills Фрумы) | **Ruchla Malowanczyk** |
| 3 | Рифки/Цифры | Рифки (A+C SURE) | mother **Rifka** |
| 4 | parents' surname | Антошевичъ (A-lean + C SURE; letterform match to act 5) | **Antoszewicz** |
| 5 | widower | Цука (C LEANING; A had it as candidate; Юдка out) | [PROBABLE: Cuka] — stays sub-gold |
| 6 | фельдшеръ vs Гольдфарбъ | **(a) feldsher** (A+C SURE; signature reads Іосковичъ; formula would be defective under (b)) | **Izrael Ioskowicz, feldsher, 55** |
| 7 | Act 2 date | восемьнадцатаго — single 18 Jan (A+C SURE) | reg. 18 Jan 1890 |
| 8 | Аукштукъ/-альская | **Аукштукальская** (A+C SURE; hyphen line-break «-ская» explains the truncated reading) | **Chana Auksztukalska** |
| 9 | maiden name | Конколь (A+C SURE) | née **Konkol** |

All promotions are consensus-PROBABLE (2-of-3). Gold-tier promotion still requires the sampled
human check per §13 — these two acts are nominated for that sample.

### ⚠️ THE LESSON OF WAVE 001 — PROMPT-INDUCED BIAS, documented
Reader B's five name errors scatter, but its two DATE errors share one cause: **the shared
prompt says "dual dating common after ~1868 — capture BOTH," and Reader B manufactured dual
dates on two acts where the ink carries one.** The prior became a hallucination template.
**Prompt v1.1 fix (for Sol at the P2 gate):** reword to "capture both dates ONLY when two
day-words are physically present in the ink; single-dated acts are common in some register
years — the absence of a dual date is normal and must not be corrected."
Secondary notes: Reader C's aside gives declarant 2's act-2 age as 45 and the closing-name as
«Хаи» — both conflict with A+B (40; Хана/Chana); logged as two NEW minor [unclear]s rather
than accepted (C was not asked those questions; asides don't get votes).
Scoreboard for the record (not a leaderboard claim, n=9): A+C aligned 9/9; B's misses were
2 prompt-bias dates, 5 name misreads incl. the literal Goldfarb trap, 1 truncation at a
hyphen line-break, 1 plausible-but-wrong widower name. Cross-vendor disagreement caught 100%
of these before they could reach gold. The protocol is the product.
