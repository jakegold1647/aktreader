# Local reader comparisons

`aktreader compare` produces a deterministic reader-to-reader agreement report from two
local label files or directories. It performs no inference, network access, archive lookup,
or model download.

The repository includes historical labels so the comparison path can run immediately after
installation:

```powershell
python -m aktreader compare labels/readerA labels/readerB `
  --output comparison-report.json
```

The command compares records with the same `record_id`, reports records present on only one
side, separates observation-state disagreements from value disagreements, and includes the
coverage and groundedness metrics for both inputs. The report also carries an explicit
`authority_warning`: agreement is not proof of truth, so every result still needs source-scan
verification.

Historical labels are accepted by default so this command is useful without preparing new
inputs. If any input is legacy or fails the continuous-transcription grounding contract, the
report says `safety_status: LIMITED_UNGROUNDED_INPUT`; that report is diagnostic, not a
publication-grade accuracy claim. Use the fail-closed mode for a grounded pair:

```powershell
python -m aktreader compare path/to/reader-a path/to/reader-b `
  --require-grounded --output grounded-comparison.json
```

This is distinct from `aktreader eval`: `compare` measures agreement between readers, while
`eval` scores supplied predictions against the clerk-year-sequestered gold corpus.
