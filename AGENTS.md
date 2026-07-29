# AGENTS.md — read me automatically, then read SPEC.md fully

**The authoritative build document is `SPEC.md` in this folder.** Read it top to bottom before
any work, starting with its HANDOFF NOTE. This file only adds standing orientation.

## Coordination bus (added 28 Jul 2026 — check EVERY session)
A standing coordinator now runs between you (Sol, builder/Reader B) and Claude
(coordinator/Reader A): `coordination/PROTOCOL.md` has the rules, `coordination/STATUS_BOARD.md`
the live state. At the start of every session: read the board, then any new messages in
`coordination/inbox_sol/` in ascending order. Write your replies, gate reports, and blockers to
`coordination/inbox_claude/` as `msg-NNN_<slug>.md` — the chat transcript is not the record;
the inbox is. Ownership and blindness rules in PROTOCOL.md override convenience.

**IDLE PROTOCOL (standing, per msg-014):** never sit idle waiting for a human relay. After
each completed item, re-check `coordination/inbox_sol/`. When idle or blocked, run
`powershell -File coordination\watch_inbox.ps1` (blocks ≤10 min; exit 0 = new message/board
change → read and act; exit 2 = timeout → run again). The coordinator's side is event-driven;
your inbox_claude posts are seen within seconds. The human only enters for spending,
credentials, human gold checks, and ESCALATE items.

## Domain skills (load before the phase that needs them)
- `skills/napoleonic-act-formula.md` — the fixed rhetorical structure of the acts, both
  languages, with slot → schema-field mapping. Needed from P2 onward; informs the P1 schema too.
- `skills/cyrillic-paleography.md` — pre-1918 orthography, handwriting confusables, dates and
  numbers written as words. Feed relevant parts INTO the Reader prompts; use for [unclear]
  adjudication.
- `skills/uncertainty-grading.md` — the grading contract. This is the soul of the tool; P2's
  acceptance metric is defined here. Violating it (guessing instead of marking [unclear]) is
  the one unforgivable bug.
- `skills/jewish-onomastics.md` — name-equivalence knowledge (Icek=Itzhak=Itche etc.), maiden
  name conventions, town-variant seeds. Needed for P4 and for gold-corpus cross-checks.

## Standing constraints (duplicated from SPEC for emphasis)
- Write ONLY inside this folder. Read-only everywhere else under E:\DNA\.
- Do NOT enter E:\DNA\BulkData\ at all today — another agent process is actively writing there.
- No archive scraping; no USHMM/Arolsen/Yad Vashem data in anything; no browser use is needed
  for P0–P2 at all (web only for package docs). P3 does not start without Jake's go-ahead.
- Gold corpus: transcribe only what the cited project files state. Never invent a field.
- Stop at each phase gate with: built / skipped+why / exact run commands.

## Today's timeline
Target P0+P1+P2 complete today. Gates are brief check-ins, not day boundaries. Smallest honest
version of each phase. P3 stops at its gate regardless of time remaining.
