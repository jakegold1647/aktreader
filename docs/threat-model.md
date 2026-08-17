# Threat model: local and single-node service

This document describes the security boundary AKT Reader actually implements today. It is an
operator aid, not a claim that the application is suitable for public hosting.

## Deployment status

The normal workbench binds to `127.0.0.1`. The Compose setup uses a container listener only so
Docker can forward a host-loopback port. Neither mode is designed for LAN access, internet exposure,
reverse proxies, external identity providers, or multi-device synchronization.

## Assets to protect

- source images, PDFs, PAGE XML, effective transcriptions, and historical revisions;
- local account password verifiers and bearer sessions;
- managed-project and backup integrity;
- model/dataset artifact metadata and locally provisioned executable/model paths;
- human-review provenance, consent records, evaluation metrics, and export receipts.

## Trust boundaries

| Boundary | Implemented controls | Remaining operator responsibility |
| --- | --- | --- |
| Browser to loopback service | Short-lived bearer session, per-project viewer/editor/owner roles, request-size limits, no filesystem paths in browser responses. | Keep the machine and local browser profile trusted; do not expose the port. |
| Project storage | Local content-addressed imported objects, append-only revision tables, output paths outside the project for derivatives. | Protect disk access and choose a backup-retention policy. |
| Backup and restore | Deterministic archive manifest, checksums, path validation, and restore verification. | Store verified backups somewhere appropriate for the material; test recovery before relying on it. |
| Local artifacts and runtimes | SHA-256-pinned regular files, declared license metadata, no artifact-byte download through the service. | Review provenance, licensing, executable safety, and model behavior before registration. |
| HTR suggestions and metrics | Suggestions stay separate from human revisions; metrics and receipts pin the source import, HTR output, runtime fingerprint, and hashed human-revision set. | Review suggestions before saving, and interpret metrics only for representative reviewed material. |

## Explicit non-goals

The following are not provided and must not be inferred:

- public or LAN hosting, TLS termination, reverse-proxy hardening, or DDoS protection;
- external identity, invitations, password recovery, MFA, or enterprise audit retention;
- encrypted-at-rest project storage, key management, secure deletion, or malware scanning;
- sandboxing untrusted local model executables or proving a model/dataset license;
- automatic transcription acceptance, production accuracy claims, or a public data portal;
- high-availability, multi-node workers, load testing, or concurrent real-time editing.

## Common threats and practical mitigations

### Accidental public exposure

An operator may bind a service broadly or publish a Docker port. Keep the documented host-loopback
mapping, do not add a reverse proxy, and verify the URL shown by `service-serve` before sharing it.
Treat any machine that can reach a broadly exposed port as outside the supported threat model.

### Stolen local session or workstation access

A bearer token exists only in the active browser tab, but a person or process with control of the
workstation may still act as that browser user. Use OS accounts and disk protection appropriate to
the records, sign out when finished, and do not leave an authenticated browser open on shared
machines.

### Stale or conflicting review

Editors send the revision they saw. The service rejects stale text, geometry, and reading-order
writes rather than overwriting a newer revision. Reload and resolve the actual content difference;
do not bypass the conflict check.

### Malicious or malformed local input

PAGE XML, images, PDFs, review packages, artifacts, and backups are local but not automatically
trusted. Import and restore validation constrains paths, checksums, object types, and archive
members. Keep software dependencies current and use synthetic material when testing an unfamiliar
input source.

### Model supply chain and unsafe output

A registered model/dataset is only a local file with declared metadata and a hash. AKT Reader does
not execute arbitrary service artifacts, verify licenses, or prove a model safe. The configured
Kraken executable and model are operator-provisioned local dependencies. Review provenance and
license terms, pin bytes, and treat all recognition output as an untrusted proposal until a person
saves a correction.

### Data disclosure through exports

PAGE XML, transcript, CSV, review packages, training bundles, and evaluation receipts are separate
derivatives. Only create and distribute them when their content and recipients are appropriate.
Text/CSV exports intentionally omit model proposals; evaluation receipts omit raw transcription
text, source images, and filesystem paths.

## Operator checklist

Before using a service workspace with sensitive records:

1. Keep the service on one trusted machine and confirm it is bound/published only to loopback.
2. Use unique local account passwords and grant the least project role needed.
3. Review source rights, personal-data handling, and explicit training consent before imports or
   training exports.
4. Register only reviewed local model/dataset files, retaining their hashes and license records.
5. Create and verify backups, then perform a restore drill on a disposable location.
6. Review browser-visible exports and evaluation receipts before sharing them.
7. Record the deployed commit and local runtime/model hashes alongside substantive research outputs.

## Incident response

If a local account, browser session, workstation, project copy, backup, or export may have been
exposed, stop treating the workspace as confidential. Disconnect or stop the service, preserve
enough logs and hashes to understand the event, rotate or recreate affected local credentials, and
decide whether project copies and backups need to be replaced. Re-verify a clean backup before
restoring. Do not publish source records in a bug report.

For behavior that may be a product vulnerability, follow [SECURITY.md](../SECURITY.md).
