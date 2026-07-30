from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-29
re: owner-directed Serock public-source audit and zero-cost standard seed
requires_ack: n

The owner directed a web search for free Serock manuscript standards. I performed source
discovery only; no archive was scraped or mirrored, no login was used, and no restricted
database content was downloaded.

Frozen artifacts:

- `resources/serock_public_source_inventory.json`
- `resources/serock_public_act_leads.csv`
- `docs/serock-zero-cost-standards.md`

Findings:

1. No complete openly licensed scan-aligned Serock transcription corpus was found.
2. Howard Orenstein's public 2006-era post supplies four exact act coordinates:
   D20/1878, D8/1878, D16/1882, and M3/1900. The legacy image URLs are unavailable.
   These are stamped `REFERENCE_ONLY_DO_NOT_TRAIN`.
3. NLI/CAHJP catalogs a 174-leaf Serock birth/marriage/death manuscript for 1812-1820,
   but explicitly reports no online access.
4. A public Pieniek GEDCOM exposes many Serock act coordinates, but its source block identifies
   JRI-Poland. It is discovery-only under the standing exclusion.
5. The zero-cost lawful seed is internal manuscript redundancy in the permitted local scans:
   act principal + closing-formula repeat + SkU/SkM/SkZ row, signatures, and annex duplicate
   certificates. These remain WEAK_REFERENCE until image-attested.

Recommended immediate benchmark seed: ten 1890 death acts where prose, closing formula, and
SkZ row agree; ask the human only to confirm same-name shape and act number, admit only verified
fields, and sequester the ten from training. This yields structured-extraction holdout truth,
not continuous-transcription/CER gold.
