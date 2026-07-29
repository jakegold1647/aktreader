# Gold labeling protocol

Status: P1, 2026-07-28.

## Source boundary

Gold labels are imports of verified local civil-register research notes. They are not fresh
transcriptions and do not complete fields that the notes omitted. Memorial-institution material
is excluded even when a local note contains it. P1 uses:

- `E:\DNA\Helene_Research\Majer_Thirteen_Children.md`
- `E:\DNA\Helene_Research\Serock_Acts_Read.md`
- `E:\DNA\Helene_Research\C_Serock_Registers_Goldsztajn_Miara.md`
- `E:\DNA\Helene_Research\Pultusk_Fond84_Goldsztejn.md` for seven supplemental, already-read acts

The corpus is 29/36 Serock acts. The seven Pułtusk acts are a labeled supplement, not P3 batch
acquisition. No site was visited and no scan was fetched for P1.

## What a gold field means

- `PRESENT`: the verified note states the value.
- `NOT_ANNOTATED`: the note does not label this field. It does **not** mean the register left it
  blank, that the form lacked it, or that it was unreadable.
- `BLANK`, `ABSENT_ON_FORM`, `STATED_UNKNOWN`, and `ILLEGIBLE` are used only when the note says
  that specific historical fact.
- `UNCLEAR` retains candidates in both the normalized marker and `alternatives`.
- `original_script` is populated only when the source note preserves the page wording. A translated
  summary never masquerades as original script.

Existing notes do not document two independent reader passes for each field, so imported values
default to `PROBABLE`, even when the note calls the act documented. `CONFIDENT` remains reserved for
the P2 multi-pass contract.

## Gold attestation contract (v1.0)

Machine-reader continuous-transcription support does not apply to human gold. Instead, every
asserted gold field must have a sidecar conforming to
schemas/gold-attestation-1.0.0.schema.json: an artifact SHA-256 plus source-pixel region or act
locator, and a dated attestation naming the verifier, method, and verbatim answer.
VERIFIED_FROM_IMAGE fields may be benchmark eligible; DERIVED_FROM_RESEARCH fields must use the
research-note extraction method and are not benchmark truth.

The read-only 29 July audit found **0/36** stored acts fully compliant. Existing records remain
frozen research artifacts, not erased or silently upgraded. The adjudication command is the route
for creating future attestations; publication-grade gold should still be sampled by a reader of
the script.

## Provenance and correction flywheel

Each record stores the source-note path, SHA-256, section locator, local artifact path/checksum when
available, and the authority warning. Existing imports are:

- evaluation-eligible;
- not expert-tier merely because an earlier agent called them verified;
- not training-eligible because corrector consent is not recorded;
- initialized with an empty correction history.

A later correction must append the prior value, corrected value, corrector identity or stable ID,
verification tier, timestamp, consent status, and source crop. Corrections never overwrite the
historical annotation in place.

## Known coverage gap

All 36 permitted verified acts are Russian-language. The only Polish act encountered in the three
initially cited files is tentative and embedded in prohibited memorial-derived material, so it is
excluded. P1 therefore meets the numeric and birth/marriage/death coverage targets but not the
Polish-language target. A Polish act may be added only from an independently verified, permitted
artifact; it must never be invented to make the coverage table look complete.
