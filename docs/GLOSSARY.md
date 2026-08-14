# AKT Reader glossary

This is a quick guide to the project’s specialist language. The linked files are authoritative; this page is an orientation layer, not a replacement for the schemas or evidence contracts.

## The reader and the record

**Act**  
A civil-register record with a fixed structure: type and number, dates, people, relationships, witnesses, officiant, and notes. AKT Reader extracts what the document supports; it does not infer a family relationship that the act does not state. See the [act schema in the build specification](../SPEC.md#the-act-schema).

**HTR (handwritten text recognition)**  
A system that turns handwriting in an image into text. AKT Reader treats HTR output as evidence to grade and review, not as authority by itself. See the [project architecture](architecture.md).

**Diplomatic transcription**  
A transcription that stays close to the document’s script, order, and visible wording, while preserving uncertainty and missing-text states instead of silently normalizing or completing them. The [build specification](../SPEC.md#0-one-paragraph-mission) describes this boundary.

**Filiation**  
The parentage information stated by the act, including the mother’s maiden name where present. It is an extraction field, not an invitation to make an unsupported genealogy or identity claim. See the [act schema](../SPEC.md#the-act-schema).

**Grounding / source span**  
The connection between an assertion and the exact evidence that supports it: a source-text span, image region or act locator, artifact hash, and relevant reader metadata. See the [gold-labeling protocol](gold-labeling-protocol.md).

**Artifact binding**  
Keeping an output tied to the precise input artifact and its identity information, rather than treating a copied sentence as free-floating truth. In practice this includes hashes, locators, reader identity, and prompt/schema pins. See [the README’s non-negotiable behavior](../README.md#non-negotiable-behavior) and the [gold-labeling protocol](gold-labeling-protocol.md).

## Reading and agreement

**Blind pass**  
One independent reading made without seeing another reader’s prediction. Independent passes reduce anchoring and make disagreements visible. See the [uncertainty-grading skill](../skills/uncertainty-grading.md).

**Blind group**  
The identifier for the set of records and readers that belong to one independent reading round. It helps keep provenance and evaluation splits auditable. See the [labeling and evidence rules](../CONTRIBUTING.md#data-and-label-changes).

**Consensus**  
A comparison or merge of independent readings that preserves the evidence and unresolved disagreement. Consensus is not permission to turn a weak majority into a confident fact. See the [architecture notes](architecture.md).

**Adjudication**  
A bounded human review step for the residue left by reading and verification. An adjudicator answers a focused question with the supplied evidence; the process records the consequence and does not silently rewrite a label. See [human adjudication packets](adjudication.md).

**Uncertainty grade**  
The project’s confidence vocabulary for a supported assertion: \`CONFIDENT\`, \`PROBABLE\`, or an unresolved \`UNCLEAR\` result. A single reader cannot emit \`CONFIDENT\`; the exact contract lives in the [uncertainty-grading skill](../skills/uncertainty-grading.md).

**\`[unclear: X/Y]\`**  
The project’s marker for competing plausible readings. \`X\` is the preferred candidate and \`Y\` is an alternative; the alternatives remain visible instead of being collapsed into one invented answer. See the [uncertainty-grading skill](../skills/uncertainty-grading.md).

**Wrong-but-CONFIDENT**  
The rate of incorrect assertions that were labeled \`CONFIDENT\`, divided by all evaluated \`CONFIDENT\` assertions. When there are no confident assertions, the result is \`N/A\`, not a passing zero. See [SerockBench’s headline metrics](serockbench.md#headline-metrics).

## Evidence states and quality tiers

**Observation state**  
The status of a field when the record does not simply contain a value. The project keeps \`ABSENT_ON_FORM\`, \`BLANK\`, \`STATED_UNKNOWN\`, and \`ILLEGIBLE\` distinct; imported notes may also use \`NOT_ANNOTATED\` when the note did not cover a field. See the [gold-labeling protocol](gold-labeling-protocol.md#what-a-gold-field-means) and the [versioned label schemas](../schemas/).

**Typed absence**  
An explicit observation state explaining why a resolved value is not present or readable. It is not the same as guessing, leaving a field out, or claiming that the form lacked the field. See [the README’s non-negotiable behavior](../README.md#non-negotiable-behavior).

**Gold**  
The human-verified evidence tier intended for benchmark-quality records. A record imported from an old research note is not automatically image-attested gold: the project keeps its attestation, provenance, and eligibility status explicit. See [what a gold field means](gold-labeling-protocol.md#what-a-gold-field-means) and the [gold attestation contract](gold-labeling-protocol.md#gold-attestation-contract-v10).

**Silver**  
A machine-derived or machine-consensus tier that has not been human-verified as gold. \`SILVER\`/\`PROBABLE\` is useful evidence, but it must not be described as human-verified gold. See the [contributor rules](../CONTRIBUTING.md#data-and-label-changes).

**Provenance**  
The record of where an assertion came from and how it was produced: source-note path and hash, section locator, artifact identity, reader identity, prompt/schema pins, and later corrections or consent events. See the [provenance section of the gold-labeling protocol](gold-labeling-protocol.md#provenance-and-correction-flywheel).

## Evaluation and repository boundaries

**Clerk-year**  
A split unit combining the register clerk and year. It is used because handwriting and local practice can recur across acts; evaluation must not leak the same clerk-year into training. See the [holdout and corpus notes](serockbench.md#corpus-and-isolation).

**Holdout**  
The evaluation set kept separate from training, with separation enforced at the clerk-year level rather than only by act ID. See the [training transition gate](training-transition.md) and the [holdout manifest](../gold/clerk_year_holdout.json).

**Reader identity**  
The stable identity of the reader or model that produced an output. It is part of the evidence record, not a cosmetic label. See the [contributor rules](../CONTRIBUTING.md#data-and-label-changes).

**Local-only / no-egress**  
The installed application does not call hosted model APIs, scrape archives, or make network requests during its supported local paths. The no-egress claim is tested, and owner-only acquisition scripts are a separate boundary. See the [README’s no-egress section](../README.md#verifiable-no-egress).

**Repository roles**  
\`aktreader\` is the **Application**; \`aktreader-research\` is the **Evidence Lab**; and \`congress-poland-registers\` is the independent **Benchmark Dataset**. Keeping those roles separate prevents application behavior, research evidence, and benchmark data from being conflated. See the [repository map](../README.md#which-repository-do-i-need).

**Correction flywheel**  
The consent-gated record of later human corrections that can improve future evaluation or training without overwriting the original evidence. See [provenance and correction](gold-labeling-protocol.md#provenance-and-correction-flywheel).

If a term here conflicts with a schema or contract, follow the linked schema or contract and report the documentation mismatch.
