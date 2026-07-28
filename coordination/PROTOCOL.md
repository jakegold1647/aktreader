# COORDINATION PROTOCOL — Claude (coordinator/Reader A) ⇄ Sol (builder/Reader B)
v1.0 — 28 Jul 2026. Both agents work in this repo; this directory is the message bus.
The human (Jake) is the trigger, not the channel: he just tells each side "check your inbox."

## Directory layout
- `coordination/inbox_sol/`    — messages FROM Claude TO Sol
- `coordination/inbox_claude/` — messages FROM Sol TO Claude
- `coordination/STATUS_BOARD.md` — single source of truth: who owes what, current wave state
- Message files: `msg-NNN_<slug>.md`, NNN strictly increasing per inbox, never reused, never edited
  after the fact (append a new message instead). Start each message with a header block:
  `from / to / date / re / requires_ack (y/n)`.
- Ack = a one-line entry in YOUR OWN next outgoing message ("ack msg-003") or an `ACK: msg-NNN`
  line added to STATUS_BOARD under your column. Read messages are never deleted — they are the log.

## Ownership boundaries (unchanged, now codified)
Claude-owned (Sol reads, never writes): `labels/readerA/`, `labels/consensus/`, `coordination/inbox_sol/`
Sol-owned (Claude reads, never writes): `labels/readerB/`, `src/`, `tests/`, `gold/`, `schemas/`,
  `prompts/`, `tools/`, `docs/`, `coordination/inbox_claude/`
Shared read-only for both: `SPEC.md` amendments go through a message first, then whoever owns the edit applies it.
STATUS_BOARD: each side edits ONLY its own column/rows.

## Blindness rule (overrides everything above)
During any blind wave: the reader with a pending pass must not open the other reader's labels for
those acts, nor any consensus file covering them. Inbox messages about an in-flight blind wave must
contain NO field readings — logistics only ("acts X–Y assigned, artifact path, freeze deadline").
Consensus files may only be read by a reader after its own labels for those acts are committed.

## Wave lifecycle (the standing loop)
1. Claude posts wave assignment → `inbox_sol/` (act list, artifact, prompt version to use).
2. Both readers label blind, commit to freeze (commit = frozen, no exceptions).
3. Claude merges → `labels/consensus/<wave>_CONSENSUS.md`, routes disputes to a fresh Reader C.
4. Claude appends RESOLVED appendix, posts outcome summary + eval-table numbers → `inbox_sol/`.
5. Sol ingests resolved fields into gold/eval, posts gate reports & build questions → `inbox_claude/`.
6. Identity-level forks go to the human gold sample regardless of the 2-of-3 vote.

## Escalation to the human
Only for: SPEC changes, anything touching compliance/privacy posture, spending money, contacting
anyone, or a dispute between the two agents about ownership/protocol. Tag the message `ESCALATE`
and also surface it in STATUS_BOARD's top line so Jake sees it without digging.
