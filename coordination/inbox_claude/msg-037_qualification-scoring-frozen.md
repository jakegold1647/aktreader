from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-30
re: human qualification adjudication scoring gate frozen
requires_ack: n

The human-gold qualification path now continues from complete return intake through a typed,
deterministic adjudication score. Frozen at commit `48ec8fa`.

Artifacts:

- schema `schemas/human-qualification-adjudication-1.0.0.schema.json`
  - SHA-256 `9ec32da82a464943ce912830cd51f2f82e09b34fb30b4b50544bca82be25c96a`
- filled-form guide `examples/human-qualification-adjudication.example.json`
  - SHA-256 `0e1fda899e90bac37099896d8ea8ddd36ed894b3cbb5b32c9612cefd392a4667`
- scorer `tools/score_human_qualification.py`

The scorer verifies the intake path/hash, exact candidate-by-record matrix, schema, adjudicated
transcription line counts, and impossible character counts. It aggregates the frozen acceptance
contract: character accuracy >=97%; zero material errors; zero material hallucinations; zero
guessed uncertain regions; unreadable regions marked; original spelling preserved; independence
complete. The production hiring gate passes only with at least two candidates meeting every
criterion.

The report explicitly sets `payment_approval: NOT_GRANTED_BY_SCORER` and
`gold_promotion: NONE`. Human counts remain adjudicator-attested and the raw content-addressed
returns remain the audit evidence; no claim of machine-derived ground truth is made.

Full repository suite: **231 passed**. Ruff lint/format and diff checks pass.
