# Fully exact satellite holdouts: runtime pilot

The [subsequent per-fit execution](atomic/README.md) completes the scan-0
comparison with all 56 folds qualified. It selects the existing t4/200 endpoint
by common held score. Geographic assessment and the other seven screen scans
remain outstanding. The original whole-family runtime pilot below is retained
as executed, including both timeouts.

The index-0 pilot is incomplete and cannot select a model. IID and source
weighting each finish all 14 source holdouts with qualified refits. Both robust
families hit the 90-second cap for the entire family process before writing a
result. These are runtime failures, not adverse likelihood or geographic
results. No reference errors were evaluated and no wider screen was launched.

| Family | Terminal status | Qualified folds retained | Wall time |
|---|---|---:|---:|
| IID t4/100 | exit 0 | 14/14 | 85.05 s |
| Source/receiver equal | exit 0 | 14/14 | 77.95 s |
| t8/100 | timeout, exit 124 | unavailable | 90.17 s |
| t4/200 | timeout, exit 124 | unavailable | 90.16 s |

The complete denominator is four families, with results available for two.
The missing families cannot be omitted from selection. The two available held
score sums are -7113.2560 and -7119.5472 nats respectively; these are an
incomplete comparison, not a selected winner. The verification records
`selectable=false` and `selected_family=null`.

The [protocol](PROTOCOL.md) freezes exact deletion fits, original conditional
source assignments, unchanged surviving weights, training-only CFO profiling,
identical coverage, and selection by summed common-model held density. The
runner uses the same optimizer settings and qualification gates as the prior
exact audit. This experiment does not use its rejected influence approximation.

Five owned tests pass. Review checks source membership, weight retention,
training-only nuisance fitting, endpoint and terminal receipt bindings, and
selection requirements. The [pilot verification](pilot-verification.json)
validates both completed outputs and all four receipts, recomputes fold
membership and qualification, and reproduces all four available overlaps with
the preceding exact audit within 1e-6 in coordinates and held score.

The frozen pilot has no retries. The measured runtime justifies a separate
execution revision that saves and caps each individual fit, preserves completed
evidence, and records every timeout. Such a revision must retain the same
scientific comparison and all-fold qualification requirement; it cannot turn
this incomplete pilot into an accuracy gain. No new RF, offline orbit data,
production change, or geographic improvement is claimed.
