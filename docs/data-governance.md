# Data governance policy

AKT Reader is local-first software for historical material. Local processing does not remove the
need to assess rights, privacy, consent, and downstream disclosure before import, collaboration,
training, or publication.

## Scope and roles

The operator decides which materials enter a project, who receives a local account, where backups
are retained, and which derivatives may leave the workspace. A project `OWNER` can administer
existing service accounts for that project; this technical role does not by itself establish legal
authority over the records.

Contributors remain responsible for the accuracy and rights status of the text they save. Model
suggestions, local runtime outputs, and imported source text are not evidence of permission to
train, distribute, or publish.

## Source material

Before import, confirm that the operator has an appropriate basis to copy, process, and share the
material. Assess at least:

- archive or collection terms, donor agreements, licenses, and contractual restrictions;
- living people, sensitive personal data, indigenous or community-held knowledge, and local law;
- image and transcription rights separately when they differ;
- whether collaborators need the full scan, the transcription, a redacted derivative, or no access.

The application copies imports into a project/service workspace. Source files therefore may exist in
more than one local location after use, including backups and operator-created exports.

## Training consent

Training is opt-in and line-level. A contributor can grant consent only for their current saved
human revision. A later edit becomes unconsented, and a revocation prevents a future consent-gated
training export relying on that grant.

Consent is a technical record, not a legal conclusion. Operators must still review dataset rights,
license compatibility, privacy obligations, contributor authority, and the provenance of every
source before running a training workflow or sharing a corpus.

## Collaboration and least access

Use a `VIEWER` role for inspection, `EDITOR` for people who must save corrections or layout
changes, and `OWNER` only for people who need role or artifact-attachment authority. Create local
accounts only for known collaborators. The service currently has no invitations, external identity,
password recovery, or cross-device synchronization.

Do not put raw records, passwords, access tokens, or private model files in GitHub issues, pull
requests, screenshots, or test fixtures.

## Exports, evaluation, and publication

Exports are new local files. PAGE XML may contain images and effective text; transcript and CSV
exports carry effective source/human text; review and training bundles have their own documented
contents. Evaluation receipts contain report metadata and hashes rather than raw transcription text,
but the metadata may still be sensitive in context.

Review every derivative before sharing. Keep a release record that identifies the source project,
revision/manifest hashes, recipients, permitted use, and any redactions. This repository does not
yet implement public read-only collections or a publication approval workflow.

## Retention, backup, and deletion

AKT Reader validates backup/restore integrity, but it does not implement a retention scheduler,
cryptographic erasure, or a guarantee that all operator-created copies are deleted. Decide retention
and disposal rules before use. Include the original import location, managed project, backup
archives, review packages, training bundles, downloaded exports, and any shared copies in a deletion
or access-revocation response.

Test restore procedures on a disposable location before relying on backups for essential records.

## Governance review

Revisit this policy when project scope, collaborators, source institutions, geographical
jurisdiction, model/dataset provenance, or publication plans change. For deployment-boundary
details, see [the threat model](threat-model.md); for vulnerability reporting, see
[SECURITY.md](../SECURITY.md).
