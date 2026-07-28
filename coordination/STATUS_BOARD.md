# STATUS BOARD — single source of truth
⚠ ESCALATIONS (Jake action needed):
1. ~~Runtime blocked~~ RESOLVED 28 Jul: was Smart App Control; owner disabled it. llama-cli
   b10167 verified (exit 0), exe sha256 5719892E… posted in inbox_sol/msg-004. Model .gguf
   still absent — Sol to specify exact files+hashes, owner fetches.
2. Human gold-sample check pending: act 6 (quarantined) + sampled acts from waves 001–002 —
   promotes silver→gold. Claude will prepare the crop package.
Last updated: 28 Jul 2026 (Claude). Each side edits only its own section + its ACK lines.

## Wave state
| Wave | Acts | Reader A | Reader B | Consensus | Reader C | Resolved |
|---|---|---|---|---|---|---|
| 001 | Serock 1890 deaths 1–2 | frozen | frozen (0d9f3bc) | merged | done | ✅ 9/9, appendix in wave-001 doc |
| 002 | Serock 1890 deaths 3–6 | frozen | frozen (4839ac2) | merged (14 disputes) | done | ✅ appendix in wave-002 doc; A 12 / B 1.5; act 6 → human sample |
| 003 | not yet assigned | — | — | — | — | — |

## Claude (coordinator / Reader A) — owes
- [x] Wave-002 RESOLVED appendix (done 28 Jul)
- [x] Post wave-002 outcome + eval numbers → inbox_sol (msg-002)
- [ ] Assign wave 003 after v1.2 freezes (candidate: Serock 1890 births, or first Pułtusk acts once atlas lands)
- [ ] Human gold-sample package for act 6 (crops + both readings + C report) for Jake
- ACK: msg-001_ack-and-p2-boundaries.md (reply: inbox_sol/msg-003_silver-tier-and-v12.md)

## Tier definitions (binding, per msg-003)
- gold = human-verified, eval-only, clerk-year-sequestered
- silver = 2-of-3 machine consensus, training-eligible, never eval
- waves 001 + 002 acts 1–5 → silver; act 6 quarantined pending human check
- Prompt v1.1.0 canonical sha256: 9e679f3a… (frozen 156393b); v1.2 to follow with new traps before wave 003

## Sol (builder / Reader B) — owes
- [x] READ inbox msg-001 and msg-002; ack both
- [x] Prompt v1.1 release (patch text in labels/consensus/FOR_SOL_wave002_brief.md §3) + rehash
- [x] P2 gate report with eval table (inbox_claude/msg-002_p2-gate.md)
- [x] PROVENANCE_ERRATA note at ingest for Reader A wave-001/002 stale prompt hash
- [x] Assign resolved acts 1–5 to machine-readable SILVER (training-only, never eval,
  source-addressed fields); act 6 untiered and QUARANTINED pending human check
- [ ] skills/prompt additions proposed for v1.2: line-break surname-split trap;
  умеръ/умерла check first; scribe's -фельдъ written as в
- ACK: msg-001, msg-002 (reply: inbox_claude/msg-001_ack-and-p2-boundaries.md)
- ACK: msg-003 (reply: inbox_claude/msg-002_p2-gate.md)

## Standing facts
- Prompt v1.0.0 canonical sha256: 88e56abd… (drift resolved — Reader A's recorded hash was stale)
- Reader B dual-date bias: did NOT recur in wave 002 (clean under v1.0.0)
- Act 6 (wave 002) = identity fork → human gold sample regardless of Reader C verdict
- Runtime execution is Windows-side only; Sol's sandbox is Linux — Sol does not run/bypass it
