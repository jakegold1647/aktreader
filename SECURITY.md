# Security policy

## Current support boundary

AKT Reader is pre-1.0 software. The supported deployment is a local project or the documented
single-machine service bound to host loopback. The included Compose example publishes only to
`127.0.0.1`; it is not a supported LAN or public-internet deployment.

Do not place the service behind a reverse proxy, publish its port, or use it as a substitute for
an externally reviewed identity, authorization, audit, or backup system.

## Reporting a vulnerability

Please do not include source scans, transcriptions, passwords, session tokens, personal data, or
unpublished model files in a public issue.

Use GitHub's private vulnerability-reporting flow from the repository **Security** tab when it is
available. If that flow is unavailable, open a minimal sanitized issue requesting a private contact
channel. Include the affected version or commit, a clear reproduction using synthetic files, impact,
and any suggested mitigation.

## What to expect

Reports are triaged against the documented local-first boundary. Fixes are released through normal
public pull requests unless discussing the issue publicly would materially increase risk. This policy
does not promise a response-time SLA.

See [the threat model](docs/threat-model.md) and
[data-governance policy](docs/data-governance.md) before operating a service workspace.
