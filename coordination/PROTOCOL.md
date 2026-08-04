# COORDINATION PROTOCOL — coordinator/Reader A + per-wave blind Reader B instances
v1.1 — 4 Aug 2026 (v1.0 28 Jul 2026). Amended per msg-044 (Sol retired) and msg-046
(owner-authorized governance change): the coordinator absorbs the build side; Reader B is a
fresh blind agent instance per wave. The human (Jake) remains the trigger, not the channel.

## Directory layout
- `coordination/inbox_sol/`    — messages FROM Claude TO Sol
- `coordination/inbox_claude/` — messages FROM Sol TO Claude
- `coordination/STATUS_BOARD.md` — single source of truth: who owes what, current wave state
- Message files: `msg-NNN_<slug>.md`, NNN strictly increasing per inbox, never reused, never edited
  after the fact (append a new message instead). Start each message with a header block:
  `from / to / date / re / requires_ack (y/n)`.
- Ack = a one-line entry in YOUR OWN next outgoing message ("ack msg-003") or an `ACK: msg-NNN`
  line added to STATUS_BOARD under your column. Read messages are never deleted — they are the log.

## Ownership boundaries (amended v1.1, effective msg-044)
Coordinator-owned: `labels/readerA/`, `labels/consensus/`, `coordination/inbox_sol/`, and —
  transferred from Sol per msg-046 — `src/`, `tests/`, `gold/`, `schemas/`, `prompts/`, `tools/`,
  `docs/`.
`labels/readerB/`: written only from the verbatim output of a fresh Reader B instance (see
  Reader B section below). The coordinator ingests and freezes these files but must never alter,
  supplement, or reinterpret a reading — ingest is copy-and-commit, nothing else.
`coordination/inbox_claude/`: closed to new senders (historical log; Sol's messages preserved).
`SPEC.md`: amendments are recorded in a coordination message first, then applied.
STATUS_BOARD: coordinator edits; Sol's frozen section is history and is never edited.

## Reader B (v1.1 — fresh blind instances)
Each wave's Reader B pass is executed by a FRESH agent instance with no session contamination:
- It receives ONLY: the frozen wave brief (b416c70 format), the scan crops for its acts, and the
  pinned prompt/schema v1.4 (prompt sha256 5d14dcb8…, label schema
  `schemas/reader-label-1.0.0-v1.4.schema.json`). Nothing else.
- It must NEVER see: Reader A outputs, prior-wave labels or consensus files, coordination traffic,
  STATUS_BOARD, or any conversation history from the coordinator's session.
- Its identity is recorded per wave in the freeze commit and the wave row, as
  `readerB-w<NNN>-<YYYYMMDD>` (e.g. `readerB-w006-20260805`).
- The same blind-pass discipline applies unchanged: labels committed to freeze (commit = frozen,
  no exceptions), scan-only audits before freeze, no consensus reads until its own labels for
  those acts are committed.
Reader C / arbiter rules are unchanged from v1.0.

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
