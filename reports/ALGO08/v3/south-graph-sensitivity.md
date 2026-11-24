# Duplicate Graph proposals explain the four South owner losses

The **CFO changes alone** reproduced the drop from 442 to 438 assigned Graph points. Changing only the three detector score and margin fields had no effect. All four observations absent from the newer Graph were also the four missing published owners in each calibration arm. The numerical fork occurs in final RX1 CH1 Graph ownership, before catalogue ranking, exterior scoring or position fitting. [Frozen four-cell protocol](south-graph-sensitivity-protocol.md) · [Crossed Graph receipt](measurements/south-graph-sensitivity.json.gz)

| CFO vector | Score and margin fields | Assigned Graph points | Tracks |
|---|---|---:|---:|
| Earlier South | Earlier South | 442 | 30 |
| Earlier South | Combined South | 442 | 30 |
| Combined South | Earlier South | 438 | 30 |
| Combined South | Combined South | 438 | 30 |

Every cell used the same 456 winning observations, the original signed times and lanes, the installed track configuration, and the reviewed exact Graph options. The two 442-point cells matched ordered support digests, and the two 438-point cells matched each other. Across the four cells, all 160 native path calls agreed bitwise with the installed Python recurrence. The edge topology and discrete path choices matched. RX1 CH1 had 38 observations and the first discrete fork was the support passed to final polynomial compression. No satellite or TLE fitting was needed to localize the fork. [Graph attribution driver](south_graph_sensitivity.py)

## Why a sub-nanohertz change matters

Two accepted quadratic proposals in RX1 CH1 have the same 19 ordered observations, centred at 228.01 s with an 18 s scale. The earlier packet produced identical coefficients for both, so its strict residual-improvement test kept the first proposal. With the newer CFO values, the coefficients differ by roughly 10⁻¹¹ Hz despite retaining the same native alias lift and support. On four observations, the second proposal wins by exactly **1.45519 × 10⁻¹¹ Hz** of wrapped residual, one binary64 spacing at half the alias period. These values are far from the 450 Hz gate. The subtraction changes membership before the final refit. The first proposal's full rows 19–37 become 21–28, 30–34 and 36–37 in the first final refit, while the final Graph drops exactly the four stolen rows.

| Receive time (s) | New − old measured CFO (Hz) | Earlier wrapped residual (Hz) | Published owner in both old arms |
|---|---:|---:|---|
| 210.01 | 0 | 89.190 | 66147, conditional |
| 212.01 | −1.45519 × 10⁻¹¹ | 36.041 | 66147, conditional |
| 230.01 | +7.27596 × 10⁻¹² | 24.633 | 66147, conditional |
| 242.01 | 0 | 13.935 | 66147, conditional |

The two exactly unchanged CFO rows still move because the coefficients use their lane neighbours. The archived position fits moved from **558.143 / 810.906 m** horizontal error to **553.231 / 823.863 m** for fixed-zero and fitted `c`, with **6.061236 / 5.968386 Hz** RF RMS moving to **6.074602 / 5.974579 Hz**. This Graph intervention resolves the source of the four missing owners. It does not isolate the position effect of those four rows from the rest of the changed receiver measurements. [Paired signed South outcomes](combined-raw-south.md)

## Duplicate-only correction fails held exact compatibility

The research reducer retains the earlier proposal when both have the same ordered support, degree, time frame, absolute integer alias lifts and strict gate admission, and their predictions differ by no more than one binary64 spacing of the alias period. It changes neither the numerical residual gate nor the graph-path recurrence. [Frozen reducer protocol](duplicate-graph-proposals-protocol.md) · [Implementation](duplicate_graph_proposals.py)

| Saved input | Original → filtered Graph points | Filtered proposals | Result |
|---|---:|---:|---|
| Earlier South | 442 → 442 | 4 | Full Graph bytes equal |
| Combined South | 438 → 442 | 4 | Earlier ordered support recovered exactly |
| Weak DS30-0016 | 354 → 354 | 0 | Full Graph bytes equal |
| North | 444 → 452 | 1 | Held Graph support changed |

The reducer took **0.207 ms CPU** in the combined South Graph. It failed the frozen exact-compatibility gate on North. Its effect on published North owners, positions and figures was unmeasured in this experiment. No correction was added to the cumulative CLI or deployed. The research patch remains available for a separately preregistered accuracy test. Six focused component cases passed. The two receipts have uncompressed SHA-256 `1d2d1cd72ea348d53646fdea6045c25d000f6f1f63362f3ee6e0df7bf1828199` and `fc3137f04fd3053301ccade2302d6ec7ceb892c1a634c0e55c47872633cd9d35`. [Held Graph transfer](measurements/duplicate-graph-proposals.json.gz)
