# Position-support boundary diagnostic

This is a descriptive diagnostic over all 64 sealed `merge128_to32` receipts. Every run
stopped after its first factor, so each receipt's 32 final components are also its saved
first-factor reduced state. No fit was rerun and no gate was changed.

The frozen predicate raises `position_support_boundary` when any component satisfies

`norm(mean_EN) + 5 * sqrt(max_eigenvalue(covariance_EN)) > 489 km`.

It is existential and ignores component weight. For each scan, this diagnostic sums the
weights of components satisfying that predicate. Across 64 scans, the minimum, median, and
maximum such weights are 0, 0.008386, and 0.108865. Fifty-nine scans contain at least one
triggering component, and 28 of those 59 assign the triggering components less than 1% total
weight. The number of triggering components is 0–4 with median 1.

For comparison, component centers alone cross the intended 250 km disk in 34 scans. Their
summed weights have minimum, median, and maximum 0, 0.001046, and 0.994774; 17 of the 34
nonzero cases are below 1%. Center-crossing component counts range from 0 to 16 with median
1 across all scans.

These results answer the narrow mechanism question: a single low-weight, broad component is
sufficient to explain many of the nearly universal position-support failures. The position
gate fires in 59/64 scans, and in 28 scans its entire triggering component set carries less
than 1% weight. It does not explain the other five first-factor failures, and some scans have
material boundary-crossing weight. All 64 merge runs failed at least one frozen gate.

The summed weights are component weights selected by a mean-plus-five-sigma predicate. They
are not estimates of Gaussian probability outside 489 km: covariance orientation, overlap,
and the nonlinear circular boundary are not integrated here. Likewise, a five-sigma bound is
a conservative support test rather than a calibrated credible-region statement.

