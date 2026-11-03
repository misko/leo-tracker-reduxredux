# Predictive tails and extrapolation uncertainty explain much of the transfer failure

Holding every fitted curve, component weight and model-selection decision fixed, Student-t4 predictive tails plus design-based extrapolation uncertainty give positive pooled gains against a **same-density robust-mean comparator** in all three datasets and both split types. The primary 100 Hz version improves 3/4, 4/4 and 3/4 forward scans. Eight pre-existing unconverged robust controls remain missing in alternating folds, so the complete primary gate still fails. No localization model is promoted.

| Dataset | Alternating gain: fixed matched t4 | Alternating: leverage matched t4 | Forward: fixed matched t4 | Forward: leverage matched t4 | Forward scans improved with leverage |
|---|---:|---:|---:|---:|---:|
| DS9 | +0.872 | +0.776 | −0.010 | +0.123 | 3/4 |
| DS10 | +1.661 | +1.501 | +0.307 | +0.536 | 4/4 |
| DS11 | +1.543 | +1.383 | +0.218 | +0.424 | 3/4 |

Values are nats per held observation, sigma=100 Hz, selected mixture policy minus equally adjusted robust-mean control. “Matched t4” matches the Gaussian variance, dividing its standard deviation by sqrt(2) to obtain the t4 scale. This prevents attributing a simple variance increase solely to heavier tails. The same-scale t4 controls show similar directional behavior, with forward leverage gains +0.097 / +0.493 / +0.391.

![Tail and leverage ablations](predictive-uncertainty-summary-v1.png)

## What was isolated

The earlier transfer compared fixed-width Gaussian policy predictions with a heavy-tailed robust-single predictor. That comparison was operationally valid for those two policies, but conflated trajectory means and predictive density. Here each arm applies the **same density family and uncertainty construction to both means**. Fixed-Gaussian evaluation of both fitted means gives pooled forward differences +48.24 / +76.63 / +184.02, showing how strongly the previous ranking depended on the heavy-tailed comparator rather than simply which curve was fitted. These large Gaussian score differences are not evidence of calibrated Gaussian prediction.

The mixture policy also improves over a single OLS curve when both receive matched-t4 leverage predictions: forward gains are +0.240 / +0.458 / +0.433. Thus the positive result is not only a contrast between robust and non-robust mean fitting. Yet one DS9 and one DS11 forward scan still worsen, and this remains reused development evidence.

Adding leverage slightly reduces alternating gains but improves forward gains. That pattern is consistent with uncertainty being most useful outside training support. At the frozen 300 Hz control scale, matched-t4 leverage improves only one of four DS9 forward scans, so the evidence is not uniformly robust to scale choice. Do not choose a scale by these outcomes or claim universal transfer.

## Mathematical approximation and limits

For a quadratic design row x and training design X, the component covariance approximation is sigma² (Xᵀ R X)⁻¹. R contains training responsibilities from the frozen Gaussian mixture; single OLS uses identity weights, and robust single uses its frozen t4 IRLS weights. Predictive variance is sigma²[1+xᵀ(Xᵀ R X)⁻¹x]. Component means, weights, fitting choices and training/held partitions are unchanged. Mixture scores sum normalized densities over components.

This is conditional weighted-design uncertainty, not a calibrated Bayesian posterior. It omits component-assignment uncertainty, cross-component parameter coupling, temporal correlation and model discrepancy. The robust version is an IRLS metric approximation. Rank-deficient or condition-number-above-1e12 information is rejected rather than pseudoinverted. No such new leverage failures occurred; the eight missing primary comparisons are the saved robust-control convergence failures.

The unadjusted Gaussian score replay matches the saved policy scores within 5.83e-10 nats. The original robust t4 scores also reproduce within the declared numeric tolerances. Primary alternating coverage remains 371/372, 357/362 and 372/374 folds; every forward comparator is available. Five tests cover analytic leverage, singular-design rejection, mixture-density parity, extrapolation growth, variance-matched t4 scaling and explicit missing-control denominators. The bounded replay exited successfully without any fitting, orbit calculation, GPS score or RF access.

## Next decision

Do not relabel the earlier Gaussian transfer as successful. Its fixed-width predictive policy failed. This follow-up identifies a different, better-motivated prediction rule and records its remaining weaknesses. Before integrating component assignments into localization, resolve the eight robust-control numerical failures in a separately bounded replay and freeze one predictive rule for another complete-block check. The source fits and failed receipts must remain unchanged. A later localization arm must still account for exclusive observations, component-specific offsets, changed point retention and the same single/pair/quad budgets; radio log-score improvements are not meter-error improvements.

Plans and receipts: `PREDICTIVE_UNCERTAINTY_PLAN.md`, `predictive-uncertainty-v1.json` and `predictive-uncertainty-summary-v1.json`, with SHA sidecars. All six density/leverage arms, both noise scales, per-scan gains and missing comparisons remain available.
