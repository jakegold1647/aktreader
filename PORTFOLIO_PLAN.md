# AKTREADER as a "can we hire you" artifact — the plan
For Jake (23, Pitt CS '26, targeting AI/ML engineering roles). Written 28 Jul 2026.
Premise: hiring signal doesn't come from "I made an AI app." It comes from demonstrating the
exact skills teams can't hire enough of — evaluation design, calibration engineering, data
curation, and shipping to real users — wrapped in a story no other candidate has.

## 1. What actually makes engineers say "wow" (build toward these, in order)

### 1.1 The benchmark (SerockBench) — the single strongest hire-signal
Anyone can call a vision API. Almost nobody designs a rigorous domain benchmark. Ship:
- A public eval set (public-domain acts + verified labels) with a documented labeling protocol.
- **Novel metrics that show taste:** filiation exact-match; *wrong-but-confident rate* as the
  headline; the blank/unknown/absent three-way scored explicitly; calibration curves
  (confidence vs accuracy per grade).
- A leaderboard table in the README scoring 3–4 frontier VLMs + Transkribus on YOUR benchmark.
  "I benchmarked GPT-5.6, Fable 5, and Transkribus on 19th-c Cyrillic registers; here's where
  each fails" is an interview story that runs 45 minutes by itself.
### 1.2 The calibration engineering
The two-pass disagreement→[unclear] protocol, the cross-act consistency validators (witness-age
continuity, dual-date arithmetic), and a measured claim: "reduces wrong-but-confident readings
from X% to Y% at Z% coverage." Selective-prediction framing = ML-engineer catnip; it maps
directly to how serious labs think about hallucination.
### 1.3 The corpus-level solver (v2 §9.1) — the research-flavored crown
Register-as-constraint-system (scribe priors, propagated arithmetic). Even a modest result
("corpus context resolves 41% of per-page [unclear]s") is a legitimate workshop-paper claim.
Target venue if desired: an ML4DH/digital-humanities workshop — a peer-reviewed line on a
resume at 23 is a differentiator.
### 1.4 Real users + a real institution
Ten strangers who used it beat ten thousand GitHub stars for hire-signal. Collect: usage
numbers, 3 quoted testimonials from society members, and THE letter — if Yad Vashem (or
JRI-Poland/a JGS) acknowledges or adopts anything, that paragraph leads the resume bullet.

## 2. The deliverable stack (each is a resume line; together they're a candidacy)
1. **The repo** — clean, tested, typed, CI badge, honest README with the calibration table.
2. **SerockBench** — separate repo or /bench, with protocol doc + leaderboard.
3. **The technical writeup** (3–5k words): "Teaching machines to read what the last readers
   are forgetting" — problem, why OCR fails, the honesty layer, benchmark results, Pułtusk
   map. Post to a personal site; submit to HN (Show HN) + r/MachineLearning + genealogy subs.
   Writing quality is itself screened for; this doubles as the writing sample.
4. **The Pułtusk town graph** — the demo that makes non-engineers gasp: an explorable,
   evidence-linked reconstruction of a murdered community, 1875–1935. Interactive > static;
   every node click shows the act crop it came from (the artifact-first rule as UX).
5. **A 3-minute demo video** — scan goes in, graded JSON + graph comes out, one [unclear]
   shown honestly. Recruiters watch videos; they don't clone repos.
6. **The talk** — offer it to JGS chapters + Pitt's DH/Jewish-studies groups; record one.
   "Invited speaker" is a line; the recording is proof of communication skills.

## 3. Sequencing (calendar-realistic)
- **Week 1 (now):** P0–P2 via Codex/Sol — pipeline + gold + first calibration numbers.
- **Weeks 2–3:** P3 Pułtusk acquisition (polite-pace, gated) + batch read; SerockBench v1 with
  the multi-model leaderboard; repo hygiene (tests, CI, docs).
- **Week 4:** Town-graph v1 on Pułtusk output; writeup drafted; demo video.
- **Week 5:** Publish everything simultaneously (repo + bench + writeup + Show HN same day —
  one coordinated splash beats a dribble). Send the Yad Vashem letter and the JRI-Poland note
  (Jake personally, per standing rules).
- **Weeks 6–8:** Talks, testimonials, v2 corpus-solver experiment → workshop paper if results
  merit. Iterate from real user feedback.

## 4. The story discipline (why this beats a generic portfolio)
The narrative is singular and true: *"My family's names were locked in registers no living
person could read. I built the machine that reads them honestly — then gave it to everyone,
starting with Yad Vashem."* Every artifact reinforces it. Rules:
- Never overclaim (the field's trust is the product; also interviewers probe exaggeration).
- Publish failures alongside wins (the leaderboard shows where every model, including the
  chosen one, breaks — that's what senior engineers respect).
- Real numbers everywhere; no "up to 90%" marketing math.
- The mitzvah framing is real but the resume bullet leads with engineering: benchmark,
  calibration, users. The story is the cover letter; the numbers are the resume.

## 5. Resume bullets this plan produces (draft, to be filled with real numbers)
- "Built and open-sourced AKTREADER, a calibrated vision-LM pipeline for 19th-c Cyrillic/Polish
  civil registers; reduced wrong-but-confident field extractions to <2% at N% coverage."
- "Designed SerockBench, the first public benchmark for genealogical act extraction; evaluated
  4 frontier VLMs; adopted/cited by [society]."
- "Reconstructed the Jewish community of Pułtusk (12k records, 1875–1935) as an evidence-linked
  population graph; findings contributed to Yad Vashem's Hall of Names via [outcome]."
- "Shipped to N users across genealogical societies; invited talks at [venues]."

## 6. Anti-goals (things that would dilute the signal)
- Feature sprawl (user accounts, mobile apps, GEDCOM editors) — the instrument, not a platform.
- Training a from-scratch model for its own sake — only fine-tune if SerockBench proves the
  frontier models leave headroom AND the gain is measurable.
- Growth hacking / fake traction — this community detects it instantly and it poisons the story.
- Letting the site/tool make kinship claims — extraction only; the never-overclaim rule is
  also the legal/ethical moat.
