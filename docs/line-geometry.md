# Local line geometry revisions

PAGE XML imported into an AKT Reader project is immutable evidence. If a line polygon or baseline
needs correction, append a local geometry revision rather than modifying the source XML.

Create a strict local JSON object in source-image pixels:

```json
{
  "polygon": [[12, 12], [88, 12], [88, 24], [12, 24]],
  "baseline": [[12, 21], [88, 21]]
}
```

Both polygon and baseline points must be integer pixels inside the imported source image. A
baseline may be `null` to explicitly remove it; the polygon needs at least two distinct points.

    aktreader project-revise-line-geometry E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --source-span-id <pagexml-source-span-id> --geometry E:\changes\line-geometry.json --editor layout-reviewer --expected-revision 0

The command appends an audit record with the prior and proposed geometry. It does not move text,
change HTR suggestions, alter the project source object, or grant training consent. Read the
line's current geometry `revision` with `project-show-page-layout` and pass it as
`--expected-revision`; the command rejects a stale value instead of overwriting newer work.

Undo the latest geometry change with the same displayed revision:

    aktreader project-undo-line-geometry E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --source-span-id <pagexml-source-span-id> --editor layout-reviewer --expected-revision 1

Undo appends the prior polygon and baseline as a new revision; it never deletes the revision being
reversed. Revision zero reports `UNDO_UNAVAILABLE`, and a stale revision is rejected. Because undo
itself is a revision, undoing it again restores the geometry it replaced.

Export the revised layout as a new PAGE XML derivative:

    aktreader project-export-pagexml E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --output E:\exports\serock-layout.page.xml

The export applies the latest human text revision and the latest line geometry revision, leaving
the stored source PAGE XML untouched. Reading order and region geometry remain independent
revision streams with their own explicit edit and undo commands.
