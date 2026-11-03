# Later archived orbit availability — offline only

The user explicitly keeps causal positioning primary and permits offline
results only as a separate comparison. This inventory is not a positioning
experiment and cannot satisfy the causal improvement goal.

The archive timestamp is assigned at request start, before fetching and
fsyncing the snapshot. Consequently the four-hour cutoff below screens request
timestamps; proving that bytes were available by that exact deadline would
require separate completion evidence. This inventory makes no such guarantee.

Using each scan's start plus four hours as a fixed information deadline changes
the element bytes for 1495/3071 distinct `(scan, retained candidate NORAD)`
occasions. All 32 original scans have archived provider snapshots with request
timestamps under that deadline. The median of scan-level median absolute epoch ages falls
only from 0.99990 to 0.93179 days. New publication therefore does not imply a
large improvement in epoch proximity or orbit accuracy.

For each deadline select the latest archived snapshot from each original bank
provider, then the newest element per object with collection-time/digest ties.
Retain the original element if an object is missing or its new epoch is older.
Keep the original retained candidate identities. No orbit is propagated, no
frequency is scored, and no position or reference error is used. This measures
availability; it does not show that any updated element is more accurate.

[inventory.json](inventory.json) preserves element digests, epochs, selected
snapshot digests, deadlines, fallbacks and source bindings. The original bank
provider selections are reconstructed exactly. [inventory.py](inventory.py)
reads the archive without changing it and writes its output exclusively.
Execution completed within a 60second cap with one numerical thread.
