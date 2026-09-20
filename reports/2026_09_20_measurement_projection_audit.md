# Measurement projection and receiver-altitude checks

The code-path review found no obvious duplicate RF normalization or probe-start
timestamp substitution. Twenty-eight existing projection/trajectory tests pass.
Freeing receiver altitude in the recent independent fit also leaves kilometre-
scale position error. These checks do not establish field calibration of the
underlying RF estimator or host clock.

## Traced measurement path

1. `project_scanner_candidates` in `src/leo/application/scanner_trajectory.py`
   consumes each candidate's fractional tracking CFO. UTC comes from integer
   device-counter differences, native sample rate, probe offset, and the
   fractional GLRT support centre. The absolute device counters are subtracted
   before floating-point fractional offsets are added.
2. `fractional_glrt64_support_geometry` in
   `src/leo/application/persistent_hop_trajectory.py` computes the centre of the
   retained GLRT symbol supports and retains support moments. The timestamp is
   not simply the beginning of the 20 ms probe.
3. `_lane_tracklets` in `src/leo/analysis/persistent_hop_trajectory.py` scales
   measured frequency by canonical RF / actual RF. Alias spacing is scaled by
   the same factor. The exported graph uses the normalized dealiased frequency.
4. `tools/study_adaptive_sky_position.py` exports those normalized measurements
   and marks their RF as 11.2 GHz. `load_observations` in
   `tools/replay_regional_doppler.py` consumes them without a second RF scaling.

This traces the intended transformations. It does not independently verify the
hardware sample clock, analogue frequency calibration, true estimator support
weighting under noise, or firmware first-sample UTC semantics. Those distinctions
matter before calling the measured frequency/UTC scale calibrated.

The targeted command was:

```sh
PYTHONPATH=src python -m pytest \
  tests/application/test_scanner_tracking.py \
  tests/application/test_persistent_hop_trajectory.py \
  tests/analysis/test_persistent_hop_trajectory.py -q
```

Result: **28 passed**. No production algorithm changes were made.

## Altitude sensitivity, without a supplied height

The original wide fit fixes receiver altitude to zero. This replay keeps its
assignments, partitions, selection, and start point, but allows altitude between
−500 and 5,000 m. It does not supply the known latitude/longitude to inference.

| Cohort | Clock | Fitted altitude (m) | Horizontal error (m) | Evaluation RMS (Hz) |
|---|---|---:|---:|---:|
| All | Fixed UTC | −101.4 | 4,674.6 | 166.45 |
| All | Shared ±0.5 s | −131.7 | 3,784.9 | 163.42 |
| Selected | Fixed UTC | −139.8 | 4,421.1 | 85.34 |
| Selected | Shared ±0.5 s | −142.6 | 3,760.6 | 84.54 |

All fits converged. These fitted heights can absorb model error; they are not
independent altitude estimates or evidence that the antenna is below the
ellipsoid. Even this additional freedom does not meet the sub-kilometre goal.
A measured antenna altitude with its datum remains useful for constraining a
future fit.

[Sealed altitude replay](2026_09_20_measurement_projection_audit/free-height-inference.json)
records the parent/state digests and every fit. It uses the existing tested
`compare_positioning_cohorts.fit(..., fit_height=True)` for both original masks
and both fixed/shared-clock settings. Distances are evaluated after inference
against the supplied antenna coordinate with the existing spherical convention.
