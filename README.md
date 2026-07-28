# AKTREADER

AKTREADER is an evidence-first pipeline for scanned civil-register acts from partitioned
Poland. Its intended output is a structured genealogical extraction in which every field is
traceable to the scan and uncertainty is recorded instead of guessed.

> **Project status: P2 implementation gate.** The local-only Reader, external-label ingest,
> consensus, validators, resumable batch engine, and SerockBench harness are implemented and
> tested. The real local-model baseline is **NOT RUN**: Windows Security blocked the exact
> downloaded inference runtime before it could execute. No accuracy number is inferred from
> unit tests, vendor benchmarks, or an empty prediction set.

## Why this project exists

Most handwriting tools optimize for plausible text. AKTREADER uses one local open-weights
vision-language model for inference and concentrates on the layers above recognition:
act-format structure, filiation-first extraction, evidence provenance, explicit uncertainty,
and evaluation of wrong-but-confident claims. Labels produced manually in two independent
subscription AI sessions can be imported as files; the application never calls those assistants.

The pilot goal is to reconstruct the Jewish community of Pułtusk from civil registers as a
reviewable evidence graph. No record becomes a person-level conclusion merely because a model
suggests it.

## Non-negotiable behavior

- Never fill a missing or unreadable field from expectation.
- Preserve unresolved alternatives as `[unclear: X/Y]`.
- Keep `ABSENT_ON_FORM`, `BLANK`, and `ILLEGIBLE` distinct.
- Treat act-local person mentions as evidence; later identity links remain reviewable
  hypotheses.
- Refuse acts inside the configured privacy window by default.
- Keep source spans and artifact provenance with extracted assertions.
- Include “extraction is not authority — verify against the scan” in generated outputs.
- Never scrape archive sites or bulk-ingest memorial-institution data.
- Never put an API backend, hosted-model key, or automatic model download in the Reader path.
- Never add a correction to training data without recorded consent.

## Local-only Reader

The application invokes a content-pinned `llama-cli` executable directly as a subprocess. It
does not start an inference server, send HTTP to localhost, use a hosted SDK, or accept an API
key.

- **16 GB development default:** Qwen3.5-9B, quantized Q5 first and Q4 if measured headroom
  requires it.
- **24 GB quality profile:** Qwen3.6-27B Q4.
- **Smaller fallback:** Qwen3.5-4B.

Those are provisional hardware profiles, not handwriting accuracy claims. Qwen's published OCR
scores do not test nineteenth-century Russian or Polish cursive. See
[local model and runtime](docs/local-model.md).

## Development

Python 3.10 or newer is supported. Python 3.12 is the development version.

With [`uv`](https://docs.astral.sh/uv/):

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run aktreader doctor
```

Without `uv`, use an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\aktreader.exe doctor
```

The source tree uses the `src/` layout. The local CLI exposes `prompt-verify`,
`label-validate`, `consensus-merge`, `reader-inspect`, `reader-infer`, `batch-run`, and `eval`
in addition to `doctor`. `reader-infer` and `batch-run` are execution commands: do not issue
them until the owner has authorized a trusted, checksum-pinned local runtime and model. The
[example Reader configuration](examples/local-reader.config.example.json) contains deliberate
path and checksum placeholders and cannot run until every pin is replaced.

## Gold corpus

P1 contains 36 act-level JSON records: 29 Serock acts and seven already-verified Pułtusk
supplements. Rebuild and validate them with:

```powershell
uv run python -m tools.build_gold
uv run pytest
```

See the [labeling protocol](docs/gold-labeling-protocol.md),
[coverage manifest](gold/manifest.json), and [five-act spot-check list](gold/spot_check.json).
All currently permitted verified acts are Russian-language; the missing Polish slice is recorded
as a coverage gap instead of being filled from tentative or prohibited material.

All 36 records are evaluation-only and sequestered by 21 clerk-year IDs in
[`gold/clerk_year_holdout.json`](gold/clerk_year_holdout.json). Their correction consent is not
recorded, so none is training-eligible.

Machine consensus is kept separate. [`labels/silver/manifest.json`](labels/silver/manifest.json)
assigns resolved acts 1–5 to the training-only `SILVER` tier, pins every source label and
arbitration document by SHA-256, and explicitly excludes them from evaluation. Its resolved
field payloads remain content-addressed in the coordinator appendices rather than duplicated;
`training_materialized: false` prevents claiming that a model-ready export already exists. Act 6
has no tier and is quarantined pending the required human identity check.

## P2 implementation and baseline

P2 now contains:

- one fully local, checksum-pinned llama.cpp Reader;
- immutable canonical and explicitly downgraded legacy label ingest;
- strict field-level blind consensus and `[unclear: X/Y]` disagreements;
- date, formula-position, witness-age, and within-clerk-year validators;
- a crash-safe SQLite batch state machine with atomic outputs and progress totals;
- fail-closed privacy preflight;
- SerockBench filiation, calibration, wrong-but-confident, abstention, and observation-state
  metrics with clerk-year leakage rejection.

The batch runner fingerprints the scan, crop/target, model, prompt, schema, decoding settings,
privacy policy, and output destination. A matching success is skipped on resume only while its
output remains a readable JSON object; a missing or damaged output is requeued. Interrupted and
bounded failed jobs can retry; unknown/multi-act targets route to review instead of being guessed.

### Local baseline status

| Measure | Result |
|---|---:|
| Baseline run | **NOT RUN** |
| Gold records evaluated | **0/36** |
| Clerk-year groups sequestered | **21** |
| Prediction coverage | **N/A** |
| Filiation exact match | **N/A** |
| Wrong-but-CONFIDENT rate | **N/A** |
| CONFIDENT / PROBABLE / UNCLEAR calibration | **N/A** |
| Observation-state accuracy | **N/A** |

Windows Security blocked the exact downloaded llama.cpp runtime before model invocation, and no
bypass was authorized. The project did not disable, evade, or weaken that control. Running the
baseline requires explicit owner action to review and provision a trusted runtime, then record
its checksum with the model, projector, prompt, and schema checksums. Until that happens, there
are no local-model predictions and every accuracy or calibration metric is `N/A`.

See the [label factory](docs/label-factory.md) and
[P2 evaluation report](docs/p2-evaluation.md).

## Roadmap and phase gates

1. **P0 — scaffold and landscape:** completed.
2. **P1 — Serock-seeded gold corpus:** completed and owner-approved.
3. **P2 — local MVP pipeline:** implementation complete; real baseline blocked as documented
   above. Acceptance remains filiation exact-match at least 90% and wrong-but-confident below
   2%; no result is claimed yet.
4. **P3 — Pułtusk batch:** begins only after the explicit corpus-acquisition gate.
5. **P4 — name and place variant bridge.**
6. **P5 — publication and single-act interface.**

See [the architecture notes](docs/architecture.md) and
[the dated landscape review](docs/landscape.md).

## License

No open-source license has been selected yet. The P5 decision is explicitly reserved for Jake
(AGPL or MIT). Until a license is added, the repository is not yet offered for reuse.
