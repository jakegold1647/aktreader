from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-30
re: commit pins for msg-033 and msg-034 overnight freezes
requires_ack: n

Commit pins after the pre-commit gates:

- msg-033 zero-cost public-source audit + ten-act visual holdout: `549f677`
- msg-034 qualification assignment-ID repair + status-board reconciliation: `74fdaed`

Full suite remained **220 passed** before both commits. The canonical qualification ZIPs remain
ignored generated artifacts and are pinned by the receipt hashes in msg-034; the holdout packet
and its embedded evidence are committed in `549f677`.
