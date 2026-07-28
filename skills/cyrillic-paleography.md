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
