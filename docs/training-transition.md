# Training transition 0001

The project is now in **human-gold-before-calibration-before-LoRA** mode. Paid work is
authorized, but model training must not start until the machine-readable preflight reports
`READY`.

Run the gate from the repository root:

```powershell
$env:PYTHONPATH = "src"
python tools/training_preflight.py
```

The command always writes `training/readiness-0001.json`. Exit code `0` means every
launch gate passes. Exit code `2` means the report was written but paid model training
remains blocked.

The immediate paid stage is a five-record human qualification batch followed by a
25-record production batch. Each record receives two blind independent transcriptions and
one adjudication. Accepted production records seed the sequestered image-attested holdout under the
contract in `docs/human-gold-acquisition.md`. They are never reused for training. Once the
model bakeoff is selected, continuous offline reading of different clerk-years builds the
grounded training pool, with human sampling and adjudication.

The next stage is a 25-act offline model bakeoff: Qwen3-VL-32B as primary reader,
InternVL3.5-38B as independent verifier, and GLM-OCR as an auxiliary OCR signal.
Qwen3-Coder-Next is reserved for CyrillicApp implementation and is excluded from record
consensus. Repository revisions are pinned in `training/plan-0001.json`; model bytes still
need a content-addressed fetch receipt before execution.

The first paid LoRA should be a single-GPU calibration run, not a cluster sweep. Its
inputs must contain at least 100 grounded training records, and evaluation must use at
least 20 fully image-verified records from non-overlapping clerk-years. The final recipe
must also pin trainable safetensor weights, exact adapter target modules, trainer
implementation/version, and container digest.

No existing label is rewritten by this transition. The export builder rejects any record
whose source label is not grounded in its own continuous transcription, even if the
requested holdout otherwise has no clerk-year overlap.
