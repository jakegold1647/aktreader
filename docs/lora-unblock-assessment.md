# LoRA unblock assessment

Written 2026-08-05. This is a decision document about why the adapter stage has
not started and what it would actually take. It changes no gate, threshold,
holdout, tier definition, or manifest. Adjusting a rule to make a gate pass is
the failure mode this assessment exists to avoid.

## Status: blocked by gates, not cancelled

Nothing in either repository retires the adapter. `SPEC.md` §12 keeps the LoRA
as the independence path and §14 supersedes only the API-backend portion of it,
leaving the adapter in place as the step after subscription-session labelling.
`TRAINING_CORPUS_PLAN.md` sequences a first LoRA at corpus scale.
`training/plan-0001.json` names the current phase
`HUMAN_GOLD_THEN_CALIBRATION_THEN_LORA` and records
`paid_training_authorized: true` against
`readiness-0001.json: paid_training_launch_allowed: false`. Five of six launch
gates report `BLOCKED`; only `MODEL_BAKEOFF_REVISIONS_PINNED` passes.

The supporting code is real rather than aspirational: `src/aktreader/training.py`
builds and validates the export, `tools/build_training_export.py` drives it,
`tools/training_preflight.py` writes the readiness report,
`schemas/adapter-identity-1.0.0.schema.json` binds base model to adapter, and
`src/aktreader/local_reader.py` already passes `--lora` to the runtime. What is
missing is training data the project is permitted to use, and a trainer pin.

## The bind, stated correctly

Every clerk-year the project has labelled is sequestered for evaluation.
`gold/clerk_year_holdout.json` lists 21 clerk-year identifiers under policy
`CLERK_YEAR_SEQUESTERED_EVALUATION_ONLY`, and waves 001 through 006 read only
Serock 1890 and Serock 1877 — both on that list. The consequence is precise:

- `labels/silver/manifest.json` holds five records, all Serock 1890, all
  `training_eligible: false`, and additionally void as ungrounded per
  `docs/label-factory.md` and commit `92da8fb`.
- The `CLERK_YEAR_ISOLATION` gate reports
  `overlap=['73-826-0|serock|1890|clerk-unknown']` for exactly this reason.
- Wave 006 produced eight further silver acts in Serock 1877. Materialising them
  into the silver manifest would not help and would make the isolation overlap
  worse, because 1877 is sequestered too.

So the labelling programme has, to date, produced zero training-eligible
records. That is a consequence of the holdout doing its job, not a defect in the
waves — but it does mean the effort spent on waves has bought evaluation
integrity and reader methodology, and not one row of training data.

### Where the received framing was wrong

It is tempting to conclude from the above that the corpus itself is exhausted
and that a LoRA therefore waits on archive acquisition, which now runs about
three months per the Warsaw reply of 3 August. That conclusion is false, and it
is the most important finding here.

The holdout is **year-granular within Serock**, not blanket. Sixteen Serock
clerk-years are sequestered; the zespół contains others, and the local harvest
already holds nine of them:

| Clerk-year | Acts (approx.) |
| --- | --- |
| 1878 | 83 |
| 1879 | 87 |
| 1880 | 44 |
| 1881 | 157 |
| 1889 | 119 |
| 1895 | 67 |
| 1898 | 95 |
| 1900 | 101 |
| 1904 | 190 |
| **Total** | **~943 acts across 9 unsequestered clerk-years** |

Counts are derived from the completed ranges in
`BulkData/Serock_0826d/HARVEST_STATE.txt`; the scans are already on disk, already
hashed in `SHA256SUMS.txt`. Against the gate minimum of 100 grounded training
records, the available unsequestered pool is roughly nine times what a first
calibration adapter requires.

The binding constraint is therefore **reading throughput on years the project is
allowed to train on** — not acquisition, not archive queues, not GPU budget.

## Options

**(a) Read the unsequestered years already on disk.** Cost is agent and human
review time only: no acquisition, no waiting on Grodzisk, no policy change. At
the wave-006 shape of ten acts per wave with two blind readers plus arbitration,
the 100-record gate is roughly ten waves out. This preserves every existing
guarantee, because the holdout is untouched and the training pool is drawn from
clerk-years no benchmark record occupies.

**(b) Revise or narrow the holdout.** This is self-defeating and should be
rejected. The holdout exists because, as `TRAINING_CORPUS_PLAN.md` puts it, a
benchmark sharing clerk-years with training measures handwriting memorisation
rather than reading. Freeing 1890 for training would convert SerockBench from an
honest instrument into a flattering one, and the flattering number would then be
the number published. There is no version of this worth the acts it liberates.

**(c) Rebuild the five voided silver records to grounded v1.4.** Worth doing for
its own sake — the grounding retro-audit found real defects and the records are
misleading as stored — but it buys nothing for training. All five are Serock
1890 and stay sequestered after any rebuild. Treat it as label hygiene, not as
progress toward an adapter.

**(d) Do nothing on the adapter and keep improving prompted reading.** This is
the honest default, and it is not a failure. The b10274 baseline recorded
filiation exact match of 0% for the local reader with 21 of 24 jobs rejected by
the pipeline's own gates. A LoRA over ~1,000 acts will not repair a model that
cannot currently hold the output contract. Option (a) and option (d) are
compatible and probably belong together.

## Recommendation

Move the reading programme to unsequestered clerk-years, starting with 1881 and
1904 as the densest, and treat every wave from here as training-pool
construction rather than benchmark construction. The benchmark has 36 gold
records and 21 sequestered clerk-years already; it does not need more, and each
additional sequestered wave actively subtracts from the trainable pool.

Do not schedule a GPU rental against this yet. A single-GPU LoRA on a 9B base is
genuinely cheap — hours of one A100- or H100-class card, which is tens of
dollars at current rental rates, consistent with SPEC §12 — so cost is not what
gates it. What gates it is having 100 grounded records and 20 image-verified
holdout records that do not share a clerk-year, plus a trainer pin. Renting
before those exist buys an adapter nobody can honestly evaluate.

On the public description: the research repository should not imply a working
adapter, and at present it does not. That should stay true. It is accurate and
more interesting to say that the project has an adapter pathway with
machine-checked launch gates that currently report blocked, and to show the
readiness report. A gate that publicly reports `BLOCKED` is a stronger claim
about method than a capability bullet would be.

Whether the LoRA belongs in v1 at all remains open. `SPEC.md:125` already
scope-fences it as "a v2 question", and nothing in this assessment argues with
that. The realistic sequence is: unsequestered reading now, first calibration
adapter when the pool clears 100 grounded records, and no promises in between.

## What can be done now without new labels

1. **Refresh the readiness report.** `training/readiness-0001.json` was measured
   on 2026-07-29 and its `input_pins` still carry the pre-move `E:\DNA` paths.
   Re-running `tools/training_preflight.py` costs nothing and keeps the reported
   state honest. It will still report blocked.
2. **Do not materialise wave-006 silver into the manifest.** It is sequestered
   and would deepen the isolation overlap. If the eight acts are recorded
   anywhere, record them as what they are: silver, eval-adjacent, not trainable.
3. **Leave the trainer recipe unpinned until a trainer is actually chosen.**
   `examples/lora-recipe.example.json` holds nulls for trainer implementation,
   version, and container digest, and an empty `target_modules`. Those nulls are
   why `TRAINER_RECIPE_PINNED` blocks, and filling them with plausible guesses
   would flip a gate to green without making anything true. The pin belongs to
   the same decision as the bakeoff.
4. **Rebuild the five voided silver records** as label hygiene, separately from
   any training argument.

The one structural change worth considering is recording, in the corpus plan,
which clerk-years are reserved for evaluation and which are open for training,
so that a future wave assignment cannot quietly consume a trainable year by
accident. That is a documentation change and does not touch the holdout itself.
