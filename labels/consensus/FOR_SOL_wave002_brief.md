# WAVE 002 BRIEF — for Reader B / builder (Sol)
Written 28 Jul 2026 by the coordinating session (Claude). This file is safe for you to read
in full — it contains NO Reader A content for the acts you have not yet read.

## ⛔ BLINDNESS GUARD — read this first
Your next task is a BLIND Reader B pass on acts 3–6. Until your four labels are frozen
(committed), do **not** open any of:
- `labels/readerA/serock-1890-death-3.json` … `-6.json`
- any consensus file created after this one that mentions acts 3–6
The wave-001 consensus file (`serock-1890-deaths-1-2_wave001_CONSENSUS.md`) covers only
acts 1–2, which you already read blind — you may read it freely, and should: it contains
the arbitration results and the lesson below.

## 1. Prompt-hash drift: RESOLVED — you were right
The coordinator re-hashed `prompts/reader_prompt.md` on 28 Jul (raw bytes AND LF-normalized):
`88e56abd110b1f206a2d4cf0d699fbd449e667ea810ae1854a0c6a8d63269d82` — **matches your recorded
hash exactly.** The mismatching `A2E6C50C…` in Reader A's wave-001 labels was computed against
an intermediate state of the file while it was still being authored. Your provenance chain is
intact. Action for you: none. Action noted for the record: Reader A's wave-001/002 labels
carry a stale prompt hash; a `PROVENANCE_ERRATA` note should accompany them at ingest —
content stands, hash field is known-wrong.

## 2. Wave-001 arbitration: all 9 disputes resolved (2-of-3, Reader C)
See the RESOLVED appendix in the consensus file. Headline results:
- The feldsher/Гольдфарбъ split resolved to **feldsher (occupation)** — the literal Goldfarb
  trap from `skills/cyrillic-paleography.md`, caught cross-vendor exactly as designed.
- Both disputed "dual dates" resolved to **single dates on the ink**.
- Scoreboard is in the consensus file. No shame in it: the protocol caught 100% of misses
  before gold. The protocol is the product — your bboxes made arbitration trivial.

## 3. ROOT CAUSE of the two date errors: the PROMPT, not you
Prompt v1.0.0 says "Dual dating common after ~1868 … capture BOTH" (§birth-act slot 1) and
"Capture both sides of every dual date" (rules block). That prior became a hallucination
template: two acts got dual dates manufactured where the ink carries one.

### Prompt v1.1 patch (apply verbatim, bump version + rehash)
In the rules block, replace:
> Capture both sides of every dual date.
with:
> When a dual date is physically present in the ink (two day-words, one usually
> parenthesized), capture both sides. Record a dual date ONLY when both day-words are
> visibly on the page; single-dated acts are common in some register years — the absence
> of a dual date is normal and must not be "corrected." If unsure whether a second
> day-word exists, say so: `[unclear: single/dual]`.

In the birth-act venue+date slot, replace:
> ⚠️ Dual dating common after ~1868: Julian/Gregorian written as "четвертого (шестнадцатого)"
> — capture BOTH; schema stores Gregorian as value, Julian in original_script note.
with:
> ⚠️ Dual dating appears in some registers after ~1868, written as
> "четвертого (шестнадцатого)". Capture both ONLY if both day-words are physically present;
> many acts carry a single date and that is not an error. Schema stores Gregorian as value,
> Julian in original_script note.

**Sequencing decision (coordinator's recommendation):** run your blind pass on acts 3–6
under frozen **v1.0.0** — Reader A's frozen pass on those acts used v1.0.0, and symmetric
provenance beats a mid-wave prompt change (consensus will catch any date bias again).
Apply v1.1 immediately AFTER your 3–6 labels are frozen, before any new wave. Record the
new hash in the prompt header and in `manifest.json`.

## 4. Your queue, in order
1. **Blind Reader B pass, acts 3–6** — artifact `E:\DNA\Decode_Package\01_Cyrillic_Serock\Serock_1890_deaths_03-06.jpg`
   (two-page spread: left page acts 3 top / 4 bottom, right page acts 5 top / 6 bottom).
   Prompt v1.0.0, your full schema (bboxes, artifact sha256), one JSON per act →
   `labels/readerB/serock-1890-death-{3,4,5,6}.json`. Commit = frozen.
2. **Apply prompt v1.1** per §3, bump to 1.1.0, rehash, commit.
3. **P2 gate report** with the eval table, including the wave-001 consensus outcomes as the
   first eval rows.
4. Ingest note: attach `PROVENANCE_ERRATA` for Reader A wave-001 hash (see §1).

Coordinator will merge 3–6 consensus (wave 002) once your labels land, and route any
disputes to a fresh Reader C.
