# Landscape re-check

Checked: 2026-07-28. This is a product-documentation review, not a benchmark. No accounts were
created, no documents were uploaded, and no claims below imply hands-on validation.

## Result

AKTREADER still has a distinct target, but the original comparison was too broad. Transkribus
and Metryki both advertise structured extraction. The defensible gap is narrower:

- open, act-format-aware extraction for Polish/Russian civil registers;
- per-assertion provenance and explicit alternatives;
- scored separation of `ABSENT_ON_FORM`, `BLANK`, and `ILLEGIBLE`;
- a public filiation benchmark with wrong-but-confident rate as a headline metric;
- evidence-preserving corpus reasoning in which entity matches require human confirmation.

The README and future positioning must use this narrower claim.

## Transkribus / READ-COOP

Confirmed:

- The public “Russian Civil Records late XIX cent.” model remains listed at 7.3% validation CER
  and is described as working particularly well on Congress Poland civil records.
- Transkribus advertises 300+ public models, field models, entity tagging, structured exports,
  source-image coordinates for TEI entities, and batch/API workflows.
- Recognition remains credit-metered: the public pricing page lists one credit per HTR page,
  plus separate charges for line, table, and field recognition.
- The main product is a hosted platform; a separately licensed on-premises offering exists.

Implication: AKTREADER must not claim that Transkribus lacks fields or provenance. Its
differentiator is the fixed civil-act evidence schema, uncertainty semantics, filiation metric,
and corpus-level honesty layer. A Transkribus import remains a valuable Reader implementation.

Primary sources:

- <https://www.transkribus.org/models/russian-civil-records-late-xix-cent>
- <https://www.transkribus.org/document-data-extraction>
- <https://www.transkribus.org/pricing>
- <https://www.transkribus.org/integration>
- <https://legal.transkribus.org/terms>

## Metryki

Confirmed:

- Metryki is a hosted, account-based, credit-priced product supporting Polish, Latin, German,
  Russian, Cyrillic, and other historical records.
- It advertises transcription, translation, structured genealogy fields, confidence scores,
  missing-field and inference notes, review queues, project-level search, family connections,
  JSON/CSV/GEDCOM exports, and archive import.
- Its terms state that processing uses third-party AI services.

The public pages do not document an open-source implementation, a source-span schema for every
assertion, the three-way blank/absent/illegible distinction, or a public wrong-but-confident
benchmark. These are documentation observations, not claims that private functionality cannot
exist.

Primary sources:

- <https://www.metryki.com/>
- <https://www.metryki.com/Home/Services>
- <https://www.metryki.com/Home/Terms>

## L'Dor V'Dor AI Lab / PastPort

Confirmed:

- The AI Lab lists handwriting models in Russian, Polish, Yiddish, Hebrew, and Arabic and
  describes “PastPort” under experiences and apps.
- Its own AI Lab page labels the available walkthrough “PastPort (Preview).”
- A July 2026 LDVDF page calls a Kingdom of Poland surname lookup through PastPort
  “forthcoming.”

No official page located in this check documents a released open PastPort pipeline for
per-field graded filiation extraction. The pivot watch remains active: if such a component ships
openly, AKTREADER should become its evidence/evaluation layer where possible.

Primary sources:

- <https://ldvdf.org/ai-lab/>
- <https://ldvdf.org/new-gate-polish-jewry-community-connection/>

## Additional nearby products

Two current products surfaced in the broad re-check:

- KinProof advertises structured genealogy extraction, source-linked facts, and human review.
- GlyphForge advertises scan-to-graph extraction and automated tree building behind request
  access.

Neither public site reviewed here documents an open-source Napoleonic-act extractor or the
uncertainty benchmark AKTREADER proposes. Their existence further reinforces that AKTREADER
should make precise, testable claims rather than say that structured genealogy extraction does
not exist.

Sources:

- <https://kinproof.com/en>
- <https://glyphforge.com/>

## P0 decision

Proceed with AKTREADER as an evidence, grading, and evaluation layer above pluggable readers.
Re-check this landscape again before P5 publication and keep PastPort on the explicit pivot list.
