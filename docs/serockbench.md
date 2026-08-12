# SerockBench

SerockBench is AKTREADER’s scan-backed evaluation contract for uncertainty-honest civil-register
extraction. It is not a leaderboard built from vendor OCR claims.

## Corpus and isolation

- 36 human-verified acts: 29 Serock and 7 Pułtusk.
- 21 clerk-year groups.
- Russian-language births, marriages, and deaths.
- Every gold record is evaluation-only.
- `gold/clerk_year_holdout.json` forbids training overlap by clerk-year, not merely by act ID.

Before scoring, the harness rejects duplicate gold record IDs and duplicate record or clerk-year
IDs in the holdout manifest. Equality checks use sets only after uniqueness is established, so a
repeated gold row cannot receive extra metric weight while appearing to match the holdout.

Twenty-four gold records currently have localized scan artifacts. Twelve remain acquisition
targets; `examples/p2-baseline.want-list.json` maps five Serock gaps to exact zespół 318/0826d
units and ranges with `SOURCE_OBJECT_415`, while seven Pułtusk records fail closed pending their
separate collection map. Until those inputs are localized, a run’s maximum honest prediction
coverage is 24/36.

## Headline metrics

- **Filiation field exact match:** exact parentage-field agreement, including mother’s maiden
  name and typed observation state.
- **Filiation act exact match:** all evaluated filiation fields in an act must match.
- **Wrong-but-CONFIDENT:** incorrect CONFIDENT assertions divided by evaluated CONFIDENT
  assertions. Zero CONFIDENT assertions produce `N/A`, never a passing zero.
- **Calibration:** correctness reported separately for CONFIDENT, PROBABLE, and UNCLEAR.
- **Observation-state accuracy:** exact distinction among a value, `ABSENT_ON_FORM`, `BLANK`,
  `STATED_UNKNOWN`, and `ILLEGIBLE`.
- **Abstention rate:** the fraction of evaluated fields for which the Reader declines to assert a
  resolved value.

The P2 targets are at least 90% filiation exact match and below 2% wrong-but-CONFIDENT.

## Why wrong-but-confident leads

Genealogical extraction is asymmetric: an honest unresolved reading invites review, while a
plausible invented parent can corrupt a family graph. Wave 001 demonstrated the mechanism when a
prompt prior manufactured dual dates. Wave 002 caught a line-broken `Герш-/вельдъ` surname that
one Reader split into a phantom spouse; that one parse error cascaded through sex, age,
filiation, and survivor fields. Blind disagreement intercepted both failure classes before gold.

## Reproducing a report

```powershell
python -m aktreader eval `
  --predictions .\runs\p2-local-baseline\predictions `
  --gold-dir .\gold\acts `
  --holdout .\gold\clerk_year_holdout.json `
  --output .\runs\p2-local-baseline\serockbench.json `
  --strata-table .\runs\p2-local-baseline\serockbench-strata.md
```

Preserve predictions, checkpoint, runtime fingerprint, prompt/schema hashes, and the generated
JSON report and table together. Missing predictions reduce coverage; they are never backfilled
from gold.

## Reading the stratified table

The Markdown table is a count-backed view of the JSON report's `stratified` section, not a new
scoring path. Each row is one recorded register language × field family. Wrong-but-CONFIDENT is
shown before exact accuracy because a confidently wrong genealogical assertion is the primary
risk. Every rate carries its numerator and denominator; a zero denominator is `N/A (0/0)`, never
0%.

Coverage divides predicted fields by gold-scorable fields. Wrong-but-CONFIDENT divides wrong
CONFIDENT fields by all evaluated CONFIDENT fields. Exact accuracy and abstention use predicted
fields as their denominator. Register language is copied from gold and never inferred from year,
so a missing language remains `unknown` and no Polish row appears until Polish gold exists.

The current gold vocabulary supports the broader families `names`, `dates`, `ages`,
`person_attributes`, and `register_other`. It cannot honestly split names into given names,
surnames, and patronymics yet; that remains a gold-vocabulary limitation rather than a missing
display feature.

## Runtime builds are part of the measurement

A report is only comparable to another report produced by the same runtime build. The
2026-08-04 P2 local baseline on llama.cpp b10274 completed 3 of 24 jobs; the other 21 were
rejected by the pipeline's own integrity gates rather than by any infrastructure fault. Of
those, 17 had passed the same gates under the previous build with identical weights, seed 0,
and temperature 0. The build alone changed the outcome, which is why the runtime fingerprint
is folded into every job fingerprint and why cross-build metric comparison is not permitted.

That run is the current honest floor for the local reader: filiation exact match 0%, and a
wrong-but-CONFIDENT figure of `N/A` because the model issued no CONFIDENT assertions at all —
recorded as `N/A`, never as a passing zero. Run notes and the canonical report live beside the
predictions under `runs/p2-local-baseline/`.
