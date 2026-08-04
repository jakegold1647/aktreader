from: Claude (coordinator)
to: record (inbox closed per msg-044; archival entry)
date: 2026-08-04
re: owner-authorized governance change — coordinator absorbs build side; Reader B v1.1
requires_ack: n (owner authorization is the approval)

By owner decision tonight, following msg-044:

1. Build-side ownership — `src/`, `tests/`, `gold/`, `schemas/`, `prompts/`, `tools/`, `docs/` —
   transfers from Sol to the coordinator, effective immediately. Sol's frozen artifacts (prompt/
   schema v1.4, adjudicate tooling, holdout runbook, groundedness guards) remain canonical and
   in force; ownership of their maintenance moves, their content does not.

2. Reader B is redefined (PROTOCOL v1.1): each wave's blind pass is executed by a fresh agent
   instance with no session contamination — it receives only the frozen wave brief, the scan
   crops, and the pinned prompt/schema v1.4; it never sees Reader A outputs, prior-wave data,
   consensus files, or coordination traffic. Instance identity is recorded per wave
   (`readerB-w<NNN>-<YYYYMMDD>`). Freeze/hash discipline is unchanged. Reader C rules unchanged.

3. Wave state: wave-006 paired briefs (frozen b416c70) remain valid under the new procedure —
   `independence.distinct_reader_ids` holds; `distinct_model_families` remains false and stays
   honestly recorded as such. Waves 006–009 are eligible to resume once the msg-045 runtime pin
   is fetched and the grammar probe passes.

This entry is the archival record of the change; PROTOCOL.md v1.1 and STATUS_BOARD carry the
operative text.
