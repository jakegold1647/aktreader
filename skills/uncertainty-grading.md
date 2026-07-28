# The grading contract — the soul of the tool
A wrong-but-confident field is the cardinal failure. Ten honest [unclear]s beat one guess.
P2's acceptance gate: filiation exact-match ≥90% on gold AND wrong-but-CONFIDENT < 2%.

## Per-field confidence enum
- **CONFIDENT** — both independent reads agree AND the reading survives cross-checks. This
  grade is a promise; spend it carefully.
- **PROBABLE** — reads agree but a cross-check is unavailable, or one read + strong formula
  prior. Default grade for most fields.
- **[unclear: X/Y]** — genuinely ambiguous between readings X and Y (or [unclear: X?] for one
  shaky candidate). ALWAYS list the candidates; never output bare "unclear."
- **ILLEGIBLE** — the ink/scan defeats reading entirely (stain, tear, resolution).

## The three-way distinction that must NEVER collapse (hardest-won lesson of the source project)
For an expected-but-missing field, distinguish:
1. **ABSENT-ON-FORM** — the formula/form has no slot for it (e.g., mother's line not part of
   this document type).
2. **BLANK** — the slot exists and was left empty by the clerk.
3. **STATED-UNKNOWN** — the clerk wrote "unknown" («неизвѣстно»).
These are three different historical facts. Indexes that collapse them into one word have
sent real researchers down wrong paths for months. The JSON must carry which one it is.

## Cross-checks (mechanical upgrades/downgrades — implement as validators)
- **Date arithmetic**: registration_date ≥ event_date; dual-date gap = 12/13 days; stated age
  vs any known birth act.
- **Witness-age continuity**: the same witness across acts of adjacent years must age ~1 year
  (this exact check let the source project prove two death acts were one event). A witness
  aging 0 or 2 years across a year boundary is NORMAL noise; 5+ is a misread or a different
  person — flag, don't decide.
- **Within-register consistency**: same clerk-year → same spellings of recurring
  names/officiant; a one-off variant spelling of a recurring name is a misread candidate.
- **Formula position**: a value extracted from the wrong rhetorical slot (an age where the
  formula puts the hour) is auto-downgraded.

## Multi-pass protocol
Two independent Reader passes (different prompt seeds or different backends). Field-level
agreement → eligible for CONFIDENT. Disagreement → the disagreeing readings BECOME the
[unclear: X/Y] candidates automatically. Never let pass 2 see pass 1's output.

## Output honesty rules
- original_script preserves exactly what the page shows (pre-reform letters, hard signs,
  Russified name forms); value carries the normalized form; the two must never be conflated.
- Every field carries source_span (where on the page it came from) so a human can re-check
  the pixels — the project's evaluate-from-the-artifact rule, inherited.
- Calibration is measured, not asserted: the eval harness scores wrong-but-CONFIDENT as its
  headline metric, and the README publishes the number.
