# C029 native receiver-clock assignment audit

The receiver-clock extension still selects the distant endpoint. This fixed-state audit compares the two sealed receiver-clock fits, without fitting parameters or consulting reference positions. Positive likelihood differences below mean the shifted endpoint predicts worse than the incumbent. Endpoint errors from the separate, already sealed evaluation are 2.169 km (shifted) and 83.881 km (incumbent); neither is a new promoted result.

The shifted-minus-incumbent negative log likelihood is +212.650 on CH1–4 and −65.395 on CH5–8, totaling +147.255. Its smaller prior penalty reduces the objective gap to +95.776, so the incumbent remains selected.

| Channel | Shifted minus incumbent NLL |
|---|---:|
| CH1 | −45.456 |
| CH2 | +650.773 |
| CH3 | −461.400 |
| CH4 | +68.733 |
| CH5 | −120.787 |
| CH6 | +6.122 |
| CH7 | +122.424 |
| CH8 | −73.154 |

CH2 remains the largest adverse contribution. Its posterior signal mass falls from 193.511 at the incumbent to 86.147 at the shifted endpoint. Of 376 windows, 149 switch from incumbent signal to shifted clutter, contributing +844.261 NLL; 41 switch in the opposite direction, contributing −221.211. Only four retain the same dominant signal assignment. This is strong assignment disagreement, not evidence that either endpoint's assignments are correct.

Across the low band, posterior satellite/clutter overlap averages 0.478; across the high band it averages 0.557. Alias-branch disagreement contributes zero additional overlap loss in the low band and only 0.00000317 in the high band. The audit therefore localizes the remaining disagreement primarily to satellite/clutter assignments rather than within-satellite alias branches. The earlier constant-offset profile and this clock extension do not establish a calibration-only remedy. These repeatedly inspected development cases are not untouched validation.

Validation: both states replay their sealed objective and NLL within 1e-7. Transition groups partition windows and likelihood; channel totals match band totals, and receiver/time strata match channel totals. The run completed in 17.549 seconds with four objective evaluations and zero optimizer calls. The existing actual-state component test and Ruff passed before freezing the driver at research commit 45c9e875e.

Artifacts: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-overlap-029-v1/`. Result SHA256 `337f893b6c6fa257a59435b3a09580b8a340fdb4b05abdb621121636bd77bcaa`; seal SHA256 `11f1ac32352468cc17c59d948e7958e1756ceb737fa79768a309e882e322728b`. The result also retains all receiver and prespecified 30-second time strata and weighted residual summaries.
