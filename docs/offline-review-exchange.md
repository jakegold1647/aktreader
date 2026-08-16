# Offline review exchange

AKT Reader projects are local by design. To let a reviewer return transcription work without a
server or account, use a checksummed review package. The package is a local JSON file; it carries
only current text proposals, their source PAGE XML checksum, source-span IDs, base-text hashes,
and the contributor label supplied by the reviewer.

This is an integrity and conflict-detection format, not an identity or signature system. A
contributor name is a local claim. Treat packages received from another person as untrusted input,
inspect them in the owner project, and use normal project-access controls when sharing scans.

## Reviewer: export a package

The reviewer works in a project containing the same source PAGE XML, saves human revisions under
their contributor label, then exports their current revisions:

    aktreader project-export-review-package E:\reviewer\register.aktproj --manifest-sha256 <reviewer-import-manifest-sha256> --contributor reviewer-1 --output E:\handoff\register-review.aktreview.json

The package excludes source images, PAGE XML files, local paths, model outputs, credentials, and
training-consent grants. Re-exporting unchanged reviewer revisions produces the same package
content and SHA-256. The command never overwrites an existing package unless
`--replace-existing` is explicit.

## Owner: queue and decide

Import the received local package into a project that has exactly one matching source PAGE XML:

    aktreader project-import-review-package E:\owner\register.aktproj E:\handoff\register-review.aktreview.json

The command verifies strict JSON keys, the package text checksums, the source PAGE XML checksum,
and every source span. Each proposal is stored as either `PENDING` when its base text still
matches the owner project or `CONFLICT` when the owner has already changed that line. Nothing is
applied during import. The JSON report returns the stable proposal SHA-256 values.

Accepting a pending proposal appends a new human revision under the owner/editor label; rejecting
it leaves the existing transcription unchanged:

    aktreader project-resolve-review-proposal E:\owner\register.aktproj --proposal-sha256 <proposal-sha256> --decision accept --editor owner-1

A proposal whose base changes after import becomes `CONFLICT` on attempted acceptance and must
be resolved manually in the workbench. Accepting a review proposal does not transfer authorship,
grant training consent, or change the immutable source PAGE XML. Any later training consent must
be recorded explicitly against the resulting current revision.
