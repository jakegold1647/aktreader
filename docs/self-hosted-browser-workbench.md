# Self-hosted browser workbench

The first browser surface is intentionally small: it exposes one existing local
`.aktproj` project to one browser on the same machine. It does not replace the
local desktop workbench, add an account system, or upload data.

## Start it

```powershell
python -m aktreader serve serock.aktproj
```

The command prints a URL such as `http://127.0.0.1:8765/`. Open that URL in a
browser on the same machine. Use `--port 0` to have the operating system choose
an available loopback port.

The server is not started by imports, project commands, or the desktop workbench.
Stop it with Ctrl+C.

## What it provides

- document-first and page-scoped navigation with bounded, server-generated page thumbnails;
- source-page image display with effective PAGE XML line polygons, optional
  baselines, and region polygons;
- effective transcription, local HTR suggestions, and pending review-proposal
  context for each line;
- an editor that appends the same human transcription revisions as the
  desktop workbench;
- direct on-canvas line-polygon and baseline-point dragging, with source-pixel
  text fields that also allow an absent baseline to be represented as `null`;
- line-polygon and baseline edits that append the same audited line-geometry
  revisions as the local project commands;
- direct on-canvas region-vertex dragging, with a source-pixel text fallback;
- region-polygon and region-reading-order edits that append the same audited
  PAGE layout revisions as the local project commands; and
- optimistic revision checks on every write so a stale tab cannot silently
  overwrite work saved after that tab loaded; and
- project state that remains content-addressed and local.

The API never sends image filesystem paths to the browser. Source images are
streamed only after their manifest and page index resolve through the local
project store.

## Security boundary

This is a single-user, loopback-only service. It binds exclusively to
`127.0.0.1`; there is no option to expose it on a LAN or the public internet.
It sends no CORS headers, accepts no remote model configuration, keeps responses
out of HTTP caches, and limits JSON write requests to 64 KiB.

There is no login or authorization layer yet. Any process able to make requests
from the same machine can use the browser workbench while it is running. Do not
treat this phase as a multi-user deployment. Authentication, role-based access,
review assignment, audit identity, and remotely hosted collaboration are separate
roadmap work.

The service does not make outbound network requests. `network_required: false`
means it needs no external network; the explicit loopback listener is only a
local browser transport.

## Concurrent tabs

Each transcription, line-geometry, region-polygon, and reading-order save
includes the exact revision displayed when that page was loaded. Line text and
line geometry have separate revision streams, so correcting one does not make
an untouched editor for the other stale. If another tab or local command saves
the same entity stream first, the stale request returns a conflict and does not
append another audit row. Reload the page, review the newer state, and then
decide whether to apply the edit again. A conflict never merges or retries
content automatically.
