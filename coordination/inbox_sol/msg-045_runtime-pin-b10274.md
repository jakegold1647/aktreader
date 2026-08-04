from: Claude (coordinator)
to: file (Sol retired, msg-044; owner authorized this pin directly)
date: 2026-08-04
re: llama.cpp runtime pin b10274 — coordinator-pinned, owner-authorized (unblocks msg-011 item 1)
requires_ack: n

Executing msg-011's recommendation 1 with the owner's direct authorization, in the msg-004
verify-before-trust pattern. Pin recorded before fetch:

- release tag: b10274 (ggml-org/llama.cpp, published 2026-08-04)
- file 1: llama-b10274-bin-win-cuda-12.4-x64.zip (250,440,217 bytes)
  url: https://github.com/ggml-org/llama.cpp/releases/download/b10274/llama-b10274-bin-win-cuda-12.4-x64.zip
  sha256: 9702a308c056aaffad12d709adb596240c346e904f17eeaa91b8f499a8d21be5
- file 2: cudart-llama-bin-win-cuda-12.4-x64.zip (391,443,627 bytes)
  url: https://github.com/ggml-org/llama.cpp/releases/download/b10274/cudart-llama-bin-win-cuda-12.4-x64.zip
  sha256: 8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6

CUDA 12.4 variant chosen to match the b10167 install (bundled cublas/cudart 12 DLLs, gpu_layers
"all" in the runnable config). Digests are GitHub's published per-asset values from the release
metadata. Extraction target: runtime\llama.cpp-b10274\ side by side with b10167, which stays in
place untouched. Plan after verification: rerun the msg-010/011 grammar probe (schema grammar +
--jinja, job 0 argv) on the new build; on PASS, baseline rerun with --max-retries 3 continuing
the existing checkpoint (rows at retry_count=2, per msg-005's rule). Mismatched hash = stop.
