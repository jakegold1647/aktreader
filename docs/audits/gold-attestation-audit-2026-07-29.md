# Gold attestation audit — 2026-07-29

This is a read-only audit under the gold-specific contract. Machine-reader continuous
transcription support is intentionally not applied to human gold.

## Result

- Stored gold acts audited: **36**
- Asserted fields: **558**
- Fields with contract-valid attestations: **0**
- Fields verified directly from images: **0**
- Fully image-verified, benchmark-eligible acts: **0/36**

The honest stored-state result is zero benchmark-eligible acts. The existing records
carry research-note provenance but no per-field image reference and dated attestation
sidecars. The 28 July human packet verified acts 6, 34, and 39, but those acts have not
been materialized in `gold/acts`; the audit does not infer or backfill attestations.

The earlier machine-reader retro-audit's 0% transcription score for gold is void as a
gold-quality judgment. This audit supersedes that interpretation while preserving the
original read-only measurement.

## Benchmark limitation

The reported P2 baseline remains a measurement against the frozen 36-record corpus, but
that corpus is research-derived and currently has no contract-valid image-attested acts.
Its accuracy figures must not be presented as publication-grade image-verified benchmark
truth until adjudication sidecars satisfy this contract.
