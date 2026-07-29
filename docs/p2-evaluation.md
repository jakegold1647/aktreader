# P2 evaluation report

**Status:** P2 gate accepted; Wave 001/002 diagnostics recorded; baseline addendum **NOT RUN**

**Report date:** 2026-07-28

## Wave 001 arbitration diagnostic — disputed fields only

This is the first observed pipeline diagnostic, so it is reported before the unrun local-model
baseline. Reader C independently arbitrated the nine fields on which Readers A and B had
disagreed. The final outcomes used the 2-of-3 rule.

| Diagnostic | Observed result |
|---|---:|
| Disputed-field sample | 9 fields |
| Reader B aligned with the final 2-of-3 outcomes | **0/9** |
| Disagreements intercepted before gold | **9/9** |
| Promotion after arbitration | **PROBABLE**, not gold |

The nine Reader B disagreements comprised:

- 2 manufactured dual dates where only one date was physically present;
- 5 name/role reads;
- 1 surname truncated at a hyphenated line break; and
- 1 widower-name read.

The fair paired summary is **2 prompt-induced date errors + 7 paleographic/parse errors**, followed
by **0 dual-date recurrences across Wave 002's four acts** after the corrective prompt wording.

This is a deliberately selection-biased, disputed-only sample. It is **not benchmark accuracy**,
an overall Reader B error rate, a comparison of model families, or evidence that either other
Reader would score 9/9 on unselected fields. Its valid result is narrower: the blind-disagreement
protocol caught all nine selected conflicts before any could enter gold.

Every 2-of-3 promotion remains `PROBABLE`. The two acts are only candidates for the required
human sample; no arbitration promotion becomes human-verified gold without that verification.
The resolved Wave 002 disputed-field diagnostic is summarized below under the same limit.

Evidence:

- [Wave 001 resolved consensus](../labels/consensus/serock-1890-deaths-1-2_wave001_CONSENSUS.md)
- [Reader C arbitration](../labels/consensus/readerC_arbitration_wave001.md)

## Wave 002 resolved arbitration — disputed fields only

Wave 002 covers Serock 1890 death acts 3–6. Reader C arbitrated the 14 selected A/B disputes;
the coordinator then applied the 2-of-3 rule in the `RESOLVED` appendix.

| Diagnostic | Coordinator-recorded result |
|---|---:|
| Disputed-field sample | 14 arbitrations |
| Reader A prevailed | **12** |
| Reader B prevailed | **1½** (#3 plus the occupation half of split #5) |
| Reader B manufactured dual dates | **0 recurrences across 4 acts** |
| Promotion after arbitration | **PROBABLE**, not human-verified gold |

The reported fractional scoreboard follows the coordinator's convention for split #5; it is
not an overall Reader score. As in Wave 001, this sample contains only disagreements and is
selection-biased. It is not benchmark accuracy.

The highest-value catch was act 6. Reader B split the line-broken surname
`Герш-/вельдъ` into a phantom spouse, “Gersz Weksler”; the error then cascaded into the
principal's sex, name, age, filiation, and survivor structure. Cross-reader disagreement caught
the fork before gold. Act 6 is now explicitly quarantined in `gold/manifest.json` pending the
mandatory human sample, regardless of Reader C's decisive vote.

Acts 3–5 also remain outside `gold/`: their resolved fields are consensus-PROBABLE, while this
repository's eval holdout is human-verified. No Wave 002 field has been added to gold. They are
now machine-readable `SILVER` records—training-only, never evaluation—pending any later sampled
human promotion.

Evidence:

- [Wave 002 resolved consensus](../labels/consensus/serock-1890-deaths-3-6_wave002_CONSENSUS.md)
- [Wave 002 Reader C report](../labels/consensus/readerC_arbitration_wave002.md)

### Tier disposition

The machine-readable [silver manifest](../labels/silver/manifest.json) assigns resolved acts 1–5
to `SILVER`: training-eligible 2-of-3 consensus, never evaluation, never human-verified. It pins
all source labels and resolution documents by SHA-256 and content-addresses five materialized
field payloads. The training exporter rejects the current holdout because Serock-1890 appears in
both sets; a model-ready export is possible only with an explicitly selected, non-overlapping
evaluation holdout. Act 6 remains untiered and quarantined pending the mandatory human check.

## Prompt v1.1 correction

Wave 001 exposed prompt-induced date bias: the earlier wording made dual dating sound expected,
and Reader B manufactured a second date in two disputed fields. Prompt v1.1.0 now requires two
day-words to be physically visible before recording a dual date. If the second day-word is
uncertain, the required response is `[unclear: single/dual]`; a single-dated act is normal and
must not be “corrected.”

The frozen raw-byte SHA-256 is:

```text
9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09
```

The digest is recorded in [`prompts/manifest.json`](../prompts/manifest.json) and
[`prompts/reader_prompt.sha256`](../prompts/reader_prompt.sha256). The patch is a documented
protocol correction, not a retroactive benchmark result.

## Prompt v1.2 release

Wave 002 supplied three further parse safeguards: join a possible line-broken surname before
inventing a new person; resolve `умеръ` versus `умерла` before downstream gendered parsing; and
preserve the possibility that some clerks render normalized `-feld` literally as `-вельдъ`.
The globally shared prompt generalizes those rules and deliberately omits the source act,
surname, and clerk identity so it does not embed a held-out Serock-1890 answer.

Prompt v1.2.0 is frozen at commit `b11bca0`; its raw-byte SHA-256 is:

```text
ea0e83756698496414ba654de70805179829848f31acc644112b1e51f48e955f
```

Frozen v1.1 remains auditable at commit `156393b`; it was not rewritten in place.

## LocalReader baseline — NOT RUN

The owner resolved the former Smart App Control block as an owner-level OS-policy decision;
standard Defender remains active. The coordinator verified the exact runtime, but the locked
model and projector files are not on disk. No scan has been submitted and no prediction exists.
AKTREADER did not change a security setting or attempt a bypass.

| Run fact | Recorded state |
|---|---:|
| Baseline run state | **NOT RUN** |
| Model invocations | **0** |
| Gold records evaluated | **0/36** |
| Scan-backed gold inputs available | **24/36** |
| Gold records marked `NOT_LOCALIZED` | **12/36** |
| Sequestered clerk-year groups | **21** |
| Runtime verification | **PASS — 10167 (ee3d1b54c), exit 0** |
| Runtime executable SHA-256 | `5719892edd89da2ce31d2b9f5f9c53c0cf244ec92294792a7f59e150e6e9aca5` |
| Model/projector present | **No** |
| AKTREADER security-control mutation | **None** |

### Baseline metric table

| Metric | Result | Reason |
|---|---:|---|
| Prediction coverage | **N/A** | Baseline not executed; 0/36 records evaluated |
| Filiation field exact match | **N/A** | No prediction denominator |
| Filiation act exact match | **N/A** | No prediction denominator |
| Wrong-but-CONFIDENT rate | **N/A** | No predicted confidence grades |
| CONFIDENT calibration | **N/A** | No predictions |
| PROBABLE calibration | **N/A** | No predictions |
| UNCLEAR calibration | **N/A** | No predictions |
| Observation-state accuracy | **N/A** | No predicted observation states |
| Abstention rate | **N/A** | No predictions |

These are report-level `N/A` values because the baseline did not happen. They are not calculated
zeroes and do not satisfy a performance target. Once predictions exist, the harness also uses
`N/A` for a calculated ratio with a zero denominator—for example `wrong-but-CONFIDENT` when an
evaluated prediction set contains no CONFIDENT assertions.

The exact Qwen3.5-9B Q5_K_M model and F16 projector are now revision- and checksum-pinned in
[`examples/p2-baseline.artifacts.json`](../examples/p2-baseline.artifacts.json). The owner fetches
those bytes outside the application; `reader-inspect` verifies them before the coordinator runs
the committed 24-job scan-backed manifest. The 12 unlocalized records remain explicit coverage
gaps and are never assigned guessed paths.

## Intended local baseline

| Hardware profile | Reader checkpoint | Quantization target | Runtime |
|---|---|---|---|
| Consumer GPU, 16 GB VRAM (default) | Qwen3.5-9B | Q5_K_M + F16 projector (frozen P2 baseline) | Direct `llama.cpp` CLI subprocess |
| Consumer GPU, 24 GB VRAM | Qwen3.6-27B | Q4 | Direct `llama.cpp` CLI subprocess |
| Smaller-VRAM fallback | Qwen3.5-4B | Select locally after a measured fit check | Direct `llama.cpp` CLI subprocess |

Inference is local and offline. AKTREADER has no hosted-model backend, model API client, API-key
setting, or required localhost model server. Model weights and runtime binaries are
owner-provisioned artifacts; the application does not download them.

Published vendor OCR or document-understanding benchmarks informed model selection only. They
are not evidence for performance on handwritten civil-register acts and are not substituted for
this project's gold-corpus evaluation.

## Benchmark integrity

The current gold corpus contains 36 records spanning 21 clerk-year groups. Twenty-four records
have checksum-verified local scans and twelve remain `NOT_LOCALIZED`; the first executable
baseline therefore reports at most 24/36 prediction coverage. All current gold records are
evaluation-only:

- `gold/clerk_year_holdout.json` sets `training_overlap_allowed` to `false`.
- Holdout membership is sequestered by clerk-year, not by individual act.
- The harness rejects a holdout mismatch and any clerk-year leakage into training.
- Current gold records do not carry consent for training or correction reuse.

The project must not turn evaluation corrections into training examples without explicit
consent. Privacy eligibility and training consent are separate checks; satisfying an age-based
privacy rule does not grant training permission.

## Metric definitions and acceptance targets

- **Filiation field exact match:** exact agreement on evaluated parentage fields, including the
  mother's maiden name and observation state.
- **Filiation act exact match:** an act passes only when all evaluated filiation fields match.
- **Wrong-but-CONFIDENT rate:** incorrect assertions graded CONFIDENT divided by all evaluated
  CONFIDENT assertions. A `0/0` result is `N/A`, never a passing zero.
- **Calibration:** empirical correctness reported separately for CONFIDENT, PROBABLE, and
  UNCLEAR outputs.
- **Observation-state accuracy:** exact agreement among observed value, stated unknown,
  unreported, and unclear evidence states.
- **Abstention rate:** the share of evaluated fields for which the Reader declines to assert a
  resolved value.

The P2 acceptance targets are at least 90% filiation exact match and below 2%
wrong-but-CONFIDENT. A metric with no denominator cannot satisfy a target. An UNCLEAR answer is
valid only when its alternatives preserve the unresolved evidence instead of silently choosing
one reading.

## Exact local CLI commands — documented, not launched

The validation commands below were exercised; the inference command was not. `batch-run` remains
unrun until the two owner-fetched GGUF files match the committed hashes. The runtime, prompt,
schema, configuration, and 17 scan jobs are already concrete—there are no placeholder digests in
the P2 baseline configuration.

### Verify prompt v1.2.0

From PowerShell:

```powershell
Set-Location E:\DNA\Project_RegisterReader
.\.venv\Scripts\python.exe -m aktreader prompt-verify --root E:\DNA\Project_RegisterReader
```

The reported digest must be exactly
`ea0e83756698496414ba654de70805179829848f31acc644112b1e51f48e955f`.

### Validate the four Wave 001 source labels

This validates Reader A and Reader B files for acts 1–2. It does not perform a consensus merge.

```powershell
Set-Location E:\DNA\Project_RegisterReader
.\.venv\Scripts\python.exe -m aktreader label-validate `
  .\labels\readerA\serock-1890-death-1.json `
  .\labels\readerA\serock-1890-death-2.json `
  .\labels\readerB\serock-1890-death-1.json `
  .\labels\readerB\serock-1890-death-2.json
```

### Inspect and run the locked scan-backed baseline after the owner fetch

The configuration and manifest are committed at
[`examples/p2-baseline.local-reader.json`](../examples/p2-baseline.local-reader.json) and
[`examples/p2-baseline.jobs.json`](../examples/p2-baseline.jobs.json). The latter was built only
from gold records already carrying a checksum-verified local artifact. Each job names exactly one
act; a filename is never used to infer the target. Whole-page source regions are declared
honestly where no verified crop exists.

```powershell
Set-Location E:\DNA\Project_RegisterReader
$readerConfig = '.\examples\p2-baseline.local-reader.json'
$batchManifest = '.\examples\p2-baseline.jobs.json'
$runRoot = 'E:\DNA\Project_RegisterReader\runs\p2-local-baseline'
$checkpoint = Join-Path $runRoot 'checkpoint.sqlite3'
$outputDir = Join-Path $runRoot 'predictions'

.\.venv\Scripts\python.exe -m aktreader reader-inspect --config $readerConfig
.\.venv\Scripts\python.exe -m aktreader batch-run `
  --config $readerConfig `
  --manifest $batchManifest `
  --checkpoint $checkpoint `
  --output-dir $outputDir `
  --as-of-year 2026 `
  --max-retries 2
```

`reader-inspect` verifies the content pins without inference. It currently fails closed because
the two GGUF paths are absent. After the owner fetch, `batch-run` launches local inference;
reissuing the identical command resumes from the SQLite checkpoint.

### Evaluate completed predictions

Run this only after the output directory contains the completed baseline predictions:

```powershell
Set-Location E:\DNA\Project_RegisterReader
$runRoot = 'E:\DNA\Project_RegisterReader\runs\p2-local-baseline'
$outputDir = Join-Path $runRoot 'predictions'
$evaluation = Join-Path $runRoot 'serockbench.json'
.\.venv\Scripts\python.exe -m aktreader eval `
  --predictions $outputDir `
  --gold-dir .\gold\acts `
  --holdout .\gold\clerk_year_holdout.json `
  --output $evaluation
```

The evaluation command accepts either one prediction JSON file or a directory of prediction
JSON files. The first complete run should report 24/36 coverage, not 36/36. Preserve the
predictions, batch checkpoint, runtime fingerprint, content pins, and generated report as
immutable run evidence.

See [Local model runtime](local-model.md), [Label factory](label-factory.md), and
[Architecture](architecture.md) for the runtime, consensus, and data-flow contracts.
