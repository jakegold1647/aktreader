from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-28
re: QUEUE ADDITION (owner-directed): open-dataset downloader for LoRA base-script corpus
requires_ack: n

New queue item (slot it after the msg-021 schema fix; before release polish):

**Build `tools/fetch_open_datasets.ps1` + `resources/open_datasets.manifest.json`** — the
owner-run downloader for the compliant open Cyrillic/handwriting training sets from
TRAINING_CORPUS_PLAN T3. Same trust pattern as the model fetcher: manifest pins exact
URLs + expected SHA-256 (or size + post-download recorded hash where upstream publishes none),
download to `.partial`, verify, move; per-dataset LICENSE_RECEIPT capture (license name, URL,
retrieval date) written alongside the data under E:\DNA\BulkData\Training_Sources_Open\<set>\.

Candidate sets (verify current URLs/licenses yourself; drop any whose license fails the
training-eligibility bar, and say so): Digital Peter (Peter the Great cursive, open), the
Cyrillic Handwriting Dataset, HKR (handwritten Kazakh/Russian), school-notebooks-RU, and the
EHRI/EHRI-NER text corpora (CC BY 4.0; text-side name-lexicon value). NO Yad Vashem, USHMM,
Arolsen, Geneteka, or JRI content — standing exclusion regardless of accessibility.

AKTREADER itself performs no downloads: the tool is owner-executed, like fetch_p2_model.ps1.
Deliverable: script + manifest + a README note on how each set feeds the LoRA recipe
(base-script adaptation vs lexicon), posted to inbox_claude when frozen.
