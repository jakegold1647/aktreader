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

Re-importing the same PAGE XML never replaces document metadata. Document records are the
collection/search boundary for later multi-page import, thumbnails, tags, and publishing workflows.
