# AKTREADER

AKTREADER produces institutionally usable evidence objects from difficult handwritten
records — structured records, uncertainty you can act on, local deployment, machine-readable
provenance, and feedback loops that accumulate expertise instead of discarding it.

The first pilot reads civil-register acts from partitioned Poland and keeps every extracted field
traceable to the scan.

> **Project status: P2 gate accepted; constrained baseline blocked on one mtmd probe.** The
> local-only Reader, external-label ingest, consensus, validators, resumable batch engine,
> SerockBench harness, and leakage-safe silver export are implemented. The measured “before”
> baseline found two failures: b10167 `llama-cli` crashes when Qwen3.5’s chat template is combined
> with grammar sampling, while unconstrained output either repetition-loops or returns a hollow
> schema-shaped shell. The same build’s `llama-mtmd-cli` initializes grammar successfully; a
> reduced-schema one-job probe must pass before the final capped retry. No benchmark accuracy is
> inferred from unit tests or diagnostics.

## Why this project exists

Historical-record tooling still leaves four practical gaps:

- confidence scores often accompany a forced reading, while researchers need actionable
  abstention and preserved alternatives;
- page transcripts are not register-native records with filiation, roles, and typed absence;
- hosted workflows depend on accounts or page credits, while preservation needs a local path;
- plausible text can fabricate a person or swap a role. Two AKTREADER blind-review waves caught
  that phantom-person failure class before promotion.

AKTREADER concentrates on the evidence layers above raw recognition: act-format structure,
filiation-first extraction, explicit uncertainty, and wrong-but-confident evaluation. Every label
carries machine-readable model identity, software and prompt versions/hashes, blind status,
artifact binding, and uncertainty. Labels produced manually in two independent subscription AI
sessions can be imported as files; the application never calls those assistants.

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

The application invokes a content-pinned `llama-mtmd-cli` executable directly as a subprocess. It
does not start an inference server, send HTTP to localhost, use a hosted SDK, or accept an API
key.

- **16 GB development default:** Qwen3.5-9B Q5_K_M with an F16 vision projector; the exact
  revision, byte sizes, hashes, and local paths are frozen in
  [`examples/p2-baseline.artifacts.json`](examples/p2-baseline.artifacts.json).
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
in addition to `doctor`. `reader-infer` and `batch-run` are execution commands. The generic
[example Reader configuration](examples/local-reader.config.example.json) intentionally cannot
run; the [P2 baseline configuration](examples/p2-baseline.local-reader.json) contains real pins
for the executable, model, projector, frozen v1.2 prompt/schema, and reduced model-output schema.

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
arbitration document by SHA-256, content-addresses five materialized field payloads, and excludes
them from evaluation. The training exporter fails before writing an example if a chosen
evaluation holdout contains Serock-1890; consequently the current SerockBench holdout correctly
rejects all five silver records. Act 6 has no tier and remains quarantined pending the required
human identity check.

## P2 implementation and baseline

P2 now contains:

- one fully local, checksum-pinned llama.cpp Reader;
- first-class machine-readable provenance for runtime, model, prompt, schema, artifact, blind
  status, and uncertainty;
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
| Scan-backed gold records available for the first run | **24/36** |
| Runtime verification | **PASS — b10167 mtmd grammar initialization** |
| Model/projector pins | **Verified local artifacts** |
| Raw failure probes | **5 grammar crashes; repetition loop; hollow shell** |
| Clerk-year groups sequestered | **21** |
| Prediction coverage | **N/A** |
| Filiation exact match | **N/A** |
| Wrong-but-CONFIDENT rate | **N/A** |
| CONFIDENT / PROBABLE / UNCLEAR calibration | **N/A** |
| Observation-state accuracy | **N/A** |

The baseline remains unspent until one `reader-infer` probe proves constrained output through
the pinned mtmd frontend. Only then may `batch-run --max-retries 3
--rebind-failed-fingerprints` preserve the existing retry audit and spend the final approved
attempt. Failed jobs retain raw stdout/stderr paths in the checkpoint. Twelve gold records remain
honestly marked `NOT_LOCALIZED`: five exact Serock source objects returned HTTP 415 and seven
Pułtusk routes remain explicitly unresolved.

See [SerockBench](docs/serockbench.md), the [label factory](docs/label-factory.md), the
[baseline addendum](docs/p2-baseline-addendum.md), and the
[P2 evaluation report](docs/p2-evaluation.md).

## Roadmap and phase gates

1. **P0 — scaffold and landscape:** completed.
2. **P1 — Serock-seeded gold corpus:** completed and owner-approved.
3. **P2 — local MVP pipeline:** implementation gate accepted; prompt v1.3 is frozen for new
   factory waves while the measured baseline remains pinned to exact v1.2 snapshots. The real
   baseline attaches after the mtmd reduced-schema probe. The performance targets remain
   filiation exact-match at least 90% and wrong-but-confident below 2%; no model result is
   claimed yet.
4. **P3 — Pułtusk batch:** begins only after the explicit corpus-acquisition gate.
5. **P4 — name and place variant bridge.**
6. **P5 — publication and single-act interface.**

See [the architecture notes](docs/architecture.md) and
[the dated landscape review](docs/landscape.md).

## License

No open-source license has been selected yet. The P5 decision is explicitly reserved for Jake
(AGPL or MIT). Until a license is added, the repository is not yet offered for reuse.

Every declared runtime, development, build, and known transitive dependency is inventoried in
[`dependency-licenses.json`](dependency-licenses.json); run
`python -m tools.check_dependency_licenses` after dependency changes. See
[CONTRIBUTING.md](CONTRIBUTING.md).
