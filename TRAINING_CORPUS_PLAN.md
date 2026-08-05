# TRAINING CORPUS PLAN — the source material for the LoRA
Written 28 Jul 2026. Goal: a massive-breadth corpus of scan→verified-extraction pairs
("decrypted language") produced by the §13 dual-reader factory, sufficient to LoRA an open
VLM to expert-level reading of Congress-Poland civil acts (§12).

## The design principle: SCRIBE BREADTH OVER TOWN DEPTH
The model must generalize across *hands*, not memorize three clerks. Every clerk-year is
effectively one handwriting style; a register year averages 30–100 acts. Therefore the
corpus is stratified by CLERK-YEAR, not by volume: target ~50–150 distinct clerk-years
across as many towns as practical, sampling 20–60 acts per clerk-year, rather than
exhausting any single fond first. Depth comes free later (Pułtusk full-map, §10); breadth
must be designed in from the start.

## Diversity axes to cover deliberately
1. **Language/era**: Russian 1868–1915 (core) · Polish 1808–1868 (older formula, Latin
   cursive) · Polish 1915+ (Pułtusk fond runs to 1935 — closes the Polish gold gap).
2. **Act types**: births/marriages/deaths in ratio ~40/20/40, plus skorowidze index pages
   and annexes as separate task types (different layouts, cheap labels).
3. **Confession**: Jewish registers (core mission) + Catholic/Lutheran civil acts of the
   same era — SAME Napoleonic formula, different name distributions and hands. This
   multiplies available scribes ~20× and prevents the model from overfitting "every name
   is Jewish." The tool's users include Polish Catholic researchers anyway.
4. **Condition**: deliberately include faded, stained, bled-through, and skewed pages —
   the [unclear]-generation behavior must be trained, not just the reading.
5. **Register position**: opening pages, mid-register, year-end summaries, marginalia-heavy
   acts (corrections/annotations are high-value, rare, and layout-breaking).

## Source tiers (in acquisition order)
### T0 — ON DISK TODAY (start immediately, zero acquisition)
`E:\DNA\Decode_Package\01_Cyrillic_Serock\` — hundreds of Serock scans 1874–1904, incl.
skorowidze and annexes. Est. 1–2k acts, ~25 clerk-years, Russian only. The pilot kiln for
the dual-reader factory: run it end to end here before acquiring anything.
### T1 — PUŁTUSK FOND 84 (the §10 pilot; the depth pillar)
~12,300 scans, 1875–1935, Russian AND post-1915 Polish. Est. 25–40k acts, ~60 clerk-years.
Acquired per §10's polite-pace rules only, after Jake's P3 gate go-ahead. Also the §9.2
town-graph corpus — same download serves both purposes.
### T2 — THE DISTRICT RING (breadth, same archive family)
Nasielsk (fond 116, 1875–1913, 4,466 scans) · Wyszków (fond 98, 1874–1907, 2,103 scans) —
already surveyed by the research project. SAMPLE, don't exhaust: ~40 acts per clerk-year.
### T3 — THE BREADTH SWEEP (the generalization pillar)
Stratified sampling across many fonds hosted on the Polish State Archives' own portal
(szukajwarchiwach.gov.pl — the state's public scan service; many Congress-Poland fonds,
Jewish and Catholic, have full scans there) and PTG front-ends where szukajwarchiwach
lacks them. Target: 50–100 additional fonds × 30–60 sampled acts each, chosen to spread
provinces, decades, and confessions. Selection is scripted; downloading is paced per the
same politeness rules; state-portal sources are preferred (public service, public-domain
records, no third-party terms).
### T4 — THE FLYWHEEL (permanent, grows forever)
§11 corrections from real users + Hélène-style expert verifications. Highest-value labels
in the pool; re-LoRA cycles consume them.

## Label production (per §13)
Dual frontier readers (Claude-family + GPT-family), same prompt, blind to each other →
consensus fields eligible for training; disagreements → [unclear] (also trained — the model
must learn to OUTPUT [unclear]); cross-act constraint validation (witness ages, dual dates)
→ upgrades/flags; human spot-check sampling: 100% for gold/eval, ~5% for bulk training
data, 100% of high-disagreement acts. **Eval holdouts are human-verified only and are
sequestered by CLERK-YEAR (no clerk appears in both train and eval) — otherwise the
benchmark measures handwriting memorization, not reading.**

## Clerk-year reservation (check this before assigning a wave)

**Before assigning a wave, check this table.** Reading a SEQUESTERED clerk-year produces
evaluation material and exactly zero training-eligible records. Waves 001–006 consumed only
sequestered years (Serock 1890 and 1877) and so produced no training pool at all — that was
the holdout working as designed, not a defect in the waves, but it is not repeatable if the
adapter is ever to have inputs.

The reservation runs in one direction only. A SEQUESTERED year can never become training
material. An OPEN year, **once read for training, can never afterwards become holdout
material** — not because the training data spoils, but because a holdout the model has
already trained on measures handwriting memorization instead of reading, which is the exact
failure the clerk-year rule exists to prevent. Practically: do not mint gold records in a
year that has already been read into the training pool.

That asymmetry is why this table is written down. `validate_training_split` in
`src/aktreader/training.py` already fails closed on the first direction — an export whose
clerk-years touch the holdout raises `training/evaluation clerk-year leakage`. Nothing
re-validates *past* exports against a holdout that grew later, so the second direction has
no automated guard and is enforced here by reading the table first.

| Clerk-year | Status | Local acts |
| --- | --- | --- |
| 1876 | SEQUESTERED | ~123 |
| 1877 | SEQUESTERED | ~80 |
| 1878 | OPEN | ~83 |
| 1879 | OPEN | ~87 |
| 1880 | OPEN | ~44 |
| 1881 | OPEN | ~157 |
| 1882 | SEQUESTERED | ~270 |
| 1883 | SEQUESTERED | ~91 |
| 1884 | SEQUESTERED | ~99 |
| 1885 | SEQUESTERED | ~129 |
| 1888 | SEQUESTERED | ~138 |
| 1889 | OPEN | ~119 |
| 1890 | SEQUESTERED | ~65 |
| 1891 | SEQUESTERED | ~93 |
| 1892 | SEQUESTERED | ~141 |
| 1893 | SEQUESTERED | ~126 |
| 1894 | SEQUESTERED | ~110 |
| 1895 | OPEN | ~67 |
| 1896 | SEQUESTERED | ~109 |
| 1898 | OPEN | ~95 |
| 1899 | SEQUESTERED | ~96 |
| 1900 | OPEN | ~101 |
| 1902 | SEQUESTERED | not harvested |
| 1903 | SEQUESTERED | ~98 |
| 1904 | OPEN | ~190 |

Nine OPEN clerk-years carrying roughly **943 acts** are already harvested locally, against a
launch-gate minimum of 100 grounded training records. The training bottleneck is reading
throughput on these years, not acquisition. The densest are 1904 and 1881.

Pułtusk is reserved differently and more tightly: `84|putusk|` **1877, 1878, 1885, 1886, and
1890** are all sequestered. SPEC §12 names Pułtusk as training slice #1, so when that corpus
is acquired those five years must be routed to evaluation and the training slice drawn from
the others.

**How this table was derived** (re-derive it rather than trusting the prose):

- Status comes from `holdout_clerk_year_ids` in `gold/clerk_year_holdout.json` — any Serock
  year listed there is SEQUESTERED, any harvested year absent from it is OPEN.
- Act counts are approximations from `BulkData/Serock_0826d/HARVEST_STATE.txt`, summing the
  highest act number reached per act-type across completed (`OK`) ranges in each year. They
  are page-range derived, so treat them as ±a few acts, not as a census.
- "not harvested" means the year is sequestered by the holdout but has no local scans.
- `tests/test_clerk_year_reservation.py` asserts the SEQUESTERED column still matches the
  holdout file, so this table cannot silently drift out of date.

## Volume targets (realistic for a strong LoRA)
- Floor to train something useful: ~3–5k verified acts (T0 + Pułtusk first slice).
- Target: **20–40k acts across 100+ clerk-years** (T0–T3) — ample for LoRA on an 8–30B VLM.
- Eval: ~500 human-verified acts stratified across all axes, sequestered forever.

## Compliance notes (unchanged from §7/§10, restated because training raises stakes)
- Scans: Polish state-archive civil records ≥100 years old (privacy default), acquired at
  human-polite pace through public front doors; any terms wall stops that source and the
  finding goes to Jake. State portal preferred over third-party front-ends.
- NO content from Yad Vashem, USHMM, Arolsen, Geneteka indexes, or JRI-Poland indexes in
  training data — ever. Labels come from OUR readers + OUR verifications of the scans.
- The 1915/1935 tail of Pułtusk: apply the 100-year rule per act at training time (a 1935
  birth act is excluded until 2035; 1935 deaths clear the 80-year convention — encode the
  per-type rule, don't hand-wave it).
- Storage: the capture/corpus tree lives on the archive box (mirrored + B2), organized
  fond/year/scan with the label JSONs beside the images.

## Sequence
1. NOW: pilot the dual-reader factory on 10 T0 acts (manual: one prompt to each frontier
   model) — validates the protocol and the prompt before any code depends on it.
2. P2 (Codex): the same protocol, coded, on the 36-act gold set → SerockBench v1.
3. P3 gate → T1 acquisition → Pułtusk read = training slice #1 + town graph.
4. T2/T3 sampling scripts + paced acquisition → the breadth corpus.
5. First LoRA (rented GPU, §12) at ~5k acts; re-run at 20k+; local model becomes default
   Reader when it clears the human-holdout bar.
