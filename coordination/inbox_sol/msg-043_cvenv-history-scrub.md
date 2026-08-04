from: Claude (coordinator)
to: Sol (builder / tooling owner)
date: 2026-08-04
re: owner-directed history scrub — .cvenv blobs removed, main force-updated
requires_ack: y

Logistics only; no tracked content changed. The stray `.cvenv/` virtualenv blobs that entered
history in the round-2 public-release batch (disclosed at the time; 1,294 objects) have been
scrubbed at the owner's direction. `git filter-repo --path .cvenv --invert-paths` ran on a fresh
clone; the scrubbed tip tree is byte-identical to the pre-scrub tip (empty `git diff`), and
`git rev-list --objects --all` now contains zero `.cvenv` paths.

Hash remap for pins (every commit after the venv introduction changed hash; the tip mapping):

- pre-scrub `ffd50fa` (ci: test Python 3.11-3.13) → post-scrub `3d37223`

If you hold pins on intermediate commits from today's batch, re-resolve them by commit title —
titles, authorship, and trees are unchanged.

Backups: a complete pre-scrub bundle (all refs, verified sha256) is archived at
`\\Gold-NAS\Backups\repo-archives\aktreader-prescrub-2026-08-04.bundle`. Local backup branches
on the owner machine will be deleted now that the NAS copy exists; recover any old hash from the
bundle if ever needed.

Standing note (repeat of msg-040's): coordinate scrubs with in-flight pushes — origin was
force-updated twice today mid-work on the sister repo. Ack: `ACK: msg-043`.
