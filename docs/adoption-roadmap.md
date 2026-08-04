# Adoption roadmap (owner-gated)

Priorities distilled from a 2026-08 survey of the communities this tool is for — Polish/
Russian-partition genealogy transcription groups (JRI-Poland, JewishGen divisions, Geneteka)
and open HTR infrastructure (HTR-United, Kraken). Their verdict: the credible first deliverable
is a **benchmark package, not the app** — stratified accuracy with calibrated confidence, open
ground truth in standard formats, and verifiable local-only claims, with the tool positioned as
a draft assistant and never an auto-publisher. The judging principle is the project's own
abstention thesis: no ambiguous surname should become a definitive database fact merely because
a model was required to emit one string.

These tasks need owner-held materials or owner judgment (see the boundary in
[`CONTRIBUTOR_TASKS.md`](CONTRIBUTOR_TASKS.md)); they are scoped here so the order of work is
explicit.

## 1. Stratified benchmark report

Extend the evaluation report with per-field strata (given name, surname, patronymic, dates,
ages, filiation) × script era (Cyrillic 1868–1915 / Polish), each with prediction coverage,
exact accuracy, wrong-but-confident rate, and abstention rate. Publishable as a single table;
the wrong-but-confident column is the headline number, not overall accuracy.
Builds on `src/aktreader/evaluation.py`; the reduced-schema field map already encodes the
field vocabulary. No new gold required.

**Shipped 2026-08-04 (first slice):** the evaluation report now carries a `stratified` section
- field family (names / dates / ages / person_attributes / register_other) x register language
(`ru` today, `pl` slots in when Polish gold lands, `unknown` never guessed) with coverage,
exact accuracy, wrong-but-confident, and abstention per stratum. The given/surname/patronymic
split awaits a finer gold vocabulary; the publishable one-table rendering is still open.

## 2. Ground truth in an open interchange format

Export gold acts (transcription layer only, per the privacy window) to a PAGE-XML or ALTO
representation so HTR-United-style consumers can ingest them, with a regenerate-and-diff test
like the planned schema reference. Owner-gated: requires a rights/privacy pass over each act
before anything ships.

## 3. Spreadsheet-native adjudication round-trip

Reviewers live in Excel. Extend the compare/adjudication path so a disagreement table exports
to CSV/XLSX and the adjudicated answers re-import losslessly (BOM, encoding, and formula-
injection safety included). The contributor-scoped `compare --csv` task (#2 in
CONTRIBUTOR_TASKS) is the first slice; the re-import half is owner-gated because it feeds
frozen evidence.

## 4. Testable no-egress statement

Turn "local-only" from a promise into an assertion: a documented inventory of network
endpoints (none), a CI guard test that fails if networking modules appear in `src/aktreader`,
and a pinned dependency statement (SBOM-style) covering the five runtime dependencies. Small,
high-leverage for trust; owner-gated only in the wording of the guarantee.

**Shipped 2026-08-04:** `tests/test_no_egress.py` (static import blocklist + pinned runtime
dependency set + socket-disabled runs of `doctor`/`prompt-verify`/`eval`) and the README
section "Verifiable no-egress".

## Sequencing

4 → 1 → 3 → 2. The no-egress guard is an afternoon; the stratified report is the benchmark
centerpiece; spreadsheet round-trip unblocks human adjudicators; PAGE/ALTO export waits for
the per-act rights review.
