# Serock zero-cost standards bootstrap

## Verdict

The public web does not currently expose a complete, openly licensed, scan-aligned transcription
set for Serock. It does expose useful coordinates:

- four exact Cyrillic acts posted by Howard Orenstein for volunteer translation;
- a public JRI-derived family GEDCOM containing many Serock year/type/act-number references;
- an earlier 1812-1820 Serock register at the National Library of Israel, 174 leaves, with no
  online access;
- the PTG manuscript viewer containing the later civil registers, annual handwritten indexes,
  and marriage annexes.

These sources save search time, but they are not automatically gold. Public visibility and
training permission are different facts.

The machine-readable source inventory is
`resources/serock_public_source_inventory.json`. The four exact act coordinates are isolated in
`resources/serock_public_act_leads.csv` and stamped `REFERENCE_ONLY_DO_NOT_TRAIN`.

## What can be used immediately for $0

The useful free standard is inside the registers themselves:

1. **Annual handwritten indexes.** A SkU/SkM/SkZ row supplies the principal's handwritten name
   and act number independently of the prose act. It is weak truth for identity and routing.
2. **Repeated names inside an act.** The principal commonly appears in the declaration and again
   in the closing formula. Agreement supplies two samples from the same clerk.
3. **Signatures.** Literate declarants sometimes write their own names after the clerk wrote them
   in the body. These are paired name shapes, although the hand differs.
4. **Marriage annexes.** Birth-certificate copies can duplicate a birth act from another book or
   town. A matched pair supplies formula and identity supervision across hands and decades.
5. **Duplicate or corrected registrations.** The 1902/1903 Ruchla Goldsztejn records and the
   1890 red-ink rectifications are valuable disagreement examples. They teach the model not to
   flatten corrections into one guessed name.

All five are derived from original manuscript evidence rather than copied genealogy indexes.
They can enter a weak-supervision pool after the image pair is pinned. They become benchmark
truth only after human attestation.

## Fastest seed benchmark

Start with the already-localized Serock 1890 death book:

1. Select ten acts whose prose-act principal, closing-formula principal, and SkZ index row agree.
2. Pin the full image and three small regions: act number, principal in prose, principal in the
   annual index.
3. Ask a human only: “Do these three shapes identify the same written name and act number?”
4. Admit only the verified name, sex marker, act number, and event type. Leave every unverified
   field `NOT_ANNOTATED`.
5. Keep the ten acts out of training as the first image-attested structured holdout.

This does not produce character-error-rate gold or continuous transcriptions. It does produce a
defensible first benchmark for the product's core structured task at no monetary cost. Continuous
transcription gold can grow later from volunteer readers or corrections.

## Web-source rulings

| Source | Use now | Do not do |
|---|---|---|
| [Orenstein's four-act post](https://groups.jewishgen.org/g/main/topics?after=1163089320000000000&page=14760) | Locate four exact acts and compare candidate identities against the scans | Copy the candidates into training labels without image verification |
| [NLI/CAHJP Serock register, 1812-1820](https://www.nli.org.il/en/archives/NNL_CAHJP990049014480205171/NLI) | Record as a future breadth source | Claim it is online or scrapeable; the catalog says no online access |
| [Public Pieniek GEDCOM](https://familytrees.genopro.com/eu7/pieniek/FamilyTree.ged) | Discovery and cross-check only | Train on it; the file identifies JRI-Poland as the source of many entries |
| [Serock Yizkor translation](https://www.jewishgen.org/yizkor/serock/serock.html) | Name/context research only | Treat narrative or memorial-book names as register truth |
| [PTG Skanoteka Serock collection](https://skanoteka.genealodzy.pl/id318) | Verify against already permitted, owner-held scans | Launch a new mirror or automated archive scrape |

## Admission boundary

The web references never overwrite an act reading. If a web candidate and the ink disagree, the
ink wins and the disagreement is preserved. JRI-Poland, Geneteka, JewishGen, memorial-institution,
and unlicensed user-contributed content remain outside the training corpus. The project trains on
its own permitted scans and its own image-grounded labels.
