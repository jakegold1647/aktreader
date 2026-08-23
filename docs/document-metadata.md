# Document metadata

Each imported PAGE XML file is one local AKT Reader document. The original PAGE XML and page images
remain immutable content-addressed project objects; document title, tags, and notes are separate,
mutable local metadata.

Every document has a stable ID derived from its project import manifest. Existing projects receive
the same deterministic ID during the schema migration.

List documents in a project:

~~~powershell
python -m aktreader project-list-documents serock.aktproj
~~~

Update metadata with strict local JSON containing any nonempty subset of title, tags, and notes:

~~~json
{
  "title": "Serock civil register, 1890",
  "tags": ["Serock", "births", "1890"],
  "notes": "Reviewed from the bound volume."
}
~~~

~~~powershell
python -m aktreader project-update-document serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --metadata document.json
~~~

Both loopback browser workbenches expose the same fields under **Document details**.
They accept one tag per line so commas can remain part of a tag. Browser saves send
all three fields plus the document's exact `updated_at` value; a stale tab is
refused instead of overwriting metadata saved by another tab or local command.
Document and project switches guard unsaved metadata, while page and line navigation
within the same document preserves the draft. Saving metadata does not discard
unsaved transcription or layout work.

In the authenticated collaborative workbench, `VIEWER` accounts can read document
metadata, while `EDITOR` and `OWNER` accounts can save it. Project notes are visible
to every authorized member of that project; they are not personal notes. Successful
title or tag saves rerun any active project search so its current matches and labels
stay synchronized.

Re-importing the same PAGE XML never replaces document metadata. Document records are the
collection/search boundary for later multi-page import, thumbnails, tags, and publishing workflows.
