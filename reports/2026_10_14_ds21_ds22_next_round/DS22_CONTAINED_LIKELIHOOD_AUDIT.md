# What rejects the near native-C solution on DS22-131?

At the six already accepted continuation states, exact likelihood decomposition confirms a cross-band conflict in 131. The high-derived combined fit improves the high-band likelihood, but loses substantially more on the low band. The tested background correction reduces the gap without reversing it. No new estimate or model promotion follows this fixed-state audit.

All numbers below are **high-derived state minus original-full-derived state**; positive NLL/objective differences favour the original full solution. States and geography stay fixed throughout. The preceding sealed position comparison identifies those 131 states as 0.212503 km and 8.158713 km, respectively, against the unconfirmed configured reference; this audit reads no reference.

| Contribution | DS22-109 | DS22-131 |
|---|---:|---:|
| Original raw full objective difference | −7052.389474 | +3675.663089 |
| Low-band raw NLL difference | −257.067 | +4985.629 |
| High-band raw NLL difference | −6880.959 | −1194.295 |
| Receiver 0 raw NLL difference | −5630.590 | +891.513 |
| Receiver 1 raw NLL difference | −1507.436 | +2899.821 |
| Conditional uniform full objective difference | −7052.389474 | +3676.544954 |
| Conditional empirical-background objective difference | −5036.923063 | +2466.690440 |

In 131, every low channel worsens (CH1 +1392.225, CH2 +1341.589, CH3 +446.243, CH4 +1805.571); every high channel improves. Low-band expected clutter mass rises from 810.44 to 1654.11 windows, while high-band clutter mass falls from 318.20 to 181.81. The problem is not isolated to one low channel or receiver. These are model responsibilities, not independently verified signal/clutter labels.

Conditional normalization does not repair the ranking. Integrated native mass is effectively one throughout 109 and ranges from 0.960928 to one in 131. Its small normalization adjustment worsens 131's high-derived objective gap by about 0.882. The empirical background reduces the gap by about 1209.855 relative to conditional uniform, but the original full state still wins. This background is estimated from all original training windows; it is an in-sample diagnostic, not a new held-out predictive result. No density parameters were fitted using position error.

The next discriminating calibration control transfers the original fitted cross-band receiver offsets to the half-derived states while anchoring the originating band's correction exactly. For 131, the full-derived offsets are approximately −25.40/+37.63 kHz, versus −0.279/−0.004 kHz at the high-derived combined endpoint. These differences motivate a test of missed offset basins; they do not yet prove that the larger offsets are physically correct. Reverse transfers provide controls. Common intercepts must be rebased with the training high-band fractions so the anchor band's native correction, likelihood, geography and satellite timing remain unchanged. All transferred values come from saved training fits; no reference-selected offset or new model freedom is introduced.

The audit performed 24 objectives total (12 per case), zero localization fits, and no separate orbit evaluations. Raw-uniform wrapper objective and both gradients reproduce the original native objective at every state. Scores partition exactly over the original rows. Source, observation and terminal bindings are checked before and after the audit. Completion times were 35.65 and 41.45 seconds under 120-second internal and 135/140-second external bounds. Source `db70832bc`, owned partition test and Ruff pass.

Receipts: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-contained-likelihood-audit-v1/{DS22-109,DS22-131}`. See the [selected position results and curves](DS22_CONTAINED_FUSION_RESULTS.md) for the unchanged performance accounting.

## Anchored contrast transfer: actual fixed-state result

The proposed test completed with 14 additional objective evaluations, zero fits. For each receiver, replacing contrast `δ` with a saved donor value `δ′` changes the common intercept by `−(h−f)(δ′−δ)`, where `h` is the anchor band's 0/1 indicator and `f` is the frozen training high-band fraction. Consequently, the anchor band's complete native correction and likelihood stay unchanged; the opposite band receives the donor contrast. Geography, slopes, fitted c, satellite timing, bank and priors remain unchanged. This is a new initializer, not an accepted estimate.

| Transfer | DS22-109 full objective | DS22-131 full objective |
|---|---:|---:|
| Low-derived state, full-derived contrast, low anchored | 36200.741060 | 36866.120768 |
| High-derived state, full-derived contrast, high anchored | 34791.730485 | 38022.750181 |
| Full-derived state, low-derived contrast, low anchored | 43613.183334 | 41899.456546 |
| Full-derived state, high-derived contrast, high anchored | 43623.376563 | 42008.067157 |

Forward transfers lower both half-derived states' full objectives in both cases; reverse controls worsen the full-derived states. The 131 low-derived forward transfer is already 36.895365 objective units better than the old full winner, while preserving its own-band likelihood exactly. The high-derived transfer improves by 2555.929041 but still trails the old full winner by 1119.734048. This supports testing joint initialization of band contrast and physical state, rather than concluding that the unchanged model necessarily rejects every near solution. No selection uses the known position error.

All transferred states satisfy their original domain constraints. Maximum native anchor correction discrepancy is 5.83e-11 Hz; the anchor-band NLL is checked within 1e-7. Source `b6a8d55c8`, two analytic two-receiver anchor tests and Ruff pass. Each case used seven objectives in 28.73/31.07 seconds under the same 120/135/140-second bounds. Receipts: `ds22-anchored-contrast-audit-v1/{DS22-109,DS22-131}` beneath the same bulk root.

The next frozen experiment (`463e4b7bf`) runs all four transfers per case, including reverse controls, with one 60-second/600-iteration native continuation each, a five-second independent-audit reserve and external 135/140-second bounds. All eight outcomes must seal before a reference comparison. The previous accepted combined winner remains eligible. No new likelihood, calibration freedom, bank or domain is introduced; the extra eight fits are additional search cost.
