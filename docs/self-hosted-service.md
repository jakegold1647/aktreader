# Self-hosted service foundation

The AKT Reader service foundation manages copies of local \`.aktproj\` projects, durable
backup jobs, and verified backup restore. It is deliberately a single-machine boundary:
the service binds only to \`127.0.0.1\`, has no accounts, and does not make the browser
workbench available on a LAN or public address.

This is infrastructure for a future shared deployment, not that deployment. Do not put
this process behind a reverse proxy or expose its port until authentication, authorization,
audit policy, and multi-user editing controls have been added and reviewed.

## Create and populate a workspace

Create an empty workspace, then copy an existing local project into service-owned storage.

\`\`\`powershell
python -m aktreader service-create service-data
python -m aktreader service-add-project service-data serock.aktproj
python -m aktreader service-inspect service-data
\`\`\`

The service does not operate on the original project path. It validates the project and
copies it to \`service-data/projects/<project-id>.aktproj\`, so backups have one managed
local storage boundary. The CLI returns project IDs, counts, and local paths; the HTTP
API intentionally omits source and archive filesystem paths.

## Run and back up

Start the service only on the local machine:

\`\`\`powershell
python -m aktreader service-serve service-data --port 8780
\`\`\`

In another terminal, queue a backup using the managed project UUID from
\`service-list-projects\`:

\`\`\`powershell
python -m aktreader service-list-projects service-data
python -m aktreader service-queue-backup service-data --project-id <project-id>
\`\`\`

The worker persists jobs in \`service.sqlite3\`. A job that was running when the process
stopped returns to the pending queue on restart. \`GET /api/healthz\`, \`GET /api/projects\`,
and \`GET /api/jobs/<job-id>\` are the only service endpoints in this foundation; every
response declares \`network_required: false\`.

Each backup is a deterministic ZIP archive under
\`service-data/backups/<project-id>/<snapshot-sha256>.aktbackup.zip\`. It contains every
regular project file and \`backup.aktreader.json\`, whose sorted file manifest records
size and SHA-256 for each member. Archive names are content-derived; a repeated backup
of unchanged storage verifies and reuses the same archive.

## Verify and restore

Always verify a backup before retaining or restoring it:

\`\`\`powershell
python -m aktreader service-backup-verify service-data/backups/<project-id>/<snapshot>.aktbackup.zip
python -m aktreader service-backup-restore \`
  service-data/backups/<project-id>/<snapshot>.aktbackup.zip \`
  recovered.aktproj
\`\`\`

Restore verifies archive member names, duplicate entries, manifest schema, snapshot hash,
file sizes, and every file SHA-256 before writing to a new destination. It rejects
symbolic links, archive traversal paths, and an existing restore destination. The
restored directory is re-opened as an AKT Reader project before it is published.

## Optional local Compose process

The supplied \`compose.yml\` binds the service port to loopback only and keeps workspace
state in \`./service-data\`.

\`\`\`powershell
docker compose run --rm aktreader service-create /data
docker compose up --build
\`\`\`

After importing a project with \`service-add-project\` (run the same way with
\`docker compose run --rm aktreader ...\`), the service is reachable only from the host
at \`http://127.0.0.1:8780\`. Building the image may download Python packages; the
running application does not contact a network service.
