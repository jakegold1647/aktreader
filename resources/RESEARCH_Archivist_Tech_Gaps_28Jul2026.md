# Deep Research report: Unmet Needs and Technology Gaps in Handwritten Historical Records Workflows
Received 28 Jul 2026 via Jake's GPT Deep Research run. Stored verbatim below for citation in
README/portfolio/grant language. Coordinator's cross-map to AKTREADER follows the report.

[Report as received — see conversation record / Jake's paste of 28 Jul 2026. Key structure:
tool landscape (Transkribus, eScriptorium/Kraken, FamilySearch FTS, Ancestry, Zooniverse,
national programs, commercial vendors); 10-row evidence-led gap matrix; ranked top-5 shortlist;
incumbent blind-spot analysis.]

## Coordinator cross-map: the top-5 shortlist vs AKTREADER as of tonight
1. **Actionable uncertainty and abstention** (their #1) → BUILT. The grading contract
   (CONFIDENT/PROBABLE/[unclear: X/Y]/ILLEGIBLE + typed absence states), single-reader-never-
   CONFIDENT, wrong-but-confident as SerockBench's headline metric. Their cited failure case
   ("stillborn became a fabricated person") is our Gersz Weksler / Lejb Majkowski phantom class —
   we have two documented catches.
2. **Structured record extraction for civil/parish registers** (their #2) → BUILT. One record
   per act, role labels, verbatim+normalized values, field-level uncertainty, image-span bboxes.
3. **Local/offline deployment** (their #3) → BUILT BY DESIGN. No API keys, local open-weights
   VLM, no page credits, consumer GPU.
4. **User-controlled correction-to-learning loops** (their #4) → DESIGNED (§11 flywheel,
   consent/training-eligibility metadata, silver/gold separation). Not yet shipped — roadmap.
5. **Low-resource mixed-script niche, deeply solved** (their #5) → THE PILOT ITSELF: pre-1918
   Russian/Polish civil registers, Cyrillic cursive, language switching at 1868, proper-name
   extraction. Their example niche is literally our corpus.

Also directly held: their low-difficulty gap #10 (machine-readable provenance: model ID,
software version, prompt hash, review status, uncertainty summary per output) — we already do
all of it; surface it as a first-class README claim. Their "AI-first volunteer workflows —
route review only to high-uncertainty spans" is the JRI-Poland partnership pitch shape.

## Positioning sentence (adopt verbatim in README/portfolio, adapted from the report's close):
"AKTREADER produces institutionally usable evidence objects from difficult handwritten
records — structured records, uncertainty you can act on, local deployment, machine-readable
provenance, and feedback loops that accumulate expertise instead of discarding it."
