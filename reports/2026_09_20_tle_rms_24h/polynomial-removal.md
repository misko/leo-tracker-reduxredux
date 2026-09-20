# Effect of removing the polynomial association veto

The matcher now retains polynomial scores as diagnostics but no longer rejects an association because a polynomial obtains a better evaluation likelihood. Catalogue-rank, time-shift-boundary, restricted-null and wrong-time controls remain. The matcher algorithm is version 4 and its configuration digest includes the algorithm version. Existing published results are not rewritten by this code change.

The following counterfactual uses the frozen September 19–20, 05:00 UTC snapshot. It preserves all scores and candidate rankings and removes only the polynomial rejection reason. A track passes if at least one of its directly scored representative-group comparisons has no remaining rejection reasons.

For **132 tracks** with best randomized held-out RMS <60 Hz and runner-up RMS >300 Hz:

| Outcome after removing the polynomial veto | Tracks |
|---|---:|
| Already passed | 6 |
| Previously abstained; would now pass | 39 |
| Would still fail another gate | 49 |
| Not directly scored as a representative track | 38 |

Thus **49 of the previous 88 directly scored abstentions remain**, while 39 clear. The 38 without their own representative comparison must not be counted as either accepted or rejected by this counterfactual; 22 occur as members of a scored group and 16 do not.

Remaining rejection reasons among the 49 tracks overlap:

| Reason | Tracks |
|---|---:|
| +500-second wrong-time control | 26 |
| −500-second wrong-time control | 26 |
| Selected time shift at search boundary | 25 |
| Catalogue leader / rank instability | 8 |

These are individual-track RMS thresholds, not per-session medians. The [track-level ledger](polynomial-removal-impact.json) records every disposition and remaining reason set. Counts describe the frozen results with one gate removed, not a completed production reprocessing run or a verified satellite-identity count.

A regression test forces the polynomial diagnostic to have overwhelmingly better likelihood and verifies it cannot add an abstention reason. Existing matcher and scanner-service tests cover the remaining behavior.
