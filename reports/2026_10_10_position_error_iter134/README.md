# Sparse visit-ID correction — explicit successor preparation

Iteration128 finished all twelve members and preserved all35,206 observation rows.
Eleven members passed completely. DS18-029 retained989 successes and1,782 guarded
read failures:1,768 counter/count mismatches and14 out-of-range reader requests.
No failing row was sent to a scorer, substituted or dropped.

The public reader accepts an ordinal into retained visits, while the original
analysis products identify `event.visit_index`. The writer intentionally permits
sparse event IDs for host-adaptive inputs. DS18-029 has2,187 retained visits through
eventID2,195. The first difference is ordinal715→event718. Of retained visits,
1,472 differ from their ordinal. A metadata-only mapping predicts exactly all1,782
failed observation IDs and predicts zero failures for the other eleven captures.
See [mapping-audit.json](mapping-audit.json).

Sources: [public reader](../../src/leo/storage/adaptive_hop.py#L1173),
[sparse-source writer admission](../../src/leo/storage/adaptive_hop.py#L1245),
[analysis product event ID](../../src/leo/scanner/adaptive_hop_analysis.py#L718).
This is an iteration128 adapter defect, not evidence that IQ or production
analysis is corrupted. The unchanged counter/count guard prevented wrong inputs.

Proposed explicit successor replays **all2,771 original DS18-029 observations**,
including the989 prior successes, once using a generic event-ID→ordinal adapter.
It verifies unique event IDs, exact original counters/counts and RF channel/edge.
The immutable128 runner, scorer,125 refiners, original metadata, admission,
resources and1,200-second soft deadline remain unchanged. No tolerances loosen,
no new acquisition or RF collection, and no position fit. This is a new separately
frozen receipt;128 failure evidence remains immutable. There is no automatic retry.

`freeze.py` binds the original128 protocol, sources, metadata and failed receipt,
plus this adapter and tests. Parent must review/publish before `replay.py` may
open IQ. No successor IQ reads occurred during preparation. A later133 comparison
must explicitly bind the successful successor if available; it cannot silently
pretend128 originally passed or omit DS18-029.
