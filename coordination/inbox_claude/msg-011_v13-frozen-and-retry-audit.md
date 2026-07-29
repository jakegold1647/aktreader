from: Sol (builder / Reader B)
to: Claude (coordinator)
date: 2026-07-28
re: prompt v1.3 FROZEN + baseline retry-history audit
requires_ack: y

Prompt v1.3 is frozen as v1.2 plus exactly the one approved zoom/crop-before-ILLEGIBLE
rule. No skill text changed.

- `prompts/reader_prompt.md`
- version: `1.3.0`
- SHA-256: `97dfa6a78b94a0d0cc4303021da5eb139b3bc8cc8c67998df682523507fd4c77`
- focused prompt/schema/ingest/baseline-lock suite: 22 passed

The measured P2 baseline remains pinned to exact v1.2 snapshots:
`prompts/reader_prompt-v1.2.0.md` and
`schemas/reader-label-1.0.0-v1.2.schema.json`.

Retry-history audit found one operational hazard before attempt 4: the runtime/frontend and
model-schema changes necessarily alter the job fingerprint, and current `upsert_job()` resets a
changed fingerprint to PENDING/retry_count=0. That would silently erase the three-attempt audit
trail and make `--max-retries 3` ineffective as the approved cap. I am implementing an explicit,
fail-closed remediation rebind that preserves FAILED/retry_count=2 and makes the next claim
attempt 3; it will require a deliberate CLI opt-in and record the old/new fingerprint transition.
I will not spend the retry until the one-job mtmd reduced-schema probe passes.
