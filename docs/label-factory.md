# Grounded single-reader label factory

Status: restructured protocol and guarded ingest, 2026-07-29.

AKTREADER still accepts subscription-session labels only as files on disk: it does not log in
to those services, automate their sessions, call their models, or carry a key for them. The
measured wave-005 failure ended Sol's production-reader role and disproved the assumption that
two reliable frontier readers were available.

## Current workflow

1. A coordinator prepares one metadata-only batch brief with artifact, target, clerk-year,
   privacy, prompt, and reader bindings.
2. One blind production reader receives the scan, brief, and frozen v1.4 prompt.
3. That reader emits a continuous original-order transcription plus structured observations
   under the v1.4 grounded schema.
4. An independent verifier checks every field that matters. It does not inherit unsupported
   assertions merely because they are well formed.
5. Residual ambiguity becomes an `aktreader adjudicate` question with candidates, image evidence,
   structural checks, and explicit neither/can't-tell exits.
6. A human decision closes what the evidence supports; unresolved fields remain unclear.
7. Every source file is retained unchanged and content-addressed. Corrections are new events,
   never hidden rewrites.

This workflow is slower and has less cross-vendor diversity than the original dual-reader plan.
That loss is documented rather than masked. Legacy dual-reader consensus remains auditable, but
no historical label is grandfathered into grounded ingest.

## Prompt and schema v1.4 freeze

The current frozen prompt is v1.4.0:

- prompt SHA-256:
  `5d14dcb892bd1ca2f236e472adf04656a98cdad51acb40fea8797265b09fca7a`;
- full-label schema: `schemas/reader-label-1.0.0-v1.4.schema.json`, SHA-256
  `ee8f57431dfa70f85103953c27314c2bb9d61dbc08b8e20b5e092bc0376a5a08`;
- bounded model schema: `schemas/model-output-1.1.0.schema.json`, SHA-256
  `52b1dfef4bda7506987c22a7f7438fbf807f9aa42b7fdf1eb9c25ae4be512e1d`.

v1.4 retains the domain skills and prior paleographic safeguards, then adds a mechanical
grounding contract: every act has a nonblank continuous original-order transcription; every
PRESENT observation has a nonblank `original_script`; Russian PRESENT excerpts contain Cyrillic;
and each complete excerpt occurs in the transcription after Unicode NFC and whitespace
normalization only. Numeric/symbol observations must include enough adjacent inked wording to
satisfy the Russian-script rule.

Standard JSON Schema enforces the structural requirements. Both v1.4 schemas also declare
`x-aktreader-grounding-contract: 1.0.0`; AKTREADER's local schema validator executes that
declared cross-field contract and rejects substring/Cyrillic failures. This is not a documentary
annotation: `validate_instance` fails closed on it. Generated future briefs reject prompt
versions below 1.4. The measured P2 baseline remains pinned to its historical v1.2 artifacts.

## Consensus is strict, not fuzzy

Consensus applies Unicode NFC and whitespace normalization only. It does not use Soundex,
transliteration equivalence, name dictionaries, case-folding to merge values, or numeric-string
coercion. Those techniques can be useful later as review evidence; they are not permission to
turn two different readings into agreement.

| Pair result | Merged result |
|---|---|
| Value, state, alternatives, and literal script strictly agree; all provenance bindings verified | `PROBABLE`, marked `CONFIDENT_ELIGIBLE` for later validator grading |
| Values agree but prompt/artifact/blind-group/clerk-year or literal-script binding is unverified | `PROBABLE`, capped there |
| Values, states, alternatives, or literal script conflict | `UNCLEAR` with both attributed candidates |
| One Reader did not report the field | `[unclear: value/UNREPORTED]`; absence is not rewritten as `BLANK` |

Agreement is not truth. Even a fully bound agreement remains only eligible for promotion until
validators run, and sampled human verification never drops to zero. A shared model error can
survive cross-vendor agreement.

## Legacy labels

The first Reader A pilot labels predate the canonical schema. The loader has a named legacy
adapter so they remain auditable rather than being silently “upgraded.” Missing prompt hash,
artifact hash/source boxes, blind-group binding, or clerk-year is preserved as missing. Such a
label can participate in a diagnostic merge, but agreement is capped at `PROBABLE` and the pair
notes explain why. New factory waves use the canonical schema only.

This policy also turns prompt-hash drift into a visible provenance failure rather than a cosmetic
warning. A mismatched hash must be reconciled before treating a pair as fully bound.

## Local model in later waves

After the first LoRA, the local model can emit a blind first-pass or verification label under
the same v1.4 grounding contract. It never automatically decides a disagreement; conflicts route
to adjudication. As held-out performance improves, it can take more first-pass work while the
subscription reader becomes a verifier and hard-case reader. The continuous corpus batch remains
local throughout.

## Privacy, consent, and split integrity

Three decisions must not be conflated:

- **May this act be processed?** The default local policy requires 100 years for births and 80
  for marriages/deaths. Unknown years fail closed; unsupported act types require review.
- **Is this label correct enough for evaluation?** Eval records require human verification.
- **May this correction train a model?** Training requires explicit recorded correction consent,
  regardless of correctness.

The 36 P1 gold records have no recorded correction consent. They are evaluation-only and all 21
of their clerk-years are sequestered in
[`gold/clerk_year_holdout.json`](../gold/clerk_year_holdout.json). A training export must reject
every overlapping clerk-year, not merely the same act IDs. This prevents handwriting-style
memorization from contaminating the benchmark.

## Gold, silver, and quarantine

- `GOLD` is human-verified, clerk-year-sequestered, and evaluation-only.
- `SILVER` is resolved 2-of-3 machine consensus, training-eligible, and never evaluation data.
- An identity-level fork has no tier until the required human sample resolves it.

The current machine-readable catalog is
[`labels/silver/manifest.json`](../labels/silver/manifest.json). It assigns acts 1–5 to silver,
pins both source labels plus the consensus and Reader C documents by SHA-256, and leaves act 6
quarantined. Acts 1–5 now have deterministic, schema-validated materialized payloads under
`labels/silver/records/`; every payload is content-addressed by the manifest. Tier-level
`training_eligible` is not permission to violate an eval split: all five current silver acts carry
the Serock-1890 clerk-year that is also in the present gold holdout. The training exporter checks
the complete clerk-year set before reading or emitting examples and hard-fails against the
current holdout.

No label or training export may contain material from Yad Vashem, USHMM, Arolsen, Geneteka, or
JRI-Poland indexes. The factory labels only user-supplied permitted register scans.

## Local verification

These commands exercise ingest, blind pairing, consensus, and validators without contacting any
model or network service:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_label_ingest.py tests/test_consensus.py
.\.venv\Scripts\python.exe -m pytest tests/test_validators_dates.py tests/test_validators_corpus.py
.\.venv\Scripts\python.exe -m pytest tests/test_schema.py tests/test_prompt.py
```

The saved label files are evidence artifacts, not a claim that every field has been human
adjudicated. Disagreement reports remain review queues until their decisions are captured with
provenance.
