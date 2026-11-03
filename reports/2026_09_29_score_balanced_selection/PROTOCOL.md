# Score-balanced eight-scan subset prototype

Use the same 24-scan source pools, N24 expansion points, training-only geometry
matrices and profiled observed Hessians/gradients as the preceding two reports.
Enumerate all C(24,8)=735471 eight-scan subsets. Among subsets with positive
definite summed observed geographic curvature, maximize:

    log det(sum geometry information + ridge I) - g' inverse(H) g

Here g/H are summed profiled training gradients/negative Hessians, and ridge
is 1e-9 times half the full-pool geometry trace, as before. The coefficient of
the disagreement penalty is fixed at one; no sweep or target-based tuning.
The penalty is twice the local quadratic source-score gain from moving away
from N24. This is a selection heuristic, not a likelihood or calibrated bias
test. Use lexicographic subset order to break exact ties.

Require every per-scan Hessian audit to qualify. Repeat selection with the
half-step geometry matrices as in the original information selector and require
identical membership. Use exactly its six-start q020 fitting and five frozen
outside-pool target evaluations, including timing integration and checks.
Preserve failures. Compare against timestamp-balanced, information-only and
N24 results. Existing targets and reference are exposed; no blind validation.

All 24 source scans are required to select eight. This is compression of a
scouted dataset, not eight-scan acquisition or independent accuracy improvement.
Three workers capped at 300 seconds. No new RF, production edits or publishing.
