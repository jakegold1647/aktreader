# Self-hosted service foundation

The AKT Reader service foundation manages copies of local `.aktproj` projects, durable
backup jobs, verified backup restore, and password-protected local accounts with per-project
roles. It is deliberately a single-machine boundary: the normal service process binds only to
`127.0.0.1` and does not make the browser workbench available on a LAN or public address. The
supplied Compose setup uses a container-only listener solely so Docker can forward a host-loopback
port; it is not a LAN or public listener.

This is local collaborative review on one machine, not a production network deployment.
Authenticated owners, editors, and viewers can use the loopback workbench; text and layout saves
use optimistic revision checks, so stale writes return a conflict for the reviewer to reload. It
does not offer LAN/public hosting, external identity, invitations or password recovery, a complete
activity/audit policy, cross-device synchronization, or deployment hardening. Do not put it behind
a reverse proxy or expose its port.

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
role: `VIEWER` can inspect documents, revisions, layout, and recognition suggestions;
`EDITOR` can save text and layout corrections and queue backups or configured local recognition;
and `OWNER` has those capabilities plus local role administration.

Account creation remains a local CLI administration action. An `OWNER` can use the loopback
workbench to list existing local accounts and grant them a `VIEWER`, `EDITOR`, or `OWNER` role on
that project; passwords and password verifiers are never exposed to the browser. Owners cannot
change their own role through the service, and the underlying role store rejects an operation that
would leave a project with no owner. An existing service workspace is migrated in place on first
use; its existing projects remain inaccessible to HTTP sessions until an administrator grants a
role.

## Model and dataset artifact registry

The service can make a model or dataset file a named, immutable local artifact without running,
uploading, or trusting it. Register a regular local file together with the license identifier you
have reviewed, then attach it explicitly to a managed project:

```powershell
python -m aktreader service-artifact-register service-data serock-model.bin `
  --kind MODEL `
  --name "Serock baseline" `
  --license-id Apache-2.0 `
  --description "Local baseline HTR weights"
python -m aktreader service-project-attach-artifact service-data `
  --project-id <project-id> `
  --artifact-id <artifact-id>
```

Registration streams the file into `artifacts/sha256/<prefix>/<sha256>` and records its SHA-256,
byte count, declared license ID, kind, name, and description. It never fetches a model registry,
executes model code, accepts an archive directory, or asserts that a declared license is valid.
Registering repeated bytes can reuse the same local content object while preserving each explicit
metadata record.

Only an `OWNER` may attach an artifact through the service API. Project viewers can read the
attached metadata at `GET /api/projects/<project-id>/artifacts`; owners can list the remaining
registered choices at `GET /api/projects/<project-id>/available-artifacts` and attach one by ID.
The loopback workbench shows the attached model/dataset name, type, license, and SHA-256 prefix to
every authorized viewer, and gives owners an attachment selector. Neither API discloses a managed
filesystem path or serves artifact bytes. This gives projects an auditable model/dataset selection
boundary; reproducible training, evaluation, and publication receipts remain separate local
workflows.

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

This is a local-service foundation for shared review. It does not accept external identity or
expose a LAN listener.

## Collaborative browser workbench

Start the local service and open the loopback URL it prints (normally
`http://127.0.0.1:8780/`). Sign in with a local service account; the browser keeps the bearer
token only in memory for that tab.

The workbench lets an authorized reviewer choose a project, PAGE XML document, and page; view the
source image with line bounds; inspect current line revisions; and save a correction. J or Down
moves to the next line, K or Up moves to the previous line, and Ctrl/Command+Enter saves the
focused transcription for an editor or owner. Shortcuts do not steal keys from form fields other
than that explicit save shortcut. Image bytes are fetched only with the authenticated request, and
neither the API nor the page exposes a local filesystem path. `VIEWER` accounts can inspect, while
`EDITOR` and `OWNER` accounts can save.

Every save includes the line revision that was displayed. If another correction landed first, the
workbench shows the service's conflict message and reloads the current page instead of overwriting
it. **Undo latest correction** appends a new revision containing the prior text; it never deletes
the original correction and also rejects a stale revision. The activity panel lets any authorized
viewer browse those transcription, line, region, and reading-order revisions and jump to their
source page. It reports the editor, revision, and timestamp but never exposes historical text or a
local filesystem path. The source PAGE XML and image object remain immutable; only append-only
human revisions are created.

When the service is started with `--kraken-config`, editors and owners can queue local
recognition for the selected document. The resulting proposals appear beside the selected line.
**Use suggestion** copies a proposal into the transcription editor only; the reviewer must inspect
it and explicitly save to create a new human revision. Viewers can inspect proposals but cannot
apply or save them.

The **Recognition evaluation** panel reads
`GET /api/projects/<project-id>/documents/<manifest-sha256>/evaluations`. It recalculates CER,
WER, exact-line coverage, and line counts against the latest saved human corrections each time the
page reloads. With no saved human correction it reports that the result is not evaluable; it never
treats imported source text, a suggestion, or a pending review proposal as ground truth. The endpoint
does not persist a metric, promote a model, or change a transcription.

The workbench is a single service UI on loopback only. It is not a LAN/public deployment, does not
persist credentials in browser storage, and does not yet include presence indicators, comments,
or shared cursors.

## Collaborative layout API

The service exposes the imported PAGE XML layout without a filesystem path:

```text
GET /api/projects/<project-id>/documents/<manifest-sha256>/pages/<page-index>/layout
```

A signed-in `VIEWER` can inspect the current region polygons and reading order. An `EDITOR` or
`OWNER` can append audited geometry changes using these routes:

```text
POST /api/projects/<project-id>/line-geometry
POST /api/projects/<project-id>/region-geometry
POST /api/projects/<project-id>/reading-order
```

Every request must include the revision the editor saw as `expected_revision`; line changes also
include `source_span_id`, `polygon`, and `baseline`, while region changes include
`page_index`, `region_id`, and `polygon`. Reading-order changes include `page_index` and an
exact permutation of the imported `region_ids`. All three operations append revisions rather than
rewriting the original PAGE XML. A stale revision returns `409 Conflict`, so clients must reload
and explicitly reconcile before saving.

The browser workbench renders line and region outlines over the source image. An `EDITOR` or
`OWNER` can select an outline, drag its vertices, review the resulting JSON geometry, and save it
against the displayed revision. Line baseline JSON can also be edited explicitly. Region controls
move entries up or down before saving reading order. A stale save reloads the page rather than
overwriting another editor's revision.

The workbench does not provide simultaneous multi-pointer editing, comments, or presence tracking.

## Download revision-applied exports

A signed-in `VIEWER` (or higher role) can download the current effective document in three forms:

```text
GET /api/projects/<project-id>/documents/<manifest-sha256>/export/pagexml
GET /api/projects/<project-id>/documents/<manifest-sha256>/export/transcript
GET /api/projects/<project-id>/documents/<manifest-sha256>/export/transcriptions-csv
```

The PAGE XML response applies the latest human transcription, line-geometry, region-geometry,
and reading-order revisions to a fresh PAGE XML file. The transcript keeps source line order with
a form-feed between pages. The CSV retains stable page/region/line identifiers, imported text,
effective text, revision number, and editor.

All three responses are generated inside the service workspace and never accept a browser-supplied
output path or disclose managed filesystem paths. Text and CSV exports use imported text or the
latest saved human revision only: they do not apply HTR suggestions or pending offline-review
proposals. The workbench provides **Download PAGE XML**, **Download transcript**, and **Download
CSV** buttons using the in-memory bearer token.

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

The supplied `compose.yml` binds the service port to host loopback only and keeps workspace
state in `./service-data`. Inside the container it uses `--container-listen` solely for Docker
port forwarding; the Compose port mapping is the external boundary.

```powershell
docker compose run --rm aktreader service-create /data
docker compose run --rm aktreader service-add-project /data /imports/serock.aktproj
docker compose up --build
```

Put an importable project under `./projects-to-import`; Compose mounts that directory
read-only at `/imports` for the explicit copy step. Create an owner before starting the service,
using a temporary password file mounted read-only into a one-off command:

```powershell
docker compose run --rm `
  --volume "${PWD}/owner-password.txt:/run/secrets/owner-password.txt:ro" `
  aktreader service-user-create /data `
  --username owner `
  --password-file /run/secrets/owner-password.txt
```

Remove the password file after use, then add a project with `--owner owner`. The service is
reachable only from the host at `http://127.0.0.1:8780`. Do not change the host-side
`127.0.0.1:8780:8780` mapping or put the container behind a reverse proxy. Building the image
may download Python packages; the running application does not contact a network service.
