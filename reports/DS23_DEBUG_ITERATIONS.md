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

The latest [full-DS23 ordinary graph assessment](2026_10_23_algo04_ordinary_full_ds23/README.md)
completes 408 searches plus the two predeclared inherited carries, with no new
execution failures. Across all 410 positions, fitted-c association rises
70.08%→74.41% (+44,925 points), mean error improves 1.469→1.426 km, and median
improves 1.178→1.157 km. Promotion still fails: seven regressions exceed 0.5 km
in each c arm, and fitted-c p95 increases 3.157→3.202 km. Both format-specific
medians worsen slightly. Retain the published reference. The next bounded
mechanism pair is **0259/0365**: the largest new regressions enter ordinary
native fitting and constrained native rescue, respectively. Do not reopen the
previously closed 0081/0326 pair without new evidence.

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
| [013](2026_10_23_ds23_dbg01_iteration_013/README.md) |0234,0064|0234 combines an RF-supported shared step near158.38s with existing active-owner mode simplification:111 new curved points,62.28→68.59% associated,2.965→2.363km.0064 whole35-point recovery gives2.930→1.235km; constrained115-point prediction reaches79.09% at unchanged1.235km. The separate [full410 deadline assessment](2026_10_23_ds23_completed_deadline_assessment/README.md) recovers6 completed candidates: fitted mean/median1.453353/1.161472km,729 more associations,4 improve/2 worsen; block intervals include zero. No ALGO release. |0202,0262|
| [014](2026_10_23_ds23_dbg01_iteration_014/README.md) |0202,0262|0202 graph recovery adds71 curved points with only2.5m accuracy change; persistent56 predictive points reaches76.96%,2.765km.0262 other-band original curved evidence supports a shared RX1 step near116.403s:81 curved points recovered,70.98%,2.886→2.760km. Separate persistent132-point recovery gives72.43%,2.621km. A degree4 isolated endpoint creates false0202 curvature. Full-causal augmented63865→67119 family replacement fails RF evidence and five gates. No new ALGO release. |0273,0049|
| [015](2026_10_23_ds23_dbg01_iteration_015/README.md) |0273,0049|0273 reuses011's paired guard, then original constrained native recovery admits28 predictive points:67.21→69.90%,2.858→2.419km fitted c.0049 graph37-point69500 recovery improves2.858→2.123km; persistent31 more points gives67.17% but worsens to2.188km. Joint-event control fails RF gains. Nonlinear all-causal phase/alias proposals change the best nominee for a clean29-point curve from56030 to62563 under a matched screen, but the final fit fails structure gates. Identity unresolved; no ALGO release. |0386,0409|
| [016](2026_10_23_ds23_dbg01_iteration_016/README.md) |0386,0409|0386 graph recovery adds77 calibration points,38.90→44.27% associated,2.850→2.425km fitted c; constrained73-point prediction reaches49.37% but worsens to2.468km.0409 recovery +70 predictive points reaches76.53%,2.845→2.741km. Degree4 curvature survives the flagged0386 endpoint; quadratic-only rejection was insufficient. A separate [RF-frozen original-calibration role test](2026_10_23_ds23_distributed_calibration_roles_assessment/README.md) on random20 worsens fitted-c mean1.0645→1.0885km, unchanged median; reject promotion. No ALGO release. |0075,0087|
| [017](2026_10_23_ds23_dbg01_iteration_017/README.md) |0075,0087|Persistent native recovery reaches56.68%/63.16%, fitted-c errors2.827→2.720km and2.826→2.373km. All curved reentry trials reject. RF-selected whole-family tests with recovered native evidence favor58084/68562; alternatives lose>500 RF units and fail gates. RF-only22-case inventory finds79/949 calibration curves dominated by one standardized residual; no point removed or new noise model applied. No ALGO release. |0239,0261|
| [018](2026_10_23_ds23_dbg01_iteration_018/README.md) |0239,0261|Whole-curve/native recovery adds46/115 associations, reaching50.40%/79.91%; fitted-c errors2.795→2.520km and2.780→2.395km, both c arms improve. Six paired whole-source identity trials reject.0261 whole-family66399 replacement loses83 RF units; the new62146 CH4 curve fails structure while individually passing CH1 curves lose multi-owner support. Local phase-information sensitivity is diagnostic, not a validated tighter prior.48 figures,13 tests; no ALGO release. |0338,0185|

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

The [bounded ALGO04 recovery controls](2026_10_23_algo04_controlled_recovery_tests/README.md)
test graph rescue, common-family predictive ranking and receiver/family frequency
steps on 0344/0256/0404, with 0041/0272 positive controls. Ordinary graph fitting
plus rerun native recovery improves five-case fitted-c mean 3.029→2.507 km versus
the reference and coverage 66.50%→71.75%, but loses the beneficial 0272 graph
recovery. The new ranking rejects useful controls; no step model meets all
support and selection requirements. Eight tests pass and 38 endpoints replay
exactly. This is a bounded development result, not a full-DS23 rerun or ALGO
promotion. The report preserves negative controls and failed adapter receipts.

Current full-population reference:
[410-scan family-replacement assessment](2026_10_22_ds23_family_cavity_full_assessment/README.md),
fitted-c mean **1.469461 km**, median **1.178102 km**. The mean-and-median
**0.5 km goal remains unmet**. These data are from the existing site; full-DS23
improvement alone does not establish generalization to other locations.

Iteration011's full-population paired-evidence guard is a **provisional candidate**,
not a replacement of this published reference. It changes two previously studied
same-site cases and leaves GLRT coverage unchanged. Keep debug publications and
ALGO-series release decisions separate.

The completed-deadline candidate assessment is also provisional. It replays
cached completed decisions across all410 scans, with12 fresh endpoint-arm
audits and404 exact fallbacks; it is not a new410-scan fitting campaign.
Its70.1508% association and1.453353/1.161472km fitted-c mean/median do not
override the reference. One regression exceeds500m, temporal intervals include
zero, and no new-location generalization is established.

The [matched candidate error distributions](2026_10_23_ds23_algo_candidate_distributions/README.md)
compare the reference, grouped-family prediction, paired RF guard and completed-
candidate retention on the exact same410 scans. They include fitted-c and c=0
empirical CDFs, full error tails, fast/adaptive breakdowns and quantile tables.
This is a presentation of frozen separate policies, not a combined candidate
or new inference run. Completed retention improves mean/median/maximum while
worsening P95; retain distributional tradeoffs alongside aggregate gains.

The [two-worst-outlier review and next-experiment plan](2026_10_23_ds23_worst_outlier_review/README.md)
revisits0081/0326 at the user's request. Eight saved evaluations replay exactly;
new curved-data information diagnostics distinguish0081's strong displaced
model preference from0326's sparse, late, single-receiver evidence. It reviews
earlier failed position-cavity, partition, soft-identity and uncertainty controls
and proposes bounded tests of physical bias and information. No new position
fit, coverage change, candidate promotion or debug-queue closure is claimed.

The [bounded worst-outlier mechanism tests](2026_10_23_ds23_worst_mechanism_tests/README.md)
execute that plan on0081/0326:120 synthetic fits and exact replays,58590
cross-owner/following-orbit diagnostics, a matched0326 unit-power control and
conservative native recovery. Correct-label0326 simulation can reach18km error
with passing gates. Following elements barely change58590 after phase alignment.
Unit weights worsen0326 fitted-c error to17.712km; eight recovered same-family
points raise coverage13.17→14.66% but worsen error to14.991km. No ALGO release
or population improvement is claimed. Preserve these failures and move the next
general-method iteration beyond this bounded pair unless independent evidence emerges.

The [full-DS23 ALGO04 candidate assessment](2026_10_23_algo04_candidate_full_ds23/README.md)
tests frozen graph recovery plus persistent native-point recovery against the
published reference on all 410 available scans, with matched c=0/fitted-c arms.
There are 408 completed searches, one deadline fallback (0004), and one inherited
unqualified reference (0068); all remain in the population metrics. Fitted-c
association increases 70.08%→75.08% (+51,821 points), but mean error worsens
1.469→1.591 km, median 1.178→1.249 km, and p95 3.157→3.473 km. There are 53
regressions above 500 m. The c=0 arm also worsens. Most degradation enters at
graph recovery. **Reject promotion; retain the current reference.** This report
includes five figures, complete numerical tables, audit receipts and source
snapshots; it is not an ALGO04 release. The next debug pair remains 0338/0185.
