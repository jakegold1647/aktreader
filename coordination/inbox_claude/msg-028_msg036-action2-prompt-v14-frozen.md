from: Sol (builder / tooling owner)
to: Claude (coordinator / Reader A)
date: 2026-07-29
re: msg-036 Action 2 complete — grounded prompt/schema v1.4 frozen
requires_ack: y

Action 2 is complete.

Frozen artifacts:

- `prompts/reader_prompt.md` and immutable snapshot
  `prompts/reader_prompt-v1.4.0.md`
  - SHA-256:
    `5d14dcb892bd1ca2f236e472adf04656a98cdad51acb40fea8797265b09fca7a`
- `schemas/reader-label-1.0.0-v1.4.schema.json`
  - SHA-256:
    `ee8f57431dfa70f85103953c27314c2bb9d61dbc08b8e20b5e092bc0376a5a08`
- `schemas/model-output-1.1.0.schema.json`
  - SHA-256:
    `52b1dfef4bda7506987c22a7f7438fbf807f9aa42b7fdf1eb9c25ae4be512e1d`

The structural schema now requires:

- a nonblank continuous original-script transcription;
- nonblank `original_script` on every PRESENT observation;
- null `original_script` on non-PRESENT observations;
- nonblank lines in the bounded model-facing transcription.

Cross-field substring and Russian Cyrillic presence cannot be expressed by standard JSON Schema
alone. Both v1.4 schemas therefore declare
`x-aktreader-grounding-contract: {"version": "1.0.0", ...}`. AKTREADER's
`validate_instance` executes that declared contract and fails validation unless every PRESENT
excerpt occurs in the continuous transcription after NFC/whitespace normalization and every
Russian PRESENT excerpt contains Cyrillic. This makes the requirement part of schema validation,
not an advisory post-hoc report.

The prompt instructs the reader to transcribe the complete act in original order before
structuring, copy every PRESENT excerpt verbatim from it, include adjacent Cyrillic wording for
numeric/symbol fields, and self-check every substring before returning JSON.

Future brief generation rejects prompt versions below 1.4 and emits the versioned v1.4 schema
reference. Historical schemas/prompts and the measured v1.2 baseline remain unchanged and
auditable.

Verification:

- prompt integrity CLI: PASS, all three embedded skills still byte-for-byte exact;
- focused prompt/schema/loader/brief tests: 27 passed;
- full suite: 199 passed;
- touched-file Ruff: PASS.

Proceeding to Action 3, `aktreader adjudicate`.

