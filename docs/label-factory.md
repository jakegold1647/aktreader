# Out-of-band dual-Reader label factory

Status: P2 protocol and ingest implementation, 2026-07-28.

The label factory bootstraps training and review data without creating an API dependency.
Two subscription AI sessions read the same scan independently and save JSON labels. AKTREADER
does not log in to those services, automate their sessions, call their models, or carry a key for
them. Its first contact with either pass is a file on disk.

## Blind-pass workflow

1. A coordinator prepares one metadata-only batch brief: artifact identity and SHA-256, exact
   act/crop, target register metadata, clerk-year, Reader identity, blind-group ID, privacy
   decision, prompt version, and prompt SHA-256.
2. Reader A and Reader B receive the same scan, brief, and
   [`prompts/reader_prompt.md`](../prompts/reader_prompt.md). They must be from distinct model
   families and neither may see the other's output.
3. Each session emits exactly one JSON object conforming to
   [`schemas/reader-label-1.0.0.schema.json`](../schemas/reader-label-1.0.0.schema.json).
4. The files are retained unchanged. Their own SHA-256 digests become immutable source
   provenance; a corrected observation is a new label, not an edit hidden in place.
5. `LabelIngest` validates exact keys, identifiers, Reader/blind attestations, prompt binding,
   artifact binding, clerk-year, source spans, confidence/state rules, compliance metadata, and
   the authority warning. It then freezes the loaded mapping.
6. Only a legitimate blind pair reaches consensus. Different record/target metadata, same Reader
   identity or family, a false blindness attestation, conflicting artifact hashes, prompt hashes,
   blind groups, or clerk-years are rejected or explicitly capped according to the missing
   binding.
7. Field-level consensus and cross-act validators produce either reviewable evidence or a review
   item. They never write back into the source labels.

The prompt contains the Napoleonic-act formula, pre-1918 Cyrillic guidance, and uncertainty
contract verbatim. Its recorded checksum matters as much as its version string: a prompt file
changed by line endings or one character is a different Reader condition.

The current frozen prompt is v1.1.0. Its raw-byte SHA-256 is
`9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09`. The v1.1 patch removes a
dual-date prior exposed by Wave 001: a Reader may record two dates only when two day-words are
physically visible, and must use `[unclear: single/dual]` when that evidence is unresolved. This
is a protocol correction for subsequent passes, not a retroactive accuracy claim.

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

After the first LoRA, the local model can emit a third blind label under the same schema and
prompt. It does not automatically decide a two-Reader disagreement. Its agreements and conflicts
are additional attributed observations that route review. As held-out performance improves, it
can take more first-pass work while the subscription sessions become spot-checkers and hard-case
readers. The continuous corpus batch remains local throughout.

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
quarantined. `training_materialized: false` is deliberate: the resolved field payloads are still
stored in the content-addressed coordinator appendices, so no model-ready field export is claimed
yet.

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
