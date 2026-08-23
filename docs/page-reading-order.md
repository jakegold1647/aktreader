# Page reading-order revisions

AKT Reader keeps the imported PAGE XML and its page images immutable. A page reading-order revision
is a local, append-only instruction for the sequence of the imported TextRegion IDs on one page.
It is not a rewrite of the source file.

Use a strict JSON object containing the full, unique permutation of that page's imported regions:

~~~json
{
  "region_ids": ["region-2", "region-1"]
}
~~~

Record the revision locally:

~~~powershell
python -m aktreader project-revise-page-reading-order serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --region-order reading-order.json `
  --editor layout-reviewer `
  --expected-revision 0
~~~

The command validates that the list is an exact permutation of the region IDs captured in the
content-addressed import manifest. It records the previous and new sequences, an editor claim, and
a timestamp in the local project database. Repeating the current sequence reports UNCHANGED
instead of adding another revision. Read the page reading order's current `revision` with
`project-show-page-layout` and pass it as `--expected-revision`; a stale value is rejected before
anything is appended.

Reverse the latest saved order with the currently displayed revision:

~~~powershell
python -m aktreader project-undo-page-reading-order serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --editor layout-reviewer `
  --expected-revision 1
~~~

Undo appends the preceding complete region sequence as a new revision. It reports
`UNDO_UNAVAILABLE` at revision zero, rejects stale revisions, and never deletes the revision it
reverses. Undoing that new undo revision restores the order it replaced.

project-export-pagexml applies only the latest saved order for each affected page to a new
derivative PAGE XML file. It replaces that page's direct ReadingOrder element with an OrderedGroup
of indexed RegionRefIndexed entries. Export never changes the immutable source PAGE XML, its import
manifest, or the source image.

This feature deliberately handles region sequence only. Region polygons, line polygons, baselines,
and transcription text remain separate local revision streams; they must be changed with their
respective explicit workflows.
