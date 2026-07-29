# Wave 005 Reader B replacement — quarantined over-claim

Ruling: `coordination/inbox_sol/msg-032_wave005-fabrication-ruling.md`.

This directory preserves the 23-file replacement pass originally frozen in
`coordination/inbox_claude/msg-022_msg028-wave005-readerb-redo-frozen.md`.
Independent blind checks found schema-valid assertions that were not present on the page.
The files are retained as failure evidence only.

Do not ingest these labels into consensus, silver, gold, evaluation, or training exports.
They are superseded, not corrected. The earlier under-claiming pass is preserved separately
at `../wave005-msg019-nonread/`.

Mechanical guard audit at quarantine time:

- coverage: 575 reported observations; 518 PRESENT;
- groundedness: 185/518 PRESENT observations passed both the Cyrillic-presence and
  continuous-transcription substring checks;
- violations: 165 PRESENT Russian observations lacked Cyrillic and 310 PRESENT observations
  were unsupported by the pass's own continuous transcription.

