# Restoring prior project revisions

AKTReader can restore any older state from each append-only project revision stream:

- human line transcription;
- line polygon and baseline geometry;
- page region reading order; and
- TextRegion polygon geometry.

A restoration does not rewind or delete history. It reads the selected state, validates it through
the normal revision writer, and appends that value as the newest revision. The imported PAGE XML,
stored source object, and every earlier audit record remain unchanged. All four commands are local
and report `"network_required": false`.

## Revision meaning

Revision numbers are local to one entity and one stream. For example, transcription revision `2`
for one line is unrelated to geometry revision `2` for the same line or to revision `2` for another
line.

The target must be earlier than the current revision:

- target `0` selects the state imported from PAGE XML;
- a positive target selects that exact saved revision's resulting value; and
- a target equal to or later than the current revision is rejected.

Read the current transcription revision with `project-show-page`. Read current line geometry,
reading-order, and region geometry revisions with `project-show-page-layout`. The exact entity IDs
and revision numbers also appear in the content-free `project-activity` feed.

## Inspect values before restoring

`project-show-revision-history` is a separate, explicitly contentful local reader. It targets one
entity and stream, returning `imported_state` for revision zero and newest-first audit entries with
`prior_state`, `revised_state`, editor, and timestamp. Transcription output contains human-readable
text: keep it private unless you have independently confirmed that it may be shared. The command
does not write the project or use the network, and it does not change the content-free contract of
`project-activity`.

Inspect one line's transcription history:

~~~powershell
python -m aktreader project-show-revision-history serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --kind TRANSCRIPTION `
  --source-span-id <source-span-id>
~~~

Use the same line selector with `--kind LINE_GEOMETRY`. Reading order accepts only
`--page-index`; region geometry requires both `--page-index` and `--region-id`:

~~~powershell
python -m aktreader project-show-revision-history serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --kind READING_ORDER `
  --page-index 0

python -m aktreader project-show-revision-history serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --kind REGION_GEOMETRY `
  --page-index 0 `
  --region-id region-2
~~~

Results are bounded to 100 revisions by default. Set `--limit` from 1 to 500. When
`pagination.has_more` is true, pass `pagination.next_before_revision` back as the exclusive cursor:

~~~powershell
python -m aktreader project-show-revision-history serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --kind TRANSCRIPTION `
  --source-span-id <source-span-id> `
  --limit 50 `
  --before-revision <next-before-revision>
~~~

`current_revision` always reports the entity's latest revision, even while an older page of history
is being viewed. With no edits, `current_revision` is zero, `revisions` is empty, and
`imported_state` remains available.

## Commands

Restore a line transcription:

~~~powershell
python -m aktreader project-restore-line-transcription serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --source-span-id <source-span-id> `
  --target-revision 1 `
  --editor local-user `
  --expected-revision 4
~~~

Restore line polygon and baseline geometry:

~~~powershell
python -m aktreader project-restore-line-geometry serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --source-span-id <source-span-id> `
  --target-revision 1 `
  --editor layout-reviewer `
  --expected-revision 4
~~~

Restore a page's complete TextRegion order:

~~~powershell
python -m aktreader project-restore-page-reading-order serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --target-revision 1 `
  --editor layout-reviewer `
  --expected-revision 4
~~~

Restore one TextRegion polygon:

~~~powershell
python -m aktreader project-restore-region-geometry serock.aktproj `
  --manifest-sha256 <project-import-manifest-sha256> `
  --page-index 0 `
  --region-id region-2 `
  --target-revision 1 `
  --editor layout-reviewer `
  --expected-revision 4
~~~

Use target `0` in any command to restore imported state.

## Concurrency and audit behavior

`--expected-revision` must equal the entity stream's current revision. If another reviewer saves
first, the restoration is rejected as a conflict; reload the current page before deciding whether
to try again. A second current-revision check occurs when the new revision is written, so a write
racing the restoration lookup cannot be overwritten.

A successful change reports `RESTORED`, its new revision number, and `target_revision`. If the
selected historical value is already the effective value, the normal writer reports `UNCHANGED`
and does not add a duplicate audit record.

Restoring a transcription creates a new human revision. Training consent remains bound to the exact
revision for which it was granted and does not transfer to the restored revision; grant fresh
consent only after reviewing that new current revision.
