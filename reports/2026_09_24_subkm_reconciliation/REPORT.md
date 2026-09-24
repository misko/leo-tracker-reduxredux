# Why earlier positioning evaluations reached sub-kilometre errors

This review searched the repository's positioning reports for every numerical
sub-kilometre claim and traced each result to its evaluation coordinate,
association source, timing/orbit nuisance model, likelihood, data cohort and
qualification status. The current comparison is DS1 baseline versus one shared
receive-time shift, published in `reports/2026_09_24_ds1`.

## Conclusion

There has not been one previously validated blind sub-kilometre estimator that
the current pipeline accidentally removed. Earlier results fall into four
different categories:

1. results invalidated by the corrected antenna coordinate;
2. conditional development results using identities or candidate pools selected
   by earlier analyses;
3. flexible timing models that reached sub-kilometre error on one group but did
   not transfer consistently; and
4. a strong fixed-identity orbital-error model whose main ingredient—one
   constrained phase-rate correction per satellite—is absent from DS1.

The fourth category is the clearest real missing capability. On its matched
archived cohort, disabling RF orbital refinement increased error from 328 m to
3.137 km. Every tested configuration without that refinement remained between
3.137 and 3.997 km. That scale is strikingly consistent with DS1's best
full-block results of roughly 2–4 km after fitting one global time shift.

DS1 currently fits only one time shift common to every satellite and recording
in a case. It can remove a common-mode timing/orbit bias, but it cannot represent
different causal TLE phase errors for different satellites or TLE ages. It also
does not fit per-scan timing, per-track timing, correlated residuals, or a learned
measurement scale. Satellite identities are reselected at every point/time pair,
rather than frozen from a previous site-conditioned analysis.

## Reconciliation of the numerical claims

| Earlier result | Reported error | Why it was small | Qualification and comparison with DS1 |
|---|---:|---|---|
| Sep 7 pooled nominal / calibrated | 669 / 292 m | Nineteen site-selected scans; the calibrated arm used the configured site | The confirmed antenna is 1.29 km from the old configured coordinate. Corrected errors are **1.758 / 1.579 km**. These are not sub-kilometre results. |
| Sep 20 site-selected shared clock | 895 m | Fixed historical site-selected identities plus a fitted common UTC shift | Conditional on identities selected with site knowledge; broad-selected identities remained 1.909 km. A 12-policy diagnostic reached 968 m after the successful option was visible. |
| Sep 21 exploratory orbit correction | about 275 m | Fixed identities plus one constrained orbital phase-rate correction for each of 446 retained satellites | Strong development evidence, but conditional on archived identities and one repeatedly studied site. It uses far more source-specific flexibility than DS1. |
| Sep 21 formal orbital model | 328 m | Same per-satellite orbit correction, fixed identities, learned nominal causal phase prior, learned scale and correlated Student-t likelihood | Cleanest earlier sub-km result. The ablation attributes the major gain to per-satellite RF orbit refinement, not merely robust loss or correlation. |
| Sep 21 formal duration/subset fits | 403 m at 4 h; 498 m at 8 h; many sub-km subsets | Same fixed-identity formal orbit model; observations spread across passes | Non-monotonic and single-site. Some reduced fits did not converge; identities came from full-archive analysis. |
| Sep 23 sixteen-scan development | 314 m, later 412 m under training-only scoring | Conditional union of identities from earlier Sacramento/Reno searches; continuous local position fit; independent integer timing/CFO choices per track | The 314 m point used the production objective; a later training-only replay reached 412 m. The candidate universe had historical evaluation exposure and validation windows gave 1.322–13.635 km. On seven disjoint day groups, the comparable native estimator had **4.321 km median error and 0/7 below 1 km**. |
| Sep 23 fractional per-track timing | 630 m in one 10-scan group | Independent continuous timing per candidate/track | Reversed on the other 12-scan group: 1.04→3.74 km. About 96% of selected track times were noninteger and the ±5 s support greatly exceeded measured capture-time brackets. |
| Sep 23 per-scan epoch model | 886–887 m on one 79-scan TRAIN group | One regularized timing parameter per scan with fixed baseline identities | Descriptive TRAIN result. The best regularization scale changed across TRAIN groups, and no frozen validation/test result established the same accuracy. |
| Sep 21 dual-LNB beam proxy | 348 m in one of three folds | Retrospectively calibrated directional-response proxy added to the orbit-corrected Doppler fit | Unqualified: 2/20 shuffled response controls beat the 348 m point, the real proxy ranked 4th/6th/3rd across folds, and held Doppler RMS worsened in every fold. A later full-corpus test found only a 4.9 m change and ranked the real response fourth against five shuffles. |
| Sep 21 dual-receiver extension | 898 m | Changed receiver reference/coverage and added calibrated cross-receiver samples | Site-conditioned; exact-orbit approximation and uncertainty checks failed. Not a qualified sub-kilometre lock. |

## What the strongest ablations establish

The formal Sep 21 experiment is the most diagnostic matched comparison:

| Formal-model change | Error | Held RMS | Implication |
|---|---:|---:|---|
| Complete model | **328.4 m** | 86.59 Hz | Reference development result |
| Disable per-satellite RF orbit refinement | **3,137.1 m** | 165.52 Hz | Largest isolated loss; primary missing physical model |
| Remove within-track correlation | 920.6 m | 84.25 Hz | Correlation helps location but is not solely responsible |
| Fix measurement scale at 250 Hz | 927.9 m | 80.63 Hz | Learned scale helps location; lower held RMS alone does not rank accuracy |
| Gaussian independent noise with learned scale | 335.7 m | 78.77 Hz | Student-t and correlation are not required for that archive when orbit refinement remains |

Identity uncertainty by itself did not recreate the improvement. A matched
fixed-identity versus identity-mixture experiment changed error from 2.007 to
2.040 km despite slightly improving held prediction. Candidate softening is
therefore useful for honest uncertainty, but the existing reports do not identify
it as the source of the 328 m result.

The result also depends on data selection and geometry. The formal archive uses
622 fixed-identity episodes, 21,702 observations and 211 recordings. Its duration
curve is not monotonic, and quarter/half subsets show substantial convergence
and error spread. DS1 uses five different frozen eight-hour groups with at most
80 recordings per group, complete all-track accounting, and causal catalogue
candidate reselection. The problems have different information and conditioning.

## What DS1 is doing differently

| Component | DS1 shared-time model | Strong formal sub-km model |
|---|---|---|
| Time/orbit nuisance | One tau shared across the entire case | One constrained phase-rate correction per NORAD, tied to TLE age |
| Satellite identity | Reselect candidate from the causal regional catalogue at every position/tau | Fixed identities inherited from full archived RF analysis |
| Frequency offset | One constant CFO per track | Profiled per-segment offsets |
| Residual model | Occupied-second weighted 800-Hz capped squared RMS | Learned-scale normalized likelihood; formal arm uses correlated Student-t innovations |
| Geographic acquisition | Blind historical seed from 250/500 km prior, then adaptive bounded local refinement over the staged trace/point union | Three external starts over a Denver-centred 9,000-mile square, conditional fixed identities |
| Cohort | Five grouped DS1 windows, 1/6/16/all views | One 211-recording single-site archive and overlapping subsets |
| Evaluation status | Retrospective grouped regression; validation and partial TEST exposed | Conditional single-site development replay |

The DS1 fit is more restrictive in its orbit/time physics and less conditional
on a chosen identity set. That makes it harder, and the remaining kilometre-scale
bias is expected if causal TLE errors differ by satellite. The observed DS1 tau
variation supports this: completed full groups select -0.75 s except one group at
-0.20 s, while short cases span +0.30 to -1.15 s. One universal physical clock
offset does not explain that pattern.

## Recommended next comparison

Do not restore the old 446-parameter model wholesale and tune it against DS1
reference errors. The clean next step is a frozen, nested ablation on DS1:

1. **Global tau control:** retain the newly established DS1 shared-time model.
2. **Fixed-identity control:** freeze identities selected only from TRAIN under
   the same regional catalogue and compare them with DS1's pointwise reselection.
   This isolates association switching from the added nuisance physics without
   importing historical site-selected identities.
3. **Per-scan time:** add one strongly regularized scan offset around the global
   tau, with scale selected entirely inside TRAIN groups.
4. **Per-NORAD causal phase rate:** add one correction shared across appearances
   of a satellite, with a zero-centred prior learned only from pre-target catalogue
   updates. Count the prior once per NORAD and use exact-SGP4 replay as a gate.
5. **Combined low-rank model:** global tau plus constrained per-NORAD rates;
   include a no-correction control and report identifiability/location coupling.
6. **Likelihood ablation:** compare the current capped objective with a smooth
   robust model and a simple correlation-aware model while holding associations,
   nuisance structure and geographic search fixed.

Run these first on DS1 TRAIN, freeze one complete model rule, then evaluate both
validation groups without choosing the model from position truth. The exposed
TEST group can remain regression evidence, but cannot become an untouched final
test again. Every arm should retain the same tracks, randomized inner masks,
failure accounting and matched geographic search points. Report position and
held prediction together because earlier work repeatedly showed that the lowest
frequency RMS need not have the best position.

The leading hypothesis is therefore precise: **global time captures common-mode
bias; constrained per-satellite causal orbit phase is the missing term most
strongly supported by previous matched ablations.** Per-scan timing is the next
simpler competitor. Per-track timing can produce attractive coordinates, but its
cross-group reversals and excessive freedom make it a diagnostic rather than the
preferred model.

## Source reports

- `reports/2026_09_20_matched_positioning.md`
- `reports/2026_09_21_uncertain_position_comparison.md`
- `reports/2026_09_21_positioning_breakthroughs.md`
- `reports/2026_09_21_formal_position_benchmark.md`
- `reports/2026_09_21_position_ablation_report.md`
- `reports/2026_09_21_position_subset_benchmark.md`
- `reports/2026_09_21_shared_identity_orbit.md`
- `reports/2026_09_21_dual_lnb_geometry.md`
- `reports/2026_09_21_dual_lnb_geometry_followup.md`
- `reports/2026_09_22_paired_receiver_position_comparison.md`
- `reports/2026_09_23_sixteen_scan_comparison/README.md`
- `reports/2026_09_23_day_position_validation/METHODS_TABLE.md`
- `reports/2026_09_23_training_position_search/README.md`
- `reports/2026_09_23_fractional_timing_position/README.md`
- `reports/2026_09_23_second_train_epoch_replication/README.md`
- `reports/2026_09_24_ds1/REPORT.md`
