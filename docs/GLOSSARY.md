# AKT Reader Glossary

A plain-language guide to evidence-aware HTR terms used in this project.

## Core Concepts

**HTR (Handwritten Text Recognition)**  
Machine learning systems that convert images of handwritten documents into digital text.

**Evidence-aware HTR**  
HTR that preserves uncertainty and alternative readings rather than forcing a single "best guess." Critical for genealogical and archival work where accuracy matters more than confidence.

## Quality Tiers

**Gold**  
Human-verified transcriptions. The highest quality ground truth, used for training and evaluation.

**Silver**  
Machine-generated transcriptions that pass quality thresholds but haven't been manually verified. Useful for scaling, but may contain errors.

## Reading Strategies

**Blind pass**  
Transcribing without looking at existing transcriptions or predictions. Reduces bias and anchoring effects. Multiple independent blind passes can be compared to identify difficult passages.

**Filiation**  
The relationship between different versions of a text. In AKT Reader, tracking whether a transcription was derived from another transcription, from a model prediction, or created independently.

## Uncertainty Markup

**`[unclear: X/Y]`**  
Marks text where the transcriber sees two (or more) plausible readings. `X` is the preferred interpretation, `Y` is the alternative. Example: `[unclear: März/Mai]` means "probably März, possibly Mai."

**Typed absence state**  
Explicit markers for *why* text is missing or unreadable: damage, illegible handwriting, missing pages, etc. Better than silently omitting unclear text.

## Workflow Concepts

**Clerk-year sequestration**  
Isolating training data by clerk and year to prevent the model from memorizing individual handwriting styles instead of learning general patterns. Ensures the model generalizes to unseen clerks and time periods.

## Why These Matter

Genealogical research requires knowing *what we don't know*. A silently wrong date can break a family tree. Evidence-aware transcription preserves doubt, alternatives, and the human decision-making process—making errors visible and fixable rather than hidden in a black box.
