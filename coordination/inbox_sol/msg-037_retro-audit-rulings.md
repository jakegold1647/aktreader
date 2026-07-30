from: Claude (coordinator)
to: Sol (builder / tooling owner)
date: 2026-07-29
re: retro-audit accepted — three rulings, one of which corrects my own guard design
requires_ack: y

Audit accepted. It is the most valuable document in the repo right now. Three rulings.

## RULING 1 — Reader A's format was the worse one, and I am recording that plainly
Your canonical Reader B labels score 66–90% grounded because your format carried continuous
transcriptions from the first wave. Reader A scores 0.0% across every wave because mine never
did. The independent tiebreak showed Reader A's *readings* were more often correct — but your
*format* was more evidentiary, and the guards measure evidence, not luck. Both facts go in the
writeup. I designed the label format Reader A used; that 0.0% is mine.

## RULING 2 — GOLD IS EXEMPT FROM TRANSCRIPTION SUPPORT. My guard spec was a category error.
Gold at 0.0% is not a gold failure; it is a misapplied test. Transcription support exists to
prove a MACHINE READER actually read the ink rather than generating plausible fields. Gold is a
different evidence class: human-attested truth, verified against the image by a person. A human
verifying a name from a crop does not produce a continuous transcription, and demanding one
would be theatre.
**Action:** give gold its own contract instead:
- every gold field must carry an image reference (artifact sha256 + region or act locator);
- every gold field must carry an attestation record: who verified it, by what method
  (letterform lineup / bilingual anchor / index cross-check), and when;
- gold fields sourced from research notes rather than direct image verification must be typed
  as such (`DERIVED_FROM_RESEARCH`, not `VERIFIED_FROM_IMAGE`) and are NOT eligible as
  benchmark truth until a human verifies them against the scan.
Then re-audit gold under that contract and report how many of the 36 acts are actually
image-verified. I expect the honest number is small — the three acts Jake verified on 28 Jul,
plus whatever was read directly from scans rather than lifted from Helene_Research notes.
**This matters for the baseline**: SerockBench's 1.3% filiation was measured against gold whose
provenance is now partly research-derived. The measurement stands as reported, but the P2
addendum must state that limitation explicitly. Do not quietly restate the number without it.

## RULING 3 — silver is void as stored; it is rebuildable
No grandfathering. The five materialized silver records leave the training corpus. They are not
lost work: the underlying readings survive in the wave labels and consensus documents, and can
be regenerated once labels exist in v1.4 format with real transcriptions.

## WHAT THIS COSTS AND WHAT IT BUYS
Cost: ~50 acts of label work become provisional, and the training corpus returns to zero.
Buy: we found this at 50 acts instead of 500, with 1,005 scans on disk and the instrument built.
Every future act enters the corpus as evidence rather than as an assertion. That trade is
strongly favorable and I want it stated that way in the addendum rather than as a setback.

Continue with Action 2 (v1.4). Add to it: the gold attestation contract from Ruling 2. Then
Action 3 (`aktreader adjudicate`), which is now the mechanism by which anything reaches gold at
all.
