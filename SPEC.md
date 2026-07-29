# AKTREADER — build spec for an autonomous coding agent
*A register-reading machine: scan in → graded genealogical evidence out.*
Spec written 28 Jul 2026 by Jake Goldstein's research session. Build target: a solo AI coding
agent (any capable model) working phase by phase. Jake reviews at each phase gate.

## ⚑ HANDOFF NOTE — read this first (you are a different model with zero prior context)
- **You are being handed this cold.** Everything you need is in this file plus the on-disk paths
  it cites. Do not assume access to any prior conversation; where this spec says "the project,"
  it means the genealogy research tree rooted at `E:\DNA\` on Jake's Windows 11 machine.
- **Your workspace is `E:\DNA\Project_RegisterReader\` ONLY.** You may READ anywhere under
  `E:\DNA\` (the gold-corpus source files in §2/P1, the scans in `Decode_Package\`), but you
  WRITE only inside `Project_RegisterReader\`. Never modify, reorganize, or "clean up" anything
  outside it — the rest of the tree is an active research operation with its own rules.
- **Environment:** Windows 11, PowerShell + Git Bash available, Python via `uv` preferred. Make
  this folder a standalone git repo (`git init` here; a parent repo may exist — do not touch it).
- **Hard rules inherited from the research operation (non-negotiable):** no web scraping of any
  archive; no use of USHMM/Arolsen/Yad Vashem content in any training or bulk capacity; no
  contacting any person or institution; no logins/consents on Jake's behalf; the sites
  gedmatch.com, ancestry.com, myheritage.com, 23andme.com are off-limits entirely. Web access is
  otherwise fine for docs/packages and the §1 landscape re-check.
- **Source-of-truth discipline:** when building the gold corpus (P1), transcribe ONLY what the
  cited project files actually state — never invent or "complete" a field. Uncertainty is a
  first-class value in this project: `[unclear: X/Y]` beats a guess, always.
- **Phase gates:** stop at the end of each phase (§5) and wait for Jake's review before
  continuing. Deliver each gate as: what was built, what was skipped and why, exact commands to
  run it.
- A partial scaffold may exist from an aborted earlier start — inspect what's there, keep what
  conforms to this spec, replace what doesn't, and say which you did.

## 0. One-paragraph mission
Take a scanned 19th–early-20th-century civil register act from partitioned Poland (Russian
Cyrillic 1868–1915, Polish before/after) and produce a **structured, uncertainty-honest
extraction**: act type/number/year, principal, dates, **filiation (parents, incl. mother's maiden
name), spouses, witnesses (with ages), officiant, addresses/towns** — every field carrying a
confidence grade, every unresolvable glyph marked `[unclear: X/Y]` rather than guessed. First to
assist THIS project's search; then published open-source for every descendant staring at a scan
they cannot read.

## 1. Why this doesn't already exist (verified 28 Jul 2026 — re-verify at build start)
- **Transkribus** (READ-COOP): the strong incumbent for raw HTR — 300+ models incl. a Russian
  civil-records model (L'Dor V'Dor, CER 7.3%) and field/table extraction. But: credit-metered,
  closed platform, generic fields, **no act-format priors, no evidence grading, no uncertainty
  discipline** — it picks a reading. https://www.transkribus.org/
- **Metryki.com**: commercial AI transcription for Polish/Latin/German/Russian records. Same
  gaps; not open.
- **LDVDF DoJR AI Lab / "PastPort"** (announced for early 2026): Jewish-records AI, incl. Russian
  Empire vital records training. Closest philosophically — **watch it; if it ships open with
  graded filiation extraction, pivot AKTREADER to be its evidence layer instead of a rival.**
- Nothing found that is simultaneously: (a) open-source, (b) Napoleonic-act-structure-aware,
  (c) genealogically structured (filiation-first), (d) uncertainty-calibrated with an explicit
  [unclear] convention, (e) shipped with a verified gold corpus.
**Positioning: do NOT compete on raw handwriting recognition. Consume the best available reader
(a vision LLM and/or Transkribus export) and win on the layers above it: structure, grading,
honesty, evaluation.**

## 2. The unfair advantage — the gold corpus already on disk
`E:\DNA\Decode_Package\01_Cyrillic_Serock\` holds hundreds of Serock register scans, and the
project holds **human+AI-verified readings** for dozens of acts (`Serock_Acts_Read.md`,
`Majer_Thirteen_Children.md`, `PoT_Fields_Transcribed.md`): act numbers, dates, filiations,
witnesses with advancing ages, the works — including famously tricky cases (the double-registered
death 25/1902 vs 6/1903; the skorowidze year-indexes; Goldfarb-vs-Goldsztejn trap entries).
**Phase 1 deliverable is turning these into `gold/` — a JSON eval set.** No competitor ships with
a verified eval corpus; we start with one. (Scans are of 1874–1915 public civil records held by
Polish state archives; personal-use extraction is unproblematic — see §7.)

## 3. Architecture (proposed; agent may improve with justification)
```
scan.jpg → [1 Preprocess] → [2 Read] → [3 Structure] → [4 Grade] → act.json (+ act.md render)
```
1. **Preprocess** — deskew, crop act region (acts are numbered blocks on multi-act pages), enhance.
   Classic CV (OpenCV); no ML training needed.
2. **Read** — vision-LLM transcription of the act text (Cyrillic or Polish), prompted with the
   act-format prior (§4). Design as a pluggable interface: `Reader` implementations for
   (a) frontier vision LLM via API, (b) local VLM, (c) imported Transkribus text. Multi-pass:
   two independent reads; disagreements become [unclear] candidates automatically.
3. **Structure** — map the read onto the **act schema** (§4) — the Napoleonic formula makes this
   tractable: fixed rhetorical slots ("Действие происходило... явился... в присутствии
   свидетелей... объявил...").
4. **Grade** — per-field confidence: CONFIDENT / PROBABLE / [unclear: X/Y] / ABSENT-ON-FORM vs
   BLANK vs ILLEGIBLE (three different facts — never collapse them; this distinction is the
   project's hardest-won lesson). Cross-checks that upgrade/downgrade: date arithmetic (ages vs
   years), witness-age continuity across acts, name consistency within the same register year.
5. **Outputs** — `act.json` (schema §4), `act.md` (human-readable, original-order transcription +
   translation + extraction table), and a per-batch `register.csv` for grepping.

## 4. The act schema (core IP — encode the Napoleonic formula)
Fields (all with `value`, `original_script`, `confidence`, `source_span`):
`act_type` (birth/marriage/death/annex) · `act_no` · `year` · `registration_date` ·
`event_date` · `town` · `principal{name, age, occupation, residence}` ·
`father{name, age, occupation, residence}` · `mother{name, MAIDEN_NAME, age}` ·
`spouse{...}` + `spouse_parents{...}` (marriages) · `declarants/witnesses[]{name, age,
occupation}` · `officiant` · `signatures_note` · `marginalia` (late annotations — often the only
divorce/correction evidence) · `deceased_left_behind` (deaths: surviving spouse/children).
**Marriage acts additionally:** banns dates, permission notes, rabbi. **The mother's maiden name
and the witness ages are first-class citizens** — they are what genealogists actually need and
what every existing index drops.

## 5. Phases & gates
- **P0 — Landscape re-check + repo scaffold.** Re-verify §1 (PastPort esp.). Python, uv, tests.
- **P1 — Gold corpus.** Parse the project's verified readings into `gold/*.json` (target ≥30
  acts across birth/marriage/death, both languages). GATE: Jake spot-checks 5.
- **P2 — MVP pipeline** on frontier-VLM Reader. Metric: **filiation exact-match ≥90% on gold,
  AND calibrated uncertainty — over-claiming (wrong-but-CONFIDENT) < 2%.** A wrong confident
  read is worse than ten honest [unclear]s. GATE: run on 10 never-read Decode_Package acts;
  Jake compares against the scans.
- **P3 — Assist-the-search mode.** Batch-run the entire unread remainder of Decode_Package
  (incl. skorowidze index pages — cheap year-negatives); outputs feed the project's CSVs.
  This is where it pays rent immediately: **Bajla 1886/37, Jankel 1886/36, Chuna 1893/17 arrive
  from AP Grodzisk soon — the machine reads them the day they arrive.**
- **P4 — Variant bridge module** (separately shippable): expansion library for
  surname/town manglings — D-M soundex + transliteration + documented OCR manglings
  (SEROK/SEROCK, POUFTOUSK→Pułtusk, RULTUSK, PULSTUK, IAZHOMBEK→Jarząbek, KANALEK/KANAREK,
  "Serock u/Narwią", Sierck-les-Bains false-positive). Seed from this project's logged cases.
- **P5 — Publish.** Open-source (AGPL or MIT — Jake decides), docs, HF space or simple web UI
  for single-act upload, README telling the origin story honestly. Outreach AFTER release, by
  Jake personally: **Yad Vashem first (§9.3 — the thank-you, with the Serock pilot as the worked
  example)**, then JRI-Poland, PTG, LDVDF/DoJR (their terms require citing JRI-Poland where
  their data is used; the tool itself uses none of it).

## 6. Non-goals (scope fences)
No scraping or mirroring of any archive; no use of USHMM/Arolsen/Yad Vashem content as training
data (terms forbid; also unnecessary — registers are the domain); no automated submission to any
institution; no genealogy-tree inference or kinship claims (the tool extracts what the paper
says, full stop — the never-overclaim rule is architecture, not etiquette); no OCR-model
training in v1 (prompted VLMs + existing models suffice; fine-tuning is a v2 question).

## 7. Rights & ethics
Scans: user-supplied. Polish state-archive scans of pre-1915 civil records are reproductions of
public records; personal research use is standard practice — the tool processes locally/user-side
and stores nothing. Privacy guard: refuse-by-default on acts later than 100 years (configurable),
matching Polish vital-records privacy convention (100y births / 80y marriages+deaths). Living
persons never inferred. Every output embeds "extraction is not authority — verify against the
scan" plus the artifact path, inheriting the project's evaluate-from-the-artifact rule.

## 8. Success, stated plainly
A descendant with no Russian and no Polish drops in the scan of the act that names their
great-grandmother — and gets back her parents' names, honestly graded, with the one smudged
word marked [unclear] instead of invented. First user: Jake. Second: Hélène's book. Then anyone.

## 9. NEXT-GEN HORIZON (v2, after the P5 gate) — the questions no tool has ever answered
These are not features; they are research capabilities that current tools structurally lack.
Design v1's data model so these become possible (acts as nodes with provenance, not rows in a CSV).

### 9.1 Corpus-level reading — solve the register, not the page
Every existing tool reads one page at a time. A civil register is a *closed system*: one clerk's
hand for a whole year, the same families recurring, witness ages advancing act by act, the same
officiant, annual skorowidze indexes that cross-check every entry. Treat a year of acts as a
**joint constraint-satisfaction problem**: a glyph unreadable in act 14 is often the same
pen-stroke, resolved, in act 31. Concretely: (a) build per-scribe glyph priors from
high-confidence reads and re-apply them to [unclear] spans ("scribe adaptation"); (b) propagate
arithmetic constraints (ages/dates/act sequence) as soft evidence; (c) emit corpus-level
confidence — a name attested 9 times in one register year is a different epistemic object than a
hapax. **The measured goal: cut [unclear] rates roughly in half versus per-page reading, with
zero increase in wrong-but-confident reads.** Nobody has shipped this for genealogical registers.

### 9.2 Town-graph reconstruction — give a murdered community its structure back
Feed every extracted act of one town into a **probabilistic population graph**: person nodes,
filiation/marriage/witness edges, each edge carrying its acts as evidence with grades. Questions
this answers that have literally never been answerable at scale: Who witnessed whose life events
(the social fabric, not just the bloodlines)? Which children appear in birth acts but never again
(the undocumented dead)? Which families intermarried across which years? For a town like Serock —
community annihilated December 1939, registers 1874–1904 surviving — this is **reconstruction of
a destroyed world from its own paperwork.** Output: an explorable graph + per-person evidence
dossiers. Entity resolution is probabilistic and NEVER auto-merges: it proposes, with evidence,
and a human confirms (the never-overclaim rule at graph scale).

### 9.3 The Yad Vashem gift — names for the Hall of Names
**The end-state this project exists for: a thank-you to Yad Vashem, delivered as a GitHub link.**
The Hall of Names holds millions of Pages of Testimony, many filed from memory with fields blank
— submitters wrote "First name unknown" for sons, guessed years ("1904 aprox."), left parents
empty. The registers hold exactly those missing fields. v2 produces, from the user's own
extracted corpus: (a) **candidate matches** between register persons and memorial-record shapes
(name variants + dates + town + filiation), graded, human-reviewed, never auto-submitted;
(b) **the gap list** — register-documented people with no known memorial record at all, i.e.
candidates for NEW Pages of Testimony, packaged with their act-level evidence so a descendant or
researcher can file a Page that is document-backed from birth. The pilot exists in this project
already: Shaie Goldsztajn of Serock has no Page; three "First name unknown" sons died in the
Warsaw ghetto and their names are recoverable from acts.
**Boundary, absolute:** the tool never bulk-ingests, scrapes, or trains on Yad Vashem (or USHMM/
Arolsen) data. Matching runs against the USER's own extractions plus manually-entered memorial
record details, one lookup at a time, by a human. The deeper move: because the repo is open,
**Yad Vashem can run it on their own side, against their own data, at full scale** — that is the
form the thank-you takes. When P5 ships, Jake personally sends the repo to Yad Vashem's Hall of
Names / Shoah Names Recovery Project with the Serock pilot as the worked example.

### 9.4 Learned name-bridge — retire soundex
D-M Soundex misses what this project hit weekly (IAZHOMBEK↔Jarząbek, POUFTOUSK↔Pułtusk,
KANALEK/KANAREK). Train a small **cross-script name-matching embedding** (Cyrillic/Polish/
Yiddish-transliteration/OCR-mangled forms of the same names), using pairs harvested from the
project's own logged manglings + public name-variant lists. Ship as the P4 module's v2 backend —
a drop-in "same name?" scorer with calibrated thresholds. Trainable on a laptop; no archive data.

### 9.5 SerockBench — make honesty measurable for everyone
Publish the gold corpus (public-domain acts, ≥100 years old) as the **first open benchmark for
Napoleonic-act genealogical extraction**: filiation exact-match, uncertainty calibration
(wrong-but-confident rate as a headline metric), and the blank/unknown/absent three-way
distinction as scored fields. If PastPort or Transkribus beat AKTREADER on it, the field still
wins — that's the point of a benchmark, and it makes the "honest extraction" standard the thing
tools compete on.

## 10. PILOT DECISION (28 Jul 2026, Jake) — PUŁTUSK FIRST
**The first full use of AKTREADER is mapping the Jewish community of PUŁTUSK — and that map is
the gift.** Rationale:
- **The corpus exists.** AP Warszawa Oddział Pułtusk, fond 84 (Pułtusk Mokranowski/civil
  registers): **1875–1935, ~12,300 scans, digitized and publicly viewable** via the PTG's
  skanoteka/metryki front-ends. Serock (fond 73/826/0) has ZERO scans anywhere — its three
  missing acts come by mail and get read individually. Pułtusk is the one town in this family's
  story whose entire register corpus is actually readable end to end.
- **It answers this project's own open question as a side effect**: four Goldsztejn households,
  none headed by an Aron, was the finding from index-level work — a full corpus map settles the
  Goldsztejn/Glotzer picture of the district at act level.
- **The gift (§9.3) becomes concrete**: the Pułtusk town graph + the Pułtusk Pages-of-Testimony
  gap list, offered to Yad Vashem with the repo. A district capital's Jewish community,
  reconstructed from its own registers, 1875–1935.
**Corpus acquisition rules (gate before P3 batch work):** scans are fetched the way a researcher
browses — through the front-end, politely paced, session-respectful, stopping at any CAPTCHA,
login wall, or terms gate (log it and consult Jake). No parallel hammering, no mirror of the
site — a working corpus of the fond's images for personal research, acquired at human-polite
pace over days, or read in place where download is not offered. If PTG/archive terms are found
to forbid systematic saving, STOP and surface the finding — Jake decides (options include asking
PTG for a research copy, which only Jake may do).
**Gold corpus stays Serock-seeded** (P1 unchanged — the verified readings are Serock acts);
Pułtusk becomes the P3 batch target and the §9.2 graph's first town.
**Publication framing:** clean, resume-grade open-source repo under Jake's GitHub — docs, tests,
benchmark, honest README. The repo IS the portfolio piece; the Yad Vashem letter is its cover.

## 11. THE END GOAL, STATED PLAINLY (28 Jul 2026, Jake) — succession, not assistance
**AKTREADER's terminal purpose: let the last generation of human readers pass on without the
skill dying with them.** Not a helper for experts — their successor. The paleography of
pre-1918 chancery Cyrillic and old-Polish acts is no longer taught and will not be re-taught;
the goal is to capture it into data and models until the machine reads at, then above, expert
level — permanently, for everyone, free.

This is achievable here precisely because the domain is bounded: a closed corpus (the registers
are finite and fully scanned or scannable), a fixed formula, verifiable answers (cross-act
constraints + surviving experts), and an objective metric (SerockBench). "Better than the last
humans" is a measurable milestone in this domain, not marketing.

**Design consequence — the correction flywheel (build into v1, not bolted on later):**
1. Every human correction of a machine reading is captured (with the corrector's consent) as a
   labeled example: scan crop + machine reading + corrected reading + who corrected it.
2. Corrections from verified expert readers are gold-tier; they extend the eval set AND the
   fine-tuning pool. **The experts' remaining years are the harvest window — every act an
   80-year-old reader verifies is a permanent addition to the successor's knowledge.**
3. Periodic retraining/re-prompting cycles consume the flywheel; SerockBench tracks the curve.
   The public success criterion: the wrong-but-confident rate crossing below the measured
   human-expert disagreement rate on held-out acts — the point where the machine is
   demonstrably the more reliable reader.
4. Tacit knowledge (naming customs, local conventions, clerk quirks) is captured as skill
   documents (see skills/) written WITH surviving experts where possible — the things they
   know but no book states.
**Reframe of the mitzvah:** the tool doesn't replace the readers — it lets them finish. Their
corrections become the permanent inheritance. When the last of them stops, nothing stops.

## 12. INDEPENDENCE ROADMAP (28 Jul 2026, Jake) — the Reader must not need APIs forever
**End-state requirement: AKTREADER runs fully local — open-weights model, no API key, no
vendor dependency.** A preservation tool with an API in its critical path is not preserved.
Frontier APIs are scaffolding, used in exactly two bootstrap roles and then demoted:
1. **P2–P3 bootstrap:** frontier VLMs establish the accuracy ceiling on SerockBench and
   produce the first large verified batch (Pułtusk) — which, human-checked, becomes the
   fine-tuning dataset. The consent/training-eligibility plumbing already in the gold schema
   is what makes this dataset clean.
2. **Ongoing benchmark reference:** APIs stay on the leaderboard as comparison points only.
**The local path (v2):**
- Base: a strong open-weights VLM (Qwen-VL-class or better at build time) sized to run on a
  single 16–24 GB consumer GPU quantized.
- **LoRA fine-tune on a rented GPU** (RunPod/Lambda-class; LoRA on an 8–30B VLM is hours,
  tens-of-dollars, not thousands) using: the gold corpus + the human-verified Pułtusk batch +
  the correction flywheel (§11). Re-run as the flywheel grows.
- Success criterion: the LoRA'd local model matches or beats the best API model on
  SerockBench's calibration metrics. From that day the local model is the default Reader,
  the site needs no keys, and the tool is permanent.
- Distribution: weights on Hugging Face under an open license; the free site runs the local
  model server-side (or eventually in-browser via WebGPU for small enough models) — no user
  ever needs an account with anyone.
**Rule for the builder:** every Reader-dependent feature must work identically with the local
backend; nothing may be architected so that only an API backend can support it.

## 13. DUAL-READER GOLD FACTORY (28 Jul 2026, Jake) — two frontier models, side by side
**Amendment to §3's multi-pass protocol: the two independent passes come from TWO DIFFERENT
VENDORS' frontier models (e.g., a Claude-family model and a GPT-family model), same prompt,
neither seeing the other's output.** Cross-vendor agreement is stronger evidence than
same-model-twice (uncorrelated failure modes); cross-vendor disagreement auto-generates the
[unclear: X/Y] candidates.
- **Gold production at scale:** dual-reader consensus + human spot-checks at a sampling rate
  (not 100% review) becomes the gold/training-data factory. Consensus fields are eligible for
  CONFIDENT; disagreements stay [unclear] until a human or a cross-act constraint resolves
  them.
- **Honest limit, keep it in the docs:** agreement is not truth — frontier models share
  training-data ancestry and can agree on the same mistake, so sampled human verification
  never drops to zero, and the wrong-but-confident metric is measured against human-checked
  holdouts, not against consensus.
- This slots into §12 unchanged: the dual-reader duo is the bootstrap gold factory; its
  human-sampled output trains the LoRA'd local model; the duo then retires to the benchmark
  leaderboard.

## 14. AMENDMENT (28 Jul 2026, Jake) — SUBSCRIPTION-SESSION LABEL FACTORY; THE APP IS LOCAL-ONLY FROM DAY ONE
Supersedes the API-backend portions of §12/§13's bootstrap plan. **No API keys anywhere.**
- **The application ships with exactly one Reader class: the LOCAL open-weights VLM**, sized
  for consumer hardware (a desktop GPU, or quantized down to capable laptops). The app's
  batch mode runs continuously and resumably — point it at a corpus and it grinds until
  everything is indexed, at whatever speed the hardware gives. Checkpointed, interruptible,
  no cloud dependency, no account, no key. That IS the product.
- **Training labels come from the builder's own AI subscriptions, not APIs**: the two
  frontier assistants (Claude-family and GPT-family sessions) each read batches of scans
  interactively/headlessly under their plans and emit schema-conformant extractions. The §13
  dual-reader consensus logic applies unchanged — the two subscription readers are the two
  blind passes. Throughput is bounded by plan limits; the factory runs in recurring batches
  over days/weeks. Slower than APIs, free, and sufficient: T0 (~1–2k acts) in weeks, and the
  LoRA improves in waves as slices complete.
- **Bootstrapping loop**: subscription sessions label T0 → first LoRA → the local model
  becomes a THIRD reader whose disagreements with the subscription readers route review →
  each wave, the local model takes more of the load until the subscription readers are
  needed only for spot-checks and hard cases. The continuous indexing runs (Pułtusk, the
  breadth sweep) are done BY THE LOCAL MODEL on the builder's own hardware — that's the
  "runs until it indexes it all" mode, and it costs electricity.
- Pipeline code NEVER calls the subscription assistants programmatically-as-API; their
  output enters the corpus as label files produced in their own sessions, with reader
  identity recorded per record (schema already supports source attribution).
- Eval integrity unchanged: human-verified, clerk-year-sequestered holdouts (§13, corpus
  plan). Frontier-model leaderboard comparisons become OPTIONAL nice-to-haves, not
  dependencies.

### §13 amendment (28 Jul 2026, Jake): third-reader arbitration is the DEFAULT tie-break
Human arbitration of dual-reader disagreements is OPTIONAL, not required. Default resolution:
a THIRD independent reader (different model or fresh session, shown only the disputed span and
the pooled candidates, never the readers' identities or full labels) votes; 2-of-3 agreement
promotes the field to consensus-PROBABLE. Fields where all three diverge stay [unclear].
Humans remain mandatory only where they always were: the sampled verification of gold/eval
records and the clerk-year-sequestered holdouts. This keeps the human budget tiny and spent
where it counts.

---

# §15. GOVERNING PRINCIPLE — the human is in the design, not the fallback
Added 29 Jul 2026 at the owner's direction: "we should add that human back into it and stop
pretending — if something's on the fence, use shape comparisons to have a human help."

Full automation is NOT the goal of this project. It is not a milestone we are working toward
and quietly failing to reach; it is a design we are rejecting. Every system in this space
optimizes for output without a person in it, and every one of them therefore has to resolve
ambiguity by guessing. That guess is the defect this project exists to eliminate.

The commitments that follow from this:

1. **Ambiguity is routed, not resolved.** When the evidence does not decide a field, the field
   stays `[unclear]` and the question is routed to a human. No confidence threshold, no
   tie-break heuristic, no "most likely" fallback ever converts uncertainty into an assertion.

2. **Human attention is treated as the scarcest resource in the system.** The machinery exists
   to spend it well: read everything, resolve what is resolvable, and surface only the handful
   of decisions where a person's eyes are genuinely decisive. A pipeline that hands a human
   1,000 lines to proofread has failed; one that hands them ten questions has succeeded.

3. **The questions must be answerable by a non-reader of the script.** This is what makes human
   help affordable and available. Shape comparison — the disputed glyph beside labeled,
   uncontested examples of each candidate letter in the same hand — plus bilingual anchors and
   arithmetic cross-checks. Demonstrated 28 Jul 2026: three identity questions resolved and one
   machine deadlock broken by someone who reads no Cyrillic (§ human_check/).

4. **Declining is a first-class answer.** "Can't tell" and "neither candidate" must always be
   available and must cost nothing. A human forced to choose is just a slower guess.

5. **Expertise is aimed, not replaced.** Readers of the script remain necessary for
   publication-grade gold and for the residue the packet cannot settle. The system's job is to
   make sure their scarce hours land on the fields that actually need them — and to capture
   what they decide so the next model inherits it.

The claim the project makes is therefore not "the machine reads these registers." It is: **the
machine reads what it can read, states plainly what it cannot, and asks a person the right
small questions — in a form they can answer without knowing the script.**
