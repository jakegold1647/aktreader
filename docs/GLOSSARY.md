# AKT Reader Evidence Terms Glossary

This glossary explains specialized terms used in AKT Reader for evidence-aware handwritten text recognition (HTR). If you're a genealogist or Python contributor new to the project, this will help you understand the terminology without reverse-engineering it from the codebase.

## Core Evidence Concepts

### Blind Pass
A transcription pass performed without looking at the original image. This helps establish what can be read from context alone, making later corrections more traceable and reducing confirmation bias.

### Clerk-Year Sequestration
A validation technique where transcriptions from the same clerk and year are kept together during quality checks. This helps catch systematic errors in handwriting interpretation that are specific to that clerk's style.

### Filiation
The chain of evidence showing how a transcription was derived—which passes, corrections, and validation steps led to the final text. This makes the transcription process auditable.

### Typed Absence State
A structured way to record why text is missing or unreadable. Instead of just marking something as unclear, this categorizes the reason (damage, ink fade, abbreviation, etc.).

## Quality Tiers

### Silver
A transcription quality level indicating the text has been checked but may still contain minor uncertainties or require additional validation.

### Gold
The highest transcription quality level, indicating the text has been thoroughly validated and cross-checked. Gold-standard transcriptions are suitable for training machine learning models.

## Markup Conventions

### `[unclear: X/Y]`
A notation indicating uncertain text where:
- `X` is the transcriber's best guess
- `Y` is an alternative reading

Example: `[unclear: Müller/Miller]` means the transcriber reads it as "Müller" but "Miller" is also possible.

This preserves both the interpretation and the uncertainty, which is crucial for historical research where a single letter can change genealogical connections.

## Why These Terms Matter

Evidence-aware HTR treats transcription as a scientific process where uncertainty is documented, not hidden. These terms help contributors communicate precisely about transcription quality and trace how readings were established.
