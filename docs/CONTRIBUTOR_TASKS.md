# Contributor tasks

Scoped, self-contained tasks for new contributors. None of them require archive scans, model
weights, or GPU hardware — everything below runs against tracked fixtures in a plain checkout.
Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first; the evidence and privacy rules there are
binding for every task.

Claim a task by opening an issue (or commenting on an existing one) so work is not duplicated.
If a task turns out to be bigger than its scope says, stop and say so in the issue — shrinking
scope is always acceptable here, silently expanding it is not.

## 1. Test Windows in CI — shipped

**Status:** completed on 2026-08-12. CI retains the Ubuntu Python 3.11–3.13 jobs and adds one
Windows/Python 3.11 job running the same install, CLI smoke, lint, test, and license gates. The
comparison smoke also verifies that its JSON and CSV files were created.

**Why:** the project is developed on Windows, but every CI job runs on Ubuntu. Platform-specific
breakage is invisible. (The Python-version half of this task is done: CI now tests 3.11–3.13,
and the declared floor was raised to 3.11 to match reality.)

**Scope:** add one `windows-latest` job to the matrix in `.github/workflows/ci.yml` running the
same steps. Fix any genuine portability issues that surface (path handling and console encoding
are the likely culprits).

**Acceptance:** CI is green on all matrix cells; no test is skipped to get there other than the
documented owner-local checksum skip.

## 2. A glossary for outsiders — shipped

**Status:** completed in merged PR #5. The glossary now lives at
[`docs/glossary.md`](glossary.md) and links the project's terms back to their authoritative
specification, architecture, and uncertainty-grading sources.

This task is no longer available to claim. The scope and acceptance notes below are kept as a
record of what the contribution covered.

**Why:** the docs use project jargon — silver/gold tiers, clerk-year sequestration, blind pass,
filiation, `[unclear: X/Y]`, typed absence states — that newcomers previously had to
reverse-engineer from scattered files.

**Scope:** write `docs/glossary.md` with short, accurate definitions and links to the file that
is authoritative for each term. Sources: `README.md`, `SPEC.md`,
`skills/uncertainty-grading.md`, `docs/architecture.md`, `schemas/`.

**Acceptance:** every term used in `README.md` and `CONTRIBUTING.md` that is not ordinary
software vocabulary appears in the glossary; definitions do not contradict the grading contract
in `skills/uncertainty-grading.md`.

## 3. Property-based tests for the label validators — shipped

**Status:** completed in merged PR #7.

**Why:** the validators in `src/aktreader/labels.py` and `src/aktreader/gold.py` are the
project's safety floor; today they are covered by example-based tests only.

**Scope:** add `hypothesis` to the dev dependency group and write generative tests that mutate
valid label/evidence structures (drop keys, corrupt observation states, break the
`[unclear: X/Y]` convention) and assert the validators fail closed with a clear error.

**Acceptance:** tests are deterministic under a pinned seed profile in CI; at least the evidence
contract (`EVIDENCE_KEYS`, observation states, UNCLEAR conventions) is generatively covered;
`python -m tools.check_dependency_licenses` still passes after the dependency addition.

## 4. Auto-generated field reference from the schemas — shipped

**Status:** completed in PR #8. The checked-in [schema reference](schema-reference.md) is generated from the versioned contracts and guarded by a regenerate-and-diff test.

**Why:** the versioned JSON Schemas under `schemas/` are the real contract, but there is no
human-readable field reference; people read the prompt text instead.

**Scope:** a small script (`tools/build_schema_reference.py`) that renders each schema's field
tree, types, and descriptions to `docs/schema-reference.md`, plus a test asserting the committed
output is current (regenerate-and-diff).

**Acceptance:** running the tool twice is idempotent; CI fails if the committed reference drifts
from the schemas.

## 5. Actionable validator error messages

**Why:** validator errors are precise but terse (e.g. `PRESENT requires a value`); a contributor
who triggers one gets no pointer to the rule it enforces.

**Scope:** audit error messages raised in `src/aktreader/labels.py` and `src/aktreader/gold.py`;
extend each to name the violated rule and, where one exists, the document that defines it. Do not
change what is accepted or rejected — messages only.

**Acceptance:** the test suite still passes with assertions updated for new wording; no
behavioral change to validation outcomes.

## Recently shipped (not available to claim)

- **Spreadsheet-safe `compare --csv` export — 2026-08-12.** The export includes every
  disagreement regardless of the JSON detail cap, writes UTF-8 with a BOM, preserves explicit
  observation states, neutralizes formula-like cells, and covers the header-only agreement case.
  CSV re-import remains owner-gated because it would modify adjudication inputs.
- **Glossary for outsiders — merged PR #5.** The definitions and source links are in
  [`docs/glossary.md`](glossary.md).

## Explicitly not up for grabs

These require owner-held materials or decisions and are tracked on the
[adoption roadmap](adoption-roadmap.md) instead:
corpus acquisition and rights review, human gold verification, model/runtime pinning, anything
touching `labels/` frozen evidence, and the privacy window defaults.
