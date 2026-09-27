# DS6 report status

Updated September 27, 2026. DS6 is minted: **43 recordings, 95,269 visits**.
The [frozen inventory](2026_09_27_ds6_roof/TABLE.md) and
[dataset manifest](2026_09_27_ds6_roof/README.md) define its membership.

The latest validated pooled location result is approximately **755 m from the
operator reference**, driven by frequency measurements. Adding phase has not
demonstrated a useful location improvement. The reference is operator supplied,
not surveyed ground truth; numerical centimetre changes are not physical accuracy.

| Report | Status and result |
|---|---|
| [Corrected full-cohort refit](2026_09_27_ds6_envelope_refit/README.md) | Latest matched positioning comparison: CFO only 754.978 m; CFO plus phase 754.990 m. All 43 scans contribute CFO; three contribute five phase pairs. |
| [Stationary offset validation](2026_09_27_ds6_fast_offsets/README.md) | Corrects the unconverged frequency-offset profiler and validates its replacement. |
| [Phase opportunity replay](2026_09_27_ds6_phase_opportunity/README.md) | Four additional scans selected; two had eligible pairs. One pair retained both training endpoints across an 18.3-second span. |
| [Geometry versus response drift](2026_09_27_ds6_long_phase_geometry/README.md) | Latest phase mechanism comparison: geometry predicts held phase better than a constant, but equally well as slow linear response drift. No unique geometric attribution. |
| [Additional pair census](2026_09_27_ds6_pair_catalogue/README.md) | New metadata-only inventory: 12 eligible pairs, 250 visits in five of ten additional scans. Curvature ranking and IQ replay remain pending. |

Earlier [pooled results](2026_09_27_ds6_cohort_phase/README.md) used the old
offset profiler and are retained as historical experiments. Use the corrected
full-cohort refit above for the current positioning comparison. Earlier sparse
geographic grids and three-scan fits do not supersede it.

Next scientific step: select pairs using training-predicted nonlinear phase
evolution, then compare geometric and response-drift predictions on held visits.
This is needed to establish whether phase adds satellite association or location
information beyond CFO. No new RF collection or local calibration is required.

The [complete CFO investigation report](2026_09_27_ds6_results/README.md)
consolidates the independent-scan and combined-position results, numerical
repairs, negative experiments, validation record, and artifact inventory.
The corrected independent estimator has **6/43 scans below 1 km**, mean
**3333.239 m**, and median **2425.128 m**. The independently revalidated combined
CFO fit is **754.938 m**, with randomized subset errors **935.176 m** and
**637.095 m**. These are separate estimators and must not be conflated.

Historical failed or inconclusive experiments are retained as evidence, not
certified improvements. In particular, the old offset-convergence audit records
an unresolved IRLS case; the later stationary solver supersedes it. The pair
census's rank.py is preserved as exploratory tooling, with ranking results still
pending as stated in that report.
