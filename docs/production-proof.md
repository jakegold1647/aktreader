# Local-service production proof

AKT Reader's self-hosted service is intentionally a single trusted-machine, loopback-only
deployment. This page records the repeatable evidence for its supported boundary; it is not a
claim that the project is safe to expose on a LAN or the public internet.

## Safety and governance

- [Threat model](threat-model.md): attack surfaces and the loopback deployment boundary.
- [Data-governance policy](data-governance.md): provenance, consent, privacy, and publication
  requirements.
- [Security policy](../SECURITY.md): disclosure process and supported versions.
- `tests/test_no_egress.py`: CI-enforced dependency and socket checks for the installed package.

## Restore and migration

`tests/test_service.py` verifies deterministic project backups, per-file hash verification, safe
restore to a new destination, and in-place creation of new managed training storage for an existing
service workspace. Restore does not overwrite a project, accept archive traversal, or trust an
unverified archive manifest.

## Accessibility contract

`tests/test_service_production_proof.py::test_loopback_workbench_has_accessibility_basics` requests
the rendered loopback workbench and checks its skip navigation, main landmark, labels for sign-in
and transcription controls, meaningful source-image alternative text, PAGE layout label, and live
status announcements. This is a lightweight semantic regression check, not a substitute for
assistive-technology testing with real reviewers.

## Bounded concurrency check

`tests/test_service_production_proof.py::test_loopback_service_handles_bounded_concurrent_review_reads`
starts the actual threaded loopback server, authenticates a reviewer, then runs 48 document-plus-page
read sequences with eight concurrent clients. Every response must remain authorized, local-only, and
successful, and the service must still pass its health check afterward. It is a deterministic
regression load check, not a capacity claim or benchmark.

Run the service proof suite locally:

```powershell
python -m pytest tests/test_service.py tests/test_service_production_proof.py -q
```

## Public demo

`examples/public-demo/` contains a synthetic PAGE XML document and a synthetic PPM image. It contains
no historical scan, personal data, model weight, benchmark label, or genealogy assertion. Follow its
[README](../examples/public-demo/README.md) to create a project and run the normal local and
loopback-service flows.

Do not infer handwriting accuracy, production hosting readiness, or archival provenance from the demo.
