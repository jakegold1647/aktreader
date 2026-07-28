# AKTREADER

AKTREADER is an evidence-first pipeline for scanned civil-register acts from partitioned
Poland. Its intended output is a structured genealogical extraction in which every field is
traceable to the scan and uncertainty is recorded instead of guessed.

> **Project status: P1 review gate.** The repository contains a source-backed gold corpus, but
> AKTREADER does not read or extract new acts yet. Do not use this version for genealogical
> conclusions.

## Why this project exists

Most handwriting tools optimize for plausible text. AKTREADER will consume a vision reader or
imported transcription and concentrate on the layers above recognition: act-format structure,
filiation-first extraction, evidence provenance, explicit uncertainty, and evaluation of
wrong-but-confident claims.

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

The source tree uses the `src/` layout. The current CLI has only version and environment
diagnostics; pipeline commands arrive in P2.

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

## Roadmap and phase gates

1. **P0 — scaffold and landscape:** completed.
2. **P1 — Serock-seeded gold corpus:** current review gate; no inferred completions.
3. **P2 — MVP pipeline:** filiation exact-match at least 90% and wrong-but-confident below 2%.
4. **P3 — Pułtusk batch:** begins only after the explicit corpus-acquisition gate.
5. **P4 — name and place variant bridge.**
6. **P5 — publication and single-act interface.**

See [the architecture notes](docs/architecture.md) and
[the dated landscape review](docs/landscape.md).

## License

No open-source license has been selected yet. The P5 decision is explicitly reserved for Jake
(AGPL or MIT). Until a license is added, the repository is not yet offered for reuse.
