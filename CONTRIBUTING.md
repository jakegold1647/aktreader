# Contributing to AKTREADER

Contributions are welcome — this project is small enough that one good pull request moves it
visibly. AKTREADER treats provenance and uncertainty as product behavior: a contribution is not
complete when it merely produces plausible text; it must preserve the path from scan pixels to
every assertion.

You do not need archive scans, model weights, or GPU hardware to contribute. The test suite,
label validators, consensus merge, and the `compare` command all run against tracked fixtures in
an ordinary checkout.

## Getting started

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

(On Linux/macOS use `.venv/bin/python` instead.) A checksum test that binds evaluation records
to owner-local source files skips itself automatically when those files are absent — that is
expected in a public checkout.

If you are looking for somewhere to start, see
[`docs/CONTRIBUTOR_TASKS.md`](docs/CONTRIBUTOR_TASKS.md) for scoped, self-contained tasks with
acceptance criteria, or open an issue describing what you want to improve. Domain knowledge
(Cyrillic paleography, Jewish onomastics, Napoleonic act structure) is valuable but optional:
the `skills/` directory teaches the domain, and plenty of pending work is pure Python.

For a quick orientation, see the [AKT Reader glossary](docs/GLOSSARY.md) before changing evidence, labels, or evaluation documentation.

## Before opening a change

- Use Python 3.11 or newer in an isolated environment.
- Install the development group and run `python -m pytest`.
- Run `python -m ruff check .` when Ruff is installed.
- Run `python -m tools.check_dependency_licenses` after any dependency edit.
- For packaging changes, run `python tools/smoke_installed_wheel.py`; CI repeats that isolated
  install on Linux and Windows.
- Do not add model downloads, hosted-model APIs, archive scraping, login automation, or secrets.
- Do not include restricted memorial-institution material in labels or training data.

## Data and label changes

- Never edit a frozen Reader label in place; add a new attributable artifact.
- Preserve the exact scan hash, prompt hash, Reader identity, blind group, clerk-year, source
  spans, observation states, and authority warning.
- A single Reader cannot emit `CONFIDENT`.
- Machine 2-of-3 resolution is `SILVER`/`PROBABLE`, not human-verified gold.
- Any training export must pass the clerk-year split validator against its chosen evaluation
  holdout.
- Corrections require recorded training consent before they can become training data.

## Code changes

Keep commands local-only and fail closed. Add regression tests for malformed JSON, provenance
drift, retry behavior, privacy boundaries, and split leakage when relevant. Generated files must
be deterministic and content-addressed where the pipeline promises reproducibility.

Pull requests should state:

1. the behavior changed;
2. the evidence or test that justifies it;
3. any schema/prompt/artifact identity changes;
4. whether benchmark comparability changes; and
5. whether the change touches privacy, consent, or training/evaluation isolation.

The application code is MIT-licensed. Derived corpus records and labels carry the CC BY 4.0
data note in [`LICENSE`](LICENSE); source scan images are not redistributed. Contributions must
preserve that boundary and must not add copied archival images, private source paths,
credentials, or unreviewed personal data.
