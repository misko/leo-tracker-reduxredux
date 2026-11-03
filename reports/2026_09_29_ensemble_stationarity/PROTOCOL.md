# Shared-location versus per-scan location-mixture semantics

Reuse the fifteen sealed out_of_pool results without new RF likelihood calls.
For each dataset's five targets, retain the same three source N8 positions and
equal prior weights. Compare:

* fixed N24: sum_s log p(data_s | x24),
* one shared N8 location: logsumexp_k(sum_s log p(data_s | x8_k)) − log(3),
* independently mixed N8 locations: sum_s [logsumexp_k(log p(data_s | x8_k)) − log(3)].

Each p(data_s | x) already integrates that scan's timing, independently between
scans. No position or prior weight is optimized on targets. The shared mixture
has one location-component index across all five targets; the independent
mixture draws it separately per scan. Component indices label source-fit
locations, not satellites. This is a post-hoc semantics diagnostic, not a new
blind validation or a basis for changing prior weights.

Report per-component summed scores, shared posterior weights, per-target
posterior weights, and agreement of top component indices. These are
target-conditioned diagnostics, not newly validated geographic estimates.
Recompute all comparisons using stored 16- and 32-node scores to check numerical
sensitivity; preserve original published per-scan results. Verify source seals
and manifest/session bindings. No new model fitting or confidence calibration.
