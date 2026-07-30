# LoRA rental runbook

This is the provider-neutral execution procedure for training transition 0001. Paid model
training is authorized, but no GPU is provisioned until `training/readiness-0001.json` says
`READY` and `paid_training_launch_allowed` is `true`.

## Gates before rental

1. Acquire the sequestered human gold set under `docs/human-gold-acquisition.md`.
2. Run the readiness gate:

   ```powershell
   $env:PYTHONPATH = "src"
   python tools/training_preflight.py
   ```

3. Build the training export only after the gate has enough grounded records and the selected
   holdout has no clerk-year overlap:

   ```powershell
   $env:PYTHONPATH = "src"
   python tools/build_training_export.py `
     --evaluation-holdout .\path\to\chosen-holdout.json `
     --output .\training\silver.jsonl `
     --manifest-output .\training\silver.manifest.json
   ```

   Export fails closed for overlap, missing materialization, hash drift, malformed provenance,
   or any source label whose PRESENT observations are not grounded in its own continuous
   transcription.

4. Fetch the exact trainable safetensor revision from the recipe. Do not train from the GGUF
   inference artifact. Create a file-level SHA-256 manifest after download and verify it before
   upload.
5. Freeze the exact adapter target modules, trainer implementation/version, container digest,
   seed, precision, batch size, sequence length, and optimizer settings. Re-run preflight and
   hash the final recipe.

## Rental execution

1. Provision one GPU with enough VRAM for the pinned base model and trainer. Do not begin with a
   multi-node or hyperparameter sweep.
2. Verify every uploaded image, JSONL, export manifest, recipe, and base-model file against the
   local SHA-256 receipts.
3. Disable dataset discovery, sample telemetry, and every network genealogy lookup. The worker
   receives only explicit inputs and the pinned model.
4. Run one batch. Confirm loss is finite, image tensors are consumed, every target field is
   present, and a checkpoint can be downloaded and reloaded.
5. Run the frozen recipe once. Preserve raw logs, resolved configuration, environment lock,
   trainer/container identity, checkpoints, and final adapter.
6. Download outputs and compute local SHA-256 receipts before terminating the rental.

## Adapter identity and acceptance

Create a run identity conforming to `schemas/adapter-identity-1.0.0.schema.json`. Bind the
base-model manifest, training export, recipe, trainer container digest, and adapter digest.
Configure the local Reader with the adapter as a pinned artifact, then:

1. verify base and adapter hashes;
2. require a clean local load;
3. run a non-evaluation smoke image proving the adapter is active;
4. run the sequestered holdout exactly once under the frozen evaluation protocol;
5. retain the identity, manifests, recipe, logs, and metrics together.

Never compare an adapter against a holdout sharing a clerk-year, act, crop, or duplicate scan
with training. Training loss alone never promotes an adapter; promotion requires the same
wrong-but-confident and filiation metrics as every other Reader.
