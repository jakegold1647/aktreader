# DESIGN: The Adjudication Packet — the human final pass, generated automatically
Owner's concept, 29 Jul 2026: "what makes us different is that final pass is human — it gathers
all that info and asks a series of questions at the end for you to use your eyes as a researcher
to try to read the shapes."

## Why this is the product, not a feature
Every competing system ends at output. This pipeline ends at a QUESTION SET. The machine's job
is to do everything a machine can do and then hand a human the smallest possible set of
decisions, each pre-loaded with the evidence needed to decide it — including evidence a
non-reader of the script can act on.

Validated by hand on 28 Jul 2026: a generated four-item packet let the project owner, who does
not read Cyrillic, resolve three identity questions and break one machine 2–2 deadlock in about
fifteen minutes (human_check\HUMAN_CHECK_RESULTS_28Jul2026.md). Three records reached
human-verified gold as a direct result. The method — letterform lineups, bilingual anchors,
positional/arithmetic cross-checks — required zero language fluency.

## What the packet contains, per question
1. **The claim in plain language.** "The consensus says this act records a man named Boruch
   Moszko Herszfeld, age 50." No jargon, no Cyrillic required to understand the stakes.
2. **The disputed region, magnified 4–8×**, cropped tight, from the original pixels.
3. **A LETTERFORM LINEUP** — the discriminating glyph shown beside 3–6 uncontested instances of
   each candidate letter, taken from *the same clerk's hand on the same page*, each labeled with
   the word it came from. This is the core mechanism: it converts "can you read Russian?" into
   "does this shape match column A or column B?"
4. **Bilingual anchors where they exist** — Latin-script signatures, Polish-language marginalia,
   printed year headers. These are the register's own Rosetta stones and a non-reader can read
   them outright.
5. **Structural cross-checks** — act-number sequence, witness ages advancing year over year,
   date arithmetic, index cross-references. Arithmetic needs no paleography.
6. **The question**, answerable as YES / NO / CAN'T TELL, with an explicit statement that
   CAN'T TELL is a legitimate, expected answer that costs nothing.
7. **The consequence** stated up front: what promotes, what reverts, what stays unclear.

## Selection rule — what earns a question
Ranked by decision value, capped per packet (default 10 questions ≈ 15 minutes):
- identity-level forks (sex, principal name) — always
- machine deadlocks (n–n splits) — always
- fields where a corroboration source (index, lexicon, external record) disagrees with the ink
- single-coverage fields on records nominated for gold
- everything else: never surfaced. The packet must not become a transcription queue.

## Outputs
- Self-contained HTML (embedded images, dark-mode, desk-readable, no dependencies).
- A results file capturing verbatim human answers + interpretation + consequence executed.
- Answers feed three places: tier promotion (silver→gold), the correction flywheel (training
  signal), and the expert-review list for anything the human also declines.

## Honest limits (must ship in the docs)
- A non-reader verifying letterforms is doing *discrimination between two proposed readings*,
  not independent transcription. The packet must never present a question whose candidates are
  both wrong without a "neither / something else" escape — one occurred on 28 Jul (Λ-shape not
  matching either reference) and the escape mattered.
- Publication-grade gold should still be sampled by a reader of the script. The packet raises
  the floor and routes expert time to where it's actually needed; it does not replace expertise.

## Build note (queued to Sol)
`aktreader adjudicate --wave <id>` → selects questions per the rule above, cuts crops and
lineups automatically (candidate letters located from the disputed span; exemplars mined from
uncontested high-confidence spans of the same clerk-year), renders the HTML, and ingests the
answer file back into the tier/flywheel machinery. The lineup miner is the novel piece and the
part worth writing up.
