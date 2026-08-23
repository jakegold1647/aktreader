# Region geometry revisions

AKT Reader keeps imported PAGE XML and page images immutable. A region geometry revision is a local,
append-only replacement polygon for one imported TextRegion on one page. It is recorded in source
pixel coordinates and never overwrites the source XML.

Use a strict JSON object with a polygon made of at least two distinct in-bounds integer pixels:

~~~json
{
  "polygon": [[1, 15], [39, 15], [39, 29], [1, 29]]
}
~~~

Record the revision:

~~~powershell
python -m aktreader project-revise-region-geometry serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --region-id region-2 `
  --geometry region-geometry.json `
  --editor layout-reviewer `
  --expected-revision 0
~~~

The region ID must match exactly one imported TextRegion, and every polygon point must lie inside
the recorded source image dimensions. The local project records the preceding polygon, revised
polygon, editor claim, and timestamp. Repeating the latest polygon reports UNCHANGED. Read the
region's current geometry `revision` with `project-show-page-layout` and pass it as
`--expected-revision`; a stale value is rejected before anything is appended.

Reverse the latest saved polygon with the currently displayed revision:

~~~powershell
python -m aktreader project-undo-region-geometry serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --region-id region-2 `
  --editor layout-reviewer `
  --expected-revision 1
~~~

Undo appends the preceding polygon as a new revision. It reports `UNDO_UNAVAILABLE` at revision
zero, rejects stale revisions, and never deletes the revision it reverses. Undoing that new undo
revision restores the polygon it replaced.

When project-export-pagexml writes a derivative, it applies only the latest region polygon for each
affected TextRegion. The source PAGE XML, import manifest, image, and all earlier revisions remain
unchanged. Reading order, line polygons and baselines, and transcription text are separate revision
streams and require their own explicit workflows.
