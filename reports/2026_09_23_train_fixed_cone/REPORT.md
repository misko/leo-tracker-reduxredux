# Fixed-cone TRAIN generalization result

The frozen experiment completed in 562.0 seconds over 77,832 candidate common
mount orientations, five unique frozen cells, two receiver mappings, five
whole-NORAD folds, four fixed cone half-widths, and 20 receiver-label controls.
It produced 4,200 result rows with no empty folds or incomplete 12-scan cell.

For each cell and width below, values are pooled held-fold duration coverage for
the actual receiver labels, followed by the mean and range over controls. The
two receiver mappings give identical coverage because the full yaw grid can
exchange the two symmetric axes; mapping is therefore not identifiable here.

| cell | 10 degrees | 15 degrees | 20 degrees | 30 degrees |
|---|---:|---:|---:|---:|
| 1 (duplicate aliases) | .345 / .250 [.222,.291] | .540 / .431 [.396,.464] | .694 / .593 [.560,.624] | .855 / .842 [.818,.857] |
| 2 | .341 / .231 [.190,.265] | .556 / .425 [.375,.473] | .708 / .579 [.539,.621] | .842 / .809 [.777,.831] |
| 3 | .415 / .266 [.240,.291] | .666 / .487 [.449,.521] | .819 / .634 [.595,.673] | .924 / .891 [.872,.904] |
| 4 | .357 / .240 [.210,.266] | .561 / .436 [.397,.475] | .703 / .599 [.551,.647] | .852 / .834 [.813,.856] |
| 5 | .410 / .273 [.236,.310] | .674 / .493 [.458,.526] | .827 / .642 [.602,.677] | .941 / .900 [.885,.915] |

Actual labels exceed every one of the 20 controls at 10, 15, and 20 degrees in
all five cells. The separation nearly disappears at 30 degrees. The held
start/midpoint/end diagnostic is much harsher: actual coverage ranges .026-.038
at 10 degrees, .175-.219 at 15, .402-.528 at 20, and .714-.884 at 30. Thus the
narrow-cone label association exceeds these sampled controls, while a
narrow fixed cone does not contain most tracks across their sampled duration.

The primary measure assigns a track's full duration to its midpoint membership.
It is a proxy, not continuous whole-track visibility. The three-sample measure
also does not prove containment between samples. At 10 degrees, axes separated
by 20 degrees have tangent spherical caps with zero area overlap; wider caps
overlap. These are hard geometric cones, not calibrated antenna gain or
detection probability. Boolean objectives also have plateaus, so the
deterministic first-grid orientation is not a uniquely measured boresight or an
absolute mount calibration. Strong dual-receiver association can challenge a
narrow-beam interpretation, but it does not establish satellite identity.

No truth, VAL/TEST rows, position fitting, geographic search, new RF, or QNAP
write was used. Candidate selection remained the original training-only
Doppler selection. The duplicate coordinate is represented once as cell 1 and
retains both source aliases.

## Independent output review

The primary agent verified all eight result source/input bindings against files
on disk, the result SHA256 seal, all 4,200 rows, and the rendered PNG. Six
component tests pass. This is a post-execution review, not a new pre-execution
freeze. The twenty controls are descriptive comparisons, not calibrated
significance levels. Neither cell selection nor this report establishes an
independent geographic accuracy result.

Cells 3 and 5 are the two original TRAIN groups' Doppler-refined coordinates;
cells 1, 2, and 4 are coarse alternatives. Their aliases and coordinates are in
`locations.json`. At 20 degrees, the refined cells contain about 82–83% of
duration by the midpoint proxy, but only about 53% when all three sampled
directions must lie inside. This difference is material when interpreting a
fixed narrow cone as support for a complete recorded track.

Reproduce in the repository worktree with its existing authorized local TRAIN
caches and metadata: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
MKL_NUM_THREADS=1 .venv/bin/python reports/2026_09_23_train_fixed_cone/run.py`,
then `.venv/bin/python reports/2026_09_23_train_fixed_cone/plot.py`.
The machine-readable output is `results.json`; `prepared_inputs.json` contains
input provenance and explicitly marked dummy preparation profiles, not measured
cone-profile results.
