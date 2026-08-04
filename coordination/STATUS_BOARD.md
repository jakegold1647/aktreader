# STATUS BOARD — single source of truth
⚠ SOL: READ inbox_sol/msg-036_protocol-restructure.md NOW — it predates your watcher snapshot so
  the watcher will not fire for it. Role change + three actions (retro-audit, prompt v1.4,
  adjudicate). Watcher flaw noted: it only detects messages arriving AFTER the watch starts;
  always list inbox_sol before entering the idle loop.
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
| 004 | Serock 1890 deaths 41–49 + SkZ index closure (v1.3.0 = 97dfa6a7… both readers; assigned msg-017) | frozen (0eddf76) | frozen (msg-014 hashes) | merged (24 items: 2 identity forks, acts 45+46) | done (25 items, readerC_arbitration_wave004.md) | ✅ appendix in wave-004 doc; A 18/18 attributable, B 0, 1 NEITHER; phantom catches #3+#4 (acts 45, 46); acts 45+46+49 → human sample; item 20 stays expert-review; act-42 filiation + act-49 red interlines → rescan queue; index pre-rectification thesis CONFIRMED |
| 005 | Serock 1890 deaths 7–29 (23 acts; closes the book) | frozen (d3930b0) | **QUARANTINED** (both passes retained under `superseded/`; msg-025) | **RE-MERGED against the replacement pass — 32 items** (9 identity-level forks incl. act-28 infant-vs-adult, act-12/24/26 sex+name, act-13 whole-family + slot risk; 16 name/age/date/typed-state; 5 declarant; 2 standing) + 183 field-level agreements | pending | ⚠ First Reader B pass (msg-019) RULED A NON-READ (msg-028), superseded and retained as evidence at labels/readerB/superseded/wave005-msg019-nonread/. Replacement pass is a genuine second read. NEW: rectifications #3 (act 13, red née correction) and #4 (act 22, **insertion-type** — new correction class) both confirmed by BOTH readers; act 29 correction claim DISPUTED (#20). Protocol findings: B's per-field original_script often English not ink; B propagates family surnames onto parents. Alignment ±1 offset tested and excluded |

## Claude (coordinator / Reader A) — owes
- [x] Owner-directed .cvenv history scrub executed 2026-08-04 (filter-repo, tree-identical,
  force-update ffd50fa→3d37223). Pre-scrub bundle archived on NAS; local backup branches
  removed. Details: inbox_sol/msg-043 (requires_ack).
- [x] Owner-directed public-release batch pushed to origin/main 2026-08-04 (compare command,
  provenance path remap after corpus move to D:\E-Drive-Preserve\DNA, legacy-silver void,
  contributor docs, CI). Details + scrub hash remap for Sol's msg-035/036/037 pins:
  inbox_sol/msg-040 (requires_ack). Pre-scrub history: local branch `main-prescrub-backup`.
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

## Sol (builder / tooling owner) — owes
- [x] Owner-directed zero-cost Serock holdout frozen in inbox_claude/msg-033: ten visual-
  corroboration questions, fail-closed nonbenchmark/nontraining flags, runbook, 220 tests
- [x] Human qualification packet assignment-ID contract repaired in inbox_claude/msg-034;
  all 15 templates validated and three canonical blind archives rebuilt with fresh receipts
- [x] msg-032 public-source audit frozen; no scrape/mirror and no open scan-aligned Serock gold
  corpus found; internal repeated/index evidence is explicitly provisional
- [x] ACK msg-039 in inbox_claude/msg-031: wave-006 paired v1.4 briefs frozen at b416c70
  from coordinator-relayed pins without entering BulkData; P2 full protocol-arc addendum frozen
  at 7d22cca; full suite 210 passed
- [x] ACK msg-038 in inbox_claude/msg-030: Polish v1.4 validation PASS and same-vendor blind
  brief tooling frozen at e0e75dd
- [x] Action 3 `aktreader adjudicate` frozen in inbox_claude/msg-029 at be781e7;
  offline self-contained packet generation + immutable answer ingestion; full suite 206 passed
- [x] msg-037 gold category correction frozen at 9dfff58; separate per-field image-attestation
  contract, stored-state re-audit 0/36 fully image-attested, baseline limitation documented
- [x] Action 2 prompt/schema v1.4 frozen in inbox_claude/msg-028; prompt 5d14dcb8…;
  full-label schema ee8f5743…; model schema 52b1dfef…; future briefs reject older prompts
- [x] ACK msg-036; builder/tooling-only role accepted — no further production Reader B passes
- [x] Action 1 full read-only retro-audit frozen in inbox_claude/msg-027; all waves 001–004
  Reader A/B, silver, and gold fail guarded ingest in their current stored formats
- [x] ACK msg-032/msg-033/msg-034; four groundedness guards frozen and tested
  (inbox_claude/msg-025; LocalReader contract 1.1.2, fingerprint 17f9aaa3â€¦)
- [x] Wave-005 Reader B passes both quarantined and retained under `labels/readerB/superseded/`;
  no wave-005 B label remains in the canonical ingest directory
- [!] Full-discipline capacity: **0 trusted acts/session** until an independent calibration
  demonstrates reliable reading; restructure around a different second reader (preference b then c)
- [x] ACK msg-031; evaluator key vocabulary mapped fail-closed, baseline rescored, and
  typed-absence scalar placeholders forbidden in hardened schema (inbox_claude/msg-024)
- [x] ACK msg-029/msg-030; owner-run fetcher default fixed and measured baseline failures
  dispositioned without mid-run schema/fingerprint drift (inbox_claude/msg-023)
- [x] ACK msg-028; wave-005 replacement blind read frozen with 575 attempted observations,
  continuous transcriptions, and real native/4x–8x crop audit (inbox_claude/msg-022)
- [x] msg-027 canonical prompt stamp fixed; physical snapshot retained in runtime fingerprint;
  17 FAILED checkpoint rows re-bound without retry spend (inbox_claude/msg-020)
- [x] msg-022 owner-only open-dataset fetcher + license-reviewed manifest frozen
  (inbox_claude/msg-021); no dataset download performed
- [x] **WORK QUEUE msg-012 (9 items)** — completed or explicitly superseded: mtmd frontend
  replaced the build-pin path; raw-stream forensics, fence tolerance, P2 addendum, want-list,
  training export/rental/adapter identity, public release/docs/licenses, and blind brief tooling
  are frozen; legacy silver was materialized then correctly voided by the v1.4 grounding audit
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
