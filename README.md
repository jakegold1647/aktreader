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
- A content-pinned local Kraken adapter that recognizes existing PAGE XML and returns a new PAGE XML result without a server, download, or package dependency.
- Strict label validation, original-script grounding, typed absence states, consensus, human
  adjudication packets, resumable batch execution, privacy preflight, and SerockBench metrics.
- A local PAGE XML and image-directory import foundation that hashes supplied page images and
  preserves page, region, line, polygon, baseline, reading-order, and transcription provenance
  in a deterministic manifest.
- An experimental local `.aktproj` store with a SQLite index and content-addressed copies of
  PAGE XML and page images; no server, account, or network connection is involved.
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

Before operating a local service with non-public records, read the
[threat model](docs/threat-model.md), [data-governance policy](docs/data-governance.md),
[security policy](SECURITY.md), and [local-service production proof](docs/production-proof.md).
The supported service boundary remains one trusted machine on loopback; it is not a public or LAN
deployment.

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
  socket creation disabled; any attempt to open a socket fails the run. This includes
  `pagexml-import`.
- Runtime dependencies are `jsonschema`, `pillow`, and `pypdfium2`; the reviewed Python-package
  license inventory (16 packages, including transitive) is `dependency-licenses.json`. PDFium wheel
  redistributions must retain their bundled third-party notices.
- The only external processes the package starts are content-pinned local reader and Kraken
  subprocesses. They receive only local paths and a credential-free, offline environment. Owner-side
  acquisition scripts under `tools/` do use the network and are documented in "Owner-only open
  training sources"; they are not part of the installed package.

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

The CLI also provides `label-validate`, `collection-create`, `collection-add-project`,\n`collection-inspect`, `collection-list-documents`, `collection-search`, `collection-save-search`, `collection-list-saved-searches`, `collection-run-saved-search`, `collection-export-public`, `project-create`,\n`project-inspect`,
`project-list-documents`, `project-list-pages`, `project-show-page`,
`project-show-page-layout`, `project-search`, `project-activity`,
`project-show-revision-history`,
`project-revise-line-transcription`, `project-undo-line-transcription`,
`project-restore-line-transcription`,
`project-update-document`,
`project-import-pagexml`, `project-import-images`, `project-import-pdf`,
`project-import-htr-suggestions`, `project-kraken-segment`,
`project-kraken-recognize`, `project-export-pagexml`, `project-export-transcript`,
`project-export-transcriptions-csv`, `project-export-alto`, `project-export-pdf`,
`project-evaluate-htr`, `project-list-htr-evaluations`, `project-grant-training-consent`,
`project-revoke-training-consent`,
`project-training-readiness`, `project-export-consented-training-pagexml`,
`project-export-review-package`, `project-import-review-package`,
`project-resolve-review-proposal`, `project-revise-line-geometry`,
`project-undo-line-geometry`, `project-restore-line-geometry`,
`project-revise-page-reading-order`, `project-undo-page-reading-order`,
`project-restore-page-reading-order`, `project-revise-region-geometry`,
`project-undo-region-geometry`, `project-restore-region-geometry`,
`htr-build-corpus`,
`htr-inspect-corpus`, `workbench`, `serve`, `pagexml-import`,
`consensus-merge`, `reader-inspect`,
`reader-infer`, `kraken-inspect`, `kraken-recognize`, `kraken-train`, `kraken-evaluate`,
`batch-run`, `adjudicate`, `compare`, and `eval`. To run the repository's built-in
reader comparison without supplying scans or model files:

```powershell
python -m aktreader compare labels/readerA labels/readerB `
  --output comparison-report.json `
  --csv comparison-disagreements.csv
```

See [local comparisons](docs/comparisons.md). `reader-infer` and `batch-run` execute local
inference; the other commands validate or process existing artifacts.

### Local collections

A collection is a local, refreshable index across multiple projects. It stores effective line text,
document titles, tags, notes, and provenance pointers—never source scans—and never requires a server.

```powershell
python -m aktreader collection-create registers.aktcollection --name "Serock registers"
python -m aktreader collection-add-project registers.aktcollection serock.aktproj
python -m aktreader collection-list-documents registers.aktcollection --query "births"
python -m aktreader collection-search registers.aktcollection "Aleksander"
```

`collection-list-documents` searches only locally indexed document metadata. Run
`collection-add-project` again after editing a project's transcription or document metadata to refresh
its index. A named saved search is private to that local collection; it re-runs against the refreshed
index and is never included in a public static release.

```powershell
python -m aktreader collection-save-search registers.aktcollection `
  --name "Aleksander records" `
  --query "Aleksander"
python -m aktreader collection-list-saved-searches registers.aktcollection
python -m aktreader collection-run-saved-search registers.aktcollection `
  --search-id <saved-search-id>
```

To create a static, read-only release for a separate public web host, export the selected collection
explicitly. This writes `index.json` plus stable document URLs under `documents/<project-id>/<document-id>.json`;
the loopback service does not serve it. `--confirm-public` and a declared license are mandatory because the
release contains the indexed human-visible text and selected document metadata. It excludes filesystem paths and
private document notes. Review the release before uploading or sharing it, because copied public data cannot be
recalled from third-party hosts.

```powershell
python -m aktreader collection-export-public registers.aktcollection `
  --output public-registers `
  --license-id CC-BY-4.0 `
  --confirm-public
```

### Local projects

Create a project before importing material that should remain available to the future desktop
workbench. Importing copies the XML and its named page images into the project by SHA-256, while
the stored manifest retains the original local paths for provenance.

```powershell
python -m aktreader project-create serock.aktproj --name "Serock births"
python -m aktreader project-import-pagexml serock.aktproj page.xml --image-root .
python -m aktreader project-inspect serock.aktproj
python -m aktreader project-list-pages serock.aktproj
python -m aktreader project-show-page serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> --page-index 0
python -m aktreader project-show-page-layout serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> --page-index 0
```

The page commands are read-only and local-only. `project-show-page` includes source and effective
line text, stable source-span IDs, current transcription revisions, imported HTR suggestions, and
pending review proposals. `project-show-page-layout` reports effective reading order plus region
and line geometry revisions. These outputs can contain transcription content and local image paths;
review them before copying them into logs or sharing them.

For scans that have not been segmented yet, import one directory of top-level image files. AKT Reader
creates and retains a deterministic PAGE XML source with one editable full-page TextRegion per scan,
then copies the images into the same content-addressed project store.

```powershell
python -m aktreader project-import-images serock.aktproj serock-scans `
  --title "Serock births, 1890"
```

Use a separately provisioned, checksum-pinned local Kraken runtime to derive a new editable
layout document before text recognition. The raw image import remains immutable; the derivative
carries regions, lines, baselines, and reading order for visual correction.

```powershell
python -m aktreader project-kraken-segment serock.aktproj `
  --manifest-sha256 <image-import-manifest-sha256> `
  --config E:\AKTREADER_LOCAL\kraken.config.json

python -m aktreader project-kraken-recognize serock.aktproj `
  --manifest-sha256 <kraken-layout-manifest-sha256> `
  --config E:\AKTREADER_LOCAL\kraken.config.json
```

See [local Kraken layout and recognition](docs/local-kraken.md) for the local-only pinning,
validation, and review boundary.

For local PDFs, render into the same editable PAGE workflow with a fixed, recorded DPI. The original
PDF is copied into the project by SHA-256, while a receipt pins its renderer version and every
rendered page object.

```powershell
python -m aktreader project-import-pdf serock.aktproj serock-births.pdf `
  --dpi 300 --title "Serock births, 1890"
```

PDF rendering is local-only through pypdfium2/PDFium. Imports reject remote paths, encrypted or
unreadable documents, more than 500 pages, DPI outside 72–600, and pages above the 50-million-pixel
safety limit; they do not extract text or call a remote OCR service.

Projects are intentionally local-only and contain no training consent. Importing source material
does not make it training data or publishable data.

Every import is also a stable document record. Its local title, tags, and notes can be updated without
touching the PAGE XML or images; see [document metadata](docs/document-metadata.md).

Search one project without first building a collection. Results use the latest effective human
revision, can target transcription text, document titles, or tags, and never require network access:

```powershell
python -m aktreader project-search serock.aktproj "Aleksander" --field text --limit 20
```

Inspect the bounded revision trail for one imported document without exposing prior or revised
transcription content. The report includes event kind, stable page/region/line identifiers, revision,
editor, and timestamp; it is local-only and read-only:

```powershell
python -m aktreader project-activity serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> --limit 50

python -m aktreader project-activity serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --kind LINE_GEOMETRY --page-index 0 --source-span-id <source-span-id>
```

`--kind`, `--page-index`, `--source-span-id`, and `--region-id` are optional exact filters and
can be combined. The JSON report echoes their normalized values under `filters`; omitted filters
remain `null`. Filtering does not add prior text, revised text, polygons, or other revision content
to the activity feed.

When choosing a target for an append-only restoration, inspect one exact entity with the separate
`project-show-revision-history` command. Unlike the activity feed, that command deliberately returns
historical values and may therefore expose private human transcription content. See
[restoring prior revisions](docs/revision-restoration.md) for selectors, pagination, and handling.

### Loopback browser workbench

For a single-user browser editor on the same machine, explicitly serve one project on loopback:

```powershell
python -m aktreader serve serock.aktproj
```

It prints a `127.0.0.1` URL with document/page navigation and generated thumbnails, effective PAGE
line polygons and baselines, region overlays, saved human transcription revisions, and auditable
line geometry, region geometry, or reading-order changes. Layout vertices can be dragged on the
scan or entered as source-pixel coordinates. A bounded, contentful history view can inspect any of
those four streams and restore an explicitly selected older value by appending a new audited
revision. The workbench can also search effective transcription text, document titles, and tags
locally, then jump directly to a matching line. Unsaved work is identified per stream: line,
region, page, and document changes require
confirmation before discarding an affected draft, while saving one stream preserves drafts in the
others. Reloading or closing a dirty tab also triggers the browser's unsaved-work warning. Every
save and restoration is revision-checked; a stale tab must reload and review newer work before
trying again. The server rejects nonlocal request authorities, cross-origin browser
requests, and non-JSON write bodies. It has no accounts and cannot bind to a LAN or public address,
so it is not yet a shared deployment. See
[the self-hosted browser workbench boundary](docs/self-hosted-browser-workbench.md).

### Loopback service workspace and backups

A separate local service workspace can own copies of projects, run durable checksum-verified
backup jobs, enforce local password-protected project roles, issue recipient-bound, time-limited
local invitation codes for existing accounts, provide role-checked document review and optimistic
transcription updates, track attached model/dataset artifacts by hash, and serve an authenticated
collaborative browser workbench. It binds only to `127.0.0.1` on the host and must not be exposed through a reverse proxy or
public address.

```powershell
python -m aktreader service-create service-data
python -m aktreader service-add-project service-data serock.aktproj
python -m aktreader service-serve service-data
```

See [the self-hosted service foundation](docs/self-hosted-service.md) for the managed-storage,
backup verification, restore, and loopback-only Compose boundary.

### Local transcription workbench

Open an imported project in a local desktop window to choose a named document, page through only
that document's imported pages, see the source image with PAGE line bounds, select lines, and save
human transcription revisions. Each save appends a revision to the project SQLite index; it does not
overwrite the imported PAGE XML or alter the source image.

```powershell
python -m aktreader workbench serock.aktproj
```

After a reviewer has explicitly saved corrections, export a separate, standards-compatible PAGE XML
derivative for interchange or future consent-gated local HTR training. The command applies only the latest human revision
for each line; it never promotes an engine proposal by itself and it never changes the project source
object or revision history.

```powershell
python -m aktreader project-export-pagexml serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-human.page.xml
```

Exports must live outside the project and will not replace an existing file unless
`--replace-existing` is explicit.

For corrected text that needs to leave the workbench without scans or model proposals, export a
plain UTF-8 transcript, a provenance-preserving CSV, interoperable ALTO XML, or a PDF presentation
derivative. All four use imported text until a reviewer has saved a human revision; they never
promote HTR suggestions or
pending review proposals. The transcript keeps source line order and places a form-feed between
pages. The CSV includes stable page/region/line identifiers, the imported text, effective text,
revision number, and editor. The ALTO export applies current human text plus line and region
geometry and reading-order revisions as source-pixel coordinates. A PDF export is a rendered, image-only presentation derivative: it
uses the current human text and line geometry but includes neither source scans nor a selectable
text layer. Pair it with ALTO when searchable interchange is needed. The PDF uses a local
Unicode-capable TrueType font; pass `--font C:\\fonts\\NotoSans-Regular.ttf` (or set
`AKTREADER_PDF_FONT`) to pin the font for reproducible rendering. None of these exports includes
project paths or source images.

```powershell
python -m aktreader project-export-transcript serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-human.txt

python -m aktreader project-export-transcriptions-csv serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-human-lines.csv

python -m aktreader project-export-alto serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-human.alto.xml

python -m aktreader project-export-pdf serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-human.pdf
```

The CSV exposes each line's stable `source_span_id` and current `revision`. Use both to append an
optimistically locked human correction; a stale revision is refused instead of overwriting newer
work. Undo appends the prior text as a new revision, preserving the full history and the imported
PAGE XML source:

```powershell
python -m aktreader project-revise-line-transcription serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --source-span-id <source-span-id> --text "corrected text" `
  --editor local-user --expected-revision 0

python -m aktreader project-undo-line-transcription serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --source-span-id <source-span-id> --editor local-user --expected-revision 1
```

Undo restores only the immediately preceding value. To restore any older transcription or layout
revision, including imported state as revision zero, see
[restoring prior revisions](docs/revision-restoration.md). Every restoration remains append-only
and uses the current revision as an optimistic-lock precondition.

### Offline review exchange

A reviewer can send current human transcription proposals to an owner as a local checksummed JSON
package. Importing the package never overwrites text: matching bases become queued proposals,
stale bases become conflicts, and each proposal must be explicitly accepted or rejected. Packages
do not carry source scans, model outputs, or training consent.

```powershell
python -m aktreader project-export-review-package reviewer-copy.aktproj `
  --manifest-sha256 <reviewer-import-manifest-sha256> `
  --contributor reviewer-1 `
  --output register-review.aktreview.json

python -m aktreader project-import-review-package owner.aktproj register-review.aktreview.json
python -m aktreader project-resolve-review-proposal owner.aktproj `
  --proposal-sha256 <proposal-sha256> `
  --decision accept `
  --editor owner-1
```

See [offline review exchange](docs/offline-review-exchange.md) for the integrity and conflict
rules. Contributor names are local claims, not authentication, and training consent is always a
separate explicit step.

Line polygons and baselines can also be corrected as versioned source-pixel geometry revisions and
applied only to a newly exported PAGE XML derivative. See [line geometry revisions](docs/line-geometry.md).

Page region sequence is its own audited revision stream: a reviewer supplies a complete permutation
of the imported region IDs for one page, and only a new PAGE XML derivative receives that order. See
[page reading-order revisions](docs/page-reading-order.md).

TextRegion polygons use an independent versioned source-pixel revision stream and are likewise
applied only to a derivative. See [region geometry revisions](docs/region-geometry.md).

Evaluate a specific imported HTR result only against saved human revisions. The report is pinned
to the project import and recognition PAGE XML hashes; it uses Unicode NFC with exact whitespace,
and reports CER, WER, exact-line match, and the coverage counts needed to judge whether the sample
is meaningful. With no explicit human revisions it writes a `NO_EVALUABLE_HUMAN_REVISIONS` report
rather than treating imported text as truth.

```powershell
python -m aktreader project-evaluate-htr serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --result-pagexml-sha256 <imported-result-pagexml-sha256> `
  --output serock-kraken-evaluation.json

python -m aktreader project-list-htr-evaluations serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256>
```

The listing recalculates every imported run against the latest saved human revisions and prints
the newest run first. It is read-only, stays local, and includes metrics and provenance hashes but
no transcription content or filesystem paths.

Training permission is also explicit and line-level. A contributor can consent only to their
current saved revision; a later revision becomes unconsented, and withdrawal prevents any future
export that relies on that grant. This records readiness only—it neither exports material nor
starts a training job.

```powershell
python -m aktreader project-grant-training-consent serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --contributor local-user `
  --all-human-revised
python -m aktreader project-training-readiness serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --output serock-training-readiness.json
```

A report is `READY_FOR_PAGEXML_TRAINING_EXPORT` only when every source line has both a current
human revision and an active consent bound to that exact revision.

When readiness is green, create a self-contained PAGE XML bundle for a fixed split. It copies the
project’s checksum-verified images, writes only the human revisions, records opaque consent
evidence, and refuses to assign the same project import to another split later.

```powershell
python -m aktreader project-export-consented-training-pagexml serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --split train `
  --output-directory serock-train-bundle
```

The bundle is local only and does not run or download Kraken. Its `bundle.aktreader.json` records
the exact PAGE XML, image, consent, and split inputs for a separately provisioned local trainer.

To prepare one reproducible training corpus across projects, create a local JSON plan. It records
only local project locations, the immutable import IDs, and the intended split; those source paths
do not appear in the resulting corpus receipt.

```json
{
  "contract": {
    "name": "aktreader-local-htr-corpus-plan",
    "version": "1.0.0"
  },
  "inputs": [
    {
      "project": "serock-train.aktproj",
      "manifest_sha256": "<project-import-manifest-sha256>",
      "split": "train"
    },
    {
      "project": "serock-validation.aktproj",
      "manifest_sha256": "<project-import-manifest-sha256>",
      "split": "validation"
    }
  ]
}
```

Build the local corpus from that plan:

```powershell
python -m aktreader htr-build-corpus `
  --plan corpus-plan.json `
  --output-directory serock-htr-corpus
```

The command rechecks each project's current human revisions and active consent before writing an
atomic corpus. It requires both train and validation inputs, rejects duplicated source PAGE XML,
writes explicit `train.lst` and `validation.lst` manifests, and forbids Kraken's random
partitioning. Run the pinned local trainer from the corpus directory with the exact command
recorded in `corpus.aktreader.json`; it has no server address, credentials, source-project paths,
or network requirement.

Inspect it again immediately before an eventual trainer run. The inspector rereads the current plan
and consent state, then verifies every copied bundle, image, PAGE XML file, receipt, and root split
manifest without running a model.

```powershell
python -m aktreader htr-inspect-corpus `
  --plan corpus-plan.json `
  --corpus-directory serock-htr-corpus
```

Once that check is green, launch a fresh run only through a checksum-pinned local `ketos`
configuration. The runner generates the explicit experiment file, passes no remote settings,
retains local logs, and publishes `training-run.aktreader.json` with hashes for the corpus,
executable, options, and produced weights.

```powershell
python -m aktreader kraken-train `
  --config local-kraken-training.json `
  --plan corpus-plan.json `
  --corpus-directory serock-htr-corpus `
  --output-directory serock-training-run
```

When the same plan includes an explicit held-out `test` split, evaluate a checksummed weights
file from that training run. The evaluation runner repeats consent/corpus inspection and verifies
the executable, model, and training receipt before it invokes local `ketos test`.

```powershell
python -m aktreader kraken-evaluate `
  --config local-kraken-evaluation.json `
  --plan corpus-plan.json `
  --corpus-directory serock-htr-corpus `
  --training-run-directory serock-training-run `
  --output-directory serock-evaluation-run
```

See [the local Kraken guide](docs/local-kraken.md) for the configuration contract.

The workbench requires a Python installation that includes Tk desktop support. It never starts a
web server, sends data to a service, or treats a correction as model-training consent.

### PAGE XML import

`pagexml-import` is the first workbench-facing contract. It accepts one local PAGE XML file and
the local page images named by its `imageFilename` values, then writes a deterministic manifest.
It does not run a model, alter the XML, upload material, or treat a transcription as verified.

```powershell
python -m aktreader pagexml-import page.xml --image-root . --output pagexml-import.json
```

The manifest hashes the XML and each page image, preserves PAGE page/region/line IDs, line polygons
and baselines, captures explicit reading order when present, and records the selected `TextEquiv`
text without fabricating missing transcription. An owner can run the separately provisioned,
checksum-pinned [local Kraken PAGE XML adapter](docs/local-kraken.md) against that same geometry;
its output can be imported as aligned, versioned project suggestions but remains separate until a
human reviews it. The current reader-label schema remains unchanged; a later schema revision will bind observation spans to these immutable line locators.

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
