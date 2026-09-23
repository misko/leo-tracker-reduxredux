# Fixed-location TRAIN association diagnostic

This diagnostic uses only the frozen first 6 and first 16 TRAIN IDs and the
already sealed tau-zero Sacramento/Reno locations. It performs no geographic
optimization. At each fixed location it profiles every cached candidate using
TRAIN rows, records the first--second training RMS gap, and scores held rows
only after that fixed assignment. A gap is a score separation, not a calibrated
candidate probability or identity claim.

All tracks matched a visible cached candidate. Sacramento/Reno assignments agree
for all 476 first-6 tracks and for 1,124 of 1,130 first-16 tracks (99.469%).
The first--second RMS gap median is about 411 Hz for first-6 and 342 Hz for
first-16; P90 is about 1,343--1,346 Hz. Fixed-assignment held RMS medians are
155--156 Hz for first-6 and 168--169 Hz for first-16.

Short 3--10 s tracks do not dominate the capped training objective: their
weight shares are 6.3% (first-6) and 8.2% (first-16), while capped-loss shares
are 1.2% and 1.6%. The 20--30 s and 30+ s bins contribute more capped loss than
their duration weights in both views. Cross-scan recurrence is summarized as
candidate counts only; it does not infer true satellite identity.

`results.json` retains per-track fixed assignments and gaps, span-bin counts,
objective shares, held scores, agreement counts, and sealed source bindings.
The helper is lint-clean and bound as
`sha256:36381d5fecbde436f9fbc6528d91d02fd05d5c8389112cab3ff15077b109808d`.
No validation, test, reference coordinate, truth, or baseline modification was
used.
