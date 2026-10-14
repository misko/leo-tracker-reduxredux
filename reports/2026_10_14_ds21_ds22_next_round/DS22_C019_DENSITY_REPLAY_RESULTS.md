# C019 fixed-state visibility normalization audit

Visibility normalization does not change the selected endpoint in either native model on the completed 67-satellite coverage inventory. All 36 accepted full60 endpoints were replayed, without geographical filtering or any new localization fits. This rules out normalization alone as a selector repair for these endpoints; it does not establish global optimality or rule out different fitted satellite propensities.

| Model | Accepted endpoints replayed | Original winning objective | Conditional winning objective | Winning ordinal before/after | Conditional runner-up gap |
| --- | ---: | ---: | ---: | --- | ---: |
| Projected native | 16 | 42270.495787 | 42269.512217 | 0 / 0 | 627.189797 |
| Native with receiver clock | 20 | 41854.253146 | 41853.246701 | 0 / 0 | 364.821925 |

Across all endpoints, normalization corrections range from -4.368883 to numerical zero for projected native, and -4.563309 to numerical zero for native clock. These changes are small relative to the winning margins. The coordinates are unchanged: the previously reported configured-reference distances remain 142.976656 and 143.256619 km respectively. DS22 station continuity remains unconfirmed, so these are configured-reference distances, not verified accuracy. This audit never reads reference coordinates.

For every endpoint, the audit independently replays the original objective, NLL, gradients and original-domain KKT; verifies legacy-wrapper objective, gradients and responsibilities; checks the normalization identity in both objective and NLL; checks unchanged conditional gradients and branch posteriors; and replays strict conditional-domain KKT. Maximum closure discrepancies were 1.07e-11. All original acceptance classifications were retained. The conditional states are derived fixed-state diagnostics, not newly optimized fits. Smooth derivatives and KKT condition on a fixed hard-visibility pattern; this likelihood conditions on fixed branch evidence rather than modeling peak selection generatively.

The two parallel units performed 80 and 100 objective evaluations, zero localization fits, and completed in 66.425 and 64.994 seconds including preparation. All accepted states were retained in the selector. Eight tests cover closure rejection and complete-inventory validation; Ruff passes. The original source and all parent outcomes are pinned, and both unit receipts were sealed together after completion.

Implementation: `ae0a72bb5` (replay), `dd5f98a8b` (complete-inventory seal). Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-density-replay-v1`. The parent is the completed 44-call full60 inventory; its eight nonstationary outcomes remain recorded and excluded. No failed call was retried and no held observations were used.

Next investigation: satellite association/selection model adequacy on the expanded bank, rather than another unchanged coverage or normalization rerun. Any new propensity fit requires fresh expanded-bank qualification and matched controls; the results above are not evidence that such a fit improves position accuracy.
