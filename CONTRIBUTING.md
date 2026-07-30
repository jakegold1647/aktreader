# Contributing to AKTREADER

AKTREADER treats provenance and uncertainty as product behavior. A contribution is not complete
when it merely produces plausible text; it must preserve the path from scan pixels to every
assertion.

## Before opening a change

- Use Python 3.10 or newer in an isolated environment.
- Install the development group and run `python -m pytest`.
- Run `python -m ruff check .` when Ruff is installed.
- Run `python -m tools.check_dependency_licenses` after any dependency edit.
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

The repository currently has no project license. Contributions cannot be accepted for reuse
until Jake selects and adds the project license.
