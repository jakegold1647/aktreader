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
| 003 | Serock 1890 deaths 30–40 (v1.2 both readers) | frozen (02725c6) | frozen (d679320) | merged (24 disputes + 4 verification acts) | done (arbiter + verifier) | ✅ appendix in wave-003 doc; A 23 / B 0.5; acts 34+39 → human sample (act-40 surname deadlocked 2–2, rides along); ERRATA: item 20 withdrawn → expert review |
| 004 | Serock 1890 deaths 41–49 + SkZ index closure (v1.3.0 = 97dfa6a7… both readers; assigned msg-017) | frozen (0eddf76) | frozen (msg-014 hashes) | merged (24 items: 2 identity forks, acts 45+46) | pending | closure audit DRAFTED (SEROCK_1890_DEATHS_CLOSURE_AUDIT.md); index A-vs-B agreement 13/49; index predates red rectifications |
| 005 | CANDIDATE: Serock 1890 deaths 7–29 (23 acts; closes the book) | — | — | — | — | pending assignment; 5 scan files to fetch |

## Claude (coordinator / Reader A) — owes
- [x] Wave-002 RESOLVED appendix (done 28 Jul)
- [x] Post wave-002 outcome + eval numbers → inbox_sol (msg-002)
- [x] P2 gate review → **ACCEPTED** (msg-005); baseline attaches later as addendum
- [x] Wave 003 assigned (msg-006): Serock 1890 deaths 30–40, v1.2 both readers
- [x] Wave-003 scans acquired + ARTIFACTS.txt delivered (msg-007); both readers unblocked
- [x] Reader A blind pass, acts 30–40, prompt v1.2 — FROZEN at 02725c6 (11 labels)
- [ ] Human gold-sample package: **acts 6, 34, 39 pending Jake** (crops + both readings + C reports; act 40 rides along for its surname deadlock)
- [x] Model fetched+verified by owner; reader-inspect READY (fingerprint 04adc59f…)
- [!] Baseline BLOCKED (supersedes parser issue): b10167 grammar engine crashes on Qwen3.5 template (sampler init, <|im_start|>); probe matrix in msg-010/011. Parser itself now correct (attempts 1–3 fixed it). AWAITING: Sol pins a newer llama.cpp release (tag+URL+sha256) → owner fetch → grammar probe → rerun with --max-retries 3. Checkpoint rows at retry_count=2, untouched.
- ACK: msg-001_ack-and-p2-boundaries.md (reply: inbox_sol/msg-003_silver-tier-and-v12.md)
- ACK: msg-002_p2-gate.md (reply: inbox_sol/msg-005_p2-accepted.md)

## Tier definitions (binding, per msg-003)
- gold = human-verified, eval-only, clerk-year-sequestered
- silver = 2-of-3 machine consensus, training-eligible, never eval
- waves 001 + 002 acts 1–5 → silver; act 6 quarantined pending human check
- Prompt v1.1.0 canonical sha256: 9e679f3a… (frozen 156393b); v1.2 to follow with new traps before wave 003

## Sol (builder / Reader B) — owes
- [ ] **WORK QUEUE msg-012 (9 items, priority-ordered)** — build-pin first, then forensics,
  fence tolerance, P2 addendum findings, silver materialization (coordinator confirmed),
  coverage want-list, LoRA gate prep, release polish, wave-004 tooling
- [x] READ inbox msg-001 and msg-002; ack both
- [x] Prompt v1.1 release (patch text in labels/consensus/FOR_SOL_wave002_brief.md §3) + rehash
- [x] P2 gate report with eval table (inbox_claude/msg-002_p2-gate.md)
- [x] PROVENANCE_ERRATA note at ingest for Reader A wave-001/002 stale prompt hash
- [x] Assign resolved acts 1–5 to machine-readable SILVER (training-only, never eval,
  source-addressed fields); act 6 untiered and QUARANTINED pending human check
- [x] Prompt v1.2 frozen at b11bca0, sha256 ea0e8375…: line-break surname-split trap;
  умеръ/умерла check first; generalized clerk-specific -фельдъ/-вельдъ check
- [x] Exact 16 GB model/projector lock + 17-job scan-backed baseline manifest posted
  (inbox_claude/msg-003); owner fetch pending
- [x] Baseline stdout parser revised fail-closed at 8852122: anchor after final physical `> `
  line; shared checkpoint is FAILED/1 × 17, so original `--max-retries 2` grants one attempt
- [x] Wave 003 Reader B pass: 11 prompt-v1.2 labels frozen at d679320 after scan-only audits;
  no Reader A label or consensus content opened before the freeze commit
- ACK: msg-001, msg-002 (reply: inbox_claude/msg-001_ack-and-p2-boundaries.md)
- ACK: msg-003 (reply: inbox_claude/msg-002_p2-gate.md)
- ACK: msg-005 (reply: inbox_claude/msg-003_p2-baseline-lock-and-v12.md)
- ACK: msg-006 (reply: inbox_claude/msg-004_ack-wave003-pending.md)
- ACK: msg-008 (reply: inbox_claude/msg-005_baseline-parser-fixed.md)
- ACK: msg-009 (reply: inbox_claude/msg-006_wave003-readerb-frozen-and-parser-v2.md)

## Standing facts
- Prompt v1.0.0 canonical sha256: 88e56abd… (drift resolved — Reader A's recorded hash was stale)
- Reader B dual-date bias: did NOT recur in wave 002 (clean under v1.0.0)
- Act 6 (wave 002) = identity fork → human gold sample regardless of Reader C verdict
- Runtime execution is Windows-side only; Sol's sandbox is Linux — Sol does not run/bypass it
