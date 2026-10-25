# Retrospective for the evidence synthesis

This review uses completed, published evidence through commit
`79f8bc300848c930e1a2879f8e268362cd97f232`. The current parent-orbit comparison is
unfinished and supplies no new numerical or adoption claim here.

## Strongest established gains

**ALGO02 is the clearest broader gain.** On 404 common qualified DS23 pairs,
mean/median error changes 1.870/1.633→1.520/1.270 km for c=0 and
1.870/1.602→1.508/1.249 km for fitted-c. Crucially, the outside-development
group is 393 attempted recordings, **384 common qualified pairs**, rather than
393 successful comparisons: fitted-c mean/median improves
1.876/1.588→1.526/1.257 km. Qualification is 404/413 for ALGO02 versus 407/413
for ALGO01. This is a substantial within-site result with a coverage tradeoff,
not new-location transfer or sub-0.5 km performance.
[Completed ALGO02 evaluation](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_19_algo02_ds23_full/README.md).

Its retained-family predictive evidence is also a controlled useful increment:
404-case curved-only mean→paired-policy mean is 1.558→1.520 km c=0 and
1.552→1.508 km fitted-c; 365 pairs use predictive evidence and 39 retain their
curved reference. This is distinct from later speculative new-family recovery.
All-channel DS24 data also outperform either channel half on the same24 scans
(fitted-c means1.220 versus1.558/2.040 km). Neither result implies arbitrary
additional points or overlapping channels contribute independent information.

## Findings that should change priorities

| Completed experiment | Evidence | Practical interpretation |
| --- | --- | --- |
| Frozen RX1 correction | Development 24 fitted-c mean 1.220→1.120 km, but later eight mean 1.239054→1.223610 km; c=0 later mean 1.242579→1.239835. Both later P95s worsen, with 3 improvements, 3 regressions, 2 exact fallbacks per arm. | The roughly 100 m development gain does not recur at comparable magnitude. Do not retune this selector on the now-exposed eight or promote a generic smooth correction. |
| Cleaner RX2 CFO | Median fixed-degree scatter 78.07→22.18 Hz on 322 curves, without a qualified cohort accuracy gain. | Better frequency scatter is useful evidence, but is not the demonstrated limiting repair by itself. |
| More native recovery | Fitted-c postfit coverage 70.71→74.41%; mean 1.434→1.426 km, P95 3.082→3.202 km. Grouped new-family recovery worsens the fast 204 mean/median despite improving the full 410 mean slightly. | Optimize additional reliable geometry, not association count. Postfit extensions are not automatically new position-likelihood observations. |
| Phase/shape factorial | Eight shared artificial realizations; unchanged inference. Fitted-c means 0.469 original, 0.403 phase removed, 0.405 shape removed, 0.297 both removed. 30/32 newly fitted arms qualify; the two original slope failures remain. | Both generating components matter conditionally. This is no instruction to shrink real priors, and endpoint interactions do not isolate optimizer error. |
| Continuous restarts | 30 targeted restarts agree within 2.06 cm; four half-channel label transfers provide no qualified better full-data result. | Generic extra starts are low priority for these tested identities; discrete alternatives remain unresolved. |
| Information allocation | Same 26 complete unowned curved owners: information selects shorter sources in 3/4 exposed scans, but its winners include already ambiguous identities. | Information can allocate work after identity/support checks; it cannot authenticate an informative guessed identity. |
| Ordinary nomination falsification | 8/8 generated physical identities shortlisted and raw winners correct; 7/8 qualify per arm. Four raw polynomial draws favor unresolved, but 0/4 qualify numerical ordering. | No evidence here that merely enlarging the shortlist fixes ambiguity. Numerical/support handling needs qualification before false-match or identity-threshold claims. |

Sources: [receiver/later test and factorial](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_25_ds24_phase_shape_validation/README.md),
[earlier receiver/orbit controls](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_24_ds24_receiver_orbit_controls/README.md),
[recovery/measurement review](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_25_ds24_next_directions_review/README.md),
[nomination and information](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_25_ds24_nomination_information/README.md).

## Bounded next priorities and stopping rules

1. **Finish the concrete parent-covariance audit.** The completed metadata
   inventory finds 33/89 active scan-family instances without physical-mode
   covariance, covering 1,544/12,442 old likelihood points. This is a real model
   choice, but its DS24 accuracy effect is not known. Reuse the existing
   all-candidate physical-prior machinery; old DSX01 outcomes were mixed.
   Require zero-extra-variance closure, correct normalization, shared
   curved/predictive covariance and explicit uncertainty/calibration flags.
   Only the frozen fixed-RF triage can launch bounded matched diagnostics;
   stop on numerical failure or negligible effect. Keep literal and
   conservative gates separate and retain the operational reference regardless
   of this four-case result. Do not represent accepted-ID preservation as an
   original residual gate: it is an additional declared research condition.

2. **Qualify the identity decision procedure before adding its best source.**
   Test the already observed failure modes: invisible phase support must have
   zero likelihood without silently renormalizing away its prior penalty;
   clearly dominated alternatives need valid integration or conservative
   evidence bounds. Freeze these rules before re-evaluation and preserve the
   current failed trials. Stop if numerical bounds cannot certify the ordering
   under the bounded budget, or if a close physical alternative remains. Do
   not rescue a miss by forced truth retention or loosen gates because raw
   geographic error happens to improve. Any new whole-owner witness must be
   separately selected, with shared family/radio covariance retained.

3. **Investigate an omitted coupling only after a fixed-state effect exists.**
   Earlier conditional phase integration already found at most 22.8 m predicted
   local shifts while shape design and precisions were held fixed. A new test
   must include phase-dependent physical design under the same prior law,
   compare fixed RF-selected positions/gradients and show integration
   convergence before position refitting. Stop if it reproduces the old small
   effect or cannot qualify numerically. A generic full-Bayes rewrite or more
   importance samples is not a discriminating next experiment.

For any promising frozen policy, reserve a further chronological existing
recording panel before inspecting errors, reconcile exact identities/public
contracts and validate inclusion without replacement. All24 DS24 and the8 RX1V
cases are now exposed; repartitioning them does not make a fresh benchmark.
Remaining inventory candidates are not validation-ready until those checks
actually pass. Require matched c arms, all failures, exact fallbacks and
mean/median/tail accounting. A small same-site gain is not new-location transfer.

The radio conclusions remain bounded. All usable DS24 channel-comparison scans
are 10 MS/s, so there is no controlled sample-rate effect. The nominal 40-degree
feed angle changes coverage; it supplies neither measured bearing nor a
spatial triangulation baseline. Relative cross-RX contrasts retain source/path
ambiguity and cannot be added as independent duplicate evidence. Local Gaussian
ellipse scales are also conditional: the earlier 11/24 below a 95% chi-squared
reference is a descriptive comparison, not a calibrated coverage test.
[Information/geometry limits](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_24_ds24_bottlenecks/information/REPORT.md).
