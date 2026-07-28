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
