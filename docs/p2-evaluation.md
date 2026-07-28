# P2 evaluation report

**Status:** Wave 001 and Wave 002 diagnostics recorded; local-model baseline **NOT RUN**

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
repository's eval holdout is human-verified. No Wave 002 field has been added to gold. The
coordinator has been asked to name a non-gold consensus/training tier or supply human
verification before ingest.

Evidence:

- [Wave 002 resolved consensus](../labels/consensus/serock-1890-deaths-3-6_wave002_CONSENSUS.md)
- [Wave 002 Reader C report](../labels/consensus/readerC_arbitration_wave002.md)

### Tier disposition

The machine-readable [silver manifest](../labels/silver/manifest.json) assigns resolved acts 1–5
to `SILVER`: training-eligible 2-of-3 consensus, never evaluation, never human-verified. It pins
all source labels and resolution documents by SHA-256. The actual resolved fields remain
source-addressed in the coordinator appendices (`training_materialized: false`), so this gate does
not pretend that a canonical LoRA export has already been built. Act 6 remains untiered and
quarantined pending the mandatory human check.

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

## LocalReader baseline — NOT RUN

Windows Security blocked execution of the exact downloaded `llama.cpp` runtime before model
invocation. No bypass was authorized, no scan was submitted to the model, and no prediction was
produced. AKTREADER did not disable protection, add an exception, allow-list the binary, or
otherwise weaken or evade the control.

| Run fact | Recorded state |
|---|---:|
| Baseline run state | **NOT RUN** |
| Model invocations | **0** |
| Gold records evaluated | **0/36** |
| Sequestered clerk-year groups | **21** |
| Authorized security bypass | **No** |

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
zeroes and do not satisfy an acceptance target. Once predictions exist, the harness also uses
`N/A` for a calculated ratio with a zero denominator—for example `wrong-but-CONFIDENT` when an
evaluated prediction set contains no CONFIDENT assertions.

Resuming the baseline requires explicit owner action after independent review of the runtime
artifact's provenance and signature: approve that exact artifact or replace it with a trusted
build, then record the accepted executable's SHA-256. This project does not recommend or request
a security bypass.

## Intended local baseline

| Hardware profile | Reader checkpoint | Quantization target | Runtime |
|---|---|---|---|
| Consumer GPU, 16 GB VRAM (default) | Qwen3.5-9B | Q5 when measured headroom permits; Q4 otherwise | Direct `llama.cpp` CLI subprocess |
| Consumer GPU, 24 GB VRAM | Qwen3.6-27B | Q4 | Direct `llama.cpp` CLI subprocess |
| Smaller-VRAM fallback | Qwen3.5-4B | Select locally after a measured fit check | Direct `llama.cpp` CLI subprocess |

Inference is local and offline. AKTREADER has no hosted-model backend, model API client, API-key
setting, or required localhost model server. Model weights and runtime binaries are
owner-provisioned artifacts; the application does not download them.

Published vendor OCR or document-understanding benchmarks informed model selection only. They
are not evidence for performance on handwritten civil-register acts and are not substituted for
this project's gold-corpus evaluation.

## Benchmark integrity

The current gold corpus contains 36 records spanning 21 clerk-year groups. All current gold
records are evaluation-only:

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

None of the commands below was executed while preparing this update. The prompt and label
commands are local validation only. The batch command must remain unrun until the owner supplies
or authorizes a trusted local runtime and model and replaces every placeholder digest in the
Reader configuration.

### Verify prompt v1.1.0

From PowerShell:

```powershell
Set-Location E:\DNA\Project_RegisterReader
.\.venv\Scripts\python.exe -m aktreader prompt-verify --root E:\DNA\Project_RegisterReader
```

The reported digest must be exactly
`9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09`.

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

### Inspect and run a batch only after owner authorization

First copy [`examples/local-reader.config.example.json`](../examples/local-reader.config.example.json)
to an owner-selected local path and replace every sample digest with a verified SHA-256. The
prompt pin in that configuration must be the v1.1.0 digest above. The batch manifest must contain
explicit scan paths, act targets, act types, years, and matching record IDs; the runner never
infers them from filenames.

The two `Read-Host` prompts deliberately require the owner to supply those paths at run time:

```powershell
Set-Location E:\DNA\Project_RegisterReader
$readerConfig = Read-Host 'Absolute path to the owner-approved, SHA-pinned Reader config'
$batchManifest = Read-Host 'Absolute path to the explicit local batch manifest'
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

`reader-inspect` verifies the content pins without inference. `batch-run` is the command that
launches local inference; do not issue it before the explicit owner decision described above.
Reissuing the identical `batch-run` command resumes from the SQLite checkpoint.

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
JSON files. Preserve the predictions, batch checkpoint, runtime fingerprint, content pins, and
generated report as immutable run evidence.

See [Local model runtime](local-model.md), [Label factory](label-factory.md), and
[Architecture](architecture.md) for the runtime, consensus, and data-flow contracts.
