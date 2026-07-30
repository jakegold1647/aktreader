# Serock 1890 zero-cost holdout: morning runbook

## Purpose

This is a ten-question, offline human review of already-produced Serock 1890 death-register
readings. It asks whether an act-body crop is visually consistent with repeated closing-formula
or annual-index evidence. It is not independent Cyrillic transcription and cannot by itself
create publication-grade gold.

Every candidate is fail-closed:

- `benchmark_eligible: false`
- `correction_eligible: false`
- a conflict, neither, or can't-tell answer routes the field to a Cyrillic reader
- ingestion emits immutable evidence events and never edits any Reader A, Reader B, silver, or
  gold label

## Review the packet

Open this file in a normal browser:

`human_check/generated/serock-1890-zero-cost-holdout-01/packet.html`

For each of the ten questions:

1. Compare the act-body target with every repeated or independent evidence card.
2. Choose only what the pixels support. `Neither / something else` and `Can't tell` are valid.
3. Describe the visual basis verbatim; do not add a transliteration you cannot personally read.
4. Leave correction-reuse consent at `NOT_RECORDED` unless the reviewer deliberately grants it.
   Consent does not override this packet's `correction_eligible: false` guard.
5. Download the answers JSON after all ten questions are complete.

The packet is self-contained: it has 26 embedded PNGs, requires no network, and sends nothing.

## Ingest the downloaded answers

From the repository root, replace `<downloaded-answers.json>` with the actual download path:

```powershell
.\.venv\Scripts\aktreader.exe adjudicate `
  --wave serock-1890-zero-cost-holdout-01 `
  --spec .\human_check\waves\wave-serock-1890-zero-cost-holdout-01.json `
  --output-dir .\human_check\generated\serock-1890-zero-cost-holdout-01 `
  --answers <downloaded-answers.json>
```

Do not use `--replace-existing` for answer ingestion. The command verifies packet and question
fingerprints, requires exactly one answer per question, and writes a content-addressed result.
Review its expert-review list and emitted events before any downstream promotion.

## Frozen inputs and outputs

- Wave specification SHA-256:
  `8896b73a1cdca1c5c7c163291ba96043b0cb2038b297f76ff7a8aff1ef906343`
- Packet HTML SHA-256:
  `6828d741b5c7fd55d1536ea6f7d3719f213b8798929ebce79201bac98ae311ae`
- Questions JSON SHA-256:
  `44d67830303a5233a99b53ea78b8535e813737d5d31267b3070dfa047ebf7cdf`
- Answers template SHA-256:
  `07badffb477ba2ac561b0d5eb2bb835cb2297a7187f949f3be417f5e3c2362bb`
- Manifest SHA-256:
  `6022644309074a7be44b29ba3326acd2b0e15525dab3798e8e44f5380975080d`
- Pinned closure-audit SHA-256:
  `090a8d06690fd36c66e699ab7c4ce7bf2a1c5bb9af7eafd901f9e8df129a65bc`

## Freeze checks completed

- 220 project tests pass.
- Ruff lint and format checks pass for the changed adjudication code and tests.
- All ten questions use visual corroboration; there are sixteen comparison cards.
- The HTML has ten question sections and 26 embedded images.
- Every question retains both escape choices.
- All source crops were visually inspected against their canonical source scans.
