# Local model and runtime

AKTREADER has one Reader backend: a local open-weights vision-language model invoked through
`llama-mtmd-cli`. There is no hosted Reader interface, model URL, SDK, API server, account, or key in
the application.

## Current execution status

The P2 LocalReader baseline is **NOT RUN**. All locked runtime/model artifacts are present and
`reader-inspect` verifies their hashes without invoking inference.

Measured probes separated the frontend failure from the grammar engine:

- b10167 `llama-cli` crashes when its REPL prompt tokens pass through the active Qwen3.5 grammar;
- the same build's `llama-mtmd-cli` initializes the inline JSON schema correctly;
- the full label schema then caused repetition in long mechanical fields;
- the frozen remediation gives the model only a bounded target check, line-array
  transcription/translation, and observations, while AKTREADER stamps identity and provenance
  after generation.

The pinned frontend is `runtime\llama.cpp-b10167\llama-mtmd-cli.exe`, version
`10167 (ee3d1b54c)`, SHA-256
`6866b9425ec02798087380e14d5a9c69ded092a914cd48f06cf9b803552f7bfc`.
A one-job reduced-schema probe generated a complete constrained label without a grammar
crash, repetition loop, or truncation. Its first output exposed one validator-only failure:
a non-present observation carried non-null confidence. The refrozen reduced schema now uses
three mutually exclusive `oneOf` branches so PROBABLE-present, UNCLEAR-present, and null
non-present evidence cannot be mixed. The confirming one-job probe remains pending; no
baseline retry has been spent by this rebuild.

## Hardware profiles

The development machine has an NVIDIA RTX 5060 Ti with 16 GB VRAM. The initial baseline is:

- **Default — Qwen3.5-9B, GGUF Q5_K_M + F16 projector**. The selected payload is about 6.98
  GiB before runtime buffers and KV cache. If measured end-to-end headroom is inadequate, run a
  separately pinned Q4 experiment; never silently swap quants under one baseline identity.
- **24 GB quality profile — Qwen3.6-27B, GGUF Q4**. This is the strongest practical candidate
  identified for one 24 GB consumer card. It needs measured headroom for the vision projector,
  image workspace, and KV cache; a quantized weight-file estimate is not a VRAM guarantee.
- **Smaller fallback — Qwen3.5-4B**, starting with Q5 or Q6 and stepping down only when actual
  hardware measurements require it.

Both Qwen families publish their weights under Apache-2.0. The Qwen3.5-9B model card describes a
native vision encoder and 201-language coverage. Qwen's reported document scores include
OCRBench 89.2 and CC-OCR 79.3 for 9B; its Qwen3.6-27B card reports OCRBench 89.4 and CC-OCR 81.2.
These numbers justify an evaluation candidate, not a genealogy accuracy claim:

- they are vendor-reported results;
- their test material is not nineteenth-century Congress-Poland cursive;
- no cited result measures pre-reform Russian, old Polish handwriting, maiden-name extraction,
  or `[unclear: X/Y]` discipline;
- no cited result establishes the loss from the selected GGUF quantization.

SerockBench's held-out clerk-years therefore decide the model and quantization. The README must
publish that measured result even if it is weak.

Primary sources:

- [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Qwen3.6-27B model card](https://huggingface.co/Qwen/Qwen3.6-27B)
- [Qwen3.6 official repository](https://github.com/QwenLM/Qwen3.6)

## Exact P2 artifact lock

The machine-readable source of truth is
[`examples/p2-baseline.artifacts.json`](../examples/p2-baseline.artifacts.json); the runnable
local-path projection is
[`examples/p2-baseline.local-reader.json`](../examples/p2-baseline.local-reader.json).

| Role | Frozen artifact | Bytes | SHA-256 |
|---|---|---:|---|
| Model | `Qwen3.5-9B-Q5_K_M.gguf` | 6,577,841,376 | `dc2a39aef291f91a9116ad214058da0d86eb648743a124bd8c333787c4b9c91c` |
| Vision projector | `mmproj-F16.gguf` | 918,166,080 | `f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f` |

Both download URLs are pinned to Unsloth repository revision
`9f870da1e1c96da710c13926d36c6946bb7ebb38`; mutable `main` URLs are not accepted. Qwen's
official Qwen3.5 repository supplies the Apache-2.0 upstream weights, but does not publish this
GGUF pair. The prebuilt conversion is therefore explicitly third-party: its published hashes
identify the bytes, and local verification—not publisher identity—is the execution gate. A
future supply-chain-hardening run may convert the official pinned Safetensors snapshot locally
and record the newly produced hashes; those hashes cannot be truthfully predicted in advance.

## Why llama.cpp CLI

`llama.cpp` is MIT-licensed, supports Windows, CUDA and Vulkan, GGUF quantization, multimodal
projectors, GPU/CPU offload, JSON-schema-constrained generation, and LoRA adapters. Qwen's
official repository explicitly lists llama.cpp support for Qwen3.6 text and vision.

AKTREADER invokes `llama-mtmd-cli.exe` directly with `shell=False`. It does not start
`llama-server`, speak HTTP to localhost, or use an OpenAI-compatible client. The fixed command
shape is equivalent to:

```powershell
llama-mtmd-cli.exe `
  -m E:\path\model.gguf `
  -mm E:\path\mmproj.gguf `
  --image E:\path\act-crop.jpg `
  -sys "<pinned prompt contents>" `
  --json-schema "<pinned reduced-schema contents>" `
  -p "<bounded target-check request>" `
  -c 16384 `
  -n 8192 `
  --image-max-tokens 4096 `
  -s 0 `
  --temp 0 `
  --top-k 1 `
  -ngl 99
```

An optional local LoRA adds `--lora E:\path\adapter.gguf`.

The CLI grammar makes the reduced output syntactically JSON-shaped. It cannot make a
semantically wrong name true. AKTREADER consequently parses exactly one strict JSON object,
rejects duplicate keys and non-standard numbers, validates it against the checksum-pinned reduced
schema, verifies the target check, stamps all identity/provenance and source-span IDs
mechanically, validates the assembled label against the full schema, and rejects any
single-reader `CONFIDENT` grade. A local blind pass may return only
`PROBABLE`, `UNCLEAR`, or null confidence for a typed non-present state. Consensus and
validators—not the model—may later promote evidence.

Runtime documentation:

- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [JSON-schema grammars](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

## Artifact provisioning and checksum pins

Downloading, building, or converting runtime/model assets is a separate owner-controlled action.
The application never downloads them and never turns an operating-system block into a prompt to
continue. After trusted provisioning, record the SHA-256 of every required file:

```powershell
Get-FileHash -Algorithm SHA256 E:\path\llama-mtmd-cli.exe
Get-FileHash -Algorithm SHA256 E:\path\model.gguf
Get-FileHash -Algorithm SHA256 E:\path\mmproj.gguf
Get-FileHash -Algorithm SHA256 E:\path\reader_prompt.md
Get-FileHash -Algorithm SHA256 E:\path\reader-label.schema.json
Get-FileHash -Algorithm SHA256 E:\path\model-output.schema.json
```

Record a LoRA checksum too when one is used. Do not commit an invented or placeholder digest.
Pin the exact llama.cpp binary, model quant, projector, prompt, both schemas, and adapter used for an
evaluation run. `LocalReader` hashes each file before inference and fails closed on a missing
file, relative path, UNC path, URL-like locator, external schema reference, or mismatch.

The subprocess receives an allow-listed environment rather than the parent environment. Hosted
credential variables are not passed, and Hugging Face/Transformers offline flags are set. The
command uses only local paths and never uses llama.cpp's `-hf` or model-URL options. A trusted,
checksum-pinned executable is still a prerequisite: if Windows Security blocks it, inference
stops and the owner reviews or replaces the artifact outside AKTREADER. The project does not
recommend an exception, allow-list entry, disabled protection, or other bypass. That paragraph
is the standing policy for future blocks; it is not a claim that the current runtime remains
blocked.

## Construction

The runnable, content-pinned configuration is
[`examples/p2-baseline.local-reader.json`](../examples/p2-baseline.local-reader.json). It requires
separate full-label and reduced model-facing schema pins:

```powershell
.\.venv\Scripts\aktreader.exe reader-inspect `
  --config examples\p2-baseline.local-reader.json
```

## Future LoRA training hardware

Temporary rented compute is appropriate for the first LoRA because training and deployment have
different constraints. The deployment base remains Qwen3.5-9B so the resulting adapter can run
continuously on the 16 GB workstation. At the training gate, benchmark a high-memory rented GPU
profile against the clerk-year-sequestered holdout, preserve the exact base revision, training
code, dependency lock, seeds, consent-filtered corpus manifest, adapter hash, and cost/time log,
then destroy the temporary instance after verified artifact export. No rental has been selected,
provisioned, or charged in P2. A larger base is an experiment only if its measured quality gain
survives the local-throughput and deployment constraints; parameter count alone does not decide
the product.

`read()` also requires a metadata-only batch brief. It contains the record/label identity,
Reader identity, blind-group identity, prompt hash, clerk-year, artifact metadata, and target.
The artifact and prompt hashes must match the actual inputs. Output-bearing keys such as
`transcription`, `observations`, `mentions`, and `source_spans` are forbidden in the brief so a
blind pass cannot accidentally receive another Reader's work.

## Reproducibility fingerprint

Each successful inference persists the raw llama.cpp stdout and stderr beside the assembled
JSON label as `.stdout.txt` and `.stderr.txt`; failed jobs use `.failed.stdout.txt` and
`.failed.stderr.txt`, with those paths recorded in the checkpoint error. This keeps the
original model surface available for forensic review even after application stamping.

Each successful result exposes:

- the SHA-256 of the llama.cpp executable, model, projector, prompt, full label schema,
  reduced model schema, and optional LoRA;
- the prompt's canonical logical label path plus its physical snapshot filename and SHA-256;
- deterministic generation settings;
- the input image SHA-256;
- the canonical batch-brief SHA-256;
- one SHA-256 fingerprint over that content-based manifest.

Absolute paths are deliberately excluded from the fingerprint, so copying the same pinned
artifacts to another drive does not change its identity. The executable hash captures the exact
runtime build. The fingerprint establishes reproducible inputs and settings; GPU kernels and
floating-point execution can still vary by hardware and driver, so the emitted label itself
must also be retained and hashed by the batch layer.
