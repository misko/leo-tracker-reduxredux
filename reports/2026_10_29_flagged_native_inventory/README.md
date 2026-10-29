# Polynomial residual flags can hide usable physical-orbit evidence

All **21 remaining large native proposals** have now been tested, retaining their original polynomial quality flags. Outcomes: {'conditionally_supported_identity': 14, 'ambiguous_identity': 6, 'unstable_identity': 1}. Of 14 consistent causal nominations, **10 pass the unchanged individual inclusion checks** in both c arms, including every old association and point-ownership check. Overlap prevents adding these counts directly to the earlier clean cohort; the [all-quality joint policy](../2026_10_29_native_all_large_policy/README.md) resolves their interactions.

## What the flags mean here

Every one of these stored proposals carries `adjacent_residual_correlation`. A polynomial approximation is not the physical satellite Doppler curve. The original builder chooses degree with squared residual divided by a fixed 150 Hz noise scale plus `(degree+1) log(n)`, subject to its existing support and slope constraints. Correlated approximation error can therefore survive the complexity penalty. A polynomial flag is evidence to investigate, not proof that the raw measurements are clutter or that a satellite cannot explain them.

The saved models use **Legendre coefficients**, not ordinary power-series coefficients. Replaying every piece on the original lane ordering reproduces all 21 stored RMS values to within 1e-6 Hz. No degree, breakpoint, membership, CFO, alias or flag is changed. The raw data then enter the same causal orbit nomination and prediction checks as the clean proposals. Identity validation still uses three distinct randomized whole-block holdouts. The builder's legacy conditional interior-block diagnostic is retained only as existing provenance; it is not presented as new randomized validation or used to override physical checks.

The physical-model gains are observable: DS24-0053's 50-point branch falls from about 71 Hz polynomial RMS to 26 Hz orbit RMS; DS24-0075's 46-point branch falls from 34 to 19 Hz. Both pass individual inclusion. Some flagged proposals still fail, and some contain points already covered by alternative clean branches. Neither a low RMS nor a consistent nomination alone authorizes inclusion.

| scan | points | span_s | poly_degrees | polynomial_RMS_hz | annotation | norad | inclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DS24-0012 | 24 | 43.937 | 2 | 55.825 | conditionally_supported_identity | 64108 | passes |
| DS24-0014 | 40 | 58.474 | 4 | 38.468 | ambiguous_identity | 69509 | not_eligible |
| DS24-0014 | 52 | 77.617 | 4 | 74.810 | ambiguous_identity | 69509 | not_eligible |
| DS24-0014 | 56 | 62.378 | 3 | 74.232 | ambiguous_identity | 69509 | not_eligible |
| DS24-0053 | 50 | 86.821 | 4 | 71.214 | conditionally_supported_identity | 64807 | passes |
| DS24-0053 | 33 | 56.313 | 3 | 58.952 | conditionally_supported_identity | 64776 | rejected |
| DS24-0075 | 33 | 52.445 | 3 | 51.099 | conditionally_supported_identity | 63858 | passes |
| DS24-0075 | 46 | 58.117 | 4 | 33.998 | conditionally_supported_identity | 63858 | passes |
| DS24-0083 | 41 | 64.860 | 3 | 80.452 | conditionally_supported_identity | 100312 | rejected |
| DS24-0089 | 43 | 52.792 | 4 | 26.780 | ambiguous_identity | 69255 | not_eligible |
| DS24-0089 | 61 | 60.944 | 4 | 52.609 | ambiguous_identity | 69255 | not_eligible |
| DS24-0091 | 29 | 54.598 | 3 | 35.219 | conditionally_supported_identity | 66072 | passes |
| DS24-0091 | 67 | 79.745 | 4 | 70.245 | conditionally_supported_identity | 67960 | rejected |
| DS24-0097 | 30 | 61.319 | 3 | 36.653 | unstable_identity | None | not_eligible |
| DS24-0098 | 51 | 67.629 | 3 | 84.077 | conditionally_supported_identity | 63959 | rejected |
| DS24-0099 | 35 | 39.687 | 3 | 39.247 | ambiguous_identity | 63480 | not_eligible |
| DS24-0099 | 49 | 66.969 | 4 | 63.612 | conditionally_supported_identity | 63480 | passes |
| DS24-0099 | 57 | 64.133 | 3 | 77.456 | conditionally_supported_identity | 63480 | passes |
| DS24-0100 | 36 | 55.907 | 3 | 56.727 | conditionally_supported_identity | 66171 | passes |
| DS24-0101 | 38 | 54.224 | 4 | 27.488 | conditionally_supported_identity | 66425 | passes |
| DS24-0101 | 40 | 54.229 | 3 | 44.336 | conditionally_supported_identity | 66425 | passes |

See [all 14 CFO and residual figures](gallery.md), [identity ledger](flagged_annotations.csv), and [matched position trials](flagged_inclusion_trials.csv). Each plot overlays the original polynomial residual and the bias-profiled orbit residual. These are descriptive in-sample residuals after separate randomized identity tests, not an independent model-selection score. Position error and frequency fit are reported separately, with matched c=0/fitted-c settings. Selection never uses GPS; errors alone use the established evaluation site. No future TLE or new RF collection is used.

## Original graph inventory also advanced

The next eight original graph tracks, each containing 70–71 unassociated points, completed bounded annotation. Outcomes: {'conditionally_supported_identity': 5, 'unstable_identity': 2, 'prediction_mismatch': 1}. These are identity assessments, not new accepted position observations. The original ledger now has **689 / 1630 assessed entries**, preserving previous role disagreements and retests. Native proposals remain a separate overlapping inventory and do not inflate this denominator.

| scan | track_id | status | norad | execution |
| --- | --- | --- | --- | --- |
| AUTO-c0dd2487 | 791eca0e6eab43ee54eb | conditionally_supported_identity | 66109 | complete |
| AUTO-d969e15a | 89f8bbdd07fb6cb268bf | unstable_identity | None | complete |
| AUTO-7ec14096 | d6023afbd8e2c2feceaf | conditionally_supported_identity | 59835 | complete |
| AUTO-453faf4c | e1cf2ab9103a8ff316fc | conditionally_supported_identity | 55455 | complete |
| AUTO-8d229584 | f6504a9e8048e850d215 | conditionally_supported_identity | 100017 | complete |
| AUTO-c0dd2487 | afa467e94e93668d0258 | prediction_mismatch | 69341 | complete |
| AUTO-d9185bf9 | d1c38aa3c6a00ccc5b41 | conditionally_supported_identity | 63863 | complete |
| AUTO-f122bc7e | f854b8c2f5e5360099df | unstable_identity | None | complete |

The clean and flagged native cohorts together now cover all **93 discovered large native proposals**: 60 conditionally supported identities, 17 ambiguous, four unstable, ten insufficient-partition cases, and two prediction mismatches. The [complete native proposal ledger](native_branch_ledger.csv) contains all 813 proposals, the updated outcomes for all 93 large ones, and an explicit `joint_selected` column. This does not prove all 93 true satellite identities. Conditional support depends on the frozen graph, catalogue search and incumbent calibration; unresolved cases remain explicit.

Reproduce using the frozen `flagged-native-cohort-v1` protocol, `run_native_branch_annotations.py`, `run_native_branch_inclusions.py`, and `report_flagged_native_inventory.py`. All jobs use 600-second caps; annotation batches have at most eight workers. The original graph batch uses `run_annotation_inventory.py run --limit 8 --workers 8 --distinct-partitions`. [Source hashes](sources.json), [compressed evidence](evidence.json.gz), [original graph ledger](annotation_ledger.csv), and [batch results](inventory_batch.csv) preserve the audit trail. No production change or new ALGO is promoted.
