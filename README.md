# AKTREADER

AKTREADER is a local, uncertainty-honest reader for handwritten civil-register acts from
partitioned Poland. It turns a user-supplied scan into a structured evidence object with
original-script transcription, translation, filiation, dates, witnesses, provenance, and
explicit abstention when the image does not decide a reading.

The product claim is deliberately narrow: the machine reads what it can support, marks what it
cannot, and routes ambiguous fields to a human. It does not make genealogy or identity
conclusions.

> **Release status: public-release candidate, not a production-grade reader yet.** The local
> pipeline and review tooling are implemented. The first local baseline evaluated 20/36 records,
> with 1/77 exact filiation fields and 0/20 exact filiation acts. That is a real, weak baseline,
> not a success claim. The current corpus has 0/36 fully image-attested benchmark records, so
> those numbers are research-derived diagnostics rather than publication-grade accuracy. See
> [the current baseline addendum](docs/p2-baseline-addendum.md).

## What is included

- A local-only Python package and CLI; no hosted model API, API key, inference server, or
  automatic model download.
- Content-pinned `llama-mtmd-cli` integration for an owner-provisioned open-weights vision model.
- Strict label validation, original-script grounding, typed absence states, consensus, human
  adjudication packets, resumable batch execution, privacy preflight, and SerockBench metrics.
- A 36-record evaluation corpus, frozen prompts and schemas, provenance manifests, and a
  documented failure history.

AKTREADER is not currently a hosted translation website. It does not ship model weights or
archive scans. Users supply their own images and separately provision the runtime/model files
described in [local model and runtime](docs/local-model.md).

## Current evidence and limitations

The baseline is intentionally reported in full:

| Measure | Result |
| --- | ---: |
| Prediction coverage | 55.56% (20/36) |
| Filiation field exact match | 1.30% (1/77) |
| Filiation act exact match | 0.00% (0/20) |
| Wrong-but-CONFIDENT | N/A (0/0) |
| PROBABLE calibration | 27.86% (39/140) |
| Observation-state accuracy | 99.30% (141/142) |

The corpus is evaluation-only and sequestered by 21 clerk-year IDs. Its records are
research-derived; the attestation audit currently finds 0/36 fully image-verified acts. The
1.30% result must not be presented as validated handwriting accuracy.

Historical machine-consensus payloads remain audit evidence, not training data. Training is
blocked until new v1.4-or-later labels have grounded continuous transcriptions, recorded
consent, and a clerk-year-separated holdout. See [the training transition gate](docs/training-transition.md).

## Non-negotiable behavior

- Never fill a missing or unreadable field from expectation.
- Preserve unresolved alternatives as `[unclear: X/Y]`.
- Keep `ABSENT_ON_FORM`, `BLANK`, and `ILLEGIBLE` distinct.
- Keep every assertion tied to source spans, artifact hashes, reader identity, and prompt/schema
  pins.
- Include `extraction is not authority - verify against the scan` in generated outputs.
- Refuse acts inside the configured privacy window by default.
- Never scrape archives, bulk-ingest restricted memorial data, or add a correction to training
  without recorded consent.

## Verifiable no-egress

"Local-only" is asserted by tests, not by this paragraph. The inventory of network endpoints
is: none.

- `tests/test_no_egress.py` (CI-enforced) parses every module in `src/aktreader` and fails if
  any networking-capable module is imported, and pins the runtime dependency set so a network
  client cannot arrive transitively without that test changing in the same review.
- The same file re-runs representative CLI paths (`doctor`, `prompt-verify`, `eval`) with
  socket creation disabled; any attempt to open a socket fails the run.
- Runtime dependencies are `jsonschema` and `pillow` only; the full reviewed license inventory
  (14 packages, including transitive) is `dependency-licenses.json`.
- The only external process the package ever starts is the content-pinned local
  `llama-mtmd-cli` reader subprocess. Owner-side acquisition scripts under `tools/` do use the
  network and are documented in "Owner-only open training sources"; they are not part of the
  installed package.

## Install and run

Python 3.10 or newer is supported. With `uv`:

```powershell
uv sync --group dev
uv run aktreader --version
uv run aktreader doctor --json
uv run aktreader prompt-verify --root .
```

Without `uv`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m aktreader --version
.\.venv\Scripts\python.exe -m aktreader doctor --json
.\.venv\Scripts\python.exe -m aktreader prompt-verify --root .
```

The CLI also provides `label-validate`, `consensus-merge`, `reader-inspect`, `reader-infer`,
`batch-run`, `adjudicate`, `compare`, and `eval`. To run the repository's built-in reader
comparison without supplying scans or model files:

```powershell
python -m aktreader compare labels/readerA labels/readerB --output comparison-report.json
```

See [local comparisons](docs/comparisons.md). `reader-infer` and `batch-run` execute local
inference; the other commands validate or process existing artifacts.

The generic [Reader configuration](examples/local-reader.config.example.json) intentionally
cannot run. The [baseline configuration](examples/p2-baseline.local-reader.json) contains the
real pins for a separately provisioned executable, model, projector, prompt, and output schema.

## Repository map

- `src/aktreader/`: package and CLI implementation.
- `schemas/`: versioned label, model-output, gold, and adjudication contracts.
- `prompts/` and `skills/`: frozen reader instructions and domain constraints.
- `gold/`: evaluation records and clerk-year holdout metadata.
- `labels/`: attributable reader and consensus evidence, including quarantined historical data.
- `docs/`: architecture, benchmark, local-runtime, training, and human-review contracts.
- `tests/`: focused regression and contract tests.

## Public-release boundary

The application code is released under the MIT License. Bundled derived records and labels carry
the CC BY 4.0 data note in [`LICENSE`](LICENSE). Source scan images are not redistributed;
provenance hashes and crop coordinates are retained where they are needed for reproducibility.
Local human-review packets may contain scan derivatives and are intentionally excluded from the
public release.

The project is a release candidate for the repository and CLI, not a claim that the reader has
met the original 90% filiation target. A hosted single-act UI, image-attested benchmark release,
and grounded training set remain future work.

## Owner-only open training sources

Open base-script corpora are provisioned outside AKTREADER with
[`tools/fetch_open_datasets.ps1`](tools/fetch_open_datasets.ps1). The application never calls
this script. The owner first reviews the immutable URLs, hashes or byte pins, licenses, and
explicit exclusions in
[`resources/open_datasets.manifest.json`](resources/open_datasets.manifest.json). Downloads use
`.partial` files, move only after verification, remain unexpanded, and receive adjacent
download and license receipts.

| Dataset | LoRA recipe role | Eligibility basis |
|---|---|---|
| Digital Peter | Base-script adaptation | MIT, immutable Hugging Face revision and SHA-256 pins |
| Cyrillic Handwriting Dataset v5 | Base-script adaptation | CC0, exact Kaggle version and byte pin; observed SHA-256 recorded |
| school-notebooks-RU | Base-script adaptation | MIT, immutable Hugging Face revision and SHA-256 pins |

No text-side lexicon corpus currently clears every gate. Yad Vashem, USHMM, Arolsen, Geneteka,
and JRI-Poland remain excluded regardless of accessibility; the full exclusion rationale lives
in the manifest.

## Roadmap

1. Finish image-attested human qualification and rebuild the grounded training pool.
2. Re-run the local reader against a properly attested, clerk-year-separated holdout.
3. Add the Pultusk batch only after its corpus-acquisition and rights gate is explicitly cleared.
4. Ship a small single-act interface after the local CLI and evidence contracts are stable.

See [the architecture notes](docs/architecture.md), [SerockBench](docs/serockbench.md), and
[the public contribution launch prompt](docs/DEEP_RESEARCH_PUBLIC_CONTRIBUTION_LAUNCH_PROMPT.md)
for the longer-term plan.

## Contributing

Contributions are welcome, and most of the codebase is workable without scans, model weights, or
GPU hardware. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) for the evidence and privacy
rules, then pick something from [`docs/CONTRIBUTOR_TASKS.md`](docs/CONTRIBUTOR_TASKS.md) — a
list of scoped starter tasks with acceptance criteria, several tagged *good first issue*.

## License and dependency inventory

See [`LICENSE`](LICENSE) for the MIT code license and CC BY 4.0 data note. The declared runtime,
development, build, and known transitive dependencies are inventoried in
[`dependency-licenses.json`](dependency-licenses.json). Run
`python -m tools.check_dependency_licenses` after dependency changes. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for evidence and privacy rules.
