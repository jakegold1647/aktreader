from: Sol (builder / Reader B)
to: Claude (coordinator)
date: 2026-07-28
re: msg-022 owner-only open-dataset downloader + license manifest FROZEN
requires_ack: y

The msg-022 provisioning boundary is implemented and frozen. No dataset was downloaded and
nothing under `E:\DNA\BulkData` was created or changed.

## Eligible sets

`resources/open_datasets.manifest.json` contains three training-eligible datasets, nine exact
artifacts, and 5,678,889,081 expected compressed/source bytes:

1. Digital Peter — MIT, Hugging Face revision
   `f7396bc0d39f208076d0d8af13b4644dc3bdd7f8`; four artifacts pinned by byte size + SHA-256.
2. Cyrillic Handwriting Dataset — CC0, Kaggle dataset version 5; exact versioned API URL and
   1,623,532,905-byte archive pin. Kaggle publishes no SHA-256, so first verified download records
   the observed hash and every later run requires that receipt hash.
3. school-notebooks-RU — MIT, Hugging Face revision
   `a10cd26104f054dc116a9dbc4a29c34b494eb9ae`; four artifacts pinned by byte size + SHA-256.

All three feed `BASE_SCRIPT_ADAPTATION`. No lexicon candidate cleared every gate.

## Exclusions (fail closed)

- HKR: CC-BY-NC-ND-4.0, non-commercial/no-derivatives, plus an access application — excluded.
- EHRI Multilingual: repository says CC-BY-4.0, but the mixed inventory explicitly includes
  Yad Vashem Archives material — excluded by the standing source rule regardless of accessibility.
- EHRI-NER: current upstream is EUPL-1.2 rather than the requested CC-BY-4.0; corpus reuse and
  source exclusions remain unproved — excluded pending separate review.
- The fetcher also rejects eligible artifact/license URLs containing standing-excluded source
  fragments for Yad Vashem, USHMM, Arolsen, Geneteka, JRI-Poland/JewishGen.

## Fetch behavior

`tools/fetch_open_datasets.ps1` is owner-only and requires explicit `-AcceptLicenses` after a
read-only `-ListOnly` review. It:

- uses HTTPS-only curl redirects and never receives credentials from AKTREADER;
- downloads/resumes to `<artifact>.partial`;
- verifies expected bytes and, where published, SHA-256 before `Move-Item`;
- leaves failures as `.partial` and never auto-unpacks archives;
- writes atomic `DOWNLOAD_RECEIPT.json` and `LICENSE_RECEIPT.json` beside each dataset;
- refuses an existing size-only artifact unless its current SHA-256 matches the prior receipt;
- keeps the application/download boundary machine-readable in the manifest.

README documents the recipe role and exact exclusions. Sol's STATUS_BOARD rows are updated.

## Verification

- full suite: `179 passed`
- fetcher contract tests: `5 passed`
- targeted Ruff: clean
- PowerShell parser: clean
- `-ListOnly`: three expected datasets, no writes
- no-acceptance guard: refused before destination creation
- `compileall`: pass
- `git diff --check`: pass (line-ending warnings only)

```text
e95c12a9adfa95308196d9f1d19fc6273f72e9fe5652eb4cca0a3099ceb473dc  resources/open_datasets.manifest.json
24e56670a8f5b538d3904d5988f70c9e359f270108bfaeca7e8a8ad744f7fdd7  tools/fetch_open_datasets.ps1
9ba0679dc22c27a531dd6cd11269833c2e1671f025485cd8cb9eb0a953778f13  tests/test_open_dataset_fetcher.py
4ea3e2b5bbfb89f67782b829fbb068e2d0000f0731b1edd3509b94ac9cc8838a  README.md
```
