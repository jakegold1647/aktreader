# Contributor tasks

Scoped, self-contained tasks for new contributors. None of them require archive scans, model
weights, or GPU hardware — everything below runs against tracked fixtures in a plain checkout.
Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first; the evidence and privacy rules there are
binding for every task.

Claim a task by opening an issue (or commenting on an existing one) so work is not duplicated.
If a task turns out to be bigger than its scope says, stop and say so in the issue — shrinking
scope is always acceptable here, silently expanding it is not.

## 1. Test the supported Python range and Windows in CI — *good first issue*

**Why:** the package declares Python 3.10+ and the project is developed on Windows, but CI
currently tests only Python 3.12 on Ubuntu. Version- or platform-specific breakage is invisible.

**Scope:** extend the matrix in `.github/workflows/ci.yml` to cover Python 3.10 and 3.12 on
`ubuntu-latest` plus one `windows-latest` job. Fix any genuine portability issues that surface
(path handling and console encoding are the likely culprits).

**Acceptance:** CI is green on all matrix cells; no test is skipped to get there other than the
documented owner-local checksum skip.

## 2. Machine-readable and CSV output for `aktreader compare` — *good first issue*

**Why:** the `compare` command emits a JSON report; reviewers doing human adjudication often
want a flat table they can sort in a spreadsheet.

**Scope:** add a `--csv PATH` option to the `compare` subcommand that writes one row per
disagreement (record id, field path, left value, right value, disagreement kind). No new
dependencies — the standard library `csv` module is enough.

**Where to look:** `src/aktreader/comparison.py`, `src/aktreader/cli.py`,
`tests/test_comparison.py`, `docs/comparisons.md`.

**Acceptance:** round-trips correctly on the tracked `labels/` fixtures; UTF-8 output opens
cleanly in spreadsheet software (mind the BOM); tests cover an empty-disagreement report.

## 3. A glossary for outsiders — *good first issue, documentation only*

**Why:** the docs use project jargon — silver/gold tiers, clerk-year sequestration, blind pass,
filiation, `[unclear: X/Y]`, typed absence states — that newcomers currently have to
reverse-engineer from scattered files.

**Scope:** write `docs/glossary.md` with short, accurate definitions and links to the file that
is authoritative for each term. Sources: `README.md`, `SPEC.md`, `skills/uncertainty-grading.md`,
`docs/architecture.md`, `schemas/`.

**Acceptance:** every term used in `README.md` and `CONTRIBUTING.md` that is not ordinary
software vocabulary appears in the glossary; definitions do not contradict the grading contract
in `skills/uncertainty-grading.md`.

## 4. Property-based tests for the label validators

**Why:** the validators in `src/aktreader/labels.py` and `src/aktreader/gold.py` are the
project's safety floor; today they are covered by example-based tests only.

**Scope:** add `hypothesis` to the dev dependency group and write generative tests that mutate
valid label/evidence structures (drop keys, corrupt observation states, break the
`[unclear: X/Y]` convention) and assert the validators fail closed with a clear error.

**Acceptance:** tests are deterministic under a pinned seed profile in CI; at least the evidence
contract (`EVIDENCE_KEYS`, observation states, UNCLEAR conventions) is generatively covered;
`python -m tools.check_dependency_licenses` still passes after the dependency addition.

## 5. Auto-generated field reference from the schemas

**Why:** the versioned JSON Schemas under `schemas/` are the real contract, but there is no
human-readable field reference; people read the prompt text instead.

**Scope:** a small script (`tools/build_schema_reference.py`) that renders each schema's field
tree, types, and descriptions to `docs/schema-reference.md`, plus a test asserting the committed
output is current (regenerate-and-diff).

**Acceptance:** running the tool twice is idempotent; CI fails if the committed reference drifts
from the schemas.

## 6. Actionable validator error messages

**Why:** validator errors are precise but terse (e.g. `PRESENT requires a value`); a contributor
who triggers one gets no pointer to the rule it enforces.

**Scope:** audit error messages raised in `src/aktreader/labels.py` and `src/aktreader/gold.py`;
extend each to name the violated rule and, where one exists, the document that defines it. Do
not change what is accepted or rejected — messages only.

**Acceptance:** the test suite still passes with assertions updated for new wording; no
behavioral change to validation outcomes.

## Explicitly not up for grabs

These require owner-held materials or decisions and are tracked on the roadmap instead:
corpus acquisition and rights review, human gold verification, model/runtime pinning, anything
touching `labels/` frozen evidence, and the privacy window defaults.
