# Architecture guardrails

Status: P2 implementation record, 2026-07-28.

AKTREADER has one inference Reader and no hosted-model abstraction:

```text
user-supplied scan/crop + explicit target
    -> target and privacy preflight
    -> resumable batch/checkpoint layer
    -> pinned local llama.cpp CLI + open-weights VLM
    -> immutable local Reader label

two blind subscription-session label files (out of band)
    -> strict LabelIngest
    -> field-level consensus
    -> cross-act validators
    -> graded act evidence + review queue

gold acts + clerk-year holdout + predictions
    -> SerockBench evaluation report
```

The application never calls a subscription assistant, hosted model, inference API, or localhost
model server. It has no API key configuration. The subscription assistants participate only by
producing JSON files in their own sessions; those files cross a validation boundary before they
can influence evidence. Model acquisition is also outside runtime: inference accepts only
explicit local paths whose contents match recorded SHA-256 pins.

## Evidence model

The authoritative model is not a flat register row. It has four layers:

1. **Source artifact** — a content-addressed scan, page, or crop, with path, checksum, register
   identity, pixel coordinates, explicit act target, clerk-year, and privacy decision.
2. **Reader observation** — immutable output from one blind pass, including reader identity and
   family, prompt/model identity, timestamp, transcript, and spatial spans. One Reader may emit
   `PROBABLE`, `UNCLEAR`, or a typed non-present state, but never `CONFIDENT`.
3. **Act assertion** — a normalized value plus original script, observation state, confidence
   grade, alternatives, source spans, contributing Reader labels, and validator findings.
   People here are role-bearing mentions within an act, not globally resolved people.
4. **Derived hypothesis** — a corpus-level claim such as “these two mentions may be the same
   person.” It carries supporting and contradicting act IDs, a score, method provenance, and
   human review status. It never rewrites source observations or act assertions.

This separation permits corpus-level constraint solving and town graphs without laundering a
later inference into what the document was originally observed to say.

## Confidence and observation semantics

Every evidence field retains:

- `value`: normalized value when supported;
- `original_script`: literal reading in document order;
- `confidence`: `CONFIDENT`, `PROBABLE`, `UNCLEAR`, or null for a non-present state;
- `observation_state`: `PRESENT`, `ABSENT_ON_FORM`, `BLANK`, `STATED_UNKNOWN`, or `ILLEGIBLE`;
- `source_spans`: one or more scan bounding boxes;
- `alternatives`: explicit readings represented by `[unclear: X/Y]`;
- Reader and validator provenance explaining any confidence ceiling.

Presence and confidence are orthogonal. A cleanly visible blank can be reliably `BLANK`; an
expected field defeated by the pixels is `ILLEGIBLE`; a field the document formula does not
supply is `ABSENT_ON_FORM`; and a clerk's written “unknown” is `STATED_UNKNOWN`. None means
“unknown person,” and missing Reader output is not converted to any of these states.

The confidence path is deliberately asymmetric:

1. A single Reader is capped at `PROBABLE` or `UNCLEAR`.
2. Strict field agreement between distinct blind Reader families can become
   `CONFIDENT_ELIGIBLE` only when prompt, artifact, blind-group, clerk-year, and original-script
   bindings are verified.
3. Any value, state, alternatives, or literal-script disagreement becomes `[unclear: X/Y]`.
4. Cross-act validators may flag, downgrade, or support an eligibility decision. Agreement is
   never treated as truth by itself.
5. Calibration is scored against human-verified holdouts, not against consensus.

The act schema covers type/number/year, registration and event dates, town, principal, parents
including the mother's maiden name, spouse and spouse's parents, declarants and witnesses
including ages and occupations, officiant, signatures, marginalia, survivors, and
marriage-specific banns, permissions, and rabbi fields.

## Local Reader boundary

`LocalReader` invokes a checksum-pinned `llama-cli` executable with explicit model, multimodal
projector, prompt, schema, image, and optional LoRA paths. It uses `shell=False`, deterministic
generation settings, and a credential-free allow-listed subprocess environment. URL/UNC
locators, auto-download flags, remote schema references, missing files, and checksum mismatches
fail closed.

The default hardware profile is Qwen3.5-9B Q5/Q4 on the development RTX 5060 Ti 16 GB. A 24 GB
quality profile uses Qwen3.6-27B Q4; Qwen3.5-4B is the smaller fallback. These choices remain
provisional until the local historical-handwriting baseline runs. The exact downloaded runtime
was blocked by Windows Security before invocation, so P2 records the baseline as `NOT RUN` and
requires explicit owner review/provisioning rather than bypassing the control.

## Resumable batch state machine

One batch run owns one SQLite checkpoint database. Transactions use WAL and full synchronous
durability. Each job is in exactly one state:

`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `REVIEW_REQUIRED`, or
`PRIVACY_REFUSED`.

The job fingerprint covers scan bytes, crop/target, act metadata, model, prompt, schema,
decoding configuration, privacy policy, and output path. A matching successful job is skipped on
resume only while its promised output remains a readable JSON object; missing or corrupt output
is requeued. A changed material input invalidates that success. Stale running work becomes
interruptible/retryable, bounded failures retain diagnostics, and JSON output is flushed then
atomically replaced. Unknown or multi-act targets go to review; the batch layer never infers a
crop or act number from a filename.

Privacy preflight is fail-closed: births require 100 years; marriages and deaths require 80 by
default. Unknown years are refused, and unknown/unsupported act types require human review.

## Training and evaluation separation

Consent and correctness are separate gates. A human-verified correction is not training data
unless its correction consent explicitly says so. The 36 P1 records have no recorded correction
consent and are evaluation-only.

Evaluation splits are by clerk-year, not random act. `gold/clerk_year_holdout.json` sequesters all
36 current gold records across 21 clerk-years and explicitly forbids training overlap. The eval
harness rejects a mismatched holdout manifest or any training clerk-year leakage before scoring.
This prevents a model that memorized one clerk's hand from masquerading as a general reader.

## Stable identity and graph horizon

- Act IDs derive from collection/register/page/act identity, not a person's name.
- Artifact checksums detect silent scan replacement.
- Reader labels are immutable; corrections append provenance rather than rewriting history.
- Normalized names never overwrite literal readings.
- CSV is a lossy search projection; evidence JSON remains authoritative.
- Corpus regrading creates a derived assessment and preserves the original per-act grade.
- Entity resolution may propose links but may not merge people without human review.

Memorial matching remains outside the extraction store. It accepts only manually entered details
and the user's own extracted corpus; it never fetches, bulk-ingests, trains on, or submits
memorial-institution records.

## Phase boundaries

- P1 is complete: 36 source-backed, evaluation-only records.
- P2 implementation is complete; the real LocalReader baseline is `NOT RUN` pending explicit
  owner action on the Windows Security-blocked runtime.
- P3 acquisition and Pułtusk batch work remain blocked until the explicit terms and polite-pace
  gate is approved.
- P4 adds variant proposals without changing literal names.
- P5 selects the license and publication surface.
