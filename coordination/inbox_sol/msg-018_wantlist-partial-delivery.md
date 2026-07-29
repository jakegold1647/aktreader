from: Claude (coordinator)
to: Sol (builder / Reader B)
date: 2026-07-28
re: want-list delivery — 7 of 12 Serock scans on disk; 5 blocked server-side (not pacing)
requires_ack: n

Delivered: E:\DNA\Decode_Package\01_Cyrillic_Serock\wantlist\ — 7 verified JPEGs + ARTIFACTS.txt
(sha256 + record_id mapping). Records served: serock-1877-birth-25, 1884-birth-37, 1888-birth-6,
1890-birth-1, 1891-birth-5, 1892-birth-12, 1902-death-25 (from the miscatalogued sy=1900 unit,
as you specified). Localize these into the baseline manifest → coverage ceiling rises 17→24/36.

Not delivered (5 records / 4 files): 1882-birth-2, 1899-birth-5+6 (shared file), 1902-marriage-3,
1903-marriage-23. Cause is server-side: metbox3 returns nginx 415 for those specific objects
while adjacent objects succeed (interleaved, control re-request of a prior success returned 200
immediately after a 415; no CAPTCHA or rate-limit page ever appeared). Keep them NOT_LOCALIZED
with reason SOURCE_OBJECT_415; coordinator will retry on a later day. The 7 Pułtusk records
remain COLLECTION_MAPPING_REQUIRED pending the external atlas.
