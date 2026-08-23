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
- previous/next line controls, a live line-position readout, and keyboard
  navigation for sustained line-by-line review;
- bounded local search across effective transcription text, document titles,
  and document tags, with direct jumps to the matching line;
- a bounded, content-free recent-activity panel for the selected document,
  with revision-stream and current-location filters plus guarded jumps to the
  affected page, line, or region;
- an editor that appends the same human transcription revisions as the
  desktop workbench;
- direct on-canvas line-polygon and baseline-point dragging, with source-pixel
  text fields that also allow an absent baseline to be represented as `null`;
- line-polygon and baseline edits that append the same audited line-geometry
  revisions as the local project commands;
- direct on-canvas region-vertex dragging, with a source-pixel text fallback;
- region-polygon and region-reading-order edits that append the same audited
  PAGE layout revisions as the local project commands; and
- bounded, contentful history for the selected transcription, line geometry,
  region geometry, or page reading order, with append-only restoration of an
  explicitly selected older state;
- per-stream unsaved-draft detection that guards affected navigation and
  restoration, warns before a dirty tab reloads or closes, and preserves other
  streams' drafts when one stream is saved;
- optimistic revision checks on every write so a stale tab cannot silently
  overwrite work saved after that tab loaded; and
- project state that remains content-addressed and local.

The API never sends image filesystem paths to the browser. Source images are
streamed only after their manifest and page index resolve through the local
project store.

## Keyboard review

Use **Previous line** and **Next line** or press Alt+Up and Alt+Down while focus
is in the review panel. When focus is on a line in the line list, plain Up and
Down move to the adjacent line and keep focus in the list. Ctrl+Enter on Windows
and Linux, or Command+Enter on macOS, saves the current transcription through
the same audited revision path as the visible save button.

Changing lines still checks unsaved transcription and line-geometry drafts. If
either stream is dirty, the workbench asks before discarding it; cancelling keeps
the current line and draft selected.

## Find a line

Open **Find a line**, choose transcription text, document title, or document tag,
and enter a nonblank query. Search is case-insensitive, runs against the existing
local project index, and returns at most 50 lines. No query or result leaves the
loopback server. Results contain effective transcription text, so screenshots of
the panel need the same privacy care as the editor itself.

Each result names its document, page, line, and current text revision. Activating
one loads that exact line and moves keyboard focus to it. A jump to another line,
page, or document uses the normal unsaved-work confirmation across transcription,
line geometry, region geometry, and reading order. Cancelling leaves the current
selection and every draft in place.

## Recent changes

Open **Recent changes** to review the newest 50 human revisions for the selected
document. The panel reuses the same content-free project activity feed as the
`project-activity` command: each event includes its revision kind, page and line
or region locator, editor, revision number, and timestamp, but never prior or
revised transcription text or a local filesystem path.

Use **Stream** to show all revisions or one exact transcription, line-geometry,
region-geometry, or reading-order stream. Use **Scope** to keep the whole
document visible or narrow the feed to the current page, selected line, or
selected region. Page, line, and region filters follow the live workbench
selection. If the selected page has no line or region, the panel reports that
the scope is unavailable and shows no events; it never falls back to a wider
feed. Every filtered response remains capped at 50 events and content-free.

Selecting an event loads its page and, where available, its exact line or region.
The jump uses the same unsaved-work confirmation as page and search navigation,
so cancelling keeps the current selection and all drafts. The feed refreshes
after successful saves and restorations, and can also be refreshed manually.

## Security boundary

This is a single-user, loopback-only service. It binds exclusively to
`127.0.0.1`; there is no option to expose it on a LAN or the public internet.
It sends no CORS headers, accepts no remote model configuration, keeps responses
out of HTTP caches, and limits JSON write requests to 64 KiB.

Every HTML, JSON, image, and error response also carries the same browser
boundary: no referrer disclosure, same-origin opener and resource policies, and
a content security policy that forbids framing, object embedding, and form
submission. These headers complement the request checks below; they do not turn
the loopback service into a remotely safe or multi-user deployment.

Every request must identify the actual bound port under `127.0.0.1` or
`localhost`. Other `Host` values are rejected before route handling, which
narrows the DNS-rebinding surface. When a browser sends `Origin` or
`Sec-Fetch-Site`, the origin must match that local authority and the request
must be same-origin (or a direct `none` navigation). Write routes additionally
require `Content-Type: application/json`; simple cross-origin form-style bodies
are not accepted. Local command-line clients may omit browser-only origin and
fetch metadata, but they still need the correct loopback `Host` and JSON media
type for writes.

There is no login or authorization layer yet. Any process able to make requests
from the same machine can use the browser workbench while it is running. Do not
treat this phase as a multi-user deployment. Authentication, role-based access,
review assignment, audit identity, and remotely hosted collaboration are separate
roadmap work.

The service does not make outbound network requests. `network_required: false`
means it needs no external network; the explicit loopback listener is only a
local browser transport.

## Revision history and restoration

Open **Revision history and restore**, choose one of the four streams, and load
the history for the selected line, region, or page. The response is bounded to
the newest 100 saved revisions and also exposes imported revision `0`. The panel
shows each resulting historical value before enabling restoration. Transcription
history contains human-readable text, so keep the browser and screenshots private
unless that content is independently cleared for sharing.

Restoring does not rewind or delete the audit trail. It runs the same project-store
operation as the local restoration commands and appends the selected historical
value as a new revision. The request includes the stream revision returned with
the history. If another tab or command writes first, restoration fails as stale
without adding an audit row. Reload the history, review the newer state, and make
a fresh decision.

## Concurrent tabs

Each transcription, line-geometry, region-polygon, and reading-order save
includes the exact revision displayed when that page was loaded. Line text and
line geometry have separate revision streams, so correcting one does not make
an untouched editor for the other stale. If another tab or local command saves
the same entity stream first, the stale request returns a conflict and does not
append another audit row. Reload the page, review the newer state, and then
decide whether to apply the edit again. A conflict never merges or retries
content automatically.
