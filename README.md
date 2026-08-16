# AKT Reader — Application

> **Repository role:** `aktreader` is the runnable local reader application. It is not the
> evidence/methodology lab and it is not the independent benchmark dataset.

The Python distribution is named `aktreader-app`. It keeps the shorter `aktreader` command and
`aktreader` import namespace for compatibility.

AKTREADER is a local, uncertainty-honest reader for handwritten civil-register acts from
partitioned Poland. It turns a user-supplied scan into a structured evidence object with
original-script transcription, translation, filiation, dates, witnesses, provenance, and
explicit abstention when the image does not decide a reading.

The product claim is deliberately narrow: the machine reads what it can support, marks what it
cannot, and routes ambiguous fields to a human. It does not make genealogy or identity
conclusions.

New to the project? Start with the [AKT Reader glossary](docs/GLOSSARY.md) for the project’s terms around filiation, provenance, observation states, uncertainty, and evaluation.

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
- The same file re-runs representative CLI paths (`doctor`, `prompt-verify`, `compare`, `eval`) with
  socket creation disabled; any attempt to open a socket fails the run.
- Runtime dependencies are `jsonschema` and `pillow` only; the full reviewed license inventory
  (14 packages, including transitive) is `dependency-licenses.json`.
- The only external process the package ever starts is the content-pinned local
  `llama-mtmd-cli` reader subprocess. Owner-side acquisition scripts under `tools/` do use the
  network and are documented in "Owner-only open training sources"; they are not part of the
  installed package.

## Install and run

Python 3.11 or newer is supported (3.10 lacks `tomllib` and rejects some ISO
date-time forms the label files use). With `uv`:

```powershell
uv sync --group dev
uv run aktreader --version
uv run aktreader doctor --json
uv run aktreader checkout-verify
uv run aktreader prompt-verify --root .
```

Without `uv`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m aktreader --version
.\.venv\Scripts\python.exe -m aktreader doctor --json
.\.venv\Scripts\python.exe -m aktreader checkout-verify
.\.venv\Scripts\python.exe -m aktreader prompt-verify --root .
```

Clone the repository for the complete public-checkout verification path. The Application also
builds a self-contained wheel for explicitly configured reader and evaluation workflows. That
wheel bundles only the three small contracts read implicitly by portable commands: the canonical
act schema, the evaluation field map, and its bound model-output schema. It does not bundle the
gold corpus, labels, prompt, source skills, examples, model weights, runtime binary, scans, or
owner-local configuration, and no package has been published to PyPI.

`aktreader doctor` reports those two boundaries separately. A source checkout must match the
`aktreader-app` identity and provide all 25 public checkout contracts. An installed distribution
must provide all three packaged runtime contracts. Neither result claims that model weights or
`llama-mtmd-cli` are installed; use `reader-inspect` with a checksum-pinned configuration for that
separate check. Installed reader commands continue to require explicit external artifact paths.

`doctor --inspect-root PATH` can diagnose another local checkout, including distinguishing the
Evidence Lab's `aktreader-research` metadata from this Application. It does not reconfigure the
running command, so an alternate root never makes `pipeline_available` true.

`checkout-verify` remains the scan-free full-checkout integrity gate. It verifies that the
checkout is the Application, checks all 25 required contract assets, verifies the frozen prompt
against its three source skills and digest, schema-validates and semantically validates every gold
record, compares the corpus coverage to `gold/manifest.json`, and checks permanent clerk-year
holdout separation.
It requires no model weights, runtime binary, source scans, or network access. Use `--json` for a
stable machine-readable report; a failed or skipped check makes the command exit nonzero.

The CLI also provides `label-validate`, `consensus-merge`, `reader-inspect`, `reader-infer`,
`batch-run`, `adjudicate`, `compare`, and `eval`. To run the repository's built-in reader
comparison without supplying scans or model files:

```powershell
python -m aktreader compare labels/readerA labels/readerB `
  --output comparison-report.json `
  --csv comparison-disagreements.csv
```

See [local comparisons](docs/comparisons.md). `reader-infer` and `batch-run` execute local
inference; the other commands validate or process existing artifacts.

The generic [Reader configuration](examples/local-reader.config.example.json) intentionally
cannot run. The [baseline configuration](examples/p2-baseline.local-reader.json) contains the
real pins for a separately provisioned executable, model, projector, prompt, and output schema.

Outside a source checkout, `eval` requires explicit `--gold-dir` and `--holdout` paths rather than
guessing under `site-packages`. Source checkouts retain the tracked defaults. The isolated wheel
gate is reproducible with `python tools/smoke_installed_wheel.py`; it builds and installs a fresh
wheel outside the checkout, inspects explicit checksum-pinned reader artifacts, merges synthetic
labels with the packaged act schema, and evaluates copied explicit corpus inputs. CI runs this
gate on Linux and Windows.

## Which repository do I need?

| Repository | Role | Use it when you want to... |
| --- | --- | --- |
| **`aktreader` (you are here)** | **AKT Reader — Application** | Run or improve the local scan-to-evidence reader. |
| [`aktreader-research`](https://github.com/jakegold1647/aktreader-research) | **AKT Reader — Evidence Lab** | Audit its claims, reproduce evaluations, inspect labels, or develop evidence-aware research utilities. |
| [`congress-poland-registers`](https://github.com/jakegold1647/congress-poland-registers) | **Congress Poland Registers — Benchmark Dataset** | Build or evaluate against an independent, rights-cleared HTR corpus. |

The application and evidence lab have separate histories on purpose. This repository ships the
reader; the evidence lab holds the evidence about how well it reads. The benchmark is independent
of both and is still under construction.

The Application and Evidence Lab share the `aktreader` Python package namespace but have distinct
distribution and preferred command identities: `aktreader-app` / `aktreader` for this Application,
and `aktreader-research` / `aktreader-lab` for the Evidence Lab. Use a separate virtual environment
for each repository. Their import paths still collide, and the Lab retains a legacy `aktreader`
alias for v0.2.0 workflows.

If this checkout was installed before the distribution rename, recreate its virtual environment;
package installers may otherwise leave stale `aktreader` distribution metadata behind.

`aktreader doctor --json` reports project identity, source-checkout readiness, packaged-runtime
readiness, runtime mode, and whether the Application command surface is available. This lets
automation distinguish a complete Application checkout, an installed Application wheel, and the
Evidence Lab rather than treating their shared import namespace as identity.

## Repository map

- `src/aktreader/`: package and CLI implementation.
- `schemas/`: versioned label, model-output, gold, and adjudication contracts. See the generated [schema reference](docs/schema-reference.md) for the human-readable field tree.
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
rules, then check the current GitHub issue queue. [`docs/CONTRIBUTOR_TASKS.md`](docs/CONTRIBUTOR_TASKS.md)
keeps the completed starter tasks and their acceptance notes as useful examples; it is not a
live queue. If there is no open scoped task, describe a small docs or test idea in an issue before
starting so the scope and privacy boundary are clear.

If you used the application and want to report a helpful result, a miss, or a confusing local
failure, use the [sanitized usage-feedback form](https://github.com/jakegold1647/aktreader/issues/new?template=usage-feedback.yml).
Please do not attach scans, record text, names, addresses, private source paths, credentials, or
tokens; the form asks only for the local behavior a maintainer can act on.

## License and dependency inventory

See [`LICENSE`](LICENSE) for the MIT code license and CC BY 4.0 data note. The declared runtime,
development, build, and known transitive dependencies are inventoried in
[`dependency-licenses.json`](dependency-licenses.json). Run
`python -m tools.check_dependency_licenses` after dependency changes. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for evidence and privacy rules.
