# Complete DS7/DS8/DS9 opportunity inventory

Extend the unchanged three-record pilot accounting to all 258 immutable manifest
members, reusing the three pilot exports. Preserve the existing 72 target and 186
donor scan split. No score-based selection, new location fit or RF collection.

Export public TrackingInput and read-only adaptive capture inspection, binding
capture digests. Preserve visit intervals, exact RF, RX probe intervals and passing
candidate counts as compressed JSON. Use the pilot's frozen interval-union auditor
for duplicate, containment, pairing and missing-visit checks. Aggregate actual
sample coverage separately by dataset, role, receiver and dwell duration.

One process at a time, batches of at most 32 previously unexported scans, each
timeout180s, AS4GiB, BLAS1/nice19; total launch wall budget900s. Persist successes
and failures without retries. Recheck installed loader bytes against the pilot
before every batch. No raw IQ, propagation, external provider, production changes
or detector recalibration. Empty extraction is not verified satellite absence.

Run the three frozen auditor tests before export. Independently check per-record
summary reconstruction and sample accounting from all saved exports afterward.
Source/input hashes freeze before launch. Full coverage must be demonstrated;
partial output is not a complete inventory.
