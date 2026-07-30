from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-30
re: owner-directed Serock zero-cost ten-act visual-corroboration holdout frozen
requires_ack: n

The msg-032 recommendation is now an executable offline human-review packet. No label was
modified, no external archive was scraped, and no independent Cyrillic-reading claim is made.

## Frozen packet

- wave spec:
  `human_check/waves/wave-serock-1890-zero-cost-holdout-01.json`
  - SHA-256 `8896b73a1cdca1c5c7c163291ba96043b0cb2038b297f76ff7a8aff1ef906343`
- packet:
  `human_check/generated/serock-1890-zero-cost-holdout-01/packet.html`
  - SHA-256 `6828d741b5c7fd55d1536ea6f7d3719f213b8798929ebce79201bac98ae311ae`
- questions:
  `human_check/generated/serock-1890-zero-cost-holdout-01/questions.json`
  - SHA-256 `44d67830303a5233a99b53ea78b8535e813737d5d31267b3070dfa047ebf7cdf`
- owner runbook:
  `human_check/SEROCK_1890_ZERO_COST_HOLDOUT_RUNBOOK.md`

The ten acts are 2, 3, 6, 30, 32, 33, 37, 39, 43, and 47:

- 3 identity forks: 6, 32, 39;
- 5 corroboration conflicts: 2, 3, 30, 33, 47;
- 2 gold-single-coverage checks: 37, 43.

All ten use `VISUAL_CORROBORATION`. The packet has sixteen comparison cards: closing-formula
repeats where available and independent annual-index rows. The HTML contains ten question
sections and 26 embedded source PNGs, has no network dependency, and retains both `Neither /
something else` and `Can't tell` for every question.

## Guardrail change

The adjudication schema and renderer now distinguish visual corroboration from same-hand
letterform choice. Visual corroboration skips glyph-lineup mining, mechanically pins its
comparison regions, and can make a selected candidate do either of the following:

- `ATTEST_FIELD`, for corroborated visual consistency;
- `ROUTE_EXPERT`, for a known conflict.

Every substantive candidate in this packet is explicitly `benchmark_eligible: false` and
`correction_eligible: false`. A non-reader's choice therefore records useful evidence without
becoming benchmark gold or training data. Conflict, neither, and can't-tell outcomes emit
expert-review routing. Answer ingestion remains immutable and never edits source labels.

## Verification

- Full repository suite: **220 passed**.
- Ruff lint and format checks pass for changed adjudication code/tests.
- Ten visual questions, sixteen comparison cards, ten rendered question sections, and 26
  embedded PNGs were counted mechanically.
- Every source crop was visually inspected against its pinned canonical scan.
- Rendered-browser interaction QA remains an owner-side morning check because this environment
  had no browser session. I am not representing structural HTML checks as browser QA.

The owner can open the packet, answer ten bounded questions, download its JSON, and run the exact
ingest command in the runbook. Any downstream benchmark promotion still requires an actual
Cyrillic-reader review; this freeze only closes the zero-cost evidence loop honestly.
