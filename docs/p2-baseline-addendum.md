# P2 local baseline addendum

**Status:** measured local baseline and protocol-restructure findings frozen; benchmark remains
under construction and is not publication-grade.

**Recorded:** 2026-07-28

**Updated:** 2026-07-29

This addendum records the measured “before” picture. It does not report a successful benchmark
run and does not convert failed jobs into zero-valued metrics.

## Executive findings

| Question | Measured answer |
|---|---|
| Did the local baseline run? | Yes: 20/24 jobs succeeded; corrected filiation field exact match was **1/77 (1.30%)**. |
| Is that publication-grade benchmark accuracy? | No: the frozen comparison corpus is research-derived and **0/36** stored acts satisfy the image-attestation contract. |
| Did blind disagreement add safety value? | Yes: it intercepted multiple phantom-identity forks before gold, but those disputed-only catches are not an accuracy estimate. |
| Did well-formed labels prove that a reader read the page? | No: wave 005 produced schema-valid fabricated fields when coverage was pressured without groundedness. |
| What protocol follows from the evidence? | Blind reader -> fresh blind same-vendor verification -> adjudication packet -> human decision, with correlated blind spots explicitly retained as a limitation. |

## Measured failure matrix

| Probe | Constraint path | Result | Finding |
|---|---|---|---|
| A | `llama-cli` + full JSON schema | Sampler initialization crash | `Unexpected empty grammar stack` when the frontend accepted `<|im_start|>` through the active grammar |
| B | `llama-cli`, no grammar, temperature 0 | Generation reached token/context cap | Fence-wrapped JSON entered a repetition loop inside a long string |
| C | Grammar + `--reasoning-format none` | Same sampler crash | Reasoning-format change did not isolate the grammar from frontend prompt tokens |
| D | Grammar without `--jinja` | Same sampler crash | Failure was template-flag independent in `llama-cli` |
| E | No grammar + repetition penalty 1.15 | Parseable but unusable shell | Schema-shaped output contained zero observations and mutated act number 11→12 |
| 5 | `llama-cli --chat-template chatml` | Same sampler crash | The `llama-cli` REPL frontend, not one template, was the collision point |
| 7 | `llama-mtmd-cli` + inline schema/system prompt | Grammar initialized | First constrained token was schema-shaped; later loop occurred in an unbounded string |
| 8 | Same + repetition penalty 1.15 | Loop moved into a hash field | Forcing the model to reproduce mechanical identifiers created another nonterminating surface |

The unconstrained model’s repetition loop and hollow schema-shaped shell are baseline findings,
not discarded setup noise. Together they are the measured argument for:

1. hard constrained decoding;
2. a bounded model-facing schema;
3. pipeline-owned identity/provenance; and
4. domain LoRA training after leakage-safe silver materialization.

They do **not** establish that a LoRA will improve accuracy; the later held-out benchmark must
measure that.

## Implemented remediation

- Runtime frontend: pinned b10167 `llama-mtmd-cli.exe`, SHA-256
  `6866b9425ec02798087380e14d5a9c69ded092a914cd48f06cf9b803552f7bfc`.
- Grammar surface: `schemas/model-output-1.0.0.schema.json`.
- Model-generated content: target check, transcription/translation, and observations only.
- Pipeline-generated content: label/record IDs, timestamps, reader identity, prompt and artifact
  pins, clerk-year identity, source envelope, compliance, and authority warning.
- Loop bounds: every model-facing string is capped at 512 characters. Transcription and
  translation are emitted as at most 120 line strings, then mechanically joined with newlines
  into the frozen full-label contract. The coordinator's b10167 micro-probe confirmed
  `maxItems: 120` with per-line `maxLength: 512` parses and generates under grammar. Observation
  arrays/counts are bounded; source-span IDs are stamped by the pipeline as a constant verified
  region.
- Repetition penalty: disabled unless the reduced-schema probe demonstrates a remaining loop.
- Failed jobs: decoded raw stdout and stderr are atomically preserved beside the intended
  prediction and their paths are recorded in the checkpoint error.
- Checkpoint safety: all 17 existing rows were first rebound to the mtmd/reduced-schema
  fingerprints and then rebound once more after the grammar-safe line-array schema change.
  The database retains all 34 transition events; the latest 17 bind every row to the frozen
  schema. Every row remains `FAILED` at `retry_count=2`; both rebinds used `--max-retries 2`, so
  no inference was claimed or consumed. Seven newly localized jobs remain outside that
  preparatory rebind and will enter at retry zero only in the coordinator-authorized full
  manifest run.

## Measured full-run result

The 24-job local baseline completed with **20 SUCCEEDED / 4 FAILED** under runtime fingerprint
`ba20dc60…`. The four failures are retained diagnostics: output-budget exhaustion left
unbalanced JSON on the longest acts, and one multi-act spread repeated the noncanonical key
`act_1`. The strict parser rejected the duplicate before schema validation.

The first generated report compared flat model keys to nested gold paths and therefore reported
a meaningless 0/77 filiation score. That report is preserved as
`runs/p2-local-baseline/serockbench.invalid-keyspace.json` and must not be published. Field-map
contract v1.0.0 now explicitly maps or dispositions all 81 observed model keys, is SHA-256-bound
to the reduced schema, and fails closed on any unmapped key. Re-evaluation required no inference.

| Metric | Corrected result | Denominator |
|---|---:|---:|
| Prediction coverage | **55.56%** | 20/36 records |
| Filiation field exact match | **1.30%** | 1/77 fields |
| Filiation act exact match | **0.00%** | 0/20 acts |
| Wrong-but-CONFIDENT rate | **N/A** | 0/0 CONFIDENT assertions |
| CONFIDENT calibration | **N/A** | 0 scored |
| PROBABLE exact calibration | **27.86%** | 39/140 scored assertions |
| UNCLEAR calibration | **N/A** | 0 scored |
| Observation-state accuracy | **99.30%** | 141/142 mapped observations |
| Scored-field abstention | **0.00%** | 0/140 UNCLEAR or ILLEGIBLE |

The result is a real weak baseline, not a passing model: it recovered some plausible word shapes
but almost no exact filiation. The single-reader contract emitted no CONFIDENT observations, so
wrong-but-CONFIDENT is correctly `N/A (0/0)`, not a passing zero.

**Gold-provenance limitation.** These metrics compare predictions with the frozen 36-record
research-note-derived corpus. The gold-attestation re-audit found **0/36** acts with complete
per-field image references and dated human attestations. The 1.30% filiation result stands as the
recorded before-picture, but it is not publication-grade image-verified benchmark accuracy. See
`docs/audits/gold-attestation-audit-2026-07-29.md`.

For future inference, the reduced schema now forbids the literal scalar placeholders `unknown`,
`unclear`, `n/a`, and `none` case-insensitively, forcing typed absence into the non-present
oneOf branch. This changes the schema pin and runtime fingerprint; the completed checkpoint is
not rebound. The hardened schema is pending its own grammar probe before any failure-only retry.
A longer-act retry must likewise use a separately fingerprinted output budget so it cannot be
silently mixed with the completed 8,192-token jobs.

## Phantom identities intercepted by blind disagreement

Blind disagreement caught four identity-level forks before they could become gold:

- act 6: a surname split across a line break (`Gersz-/weld`) became a phantom spouse,
  "Gersz Weksler," and cascaded into the principal's sex, name, age, filiation, and survivor
  structure;
- act 39: a male "Lejb Majkowski" parse forked from the arbitrated female principal Ruchla
  Makowska;
- act 45: a complete "Basia Konowska, female, 47" identity forked from Josek Makowski, male,
  baker, 71; and
- act 46: a complete Ruchla Grosman/Wolberg family forked from Rojza Bornsztejn, age one.

These are safety catches, not benchmark accuracy. Each came from a disagreement-selected sample,
and the surviving resolution remains subject to the tier's human-attestation requirements.
Their valid claim is narrower: independent reads exposed internally plausible phantom people
that a single reader could have promoted unnoticed. The frozen evidence is in the
[Wave 002](../labels/consensus/serock-1890-deaths-3-6_wave002_CONSENSUS.md),
[Wave 003](../labels/consensus/serock-1890-deaths-30-40_wave003_CONSENSUS.md), and
[Wave 004](../labels/consensus/serock-1890-deaths-41-49_wave004_CONSENSUS.md) consensus records.

## Coverage pressure without groundedness

Wave 005 measured a second failure mode in the subscription-session label factory. The first
Reader B pass under-claimed and was detectable through low coverage. A replacement pass produced
much higher coverage but included confident-looking fields not present on the page. Pressure to
raise coverage without a paired groundedness measure converted abstention into fabrication.

The coordinator caused the pressure and records that role explicitly. The replacement was ordered
with the first pass's thinness quantified against Reader A's much larger field count, creating a
coverage target without an equal groundedness constraint. This is therefore a supervisory-protocol
failure, not merely a reader failure: **pressure to increase coverage without a groundedness check
can convert an abstaining reader into a fabricating one.** The ruling and quarantine are frozen in
the wave-005 fabrication ruling recorded in the project's internal coordination log, which is not published in this repository.

Four mechanical gates now prevent recurrence:

1. every PRESENT observation on a Russian-language act must carry Cyrillic in
   `original_script`;
2. every PRESENT `original_script` must be a continuous substring of that reader's own
   transcription;
3. principal infant/child/adult mismatches or age ratios greater than 10× are emitted as
   `GROUNDEDNESS_INCIDENT`, not routine disagreements; and
4. every label/wave quality report returns coverage and groundedness together.

`label-validate`, `consensus-merge`, batch consensus construction, and LocalReader output now
fail closed on the first two gates. The LocalReader contract is `aktreader-local-reader-1.1.2`;
the verified guard-bound baseline configuration fingerprint is
`17f9aaa36e436ceef84e360ca41befea3c3d89039067f2cea16dbf5fe47c3d92`.

Historical evidence remains loadable for audit, but ungrounded labels cannot enter new consensus
or training. This distinction preserves failed passes without grandfathering their claims.

## Read-only retro-audit: coverage paired with groundedness

The four guards were applied retrospectively without modifying any label. Coverage answers
"how much did the reader assert?"; groundedness answers "how much of the PRESENT material meets
the applicable script gate and occurs in the reader's continuous transcription?" The paired
results prevent a larger label from masquerading as a better read.

| Label set | Records | Coverage | Fully grounded / PRESENT | Groundedness |
|---|---:|---:|---:|---:|
| wave-001 Reader A | 2 | 100.0% | 0/42 | **0.0%** |
| wave-001 Reader B | 2 | 87.0% | 36/40 | **90.0%** |
| wave-002 Reader A | 4 | 98.7% | 0/78 | **0.0%** |
| wave-002 Reader B | 4 | 85.3% | 66/81 | **81.5%** |
| wave-003 Reader A | 11 | 92.6% | 0/238 | **0.0%** |
| wave-003 Reader B | 11 | 69.8% | 142/173 | **82.1%** |
| wave-004 Reader A | 10 | 94.4% | 0/320 | **0.0%** |
| wave-004 Reader B | 10 | 79.4% | 69/104 | **66.3%** |
| silver records | 5 | 87.9% | 0/102 | **0.0%** |

Reader A's readings were more often correct in the independent spot-check, while Reader A's
stored format was less evidentiary: it omitted continuous transcriptions, so every PRESENT claim
failed transcription support. Reader B's canonical format carried transcriptions and therefore
scored 66.3%-90.0% grounded across waves 001-004, despite the later wave-005 fabrication finding.
The guards measure recorded evidence, not factual luck. Full counts and violation classes are in
the [groundedness retro-audit](audits/grounding-retro-audit-2026-07-29.md).

### Gold is a separate evidence class

Applying machine-reader transcription support to human gold was a category error; the raw 0%
transcription-support result for gold is void as a gold-quality judgment. Gold instead requires
an image reference and a dated, attributed human attestation for every asserted field. Under
that contract, the stored corpus contains **0 contract-valid attestations, 0 fields verified
directly from images, and 0/36 fully image-verified benchmark-eligible acts**. Three acts were
verified in a 28 July human packet, but their attestations have not been materialized into the
stored gold records, so the audit does not infer or backfill them. See the
[gold attestation audit](audits/gold-attestation-audit-2026-07-29.md).

This is why the baseline's **1/77 (1.30%)** filiation result is retained as a research-derived
before-picture but must not be described as publication-grade image-verified accuracy.

## Restructured verification protocol

The evidence no longer supports an assumption of two reliable cross-vendor readers. The frozen
protocol is:

1. one blind reader produces a v1.4-or-later label with continuous original-order transcription;
2. a fresh, blind same-vendor session independently verifies every field that matters;
3. `aktreader adjudicate` packages every residue without revealing prior answers to the decider;
4. a human makes the final decision and supplies the applicable attestation.

Same-vendor verification is weaker than cross-vendor diversity, and correlated blind spots remain
possible. It is nevertheless empirically useful: in a three-act blind check, the fresh session
disagreed with the first reader on **2/3** acts and caught two material errors--act 26's nine weeks
misread as nine months, and act 12's surname Goldberg misread as Hozenberg. Those observations
justify the verification pass; they do not establish an overall error rate or eliminate the need
for adjudication and human decision. The governing ruling is
recorded in the project's internal coordination log, which is not published in this repository.
