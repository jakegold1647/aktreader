# Self-hosted service foundation

The AKT Reader service foundation manages copies of local `.aktproj` projects, durable
backup jobs, verified backup restore, and password-protected local accounts with per-project
roles. It is deliberately a single-machine boundary: the service binds only to
`127.0.0.1` and does not make the browser workbench available on a LAN or public address.

This is infrastructure for a future shared deployment, not that deployment. The service has
local authentication and role checks for its project and job API, but it does not yet offer
shared browser editing, external identity, password recovery, audit policy, or multi-user
conflict controls. Do not put it behind a reverse proxy or expose its port.

## Create and populate a workspace

Create an empty workspace, then copy an existing local project into service-owned storage.

```powershell
python -m aktreader service-create service-data
python -m aktreader service-add-project service-data serock.aktproj
python -m aktreader service-inspect service-data
```

The service does not operate on the original project path. It validates the project and
copies it to `service-data/projects/<project-id>.aktproj`, so backups have one managed
local storage boundary. The CLI returns project IDs, counts, and local paths; the HTTP
API intentionally omits source and archive filesystem paths.

## Local identities and access

Create local accounts before assigning project access. Password input comes from a UTF-8 local
file so the CLI never prints it or places it in command history; remove that file immediately
after use.

```powershell
python -m aktreader service-user-create service-data `
  --username owner `
  --password-file owner-password.txt
python -m aktreader service-add-project service-data serock.aktproj --owner owner
python -m aktreader service-grant-role service-data `
  --project-id <project-id> `
  --username reviewer `
  --role VIEWER
```

Accounts use a salted local `scrypt` password verifier. The service stores only the verifier,
and creates short-lived bearer sessions only through `POST /api/session`. `/api/projects`,
`/api/jobs/<job-id>`, and backup-job creation require a valid session and a matching project
role: `VIEWER` can view, `EDITOR` can queue backups, and `OWNER` has both capabilities.

Account creation and role assignment are local CLI administration actions, not public HTTP
endpoints. An existing service workspace is migrated in place on first use; its existing
projects remain inaccessible to HTTP sessions until an administrator grants a role.

## Authenticated review API

A signed-in `VIEWER` may list the project documents and load revision-aware PAGE records:

```text
GET /api/projects/<project-id>/documents
GET /api/projects/<project-id>/documents/<manifest-sha256>/pages/<page-index>
```

The page response includes source geometry, current text, revision numbers, suggestions, and queued
review proposals, but intentionally omits the managed image path. An `EDITOR` (or `OWNER`) can
append a human correction with the revision it was based on:

```json
{
  "manifest_sha256": "<document-manifest-sha256>",
  "source_span_id": "<PAGE-line-source-span>",
  "text": "corrected transcription",
  "expected_revision": 3
}
```

Send that object to `POST /api/projects/<project-id>/transcriptions` with the bearer session.
The service derives the revision editor from the authenticated account and writes an append-only
project revision. If someone has saved another revision first, it returns `409 Conflict`; reload
the page and explicitly decide how to reconcile the text. It never silently overwrites a correction.

This is an API foundation for shared review, not a shared browser editor yet: it does not serve
scan image bytes, accept external identity, or expose a LAN listener.

## Run and back up

Start the service only on the local machine:

```powershell
python -m aktreader service-serve service-data --port 8780
```

In another terminal, queue a backup using the managed project UUID from
`service-list-projects`:

```powershell
python -m aktreader service-list-projects service-data
python -m aktreader service-queue-backup service-data --project-id <project-id>
```

The worker persists jobs in `service.sqlite3`. A job that was running when the process
stopped returns to the pending queue on restart. `GET /api/healthz`, `GET /api/projects`,
and `GET /api/jobs/<job-id>` are the only service endpoints in this foundation; every
response declares `network_required: false`.

Each backup is a deterministic ZIP archive under
`service-data/backups/<project-id>/<snapshot-sha256>.aktbackup.zip`. It contains every
regular project file and `backup.aktreader.json`, whose sorted file manifest records
size and SHA-256 for each member. Archive names are content-derived; a repeated backup
of unchanged storage verifies and reuses the same archive.

## Verify and restore

Always verify a backup before retaining or restoring it:

```powershell
python -m aktreader service-backup-verify service-data/backups/<project-id>/<snapshot>.aktbackup.zip
python -m aktreader service-backup-restore `
  service-data/backups/<project-id>/<snapshot>.aktbackup.zip `
  recovered.aktproj
```

Restore verifies archive member names, duplicate entries, manifest schema, snapshot hash,
file sizes, and every file SHA-256 before writing to a new destination. It rejects
symbolic links, archive traversal paths, and an existing restore destination. The
restored directory is re-opened as an AKT Reader project before it is published.

## Optional local Compose process

The supplied `compose.yml` binds the service port to loopback only and keeps workspace
state in `./service-data`.

```powershell
docker compose run --rm aktreader service-create /data
docker compose run --rm aktreader service-add-project /data /imports/serock.aktproj
docker compose up --build
```

Put an importable project under `./projects-to-import`; Compose mounts that directory
read-only at `/imports` for the explicit copy step. The service is reachable only from
the host at `http://127.0.0.1:8780`. Building the image may download Python packages;
the running application does not contact a network service.
