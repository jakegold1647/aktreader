# Human adjudication packets

`aktreader adjudicate` turns the residue left by reading and verification into a small,
self-contained question set. It does not ask a human to transcribe a register. Each question
shows a plain-language claim, a 4–8× disputed crop, 3–6 uncontested same-clerk examples of every
candidate glyph, available bilingual anchors, structural checks, and the consequence of every
choice.

## Build a packet

Prepare `human_check/waves/wave-003.json` under
`schemas/adjudication-wave-1.0.0.schema.json`, then run:

```powershell
aktreader adjudicate --wave 003
```

Use `--spec` or `--output-dir` for an explicitly different local path. The generator verifies
every image SHA-256 before opening it, cuts the source-pixel span and explicitly boxed disputed
glyph locally with Pillow, magnifies both with nearest-neighbor resampling, and embeds every PNG
as a data URI. The HTML has no
network dependency. If an exemplar has a precise `glyph_bbox`, it is used. Otherwise the miner
requires `character_index`, makes a visibly disclosed proportional character crop, and keeps
the full word beside it.

Question selection is deterministic:

1. identity forks;
2. machine deadlocks;
3. ink/corroboration conflicts;
4. single-coverage fields on gold nominees.

The nominal cap is ten. Identity forks and deadlocks are mandatory and may exceed it.
`EXCLUDE_TRANSCRIPTION_QUEUE` items are never selected. For each candidate, generation fails
closed unless it can mine at least three uncontested instances of the proposed glyph from the
same clerk-year; it selects at most six.

## Record and ingest answers

Open `packet.html` locally. “Neither / something else” and “Can’t tell” are first-class answers,
not failures. The page downloads an answers JSON; it never submits data.

```powershell
aktreader adjudicate --wave 003 `
  --answers .\human_check\generated\wave-003\adjudication-wave-003.answers.json
```

Ingestion verifies the packet and question fingerprints, requires exactly one answer per
question, and writes an immutable content-addressed result directory containing:

- verbatim answers, coordinator interpretation, and the declared consequence;
- tier-action events;
- per-field gold-attestation events;
- consent-gated correction-flywheel JSONL;
- an expert-review list for neither/can't-tell outcomes.

It never edits a reader label, silver record, or gold record. A downstream review must apply
the emitted event. Correction reuse is training-eligible only when the answer file records
explicit `GRANTED` consent.

## Honest limits

A non-reader matching letterforms is discriminating among proposals, not independently reading
the script. Both candidates can be wrong, so every question includes the neither escape.
Publication-grade gold should still be sampled by a reader of the script. The packet raises the
evidentiary floor and focuses expert time; it does not replace expertise.
