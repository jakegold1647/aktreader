# AKTREADER shared Reader prompt

Prompt version: 1.1.0

## Reader task

Read exactly the supplied civil-register act image or act crop. Produce a structured genealogical observation in the supplied JSON schema. Read the page itself: do not infer facts from filenames, indexes, family knowledge, other labels, or another reader's output. Preserve pre-reform Russian or Polish wording in `original_script`; put only a conservative normalized rendering in `value`.

This is one blind pass. A single reader may emit `PROBABLE`, `UNCLEAR`, or a typed non-present observation state, but never `CONFIDENT`. If a glyph or word has two plausible readings, render the normalized value exactly as `[unclear: X/Y]` and retain both candidates. If only one shaky candidate is visible, use `[unclear: X?]`. Never silently complete a surname, filiation, date, or maiden name from context.

Distinguish `ABSENT_ON_FORM`, `BLANK`, `STATED_UNKNOWN`, and `ILLEGIBLE`. They are not synonyms. Include an image source span for each observation. Transcribe in original order before structuring. When a dual date is physically present in the ink (two day-words, one usually
parenthesized), capture both sides. Record a dual date ONLY when both day-words are
visibly on the page; single-dated acts are common in some register years — the absence
of a dual date is normal and must not be "corrected." If unsure whether a second
day-word exists, say so: `[unclear: single/dual]`. Keep derived calendar normalization explicitly separate from what the ink states.

Return only one JSON object conforming to the schema supplied with the batch brief. The batch brief supplies artifact identity, target act, clerk-year proxy, Reader identity, blind-group identity, and prompt SHA-256. Do not add prose outside the JSON.

## Domain skills (verbatim)

The following three local skill documents are reproduced verbatim between their delimiters. These exact sections are shared by all subscription-session readers and the local open-weights Reader.

<!-- BEGIN VERBATIM: skills/napoleonic-act-formula.md -->
# The Napoleonic act formula — structure every act follows
Civil registration in Congress Poland used a fixed notarial formula, in Polish to 1867/68, in
Russian ~1868–1915. The formula is the tool's structural prior: every schema field lives in a
predictable rhetorical slot. Slot phrases below are the canonical openings to anchor on (clerk
spelling varies; anchor on the slot sequence, not exact strings).

## BIRTH ACT (akt urodzenia / акт о рождении)
1. **Venue+date slot**: «Состоялось в городе/посаде N, [date] года, в [hour] часов» /
   «Działo się w mieście N dnia [date] roku o godzinie [hour]» → registration_date, town.
   ⚠️ Dual dating appears in some registers after ~1868, written as
   "четвертого (шестнадцатого)". Capture both ONLY if both day-words are physically present;
   many acts carry a single date and that is not an error. Schema stores Gregorian as value,
   Julian in original_script note.
2. **Declarant slot**: «явился лично [name], [occupation], жительствующий в [place], [age] лет»
   → father (usually) with age, occupation, residence. If the declarant is NOT the father
   (midwife, relative — common for posthumous or illegitimate births), the formula says so —
   capture the relationship verbatim.
3. **Witnesses slot**: «в присутствии свидетелей [name1], [occupation], [age] лет, и [name2]...»
   → witnesses[] with ages. Witness ages are evidence gold (see uncertainty-grading: age
   continuity across acts).
4. **Presentation slot**: «и предъявил нам младенца мужеского/женского пола, объявляя, что он(а)
   родился/родилась в [place] [date] в [hour] часу» → event_date, sex, birthplace.
5. **Mother slot**: «от законной его жены [given name], урожденной [MAIDEN NAME], [age] лет» →
   mother with MAIDEN NAME and age. «урожденной»/«z domu» = née. THE single most valuable field.
6. **Naming slot**: «младенцу сему при обрезании (birth of boys: при обрезании = at circumcision)
   / при религиозном обряде дано имя [NAME]» → principal name.
7. **Closing slot**: «Акт сей объявляющему и свидетелям прочитан и ими/нами подписан» +
   signature notes («неграмотны» = illiterate — capture; it explains absent signatures) +
   officiant signature → officiant, signatures_note.

## MARRIAGE ACT (akt małżeństwa / акт о браке)
Same venue slot, then: witnesses; groom slot «что в присутствии... заключен религиозный брачный
союз между [groom], холостым/вдовцом (bachelor/widower), [age], сыном [father] и [mother
урожденной X] супругов [surname], родившимся в [place], жительствующим в [place]» → groom +
BOTH his parents incl. mother's maiden name; bride slot mirrors it («девицею/вдовою, дочерью...»)
→ bride + BOTH her parents. Then: banns dates (three announcements with dates), parental
permission note (if a party is a minor), prenup note («брачный договор» — rare, capture loudly),
rabbi who performed the rite. Marriage acts are the filiation jackpot: four parents per act.

## DEATH ACT (akt zgonu / акт о смерти)
Venue slot; two declarants (often unrelated neighbors — do NOT assume kinship) with ages,
occupations; «объявили, что [date] в [hour] часов умер(ла) [name], [age] лет, сын/дочь [father]
и [mother]» → deceased + filiation; «оставив после себя овдовевшего мужа / овдовевшую жену
[name]» = left a widowed spouse → deceased_left_behind. ⚠️ Filiation of elderly deceased is
often the clerk's guess or absent — grade PROBABLE at best unless declarants are stated kin.
⚠️ «вчерашнего дня» = yesterday relative to registration — resolve to a date but keep original.

## ANNEXES (allegata / аллегаты)
Loose supporting documents bound separately (birth extracts for marriages, permissions). No
fixed formula — extract free-form with slots where recognizable. Often the ONLY surviving
record when a register year is lost.

## SKOROWIDZE (annual indexes, SkU/SkM/SkZ pages)
Alphabetical surname → act number tables, one per register per year, by first letter of
surname (Cyrillic letter order in Russian years). Extract as index_page type: ordered
(surname, given, act_no) triples. Cheap year-negatives: a surname absent from a year's
skorowidz is absent from that register year (grade the negative with the index page as its
artifact).

## Known local instance (validation reference)
Serock register books read by this project confirm the formula holds throughout 1874–1904;
example verified acts and their full readings are in the P1 gold sources. Officiant in Serock
across decades: Rabbi Josef Lewinsztejn (age advances through the years — a built-in
consistency check).

<!-- END VERBATIM: skills/napoleonic-act-formula.md -->

<!-- BEGIN VERBATIM: skills/cyrillic-paleography.md -->
# Pre-1918 Russian chancery script — what modern readers don't know
The acts use pre-reform orthography and 19th-c clerk cursive. Feed the relevant parts of this
into Reader prompts; use the confusable pairs when adjudicating [unclear].

## Pre-reform orthography (abolished 1918 — models trained on modern Russian stumble here)
- **ѣ (yat)** — reads as е. Common in formulae: «въ присутствіи», «лѣтъ» (years).
- **і (decimal i)** — reads as и, used before vowels/й: «Іосифъ», «объявленіе».
- **ѳ (fita)** — reads as ф, in Greek-origin names: «Ѳейга» is NOT fita — beware; Fejga is
  usually «Фейга»; ѳ appears in e.g. «Аѳанасій» (rare in Jewish acts).
- **ъ (hard sign)** — ends every consonant-final word; carries no sound. Strip for value,
  keep in original_script.
- **ѵ (izhitsa)** — vanishingly rare; flag [unclear] if suspected.

## Handwriting confusables (the classic misread pairs in this cursive)
- и / н / п — three near-identical letter shapes; context decides.
- т / ш / м — the triple trap: cursive т is often written as «m»-like ш with a macron above
  (т̄), ш with a breve below (ш̆). The diacritics ARE the disambiguation — look for them.
- г / ч / р descenders vary by clerk.
- е / ѣ in sloppy hands; з / э; ц / щ tails.
- Capital С / Е / О in ornate openings.
- **Surname-critical**: ГОЛЬДШТЕЙНЪ vs ГОЛЬДФАРБЪ differ mid-word where cursive is worst —
  never call a surname from its first letters (the project's "Goldfarb trap").

## Numbers, dates, ages — written as WORDS
- Ages: «тридцати лѣтъ» (of thirty years — genitive). Dates: «двадцать перваго января».
- **Dual dating**: «девятаго (двадцать перваго) марта» = 9 March Julian / 21 March Gregorian
  (12-day gap in the 1800s, 13 after Feb 1900). Sanity-check the gap; a wrong gap means a
  misread digit-word.
- Month names: январь/февраль/мартъ/апрѣль/май/іюнь/іюль/августъ/сентябрь/октябрь/ноябрь/
  декабрь (with case endings, usually genitive: января, февраля...).
- Hours: «въ десять часовъ утра/вечера/по полудни».

## Formula vocabulary (high-frequency, worth hard-anchoring)
состоялось (it took place) · явился лично (appeared in person) · жительствующій (residing) ·
въ присутствіи свидѣтелей (in the presence of witnesses) · объявилъ (declared) · младенецъ
(infant) · мужескаго/женскаго пола (male/female sex) · законной его жены (his lawful wife) ·
урожденной (née) · умеръ/умерла (died) · оставивъ послѣ себя (leaving behind) · вдовецъ/вдова
(widower/widow) · холостой/дѣвица (bachelor/maiden) · неграмотны (illiterate) ·
торговецъ/рабочій/портной/сапожникъ/мясникъ (trader/laborer/tailor/shoemaker/butcher).

## Polish-era acts (pre-1868 and post-1915)
Same formula in Polish: Działo się (it took place) · stawił się (appeared) · w obecności
świadków · okazał nam dziecię płci męskiej/żeńskiej · spłodzone z jego małżonki N z domu X
(z domu = née) · umarł(a) · pozostawiwszy po sobie owdowiałą żonę. Polish long-s, crossed-ł,
and Latin-cursive confusables (u/n, e/i) apply.

## Jewish-act specifics
- Names are Russified/Polonized on the page: Ицекъ-Мошекъ = Icek Moszek. Keep the page form
  in original_script; normalized form in value (see jewish-onomastics skill).
- «при обрѣзаніи» (at circumcision) marks boys' naming; girls «при религіозномъ обрядѣ».
- Patronymic-style references («Мошковичъ» = son of Moszek) occasionally replace surnames in
  early years — capture as filiation evidence, not as surname.

<!-- END VERBATIM: skills/cyrillic-paleography.md -->

<!-- BEGIN VERBATIM: skills/uncertainty-grading.md -->
# The grading contract — the soul of the tool
A wrong-but-confident field is the cardinal failure. Ten honest [unclear]s beat one guess.
P2's acceptance gate: filiation exact-match ≥90% on gold AND wrong-but-CONFIDENT < 2%.

## Per-field confidence enum
- **CONFIDENT** — both independent reads agree AND the reading survives cross-checks. This
  grade is a promise; spend it carefully.
- **PROBABLE** — reads agree but a cross-check is unavailable, or one read + strong formula
  prior. Default grade for most fields.
- **[unclear: X/Y]** — genuinely ambiguous between readings X and Y (or [unclear: X?] for one
  shaky candidate). ALWAYS list the candidates; never output bare "unclear."
- **ILLEGIBLE** — the ink/scan defeats reading entirely (stain, tear, resolution).

## The three-way distinction that must NEVER collapse (hardest-won lesson of the source project)
For an expected-but-missing field, distinguish:
1. **ABSENT-ON-FORM** — the formula/form has no slot for it (e.g., mother's line not part of
   this document type).
2. **BLANK** — the slot exists and was left empty by the clerk.
3. **STATED-UNKNOWN** — the clerk wrote "unknown" («неизвѣстно»).
These are three different historical facts. Indexes that collapse them into one word have
sent real researchers down wrong paths for months. The JSON must carry which one it is.

## Cross-checks (mechanical upgrades/downgrades — implement as validators)
- **Date arithmetic**: registration_date ≥ event_date; dual-date gap = 12/13 days; stated age
  vs any known birth act.
- **Witness-age continuity**: the same witness across acts of adjacent years must age ~1 year
  (this exact check let the source project prove two death acts were one event). A witness
  aging 0 or 2 years across a year boundary is NORMAL noise; 5+ is a misread or a different
  person — flag, don't decide.
- **Within-register consistency**: same clerk-year → same spellings of recurring
  names/officiant; a one-off variant spelling of a recurring name is a misread candidate.
- **Formula position**: a value extracted from the wrong rhetorical slot (an age where the
  formula puts the hour) is auto-downgraded.

## Multi-pass protocol
Two independent Reader passes (different prompt seeds or different backends). Field-level
agreement → eligible for CONFIDENT. Disagreement → the disagreeing readings BECOME the
[unclear: X/Y] candidates automatically. Never let pass 2 see pass 1's output.

## Output honesty rules
- original_script preserves exactly what the page shows (pre-reform letters, hard signs,
  Russified name forms); value carries the normalized form; the two must never be conflated.
- Every field carries source_span (where on the page it came from) so a human can re-check
  the pixels — the project's evaluate-from-the-artifact rule, inherited.
- Calibration is measured, not asserted: the eval harness scores wrong-but-CONFIDENT as its
  headline metric, and the README publishes the number.

<!-- END VERBATIM: skills/uncertainty-grading.md -->
