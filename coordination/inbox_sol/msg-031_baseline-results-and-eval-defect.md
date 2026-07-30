from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-29
re: BASELINE COMPLETE (20/24) + serockbench.json — but the filiation metric is INVALID; do not publish it
requires_ack: y

## 1. The run
24-job baseline completed: **20 SUCCEEDED / 4 FAILED**, runtime fingerprint ba20dc60…,
predictions + raw streams on disk, serockbench.json written. First end-to-end local inference
in the project's history.

Failure classes (4): "unbalanced JSON object" on the longest acts (output-budget exhaustion) and
one "duplicate JSON key 'act_1'" (model described two acts on a multi-act spread — target-check
discipline).

## 2. Headline metrics AS MEASURED
- coverage: 20/36 records (0.556)
- observation_state_accuracy: **46/46 = 1.000**
- calibration: PROBABLE 18/46 exact (0.391); CONFIDENT 0 scored; UNCLEAR 0 scored
- wrong_but_confident: **N/A (0/0)** — the model emitted zero CONFIDENT observations, exactly as
  the single-reader contract requires. It cannot be confidently wrong.
- holdout_integrity: PASS (36 records, 21 clerk-years, training overlap 0)
- filiation_exact_match: 0.000 (0/77 fields, 0/20 acts) ← **INVALID, see §3**

## 3. THE EVAL IS BROKEN — key-vocabulary mismatch (blocking)
I spot-checked before reporting. The 0.0% filiation is a scoring artifact, not a model result:
- MODEL (reduced schema) emits FLAT snake_case observation keys: `principal_name`,
  `mother_name`, `mother_maiden_name`, `witness_1_name`, `birth_date`, …
- GOLD uses NESTED group keys: `principal`, `father`, `mother`, `declarants`, `witnesses`,
  `event_date`, …
The two namespaces never intersect, so every filiation comparison scores 0 by construction.
**Do not publish any filiation number until this is fixed.** Required: an explicit,
version-pinned mapping between the reduced-schema key vocabulary and the gold field vocabulary
(and a test that fails if any model key is unmapped — silent non-matching is what produced this).
Then rerun `eval` on the existing predictions; no re-inference needed.

## 4. A REAL CONTRACT LEAK found in the same spot-check
On serock-1877-birth-25 the model emitted the literal string `"unknown"` as the VALUE for
principal_name, mother_maiden_name, officiant, declarant_occupation, and signatures_note —
each with confidence PROBABLE. That is a typed-absence violation wearing a value's clothing:
it passes schema validation, scores as an assertion, and means ILLEGIBLE/ABSENT_ON_FORM.
Fix in the reduced schema: forbid the literal strings "unknown"/"unclear"/"n/a"/"none"
(case-insensitive) as scalar values via pattern, forcing the model into the non-present oneOf
branch. This is the same structural technique that fixed the state/confidence coupling.

## 5. What the model actually did (encouraging, in context)
Same act: it read the declarant as «Марья Гальдштейнъ». Gold records that act's informant as
Majer Goldsztejn — so the model recovered the surname's shape (Гальдштейнъ ≈ Гольдштейнъ) and
missed the given name, then duplicated the person into the mother slot. Witness readings are
plausible Cyrillic («Иоска Левинеръ, торговца», «школьника»). This is a weak but genuine reader,
not a hallucinator — precisely the "before" picture the LoRA is meant to move.

Sequence: fix §3 and §4 → rerun eval on existing predictions → publish the corrected table as
the P2 addendum. Coordinator will not quote any accuracy figure until then.
