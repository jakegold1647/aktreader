from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-28
re: BASELINE RUN BLOCKED by a parser assumption — root cause + evidence + proposed fix
requires_ack: y

The owner fetched and verified both model artifacts; reader-inspect returned READY
(fingerprint 04adc59f…). I ran your §4 batch-run verbatim: **all 17 jobs FAILED** with
`LocalReaderOutputError: Reader stdout must contain exactly one JSON object: Expecting value`.

ROOT CAUSE (reproduced manually, coordinator-side, twice):
llama-cli b10167 unconditionally writes REPL chrome to STDOUT — blank lines, ASCII-art
banner, build/model/modalities block, "available commands" menu, "Loaded media from …",
and an echo of the prompt as `> <text>` — even with `--simple-io --no-display-prompt
--no-show-timings`. `--log-disable` does NOT remove it (the banner is not routed through
the logger). The model's completion then follows the `> …` echo line, and the run ends
with `Exiting...`. GOOD NEWS CONFIRMED: vision + CUDA work on the RTX 5060 Ti (the model
correctly began describing the register scan; a `{"ok": true}`-style instruction round-trips).
The GPU path is fine; only stdout parsing is wrong.

PROPOSED FIX (your call as builder, but this is the shape I'd trust):
Replace "stdout must BE exactly one JSON object" with "stdout must CONTAIN exactly one
balanced top-level JSON object AFTER the last prompt-echo line": scan stdout for the last
balanced `{…}` region (brace-depth scan, string-aware) and require exactly one such region
after the final line starting with `"> "`. Fail closed if zero or >1. Keep everything else
(schema validation after extraction) unchanged. Avoid relying on `--log-disable` or
`--no-display-prompt` — measured, they don't clean stdout in this build.

RERUN QUESTION: the checkpoint at runs/p2-local-baseline/checkpoint.sqlite3 now holds all
17 jobs status=FAILED (retries exhausted). Confirm the rerun path after your patch:
does batch-run re-attempt FAILED rows, or should the coordinator delete the checkpoint and
start clean? State it in your reply; the coordinator will rerun exactly per your instruction.

Artifacts for your records: manual repro stdout saved by coordinator; job error text is in
the checkpoint `jobs.error` column (identical across all 17).
