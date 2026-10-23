# DS23 debug iterations and ALGO promotion

Continue from the existing ALGO02 and ALGO03 implementations. Each bounded
iteration selects the next **two** worst position-error scans from the latest
full-DS23 published benchmark, runs DBG01, examines unused GLRT evidence,
records hypotheses, prototypes and controlled results, and publishes an MD
report with figures and tables to remote main. Negative results are included.
Close a batch after its bounded tests; move to the next cases when progress
stalls. Revisit a closed case only for a new transferable hypothesis.

Aim for **90% supported original GLRT association**, while preserving noise,
structure, alias, visibility and physical-prior checks. Report graph-coverage
ceilings and unique measurement IDs. Do not force association or confuse a
better in-sample frequency fit with better position.

All inference uses causal TLEs, the original 25 × 25 km regional box, and no
evaluation GPS or manually selected identities. GPS may rank debug priorities
and evaluate frozen outcomes. Keep c=0 and fitted-c observations, candidates,
other priors and search budgets matched. A moving trajectory and stationary
history pooling are outside the current work.

| Iteration | Scans | Result and decision | Next batch |
| --- | --- | --- | --- |
| [001](2026_10_22_ds23_dbg01_iteration_001/README.md) | 0081, 0326 | Conditional calibration/support fixes recover 97 and 21 points; large boundary errors remain. No new ALGO release. | 0035, 0041 |
| [002](2026_10_22_ds23_dbg01_iteration_002/README.md) | 0035, 0041 | Recover 52 and 31 points; fitted-c errors become 3.741 and 2.835 km. A 30-point existing curved association enters position; conflicting shared-family merges remain rejected. No new ALGO release. | 0111, 0390 |
| [003](2026_10_22_ds23_dbg01_iteration_003/README.md) | 0111, 0390 | Adding 18 points improves 0111 to 2.422 km; adding 43 points worsens 0390 to 6.725 km despite passing gates. Random20 unrestricted growth raises association 69.69→71.35% but worsens fitted-c mean 1.742→2.195 km; a frozen RF guard changes only one case, mean 1.735 km and unchanged median. Keep incumbent; no new ALGO release. | 0221, 0322 |
| [004](2026_10_22_ds23_dbg01_iteration_004/README.md) | 0221, 0322 | Recover28/26 points; fitted-c errors2.273/3.776 km. A support-check repair recovers231 additional associations on19 other scans, mean1.620→1.609 km with unchanged median and one regression. Direct orphan likelihood exposes RF structure but no validated new minimum. No new ALGO release. | 0272, 0068 |
| [005](2026_10_22_ds23_dbg01_iteration_005/README.md) | 0272, 0068 | Graph reentry adds106 position points and148 associations in0272:67.90→73.34%, error3.783→1.220 km. Screened temporal prediction adds83 points but error remains3.746 km; independent control worsens to3.931 km.0068 remains archived3.707 km; its inherited baseline already exceeds the strict15 s phase gate. No new ALGO release. | 0069, 0291 |
| [006](2026_10_22_ds23_dbg01_iteration_006/README.md) | 0069, 0291 | Constrained supported-mode recovery reaches74.95% on0291 but worsens error3.690→7.030 km.19-case disjoint confirmation adds105 associations beyond the support control yet worsens mean1.614→1.678 and median1.337→1.598 km. Reject extension;409/410 archived outputs pass qualification, with0068 the only phase exception. | 0227, 0400 |
| [007](2026_10_22_ds23_dbg01_iteration_007/README.md) | 0227, 0400 | Grouped predictive new families add11,861 likelihood points on217/410 scans. Full fitted-c association70.08→71.22%, mean1.469→1.449 km, median1.178→1.179 km; three regressions exceed500 m and fast mean worsens slightly. Retain incumbent; no ALGO release. Independent endpoint-core prototype explains19 more0227 points and reaches2.779 km, not included in full run. | 0157, 0207 |
| [008](2026_10_22_ds23_dbg01_iteration_008/README.md) | 0157, 0207 | Whole-curve graph recovery gives0157 error3.384→1.335 km and0207 support repair3.321→3.108 km. Graph-seeded temporal recovery reaches75.41% in0207 but worsens error to3.270 km;0157 trials fail a parent ACF gate. An inconsistent endpoint and20 s duration cutoff explain a missing21-point curvy core; its calibration gives3.113 km, no further fitted-c gain. No new ALGO release. | 0028, 0311 |
| [009](2026_10_22_ds23_dbg01_iteration_009/README.md) | 0028, 0311 | All20 paired recovery trials reject.0028's26-point partial suffix favors its existing57434 family, but restoring77 points fails ACF; other-track RF covariance removes correlation yet fails raw slope/step and gives3.307 km.0311 point-priority and extra47-point searches remain structured. Retain78.38%/66.77% association and3.264/3.240 km error. No ALGO release. | 0080, 0257 |
| [010](2026_10_22_ds23_dbg01_iteration_010/README.md) | 0080, 0257 |0080 constrained temporal reaches80.83% association but fitted-c error remains3.291km, worse than3.236km incumbent.0257 short whole-curve recovery adds31 calibration points, error3.180→2.748km.20-case scan-disjoint confirmation adds394 calibration points and association69.89→71.08%, but fitted-c mean worsens1.548→1.555km despite median1.546→1.536km; c0 both regress. Retain incumbent; no ALGO release. |0163,0209|
| [011](2026_10_22_ds23_dbg01_iteration_011/README.md) |0163,0209|Same-mask RF parent choice plus existing temporal recovery gives0163 association56.31→61.33%, error3.129→2.709km;0209 temporal gives68.13→72.19%,3.051→2.907km. Full410 saved-decision paired-RF guard changes only0080/0273: fitted-c mean/median1.469461/1.178102→1.462402/1.167197km, unchanged coverage, no regressions; temporal-block intervals reach zero. Provisional, no ALGO release. Native-time index repair preserves14 prior arms exactly. |0215,0281|
| [012](2026_10_23_ds23_dbg01_iteration_012/README.md) |0215,0281|0215 support recovery adds27 calibration points,3.049→2.637km; persistent recovery reaches76.12% but worsens to2.939km.0281 whole-short32-point recovery gives73.78%,3.032→2.813km. Source-ID intersection recognizes a14-point high-leverage-endpoint core, but adds no graph-parent accuracy gain. A causal singleton60316 proposal explains29 previously unused0281 points,73.57%, yet worsens error to3.171km. No new ALGO release or full-DS23 policy adoption. |0234,0064|

0405 remains in the full evaluation. It is skipped in the next **debug queue**
because prior DBG01 and bounded recovery controls already document its stalled
case; see the [full assessment](2026_10_22_ds23_family_cavity_full_assessment/README.md).
Queue order is not an evaluation exclusion or a change to its reported error.

New **ALGO series** versions are separate from debug-iteration reports. Promote
one only when improvements are credible across the **full DS23** population:
matched c arms and availability, mean/median/tail accuracy, GLRT coverage,
individual regressions, gate failures and computational cost. Report unavailable
scans and use comparable baselines; do not select a release using only the
inspected difficult cases. This replaces the earlier positive-only iteration
publication policy, while retaining a higher bar for an algorithm release.

Current full-population reference:
[410-scan family-replacement assessment](2026_10_22_ds23_family_cavity_full_assessment/README.md),
fitted-c mean **1.469461 km**, median **1.178102 km**. The mean-and-median
**0.5 km goal remains unmet**. These data are from the existing site; full-DS23
improvement alone does not establish generalization to other locations.

Iteration011's full-population paired-evidence guard is a **provisional candidate**,
not a replacement of this published reference. It changes two previously studied
same-site cases and leaves GLRT coverage unchanged. Keep debug publications and
ALGO-series release decisions separate.
