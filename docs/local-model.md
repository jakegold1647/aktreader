# Local model and runtime

AKTREADER has one Reader backend: a local open-weights vision-language model invoked through
`llama-cli`. There is no hosted Reader interface, model URL, SDK, API server, account, or key in
the application.

## Current execution status

The P2 LocalReader baseline is **NOT RUN**. Windows Security blocked the exact downloaded
llama.cpp runtime before it could invoke a model. No prediction file was produced, so filiation,
wrong-but-confident, calibration, and coverage metrics have no denominator.

AKTREADER does not disable, evade, or weaken operating-system security controls. The next runtime
attempt requires explicit owner action: independently review the executable's provenance and
signature, decide whether to approve that exact artifact or replace it with a trusted build, and
record the accepted file's SHA-256. Until the owner makes that decision, the block is the correct
terminal state and vendor OCR scores remain background evidence only.

## Hardware profiles

The development machine has an NVIDIA RTX 5060 Ti with 16 GB VRAM. The initial baseline is:

- **Default — Qwen3.5-9B, GGUF Q5**. Try Q5 first for handwriting quality. If the pinned build,
  projector, selected image-token budget, and 16,384-token context do not fit together, use Q4.
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

## Why llama.cpp CLI

`llama.cpp` is MIT-licensed, supports Windows, CUDA and Vulkan, GGUF quantization, multimodal
projectors, GPU/CPU offload, JSON-schema-constrained generation, and LoRA adapters. Qwen's
official repository explicitly lists llama.cpp support for Qwen3.6 text and vision.

AKTREADER invokes `llama-cli.exe` directly with `shell=False`. It does not start
`llama-server`, speak HTTP to localhost, or use an OpenAI-compatible client. The fixed command
shape is equivalent to:

```powershell
llama-cli.exe `
  -m E:\path\model.gguf `
  -mm E:\path\mmproj.gguf `
  --image E:\path\act-crop.jpg `
  --system-prompt-file E:\path\reader_prompt.md `
  --json-schema-file E:\path\reader-label.schema.json `
  --ctx-size 16384 `
  --predict 8192 `
  --image-max-tokens 4096 `
  --seed 0 `
  --temp 0 `
  --top-k 1 `
  --reasoning off `
  --gpu-layers all `
  --jinja `
  --single-turn `
  --simple-io `
  --no-context-shift `
  --no-display-prompt `
  --no-show-timings
```

An optional local LoRA adds `--lora E:\path\adapter.gguf`.

The CLI grammar makes the output syntactically JSON-shaped. It cannot make a semantically wrong
name true. AKTREADER consequently parses exactly one strict JSON object, rejects duplicate keys
and non-standard numbers, independently validates the result against the checksum-pinned local
schema, and rejects any single-reader `CONFIDENT` grade. A local blind pass may return only
`PROBABLE`, `UNCLEAR`, or null confidence for a typed non-present state. Consensus and
validators—not the model—may later promote evidence.

Runtime documentation:

- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [llama-cli options](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md)
- [JSON-schema grammars](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

## Artifact provisioning and checksum pins

Downloading, building, or converting runtime/model assets is a separate owner-controlled action.
The application never downloads them and never turns an operating-system block into a prompt to
continue. After trusted provisioning, record the SHA-256 of every required file:

```powershell
Get-FileHash -Algorithm SHA256 E:\path\llama-cli.exe
Get-FileHash -Algorithm SHA256 E:\path\model.gguf
Get-FileHash -Algorithm SHA256 E:\path\mmproj.gguf
Get-FileHash -Algorithm SHA256 E:\path\reader_prompt.md
Get-FileHash -Algorithm SHA256 E:\path\reader-label.schema.json
```

Record a LoRA checksum too when one is used. Do not commit an invented or placeholder digest.
Pin the exact llama.cpp binary, model quant, projector, prompt, schema, and adapter used for an
evaluation run. `LocalReader` hashes each file before inference and fails closed on a missing
file, relative path, UNC path, URL-like locator, external schema reference, or mismatch.

The subprocess receives an allow-listed environment rather than the parent environment. Hosted
credential variables are not passed, and Hugging Face/Transformers offline flags are set. The
command uses only local paths and never uses llama.cpp's `-hf` or model-URL options. A trusted,
checksum-pinned executable is still a prerequisite: if Windows Security blocks it, inference
stops and the owner reviews or replaces the artifact outside AKTREADER. The project does not
recommend an exception, allow-list entry, disabled protection, or other bypass.

## Construction

```python
from pathlib import Path

from aktreader.local_reader import LocalReader, LocalReaderConfig, PinnedArtifact

reader = LocalReader(
    LocalReaderConfig(
        executable=PinnedArtifact(Path(r"E:\models\llama-cli.exe"), "<sha256>"),
        model=PinnedArtifact(Path(r"E:\models\qwen3.5-9b-q5.gguf"), "<sha256>"),
        mmproj=PinnedArtifact(Path(r"E:\models\qwen3.5-mmproj.gguf"), "<sha256>"),
        prompt=PinnedArtifact(
            Path(r"E:\DNA\Project_RegisterReader\prompts\reader_prompt.md"), "<sha256>"
        ),
        schema=PinnedArtifact(
            Path(
                r"E:\DNA\Project_RegisterReader\schemas"
                r"\reader-label-1.0.0.schema.json"
            ),
            "<sha256>",
        ),
    )
)
```

Replace every `<sha256>` before construction; placeholder values intentionally fail.

`read()` also requires a metadata-only batch brief. It contains the record/label identity,
Reader identity, blind-group identity, prompt hash, clerk-year, artifact metadata, and target.
The artifact and prompt hashes must match the actual inputs. Output-bearing keys such as
`transcription`, `observations`, `mentions`, and `source_spans` are forbidden in the brief so a
blind pass cannot accidentally receive another Reader's work.

## Reproducibility fingerprint

Each successful result exposes:

- the SHA-256 of the llama.cpp executable, model, projector, prompt, schema, and optional LoRA;
- deterministic generation settings;
- the input image SHA-256;
- the canonical batch-brief SHA-256;
- one SHA-256 fingerprint over that content-based manifest.

Absolute paths are deliberately excluded from the fingerprint, so copying the same pinned
artifacts to another drive does not change its identity. The executable hash captures the exact
runtime build. The fingerprint establishes reproducible inputs and settings; GPU kernels and
floating-point execution can still vary by hardware and driver, so the emitted label itself
must also be retained and hashed by the batch layer.
