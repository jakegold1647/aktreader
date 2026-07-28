# Architecture guardrails

Status: P0 design record, 2026-07-28.

The implementation follows a five-stage flow:

```text
scan -> preprocess -> read -> structure -> grade -> act.json + act.md
```

Reading is pluggable. AKTREADER does not train a handwriting-recognition model in v1. A reader
may call a frontier vision model, call a local VLM, or import text from another HTR system.

## Evidence model

The authoritative model is not a flat register row. It has four layers:

1. **Source artifact** — a content-addressed scan, page, or crop, with its path, checksum,
   register identity, page coordinates, and privacy decision.
2. **Reader observation** — immutable output from one reader pass, including reader/version,
   prompt/configuration identity, timestamp, transcript, and spatial or textual spans.
3. **Act assertion** — a normalized value plus original script, observation state, confidence
   grade, alternatives, and one or more source spans. People here are role-bearing mentions
   within an act, not globally resolved people.
4. **Derived hypothesis** — a corpus-level claim such as “these two mentions may be the same
   person.” It carries supporting and contradicting act IDs, a score, method provenance, and
   human review status. It never rewrites the source assertions.

This separation is required for corpus-level constraint solving and town graphs: new evidence
can revise a hypothesis without changing what an act was observed to say.

## Field semantics

Every schema field will retain at least:

- `value`: normalized value when one is supported;
- `original_script`: literal reading in document order;
- `confidence`: `CONFIDENT`, `PROBABLE`, or `UNCLEAR`;
- `observation_state`: `PRESENT`, `ABSENT_ON_FORM`, `BLANK`, or `ILLEGIBLE`;
- `source_spans`: one or more scan bounding boxes and/or transcript offsets;
- `alternatives`: explicit readings used by `[unclear: X/Y]`;
- `evidence`: reader-pass IDs and any cross-checks that affected the grade.

Presence and confidence are orthogonal. A cleanly visible blank is confidently `BLANK`; an
expected field that cannot be read is `ILLEGIBLE`; a field the form never supplies is
`ABSENT_ON_FORM`. None means “unknown person.”

The act schema will cover type/number/year, registration and event dates, town, principal,
parents including the mother's maiden name, spouse and spouse's parents, declarants and
witnesses including ages and occupations, officiant, signatures, marginalia, survivors, and
marriage-specific banns, permissions, and rabbi fields.

## Stable identity and provenance

- Act IDs derive from collection/register/page/act identity, not a person's name.
- Artifact checksums detect silent scan replacement.
- Pipeline runs are append-only and reproducible from recorded configuration.
- Normalized names never overwrite literal readings.
- CSV is a lossy projection for search and batch handoff; JSON remains authoritative.
- Markdown renders the original-order transcript, translation, extraction table, source path,
  and the warning: “extraction is not authority — verify against the scan.”

## Corpus and graph horizon

A later graph contains mention nodes, reviewed person-identity hypotheses, and typed edges whose
provenance points back to act assertions. Automatic entity resolution may propose links but may
not merge people. Corpus-level regrading creates a derived assessment and preserves the original
per-act grade, so repeated names or scribe priors cannot erase earlier uncertainty.

Memorial matching is deliberately outside the extraction store. It accepts only manually entered
record details and the user's own corpus, produces candidates for human review, and never fetches
or submits memorial records.

## Phase boundaries

- P1 populates only verified Serock gold fixtures.
- P2 implements preprocessing, readers, schema validation, grading, rendering, and evaluation.
- P3 acquisition is blocked until its explicit terms-and-polite-pace gate is approved.
- P4 adds variant proposals without changing literal names.
- P5 selects the license and publication surface.
