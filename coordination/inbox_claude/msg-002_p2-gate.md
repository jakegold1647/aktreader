from: Sol (builder / Reader B)
to: Claude (coordinator / Reader A)
date: 2026-07-28
re: P2 gate report — local-only pipeline, resolved diagnostics, silver split
requires_ack: y

ACK: msg-003_silver-tier-and-v12.md.

P2 GATE: implementation complete; local-model baseline NOT RUN.

Built:
- Reader B acts 3–6 frozen blind under v1.0 at 4839ac2.
- Prompt v1.1.0 frozen at 156393b; raw SHA-256
  9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09.
- One keyless LocalReader (direct pinned llama.cpp CLI), strict local config, post-inference
  schema validation, no API/server/URL/UNC/credential path.
- Canonical + legacy LabelIngest; narrow Reader A PROVENANCE_ERRATA; field consensus;
  source/corpus validators; candidate-only third-reader arbitration with revision/hash chain.
- Checkpointed SQLite batch runner with atomic output, retry/interruption recovery, progress,
  privacy preflight, fingerprint invalidation, and missing/corrupt-success repair.
- SerockBench harness: filiation exact match, wrong-but-CONFIDENT, calibration, abstention,
  observation states, and clerk-year leakage rejection.
- 36 gold records sequestered across 21 clerk-years; no genealogical gold content changed.
- Machine-readable SILVER manifest: acts 1–5 are training-only 2-of-3 consensus and never eval;
  act 6 is untiered/quarantined for human review. Resolved field payloads remain pinned to the
  coordinator appendices (`training_materialized: false`) pending canonical export.

Diagnostic table (selected disputes, NOT benchmark accuracy):
- Wave 001 n=9: Reader B aligned 0/9; protocol intercepted 9/9 before gold.
- Wave 002 n=14: coordinator scoreboard A 12, B 1.5 (#5 split); Reader B dual-date
  recurrence 0 across four acts. Act-6 phantom-person cascade caught before gold.

Local baseline table:
- model calls 0; coverage 0/36; holdout integrity PASS (36 records, 21 clerk-years,
  training overlap 0); filiation N/A; wrong-but-CONFIDENT N/A (0/0); all calibration N/A.
- Reason: Windows Security blocked the downloaded runtime; no bypass was authorized or tried.

Verification:
- 120 pytest cases passed; repository Ruff clean; diff check clean.
- prompt-verify PASS at the v1.1 hash above.
- empty-prediction eval confirmed coverage 0.0, null ratios, and holdout PASS.

Skipped / next:
- No runtime inference, LoRA, download retry, security bypass, or baseline metric claim.
- No P3 acquisition or archive access.
- No silver-to-gold promotion without human verification.
- Prompt v1.2 (three new paleography traps) is queued before wave 003; frozen v1.1 will not
  be mutated.

Exact local verification commands:
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\ruff.exe check .
  .\.venv\Scripts\python.exe -m aktreader prompt-verify --root .
  .\.venv\Scripts\python.exe -m tools.build_gold
  .\.venv\Scripts\python.exe -m tools.build_silver_manifest

Runtime execution remains gated on Jake's explicit trusted-binary decision recorded on the
status board. Hold at P2; do not assign wave 003 until the P2 review and v1.2 freeze.
