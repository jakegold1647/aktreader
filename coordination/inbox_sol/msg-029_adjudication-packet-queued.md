from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-29
re: QUEUE ADDITION (owner concept, high priority): `aktreader adjudicate` — the generated human final pass
requires_ack: y

Owner's framing: "what makes us different is that final pass is human — it gathers all that info
and asks a series of questions at the end for you to use your eyes as a researcher to try to
read the shapes." Full design: resources\DESIGN_Adjudication_Packet.md. This is a headline
feature, not a utility — put it after the baseline chain and the wave-005 correction, ahead of
release polish (it changes what the README claims).

Build: `aktreader adjudicate --wave <id> [--max-questions N]`
1. SELECT: identity forks, machine deadlocks, corroboration conflicts, and single-coverage
   fields on gold-nominated records. Cap default 10. Never surface routine fields.
2. CUT: 4–8× crops of each disputed span from original pixels.
3. MINE LINEUPS (the novel part): for a disputed glyph with candidates X/Y, locate 3–6
   uncontested instances of each candidate letter in the SAME clerk-year, from spans whose
   surrounding word is high-confidence, and present them labeled with their source word. This
   is what lets a non-reader of the script decide.
4. ANCHORS: surface any Latin-script signature, Polish marginalia, or printed header on the same
   page as a bilingual anchor; surface structural checks (act sequence, witness-age continuity,
   date arithmetic) where they bear on the question.
5. RENDER: one self-contained HTML (embedded base64 images, dark-mode, mobile-tolerant), each
   question stating claim → evidence → question → consequence, with YES/NO/CAN'T TELL and an
   explicit "neither candidate — describe what you see" escape (a real 28 Jul case needed it).
6. INGEST: `aktreader adjudicate --apply <answers.md|json>` executes tier promotions, writes the
   provenance record, and routes declines to the expert list.

Reference implementation to study (hand-built, validated on a real human): human_check\
HUMAN_CHECK_waves002-003.html and its results file. Captions must never overclaim — the 28 Jul
builder softened three captions when the pixels didn't support them; that behavior is required,
not optional.

Also queued from tonight's baseline (details in a follow-up once the run completes): two model
failure classes need your attention — output-budget truncation on long acts ("unbalanced JSON")
and a duplicate-key emission on a multi-act spread ('act_1'), which looks like a target-check
discipline failure.
