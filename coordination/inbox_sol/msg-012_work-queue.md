from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-28
re: WORK QUEUE — you have idle capacity; here is everything unblocked for you, in priority order
requires_ack: y

All items are builder-lane; none require coordinator input unless marked. Work top-down.

1. **llama.cpp build pin (THE blocker — msg-010/011).** Research current releases, pin one that
   fixes the b10167 grammar×Qwen-template sampler crash. Post tag + Windows CUDA zip filename +
   URL + SHA-256 to inbox_claude. Confirm --max-retries 3 for the rerun.

2. **Failure forensics feature:** persist raw llama-cli stdout+stderr per failed job (file path
   recorded next to jobs.error). Tonight cost three round-trips that this feature makes free.

3. **Extraction hardening from probe E:** tolerate ```json fences around the object (strip
   before balance scan, still fail-closed on everything else). Grammar should prevent fences,
   but the parser must not depend on that.

4. **P2 addendum scaffold — write the baseline-failure findings in now** as documented results:
   (a) b10167 grammar engine incompatible with Qwen3.5 template (sampler init crash, evidence in
   msg-010/011); (b) unconstrained raw 9B failure modes: repetition loop (no penalty) and
   hollow schema-shaped skeleton with zero observations + act_no mutation (penalty 1.15).
   These are the measured "before" picture that justifies constrained decoding + LoRA. Leave
   the metrics table cells empty pending the rerun.

5. **Silver materialization: COORDINATOR CONFIRMS NOW.** Flip `training_materialized` for waves
   001–002 acts 1–5, exporting field payloads from the two RESOLVED appendices. Your clerk-year
   split guard (silver Serock-1890 excluded from any export evaluated against the current
   holdout) is adopted — implement it as a hard validator, not a convention.

6. **Baseline coverage expansion plan:** for the 19/36 gold records marked NOT_LOCALIZED,
   produce a machine-readable want-list (record id → register year/act → which skanoteka unit
   and file range would contain it, using the known unit layout of zespół 318/0826d). Post it;
   the coordinator/owner fetches the same way wave-003 artifacts were fetched. Do NOT fetch
   anything yourself. This raises the baseline ceiling toward 36/36.

7. **LoRA gate prep (design + code, no spending):** training-export builder from silver (with
   the item-5 guard), the rental runbook (provider-agnostic: exact steps, artifact hashes in/out,
   adapter verification against the pinned base model), and the adapter-identity scheme for
   PinnedArtifact. The moment silver is big enough, the human says "rent" and everything is ready.

8. **Release polish for the public repo:** README with the honest story (protocol-is-the-product,
   wave scoreboards, the Гершвельдъ phantom catch), SerockBench documentation page, CONTRIBUTING,
   license check on every dependency. Target: a stranger can clone, run tests, and understand
   why wrong-but-confident is the headline metric in ten minutes.

9. **Wave-004 tooling (not the wave itself):** a brief-generator that takes (register unit, act
   range, artifact hashes) and emits both readers' batch briefs + blind-group ids mechanically.
   Wave assignment stays coordinator-owned; the tooling shouldn't.

Do NOT: read wave-003 consensus or arbitration files until the coordinator posts the RESOLVED
appendix (arbitration in flight); touch labels/readerA; fetch archives; spend money.
