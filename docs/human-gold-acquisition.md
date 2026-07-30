# Human gold acquisition contract 0001

## Outcome

Buy image-grounded expertise before buying GPU time. The pilot produces five qualification
records; production produces 25 accepted records. Every record is independently transcribed
by two people who cannot see each other's work, then adjudicated by a third qualified reader.
No model output is shown to any human reader.

This packet is ready to post on a freelance marketplace, but placing a contract requires the
owner's marketplace account and approval of the proposed **$3,000 total ceiling**.

## Recommended sourcing

Post one fixed-price project on Upwork and directly invite candidates who explicitly show
pre-1917 Russian cursive, metrical-book, civil-register, archival, or genealogy experience.
Cross-posting to ProZ is useful for finding Russian/Polish historical-language specialists.
A Fiverr historical-record gig can supply a third candidate for the qualification round, but
must pass the same blind test; marketplace ratings are not evidence of paleographic accuracy.

Current market anchors checked on 2026-07-29:

- Upwork lists general Russian transcription profiles around $10-$50/hour and states a client
  marketplace fee of up to 7.99% (3% for qualifying U.S. bank payments).
- A Fiverr gig specifically advertising handwritten Russian genealogy transcription lists $20
  for up to 2,500 characters; Fiverr's standard client fee is 5.5% plus $3.50 on orders under
  $200.
- ProZ has a Russian-to-English genealogy specialist directory, but rates must be quoted.

Use fixed prices per accepted act, not hourly billing.

Unvetted qualification-invite leads found on 2026-07-29:

- Alexandra G. on Upwork advertises transcription of Russian handwriting with pre-1918 spelling
  and has a 5.0 rating across 94 reviews.
- Sasha (`sasha_aveab`) on Fiverr advertises pre-1917 Russian cursive and archival training.
- Iryna Makedon on ProZ lists recurring Slavic genealogy/archive work at $30/hour.
- Chandon Kumar on Fiverr advertises 19th-century Russian metrical/civil records at $20 per
  2,500 characters; use only if the qualification score independently supports the claims.

These are leads, not endorsements. Invite at least three candidates and retain only the two who
pass the blind qualification threshold.

## Proposed budget and milestones

| Stage | Work | Base ceiling | With contingency/fees |
|---|---:|---:|---:|
| Qualification | 5 acts x 3 candidates + adjudication | $575 | $650 |
| Production | 25 acts x 2 transcribers + adjudication | $2,125 | $2,350 |
| Total | 65 blind readings + 30 adjudications | $2,700 | **$3,000 cap** |

Suggested unit ceilings are $30 per independent transcription and $25 per adjudication.
Release each milestone only after mechanical and expert acceptance. Never prepay the full
production batch.

## Marketplace job post

**Title:** Transcribe 19th-century Polish/Russian civil-register handwriting (Cyrillic,
pre-1917 orthography)

We need exact, line-preserving original-script transcriptions of cropped 19th-century civil
register acts from the Pułtusk/Serock area. Records may be in Polish or pre-revolutionary
Russian Cyrillic and contain names, patronymics, dates, occupations, places, relationships,
and marginal notes.

Deliver for each assigned act:

1. the record ID printed in the assignment;
2. a continuous original-script transcription preserving line order and spelling;
3. `[illegible]` for unreadable text and `[unclear: candidate]` for one uncertain reading;
4. a short note for abbreviations, superscripts, damaged text, or unusual letterforms;
5. a declaration that no other worker's transcript was viewed and whether any OCR/AI tool was
   used.

Do not modernize spelling, silently expand abbreviations, translate, infer missing names, or
copy text from genealogy indexes. Qualification work must be performed without OCR or AI.
Production machine assistance is prohibited unless separately authorized and fully disclosed.
Applicants should describe experience with pre-1917 Russian cursive or Polish archival civil
records and transcribe the supplied qualification crop.

## Blind assignment rules

- The project owner supplies act-level crops with stable record IDs and SHA-256 receipts.
- Reader H1 and Reader H2 receive the same image but never each other's output.
- Filenames and instructions contain no machine guesses or research-derived identities.
- The adjudicator receives the image and both frozen transcripts only after both are submitted.
- The adjudicator resolves character-level differences, preserves unresolved alternatives, and
  cites the visible line for every decision.
- Worker identity, timestamp, assignment ID, image SHA-256, and output SHA-256 are retained.

## Mechanical acceptance

Each worker receives `examples/human-transcription-submission.example.json` with the assignment
and returns one JSON file per act. Validate qualification work before adjudication or payment:

```powershell
$env:PYTHONPATH = "src"
python tools/validate_human_transcription.py .\submission.json --qualification
```

A submission fails before payment when any of these is missing:

- assigned record ID and exact image SHA-256;
- continuous `original_script` transcription;
- line sequence or explicit line markers;
- uncertainty markers for unreadable content;
- independence and tool-use declarations;
- UTF-8 text that can be parsed without replacement characters.

The project will convert accepted text to the Reader v1.4 schema. Every structured PRESENT
observation must be a continuous substring of the worker's own transcription. Provenance is
stamped mechanically; workers do not invent hashes or schema metadata.

## Qualification and production acceptance

The adjudicator scores each candidate on five acts:

- character accuracy on adjudicated legible text: at least 97%;
- names/dates/relationships with no material hallucination: 100%;
- all unreadable regions marked instead of guessed;
- original spelling and pre-1917 letters preserved;
- independence/tool declaration complete.

Hire the best two passing transcribers. If fewer than two pass, recruit again; do not relax the
threshold. Production is delivered in five-act milestones. Audit one record in every milestone
before release. A material invented identity, undisclosed machine use, or copied peer output
rejects the milestone and removes that worker from the gold path.

## Gold admission rule

A record enters the image-attested gold holdout only after two independent transcripts and the
adjudicator agree on all evaluation-bearing fields, or the adjudicator explicitly records the
remaining alternatives. Gold and training clerk-years remain sequestered. The same accepted
record must never appear in both sets, including crops or duplicates from the same act.

Human transcription is evidence, not archival authority. Every result retains the warning:
"extraction is not authority — verify against the scan."
