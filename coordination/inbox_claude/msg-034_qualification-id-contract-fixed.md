from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-30
re: human qualification archives rebuilt after assignment-ID contract fix
requires_ack: n

During the overnight training handoff audit I found that all generated qualification templates
used assignment IDs such as `qualification-0001-H1`, while the frozen submission schema permits
lowercase assignment IDs only. A worker could therefore have completed a correct transcript and
still failed validation.

Fixed and verified:

- generator now emits `qualification-0001-h1` / `-h2` / `-h3` assignment IDs;
- blinded worker codes remain `H1` / `H2` / `H3`;
- the packet regression fills a generated template and runs the actual qualification validator;
- all fifteen templates across the three real archives were inspected mechanically;
- every ZIP was rebuilt from the pinned non-BulkData scans and its receipt hash reverified;
- full repository gate remains **220 passed**; changed-file Ruff checks pass.

Canonical rebuilt archives under `training/qualification-0001/`:

- H1 SHA-256 `20defe9ed3b263a308a9ed7fb5f385d8f90fc0af642d2841e6b81cabd73a2a14`
- H2 SHA-256 `6402d4186c170beb8d0621f71a3e7fe6f8c55586ac87517ad260cb7e378f592b`
- H3 SHA-256 `befc726c65c44571ccb075b7d763f530402241da9462d3c0d6dca73372495c66`
- receipt SHA-256 `00b4c58ff1ea37f3b3964beafba951b15a96ed303640aabcdf95222d74a8d679`

The invalid generated packet was moved, not deleted, to
`tmp/qualification-0001-invalid-uppercase-assignment/` for recoverability. Do not distribute
that backup. The canonical three archives are now sendable when the owner elects to recruit.
