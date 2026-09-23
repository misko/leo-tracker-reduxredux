# Frozen model comparison after the dataset split

This development experiment continues the sub-300-metre long-duration objective.
It does not open the prospective test reserve. Recording assignments are fixed by
`../2026_09_23_position_train_val_test/dataset/manifest.json`: 64 training,
49 retrospective validation, and the documented quarantine. Validation was
historically exposed, so its results remain development evidence.

## Families declared before new validation fits

1. **Regularized scan timing.** At each of three existing training-derived
   geographic points, minimize training squared frequency residual plus
   `lambda * (tau_track - clock_scan)^2`. Grid lambda over
   `[0, 100, 1000, 10000, 100000]` Hz²/s² and retain a hard shared-clock control.
   Choose the configuration using reserved frequency rows within the training
   recording partition, then seal it before reading validation predictions.
   These inner rows select a model and are not an untouched performance test.
2. **Training-only continuous position search.** Fit location using per-track
   training-selected identity, integer timing and CFO, with the original
   duration-weighted 800 Hz capped objective. Use only geographic seeds from
   scans in the particular inference window, with the Sacramento-250-km and
   Reno-500-km intersection as hard support. No known coordinate or finalist
   from a different duration window may initialize validation fits.
3. **Robust continuous position search.** Use the same search, with a track-level
   pseudo-Huber objective at scale 150 Hz:
   `2 * 150^2 * (sqrt(1 + (track_training_RMS / 150)^2) - 1)`.
   This scale is declared from the training residual audit (median track RMS
   about 83 Hz, upper quartile about 128 Hz), without looking at new validation
   position outcomes. Keep the baseline and robust arms, including failures.

Each satellite/timing choice and CFO uses the exact saved training mask. Model
parameters and spatial basins may not use validation-window reserved frequency
rows. A fixed model is allowed to fit a new window's parameters from its training
rows; it is not required to reuse the old training location.

The experiments reuse conditional production candidate pools for computational
feasibility. Historical candidate discovery and seed discovery used evaluation
data. Consequently, even the new training-only spatial objective does **not**
make this an end-to-end independent full-catalogue acquisition test. Fixed-point
selection and new continuous spatial estimates must be reported separately.

## Duration and accounting

Use the manifest's non-overlapping windows at 1, 6, 18 and 48 scans. Always report
elapsed span and nominal captured duration separately. The initial bounded
continuous-search run declares the first window in each tier before fitting;
expand to all windows only if measured runtime permits, recording every attempted
window and any omissions. Never exclude a completed result because its error is
large. A single long window cannot demonstrate an error distribution.

Geographic error uses the same locked reference as the previous dataset report,
introduced only after inference is saved. Compare median/tail errors where enough
windows exist, reserved-row RMS on common support, timing-bound rates, failures,
and runtime. A low residual or sub-300-metre training case alone is not success.

## Separate physical checks

The 11.2 GHz prediction reference is not by itself a missing RF correction:
`persistent_hop_trajectory._lane_tracklets` scales measured lane CFO by
`canonical_rf_hz / actual_rf_hz`, and the exported graph carries normalized CFO.
The current cached numerical comparisons use that same convention.

The array was confirmed rotated at 2026-09-23 14:49:09 UTC, after development
validation's final nominal capture end and before the prospective-test boundary.
Future testing therefore also probes changed orientation and sky coverage.
Do not transfer phase/beam calibration across that change implicitly. See
`../2026_09_23_eight_hour_glrt_rotation_baseline.md` and the station geometry log.

No radio collection or production deployment is part of this experiment.
