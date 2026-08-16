# Schema reference

This reference is generated from the versioned JSON Schemas in [\`schemas/\`](../schemas/) by [\`tools/build_schema_reference.py\`](../tools/build_schema_reference.py). Do not edit it by hand.

It lists each schema's named object fields, required status, declared type or structure, and any description carried by the contract. References to \`$defs\` remain pointers to the reusable definition named below rather than being expanded repeatedly.

## Schemas

- `act-record-2.0.0.schema.json` — AKTREADER canonical act consensus record
- `adapter-identity-1.0.0.schema.json` — AKTREADER LoRA adapter identity
- `adjudication-answers-1.0.0.schema.json` — AKTREADER adjudication answers
- `adjudication-wave-1.0.0.schema.json` — AKTREADER adjudication wave
- `gold-attestation-1.0.0.schema.json` — AKTREADER per-field gold attestation sidecar
- `human-qualification-adjudication-1.0.0.schema.json` — AktReader human qualification adjudication
- `human-transcription-submission-1.0.0.schema.json` — AktReader human transcription submission
- `model-output-1.0.0.schema.json` — AKTREADER bounded model-facing output
- `model-output-1.1.0.schema.json` — AKTREADER v1.4 grounded bounded model-facing output
- `reader-label-1.0.0-v1.2.schema.json` — AKTREADER immutable Reader observation label
- `reader-label-1.0.0-v1.4.schema.json` — AKTREADER v1.4 grounded Reader observation label
- `reader-label-1.0.0.schema.json` — AKTREADER immutable Reader observation label
- `silver-record-1.0.0.schema.json` — AKTREADER materialized silver record
- `silver-tier-manifest-1.0.0.schema.json` — AKTREADER silver-tier provenance manifest

## AKTREADER canonical act consensus record

Source: [`schemas/act-record-2.0.0.schema.json`](../schemas/act-record-2.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/act-record-2.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string`<br>pattern: `"act-record-2\\.0\\.0\\.schema\\.json$"` | — |
| `arbitration` | yes | reference to `#/$defs/arbitration` | — |
| `artifact` | yes | reference to `#/$defs/artifact` | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `clerk_year` | yes | reference to `#/$defs/clerkYear` | — |
| `compliance` | yes | reference to `#/$defs/compliance` | — |
| `correction_events` | yes | `array`; items: reference to `#/$defs/correctionEvent` | — |
| `derivation` | yes | reference to `#/$defs/derivation` | — |
| `fields` | yes | `object`<br>minProperties: `1` | — |
| `mentions` | yes | `array`; items: reference to `#/$defs/mention` | — |
| `parent_record_sha256` | yes | oneOf: reference to `#/$defs/sha256` / `null` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `record_kind` | yes | constant `"DUAL_READER_CONSENSUS"` | — |
| `revision` | yes | `integer`<br>minimum: `1` | — |
| `schema_version` | yes | constant `"2.0.0"` | — |
| `target` | yes | reference to `#/$defs/target` | — |
| `validation` | yes | reference to `#/$defs/validation` | — |

### Reusable definitions

#### `$defs.arbiter`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `candidate_only_context` | yes | constant `true` | — |
| `full_labels_seen` | yes | constant `false` | — |
| `independence_attested` | yes | constant `true` | — |
| `independence_basis` | yes | one of `"DIFFERENT_MODEL"`, `"FRESH_SESSION"` | — |
| `reader_family` | yes | `string`<br>minLength: `1` | — |
| `reader_id` | yes | `string`<br>minLength: `1` | — |
| `reader_identities_seen` | yes | constant `false` | — |
| `reader_version` | yes | `string`<br>minLength: `1` | — |
| `session_id` | yes | `string`<br>minLength: `1` | — |

#### `$defs.arbitration`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `default_tie_break` | yes | constant `"INDEPENDENT_THIRD_READER"` | — |
| `events` | yes | `array`; items: reference to `#/$defs/arbitrationEvent` | — |
| `policy_version` | yes | constant `"1.0.0"` | — |
| `requests` | yes | `array`; items: reference to `#/$defs/arbitrationRequest` | — |

#### `$defs.arbitrationEvent`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `arbiter` | yes | reference to `#/$defs/arbiter` | — |
| `arbitration_id` | yes | `string`<br>pattern: `"^arb-[a-f0-9]{16}$"` | — |
| `field_path` | yes | `string`<br>minLength: `1` | — |
| `occurred_at` | yes | `string`<br>format: `"date-time"` | — |
| `outcome` | yes | one of `"RESOLVED_2_OF_3"`, `"ALL_DIVERGE"` | — |
| `result_confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"` | — |
| `vote` | yes | reference to `#/$defs/vote` | — |

#### `$defs.arbitrationRequest`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `arbitration_id` | yes | `string`<br>pattern: `"^arb-[a-f0-9]{16}$"` | — |
| `candidates` | yes | `array`; items: reference to `#/$defs/publicCandidate`<br>minItems: `1` | — |
| `context_policy` | yes | reference to `#/$defs/contextPolicy` | — |
| `field_path` | yes | `string`<br>minLength: `1` | — |
| `source_spans` | yes | `array`; items: reference to `#/$defs/arbitrationSpan` | — |
| `span_binding_status` | yes | one of `"VERIFIED"`, `"PARTIAL"`, `"UNVERIFIED"` | — |
| `status` | yes | one of `"PENDING"`, `"RESOLVED_2_OF_3"`, `"ALL_DIVERGE"` | — |

#### `$defs.arbitrationSpan`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact_sha256` | yes | reference to `#/$defs/sha256` | — |
| `bbox` | yes | reference to `#/$defs/bbox` | — |
| `description` | yes | `string`<br>minLength: `1` | — |

#### `$defs.artifact`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `binding_status` | yes | one of `"VERIFIED"`, `"SINGLE_READER_HASH"`, `"PATH_ONLY_UNVERIFIED"` | — |
| `path` | yes | `string`<br>minLength: `1` | — |
| `regions` | yes | `array`; items: reference to `#/$defs/artifactRegion` | — |
| `sha256` | yes | oneOf: reference to `#/$defs/sha256` / `null` | — |

#### `$defs.artifactRegion`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `act_region` | yes | reference to `#/$defs/bbox` | — |
| `height_px` | yes | `integer`<br>minimum: `1` | — |
| `page_index` | yes | `integer`<br>minimum: `0` | — |
| `source_label_id` | yes | `string`<br>minLength: `1` | — |
| `width_px` | yes | `integer`<br>minimum: `1` | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.candidate`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `candidate_id` | yes | `string`<br>pattern: `"^cand-[a-f0-9]{16}$"` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"`, `"UNVERIFIED"`, `"UNREPORTED"` | — |
| `original_script` | yes | `string` or `null` | — |
| `reader_family` | yes | `string`<br>minLength: `1` | — |
| `reader_id` | yes | `string`<br>minLength: `1` | — |
| `reader_label_id` | yes | `string` or `null` | — |
| `reported` | yes | `boolean` | — |
| `reported_alternatives` | yes | `array`; items: reference to `#/$defs/reportedAlternative` | — |
| `source_kind` | yes | one of `"BLIND_READER_LABEL"`, `"ARBITER_VOTE"` | — |
| `source_span_ids` | yes | `array`; items: `string`<br>unique items | — |
| `value` | yes | unconstrained | — |

#### `$defs.clerkYear`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `binding_status` | yes | one of `"VERIFIED"`, `"SINGLE_READER_METADATA"`, `"UNVERIFIED"` | — |
| `id` | yes | `string`<br>minLength: `1` | — |
| `source_label_ids` | yes | `array`; items: `string`<br>unique items | — |

#### `$defs.compliance`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `privacy_binding_status` | yes | one of `"ALL_READERS_ATTESTED"`, `"SINGLE_READER_ATTESTED"` | — |
| `privacy_decision` | yes | one of `"ALLOW"`, `"REFUSE"` | — |
| `restricted_sources_status` | yes | one of `"ALL_READERS_ATTESTED"`, `"SINGLE_READER_ATTESTED"` | — |
| `restricted_sources_used` | yes | constant `false` | — |
| `training_basis` | yes | `string`<br>minLength: `1` | — |
| `training_eligible` | yes | `boolean` | — |

#### `$defs.confidenceSummary`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `confident_eligible_count` | yes | `integer`<br>minimum: `0` | — |
| `dual_disagreement_count` | yes | `integer`<br>minimum: `0` | — |
| `exact_agreement_count` | yes | `integer`<br>minimum: `0` | — |
| `field_count` | yes | `integer`<br>minimum: `1` | — |
| `probable_count` | yes | `integer`<br>minimum: `0` | — |
| `unclear_count` | yes | `integer`<br>minimum: `0` | — |
| `unresolved_state_count` | yes | `integer`<br>minimum: `0` | — |
| `validator_finding_count` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.consensusField`

Type: `object`; allOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `candidates` | yes | `array`; items: reference to `#/$defs/candidate`<br>minItems: `2` | — |
| `confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"`, `null` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"`, `"UNVERIFIED"`, `"UNRESOLVED"` | — |
| `original_script` | yes | `string` or `null` | — |
| `resolution` | yes | reference to `#/$defs/resolution` | — |
| `validator_finding_ids` | yes | `array`; items: `string`<br>unique items | — |
| `value` | yes | unconstrained | — |

#### `$defs.contextPolicy`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `full_labels_hidden` | yes | constant `true` | — |
| `reader_identities_hidden` | yes | constant `true` | — |
| `span_and_candidates_only` | yes | constant `true` | — |

#### `$defs.correctionEvent`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `consent` | yes | `object`<br>additional properties are not allowed | — |
| `correction_id` | yes | `string`<br>minLength: `1` | — |
| `corrector` | yes | `object`<br>additional properties are not allowed | — |
| `field_path` | yes | `string`<br>minLength: `1` | — |
| `occurred_at` | yes | `string`<br>format: `"date-time"` | — |
| `prior_record_sha256` | yes | reference to `#/$defs/sha256` | — |
| `replacement` | yes | reference to `#/$defs/consensusField` | — |
| `source_crop_sha256` | yes | reference to `#/$defs/sha256` | — |

#### `$defs.derivation`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `confidence_summary` | yes | reference to `#/$defs/confidenceSummary` | — |
| `method` | yes | constant `"blind-field-consensus"` | — |
| `pair_assessment` | yes | reference to `#/$defs/pairAssessment` | — |
| `policy_version` | yes | constant `"1.0.0"` | — |
| `source_labels` | yes | `array`; items: reference to `#/$defs/sourceLabel`<br>minItems: `2` | — |

#### `$defs.finding`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `blocks_confident` | yes | `boolean` | — |
| `code` | yes | `string`<br>minLength: `1` | — |
| `evidence` | yes | unconstrained | — |
| `field_paths` | yes | `array`; items: `string` | — |
| `finding_id` | yes | `string`<br>pattern: `"^finding-[a-f0-9]{16}$"` | — |
| `message` | yes | `string`<br>minLength: `1` | — |
| `record_ids` | yes | `array`; items: `string`<br>minItems: `1`; unique items | — |
| `severity` | yes | `string`<br>minLength: `1` | — |

#### `$defs.mention`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `mention_id` | yes | `string`<br>pattern: `"^[a-z0-9-]+#[a-z0-9-]+$"` | — |
| `metadata_status` | yes | one of `"AGREED"`, `"SINGLE_READER_METADATA"` | — |
| `role` | yes | one of `"principal"`, `"father"`, `"mother"`, `"spouse"`, `"spouse_father"`, `"spouse_mother"`, `"declarant"`, `"witness"`, `"officiant"`, `"survivor"` | — |
| `source_label_ids` | yes | `array`; items: `string`<br>minItems: `1`; unique items | — |

#### `$defs.pairAssessment`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact_binding_verified` | yes | `boolean` | — |
| `blind_group_verified` | yes | `boolean` | — |
| `clerk_year_verified` | yes | `boolean` | — |
| `fully_verified` | yes | `boolean` | — |
| `notes` | yes | `array`; items: `string` | — |
| `prompt_binding_verified` | yes | `boolean` | — |

#### `$defs.provenanceErratum`

Type: `object`; oneOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `canonical_sha256` | yes | constant `"88e56abd110b1f206a2d4cf0d699fbd449e667ea810ae1854a0c6a8d63269d82"` | — |
| `claimed_hash_field_status` | yes | one of `"ABSENT_IN_FILE"`, `"PRESENT_STALE"` | — |
| `claimed_sha256` | yes | oneOf: reference to `#/$defs/sha256` / `null` | — |
| `code` | yes | constant `"PROVENANCE_ERRATA"` | — |
| `coordinator_reported_sha256` | yes | constant `"a2e6c50ca84a2e0141dfc785680a79429372e54e882120b6d908cefdad110fe5"` | — |
| `effect` | yes | constant `"CONTENT_STANDS_PROMPT_BINDING_UNVERIFIED"` | — |
| `kind` | yes | constant `"STALE_INTERMEDIATE_PROMPT_HASH"` | — |
| `prompt_version` | yes | constant `"1.0.0"` | — |
| `source` | yes | constant `"labels/consensus/FOR_SOL_wave002_brief.md#1-prompt-hash-drift-resolved"` | — |
| `status` | yes | constant `"KNOWN_ERRATUM"` | — |

#### `$defs.publicCandidate`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `candidate_id` | yes | `string`<br>pattern: `"^cand-[a-f0-9]{16}$"` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"`, `"UNVERIFIED"` | — |
| `original_script` | yes | `string` or `null` | — |
| `reported_alternatives` | yes | `array`; items: reference to `#/$defs/reportedAlternative` | — |
| `value` | yes | unconstrained | — |

#### `$defs.readerIdentity`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `mode` | yes | one of `"subscription_session"`, `"local"` | — |
| `reader_family` | yes | `string`<br>minLength: `1` | — |
| `reader_id` | yes | `string`<br>minLength: `1` | — |
| `reader_version` | yes | `string`<br>minLength: `1` | — |

#### `$defs.reportedAlternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null` | — |
| `value` | yes | unconstrained | — |

#### `$defs.resolution`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `arbitration_id` | yes | `string` or `null` | — |
| `confidence_cap` | yes | one of `"CONFIDENT_ELIGIBLE"`, `"PROBABLE"`, `"UNCLEAR"` | — |
| `confidence_eligible` | yes | `boolean` | — |
| `reason` | yes | `string`<br>minLength: `1` | — |
| `status` | yes | one of `"EXACT_AGREEMENT"`, `"DUAL_DISAGREEMENT"`, `"ARBITRATED_2_OF_3"`, `"ARBITRATION_ALL_DIVERGE"` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.sourceLabel`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact_binding_verified` | yes | `boolean` | — |
| `binding_notes` | yes | `array`; items: `string` | — |
| `blind_attested` | yes | constant `true` | — |
| `blind_group_id` | yes | `string` or `null` | — |
| `clerk_year_id` | yes | `string` or `null` | — |
| `label_id` | yes | `string`<br>minLength: `1` | — |
| `prompt_binding_verified` | yes | `boolean` | — |
| `prompt_sha256` | yes | oneOf: reference to `#/$defs/sha256` / `null` | — |
| `provenance_errata` | yes | `array`; items: reference to `#/$defs/provenanceErratum` | — |
| `reader` | yes | reference to `#/$defs/readerIdentity` | — |
| `schema_kind` | yes | one of `"canonical"`, `"legacy_reader_a"` | — |
| `source_path` | yes | `string` or `null` | — |
| `source_sha256` | yes | oneOf: reference to `#/$defs/sha256` / `null` | — |

#### `$defs.target`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `act_no` | yes | oneOf: `integer` / `null` | — |
| `act_type` | yes | one of `"birth"`, `"marriage"`, `"death"`, `"annex"`, `"index_page"` | — |
| `fond` | yes | `string`<br>minLength: `1` | — |
| `language` | yes | one of `"ru"`, `"pl"`, `"mixed"`, `"unknown"` | — |
| `town` | yes | `string`<br>minLength: `1` | — |
| `year` | yes | `integer`<br>minimum: `1800`; maximum: `2100` | — |

#### `$defs.validation`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `findings` | yes | `array`; items: reference to `#/$defs/finding` | — |
| `policy_version` | yes | constant `"1.0.0"` | — |

#### `$defs.vote`

Type: `object`; oneOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `novel_candidate` | yes | oneOf: reference to `#/$defs/publicCandidate` / `null` | — |
| `selected_candidate_id` | yes | `string` or `null` | — |


## AKTREADER LoRA adapter identity

Source: [`schemas/adapter-identity-1.0.0.schema.json`](../schemas/adapter-identity-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/adapter-identity-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | constant `"../schemas/adapter-identity-1.0.0.schema.json"` | — |
| `adapter` | yes | reference to `#/$defs/pin` | — |
| `adapter_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `base_model` | yes | reference to `#/$defs/pin` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `trainer_runtime` | yes | `object`<br>additional properties are not allowed | — |
| `training_export` | yes | reference to `#/$defs/pin` | — |
| `training_recipe` | yes | reference to `#/$defs/pin` | — |
| `verification` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.pin`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `path` | yes | `string`<br>minLength: `1` | — |
| `sha256` | yes | `string`<br>pattern: `"^[a-f0-9]{64}$"` | — |


## AKTREADER adjudication answers

Source: [`schemas/adjudication-answers-1.0.0.schema.json`](../schemas/adjudication-answers-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/adjudication-answers-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string`<br>pattern: `"adjudication-answers-1\\.0\\.0\\.schema\\.json$"` | — |
| `answered_at` | yes | `string`<br>format: `"date-time"` | — |
| `answers` | yes | `array`; items: `object`<br>minItems: `1` | — |
| `packet_id` | yes | `string`<br>minLength: `1` | — |
| `questions_sha256` | yes | reference to `#/$defs/sha256` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `spec_sha256` | yes | reference to `#/$defs/sha256` | — |
| `verifier` | yes | `object`<br>additional properties are not allowed | — |
| `wave_id` | yes | `string`<br>minLength: `1` | — |

### Reusable definitions

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._


## AKTREADER adjudication wave

Source: [`schemas/adjudication-wave-1.0.0.schema.json`](../schemas/adjudication-wave-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/adjudication-wave-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string`<br>pattern: `"adjudication-wave-1\\.0\\.0\\.schema\\.json$"` | — |
| `exemplar_catalog` | yes | `array`; items: reference to `#/$defs/exemplar` | — |
| `questions` | yes | `array`; items: reference to `#/$defs/question`<br>minItems: `1` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `title` | yes | `string`<br>minLength: `1` | — |
| `wave_id` | yes | `string`<br>pattern: `"^[a-zA-Z0-9_-]+$"` | — |

### Reusable definitions

#### `$defs.anchor`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact` | yes | reference to `#/$defs/imageRegion` | — |
| `label` | yes | `string`<br>minLength: `1` | — |
| `plain_text` | yes | `string`<br>minLength: `1` | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.candidate`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `benchmark_eligible` | no | `boolean` | — |
| `candidate_id` | yes | `string`<br>pattern: `"^[a-zA-Z0-9_-]+$"` | — |
| `consequence` | yes | `string`<br>minLength: `1` | — |
| `correction_eligible` | no | `boolean` | — |
| `effect` | no | one of `"ATTEST_FIELD"`, `"ROUTE_EXPERT"` | — |
| `glyph` | yes | `string`<br>minLength: `1`; maxLength: `4` | — |
| `label` | yes | `string`<br>minLength: `1` | — |
| `value` | yes | unconstrained | — |

#### `$defs.comparisonEvidence`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact` | yes | reference to `#/$defs/imageRegion` | — |
| `evidence_id` | yes | `string`<br>pattern: `"^[a-zA-Z0-9_-]+$"` | — |
| `label` | yes | `string`<br>minLength: `1` | — |
| `plain_text` | yes | `string`<br>minLength: `1` | — |

#### `$defs.exemplar`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact` | yes | reference to `#/$defs/imageRegion` | — |
| `clerk_year_id` | yes | `string`<br>minLength: `1` | — |
| `confidence` | yes | constant `"UNCONTESTED"` | — |
| `exemplar_id` | yes | `string`<br>pattern: `"^[a-zA-Z0-9_-]+$"` | — |
| `glyph` | yes | `string`<br>minLength: `1`; maxLength: `4` | — |
| `label` | yes | `string`<br>minLength: `1` | — |
| `text` | yes | `string`<br>minLength: `1` | — |

#### `$defs.imageRegion`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `bbox` | yes | reference to `#/$defs/bbox` | — |
| `character_index` | no | `integer`<br>minimum: `0` | — |
| `glyph_bbox` | no | reference to `#/$defs/bbox` | — |
| `path` | yes | `string`<br>minLength: `1` | — |
| `sha256` | yes | reference to `#/$defs/sha256` | — |

#### `$defs.question`

Type: `object`; allOf: unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `artifact` | yes | allOf: reference to `#/$defs/imageRegion` / unconstrained | — |
| `bilingual_anchors` | yes | `array`; items: reference to `#/$defs/anchor` | — |
| `candidates` | yes | `array`; items: reference to `#/$defs/candidate`<br>minItems: `2`; maxItems: `4` | — |
| `cant_tell_consequence` | yes | `string`<br>minLength: `1` | — |
| `claim` | yes | `string`<br>minLength: `1` | — |
| `clerk_year_id` | yes | `string`<br>minLength: `1` | — |
| `comparison_evidence` | no | `array`; items: reference to `#/$defs/comparisonEvidence`<br>minItems: `1`; maxItems: `5` | — |
| `field_path` | yes | `string`<br>minLength: `1` | — |
| `magnification` | no | `integer`<br>minimum: `4`; maximum: `8` | — |
| `neither_consequence` | yes | `string`<br>minLength: `1` | — |
| `question` | yes | `string`<br>minLength: `1` | — |
| `question_id` | yes | `string`<br>pattern: `"^[a-zA-Z0-9_-]+$"` | — |
| `record_id` | yes | `string`<br>minLength: `1` | — |
| `record_sha256` | yes | reference to `#/$defs/sha256` | — |
| `review_mode` | no | one of `"LETTERFORM_CHOICE"`, `"VISUAL_CORROBORATION"` | — |
| `selection_reason` | yes | one of `"IDENTITY_FORK"`, `"MACHINE_DEADLOCK"`, `"CORROBORATION_CONFLICT"`, `"GOLD_SINGLE_COVERAGE"`, `"EXCLUDE_TRANSCRIPTION_QUEUE"` | — |
| `structural_checks` | yes | `array`; items: reference to `#/$defs/structuralCheck` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.structuralCheck`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `interpretation` | yes | `string`<br>minLength: `1` | — |
| `label` | yes | `string`<br>minLength: `1` | — |
| `result` | yes | one of `"SUPPORTS"`, `"CONTRADICTS"`, `"NEUTRAL"` | — |


## AKTREADER per-field gold attestation sidecar

Source: [`schemas/gold-attestation-1.0.0.schema.json`](../schemas/gold-attestation-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/gold-attestation-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

A human-attested provenance contract for fields proposed as benchmark gold. Machine-reader transcription support is deliberately not part of this contract.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string`<br>pattern: `"gold-attestation-1\\.0\\.0\\.schema\\.json$"` | — |
| `field_attestations` | yes | `object`<br>minProperties: `1` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `record_sha256` | yes | reference to `#/$defs/sha256` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |

### Reusable definitions

#### `$defs.attestation`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `adjudication_packet_sha256` | no | oneOf: reference to `#/$defs/sha256` / `null` | — |
| `attested_at` | yes | `string`<br>format: `"date-time"` | — |
| `attestor_id` | yes | `string`<br>minLength: `1` | — |
| `method` | yes | one of `"LETTERFORM_LINEUP"`, `"BILINGUAL_ANCHOR"`, `"INDEX_CROSS_CHECK"`, `"DIRECT_SCRIPT_READING"`, `"STRUCTURAL_CROSS_CHECK"`, `"RESEARCH_NOTE_EXTRACTION"` | — |
| `verbatim_answer` | yes | `string`<br>minLength: `1` | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.fieldAttestation`

Type: `object`; allOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `attestation` | yes | reference to `#/$defs/attestation` | — |
| `benchmark_eligible` | yes | `boolean` | — |
| `evidence_class` | yes | one of `"VERIFIED_FROM_IMAGE"`, `"DERIVED_FROM_RESEARCH"` | — |
| `image_reference` | yes | reference to `#/$defs/imageReference` | — |

#### `$defs.imageReference`

Type: `object`; oneOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `act_locator` | no | `string`<br>minLength: `1` | — |
| `artifact_sha256` | yes | reference to `#/$defs/sha256` | — |
| `region` | no | reference to `#/$defs/bbox` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._


## AktReader human qualification adjudication

Source: [`schemas/human-qualification-adjudication-1.0.0.schema.json`](../schemas/human-qualification-adjudication-1.0.0.schema.json)

Schema ID: `https://aktreader.local/schemas/human-qualification-adjudication-1.0.0.schema.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | constant `"../schemas/human-qualification-adjudication-1.0.0.schema.json"` | — |
| `adjudicator` | yes | `object`<br>additional properties are not allowed | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `intake_report` | yes | reference to `#/$defs/pin` | — |
| `packet_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `records` | yes | `array`; items: reference to `#/$defs/record`<br>minItems: `1` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |

### Reusable definitions

#### `$defs.assessment`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `candidate_code` | yes | `string`<br>pattern: `"^[A-Z][A-Z0-9-]+$"` | — |
| `character_error_count` | yes | `integer`<br>minimum: `0` | — |
| `independence_declaration_complete` | yes | `boolean` | — |
| `legible_character_count` | yes | `integer`<br>minimum: `1` | — |
| `material_error_count` | yes | `integer`<br>minimum: `0` | — |
| `material_hallucination_count` | yes | `integer`<br>minimum: `0` | — |
| `notes` | yes | `array`; items: `string` | — |
| `original_spelling_preserved` | yes | `boolean` | — |
| `uncertain_regions_guessed_count` | yes | `integer`<br>minimum: `0` | — |
| `unreadable_regions_marked` | yes | `boolean` | — |

#### `$defs.pin`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `path` | yes | `string`<br>minLength: `1` | — |
| `sha256` | yes | `string`<br>pattern: `"^[a-f0-9]{64}$"` | — |

#### `$defs.record`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `adjudicated_original_script` | yes | `string`<br>minLength: `1` | — |
| `candidate_assessments` | yes | `array`; items: reference to `#/$defs/assessment`<br>minItems: `1` | — |
| `line_count` | yes | `integer`<br>minimum: `1` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |


## AktReader human transcription submission

Source: [`schemas/human-transcription-submission-1.0.0.schema.json`](../schemas/human-transcription-submission-1.0.0.schema.json)

Schema ID: `https://aktreader.local/schemas/human-transcription-submission-1.0.0.schema.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | no | `string`<br>minLength: `1` | — |
| `artifact` | yes | `object`<br>additional properties are not allowed | — |
| `assignment_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `source_language` | yes | one of `"pl"`, `"ru"` | — |
| `submitted_at` | yes | `string`<br>format: `"date-time"` | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |
| `worker` | yes | `object`<br>additional properties are not allowed | — |


## AKTREADER bounded model-facing output

Source: [`schemas/model-output-1.0.0.schema.json`](../schemas/model-output-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/model-output-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `observations` | yes | `object`<br>minProperties: `1`; maxProperties: `128` | — |
| `target_check` | yes | `object`<br>additional properties are not allowed | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null`<br>maxLength: `512` | — |
| `value` | yes | reference to `#/$defs/scalarValue` | — |

#### `$defs.evidence`

Type: oneOf: `object` / `object` / `object`.

_No named properties._

#### `$defs.nonPlaceholderString`

Type: `string`.

Constraints: maxLength: `512`.

_No named properties._

#### `$defs.scalarValue`

Type: anyOf: reference to `#/$defs/nonPlaceholderString` / `integer` / `number` / `boolean` / `null`.

_No named properties._


## AKTREADER v1.4 grounded bounded model-facing output

Source: [`schemas/model-output-1.1.0.schema.json`](../schemas/model-output-1.1.0.schema.json)

Schema ID: `https://aktreader.org/schema/model-output-1.1.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `observations` | yes | `object`<br>minProperties: `1`; maxProperties: `128` | — |
| `target_check` | yes | `object`<br>additional properties are not allowed | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null`<br>maxLength: `512` | — |
| `value` | yes | reference to `#/$defs/scalarValue` | — |

#### `$defs.evidence`

Type: oneOf: `object` / `object` / `object`.

_No named properties._

#### `$defs.nonPlaceholderString`

Type: `string`.

Constraints: maxLength: `512`.

_No named properties._

#### `$defs.scalarValue`

Type: anyOf: reference to `#/$defs/nonPlaceholderString` / `integer` / `number` / `boolean` / `null`.

_No named properties._


## AKTREADER immutable Reader observation label

Source: [`schemas/reader-label-1.0.0-v1.2.schema.json`](../schemas/reader-label-1.0.0-v1.2.schema.json)

Schema ID: `https://aktreader.org/schema/reader-label-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string` | — |
| `artifact` | yes | `object`<br>additional properties are not allowed | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `clerk_year` | yes | `object`<br>additional properties are not allowed | — |
| `compliance` | yes | `object`<br>additional properties are not allowed | — |
| `created_at` | yes | `string`<br>format: `"date-time"` | — |
| `label_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `mentions` | yes | `array`; items: reference to `#/$defs/mention` | — |
| `observations` | yes | `object`<br>minProperties: `1` | — |
| `prompt` | yes | `object`<br>additional properties are not allowed | — |
| `reader` | yes | `object`<br>additional properties are not allowed | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `source_spans` | yes | `object`<br>minProperties: `1` | — |
| `target` | yes | `object`<br>additional properties are not allowed | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null` | — |
| `value` | yes | unconstrained | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.evidence`

Type: `object`; allOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `alternatives` | yes | `array`; items: reference to `#/$defs/alternative` | — |
| `confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"`, `null` | — |
| `notes` | yes | `array`; items: `string` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"` | — |
| `original_script` | yes | `string` or `null` | — |
| `source_span_ids` | yes | `array`; items: `string`<br>minItems: `1`; unique items | — |
| `value` | yes | unconstrained | — |

#### `$defs.mention`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `mention_id` | yes | `string`<br>pattern: `"^[a-z0-9-]+#[a-z0-9-]+$"` | — |
| `role` | yes | one of `"principal"`, `"father"`, `"mother"`, `"spouse"`, `"spouse_father"`, `"spouse_mother"`, `"declarant"`, `"witness"`, `"officiant"`, `"survivor"` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.sourceSpan`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `bbox` | yes | reference to `#/$defs/bbox` | — |
| `description` | yes | `string`<br>minLength: `1` | — |


## AKTREADER v1.4 grounded Reader observation label

Source: [`schemas/reader-label-1.0.0-v1.4.schema.json`](../schemas/reader-label-1.0.0-v1.4.schema.json)

Schema ID: `https://aktreader.org/schema/reader-label-1.0.0-v1.4.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string` | — |
| `artifact` | yes | `object`<br>additional properties are not allowed | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `clerk_year` | yes | `object`<br>additional properties are not allowed | — |
| `compliance` | yes | `object`<br>additional properties are not allowed | — |
| `created_at` | yes | `string`<br>format: `"date-time"` | — |
| `label_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `mentions` | yes | `array`; items: reference to `#/$defs/mention` | — |
| `observations` | yes | `object`<br>minProperties: `1` | — |
| `prompt` | yes | `object`<br>additional properties are not allowed | — |
| `reader` | yes | `object`<br>additional properties are not allowed | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `source_spans` | yes | `object`<br>minProperties: `1` | — |
| `target` | yes | `object`<br>additional properties are not allowed | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null` | — |
| `value` | yes | unconstrained | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.evidence`

Type: `object`; allOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `alternatives` | yes | `array`; items: reference to `#/$defs/alternative` | — |
| `confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"`, `null` | — |
| `notes` | yes | `array`; items: `string` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"` | — |
| `original_script` | yes | `string` or `null` | — |
| `source_span_ids` | yes | `array`; items: `string`<br>minItems: `1`; unique items | — |
| `value` | yes | unconstrained | — |

#### `$defs.mention`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `mention_id` | yes | `string`<br>pattern: `"^[a-z0-9-]+#[a-z0-9-]+$"` | — |
| `role` | yes | one of `"principal"`, `"father"`, `"mother"`, `"spouse"`, `"spouse_father"`, `"spouse_mother"`, `"declarant"`, `"witness"`, `"officiant"`, `"survivor"` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.sourceSpan`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `bbox` | yes | reference to `#/$defs/bbox` | — |
| `description` | yes | `string`<br>minLength: `1` | — |


## AKTREADER immutable Reader observation label

Source: [`schemas/reader-label-1.0.0.schema.json`](../schemas/reader-label-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/reader-label-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | `string` | — |
| `artifact` | yes | `object`<br>additional properties are not allowed | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `clerk_year` | yes | `object`<br>additional properties are not allowed | — |
| `compliance` | yes | `object`<br>additional properties are not allowed | — |
| `created_at` | yes | `string`<br>format: `"date-time"` | — |
| `label_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9._-]+$"` | — |
| `mentions` | yes | `array`; items: reference to `#/$defs/mention` | — |
| `observations` | yes | `object`<br>minProperties: `1` | — |
| `prompt` | yes | `object`<br>additional properties are not allowed | — |
| `reader` | yes | `object`<br>additional properties are not allowed | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `source_spans` | yes | `object`<br>minProperties: `1` | — |
| `target` | yes | `object`<br>additional properties are not allowed | — |
| `transcription` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null` | — |
| `value` | yes | unconstrained | — |

#### `$defs.bbox`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `coordinate_space` | yes | constant `"source_pixels"` | — |
| `height` | yes | `integer`<br>minimum: `1` | — |
| `width` | yes | `integer`<br>minimum: `1` | — |
| `x` | yes | `integer`<br>minimum: `0` | — |
| `y` | yes | `integer`<br>minimum: `0` | — |

#### `$defs.evidence`

Type: `object`; allOf: unconstrained / unconstrained.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `alternatives` | yes | `array`; items: reference to `#/$defs/alternative` | — |
| `confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"`, `null` | — |
| `notes` | yes | `array`; items: `string` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"` | — |
| `original_script` | yes | `string` or `null` | — |
| `source_span_ids` | yes | `array`; items: `string`<br>minItems: `1`; unique items | — |
| `value` | yes | unconstrained | — |

#### `$defs.mention`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `mention_id` | yes | `string`<br>pattern: `"^[a-z0-9-]+#[a-z0-9-]+$"` | — |
| `role` | yes | one of `"principal"`, `"father"`, `"mother"`, `"spouse"`, `"spouse_father"`, `"spouse_mother"`, `"declarant"`, `"witness"`, `"officiant"`, `"survivor"` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.sourceSpan`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `bbox` | yes | reference to `#/$defs/bbox` | — |
| `description` | yes | `string`<br>minLength: `1` | — |


## AKTREADER materialized silver record

Source: [`schemas/silver-record-1.0.0.schema.json`](../schemas/silver-record-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/silver-record-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | constant `"../../schemas/silver-record-1.0.0.schema.json"` | — |
| `artifact` | yes | `object` | — |
| `authority_warning` | yes | constant `"extraction is not authority â€” verify against the scan"` | — |
| `clerk_year` | yes | `object`<br>additional properties are not allowed | — |
| `observations` | yes | `object`<br>minProperties: `1` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `resolution` | yes | `object`<br>additional properties are not allowed | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `source_spans` | yes | `object` | — |
| `target` | yes | `object` | — |
| `tier` | yes | constant `"SILVER"` | — |

### Reusable definitions

#### `$defs.alternative`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `original_script` | yes | `string` or `null` | — |
| `value` | yes | unconstrained | — |

#### `$defs.observation`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `alternatives` | yes | `array`; items: reference to `#/$defs/alternative` | — |
| `confidence` | yes | one of `"PROBABLE"`, `"UNCLEAR"`, `null` | — |
| `notes` | yes | `array`; items: `string` | — |
| `observation_state` | yes | one of `"PRESENT"`, `"ABSENT_ON_FORM"`, `"BLANK"`, `"STATED_UNKNOWN"`, `"ILLEGIBLE"` | — |
| `original_script` | yes | `string` or `null` | — |
| `source_span_ids` | yes | `array`; items: `string`<br>minItems: `1` | — |
| `value` | yes | unconstrained | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.sourceFile`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `path` | yes | `string`<br>minLength: `1` | — |
| `sha256` | yes | reference to `#/$defs/sha256` | — |


## AKTREADER silver-tier provenance manifest

Source: [`schemas/silver-tier-manifest-1.0.0.schema.json`](../schemas/silver-tier-manifest-1.0.0.schema.json)

Schema ID: `https://aktreader.org/schema/silver-tier-manifest-1.0.0.json`

### Field tree

#### `root`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `$schema` | yes | constant `"../../schemas/silver-tier-manifest-1.0.0.schema.json"` | — |
| `authority_warning` | yes | constant `"extraction is not authority — verify against the scan"` | — |
| `created_on` | yes | `string`<br>format: `"date"` | — |
| `quarantine` | yes | `array`; items: reference to `#/$defs/quarantineRecord` | — |
| `records` | yes | `array`; items: reference to `#/$defs/silverRecord`<br>minItems: `1` | — |
| `restricted_sources_used` | yes | constant `false` | — |
| `schema_version` | yes | constant `"1.0.0"` | — |
| `tier_definition` | yes | `object`<br>additional properties are not allowed | — |

### Reusable definitions

#### `$defs.provenance`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `arbitration_document` | yes | reference to `#/$defs/sourceFile` | — |
| `consensus_document` | yes | reference to `#/$defs/sourceFile` | — |
| `reader_a_prompt_binding` | yes | constant `"PROVENANCE_ERRATA_UNVERIFIED"` | — |
| `reader_b_prompt_sha256` | yes | constant `"88e56abd110b1f206a2d4cf0d699fbd449e667ea810ae1854a0c6a8d63269d82"` | — |
| `source_labels` | yes | `array`; items: reference to `#/$defs/sourceLabel`<br>minItems: `2`; maxItems: `2` | — |

#### `$defs.quarantineRecord`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `eval_eligible` | yes | constant `false` | — |
| `human_verified` | yes | constant `false` | — |
| `provenance` | yes | reference to `#/$defs/provenance` | — |
| `reason` | yes | `string`<br>minLength: `1` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `status` | yes | constant `"HUMAN_VERIFICATION_REQUIRED"` | — |
| `tier` | yes | `null` | — |
| `training_eligible` | yes | constant `false` | — |

#### `$defs.sha256`

Type: `string`.

Constraints: pattern: `"^[a-f0-9]{64}$"`.

_No named properties._

#### `$defs.silverRecord`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `clerk_year_id` | yes | `string`<br>minLength: `1` | — |
| `confidence_cap` | yes | constant `"PROBABLE"` | — |
| `eval_eligible` | yes | constant `false` | — |
| `human_verified` | yes | constant `false` | — |
| `provenance` | yes | reference to `#/$defs/provenance` | — |
| `record_id` | yes | `string`<br>pattern: `"^[a-z0-9][a-z0-9-]+$"` | — |
| `resolution_method` | yes | constant `"BLIND_2_OF_3_MACHINE_CONSENSUS"` | — |
| `resolved_fields` | yes | `object`<br>additional properties are not allowed | — |
| `tier` | yes | constant `"SILVER"` | — |
| `training_eligible` | yes | constant `false` | — |
| `training_materialized` | yes | constant `false` | — |

#### `$defs.sourceFile`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `path` | yes | `string`<br>minLength: `1` | — |
| `sha256` | yes | reference to `#/$defs/sha256` | — |

#### `$defs.sourceLabel`

Type: `object`.

Constraints: additional properties are not allowed.

| Field | Required | Type / structure | Description |
| --- | --- | --- | --- |
| `path` | yes | `string`<br>minLength: `1` | — |
| `reader_role` | yes | one of `"A"`, `"B"` | — |
| `sha256` | yes | reference to `#/$defs/sha256` | — |

