# Receiver and RF attribution of cross-time score disagreement

At the existing N24 source fit in each dataset, compute each track's original
q020 TRAINING score gradient independently. Verify track sums reproduce each
stored scan gradient and score. Apply the same scan-level timing-profile
operator to every track so contributions add to the previous profiled scan
gradient. This is local algebraic attribution, not a receiver-only re-fit.

Aggregate by frozen early/middle/late window, receiver and exact RF center.
Report both receiver vectors and their cosine, individual RF contributions,
and per-track concentration measured against gross absolute vector magnitude.
Do not select/exclude tracks or infer that shared receiver directions prove
orbit error, host timing error or satellite identity. No new location fit.

All 72 source scans are included. No target score or geographic reference is
used in attribution. Three workers capped at 120 seconds; preserve failures.
No RF collection, production edits or publication.
