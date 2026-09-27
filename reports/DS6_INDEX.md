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

This index covers published DS6 phase work and the completed metadata census.
Other local exploratory directories are not certified results merely because
they exist in a working tree.
