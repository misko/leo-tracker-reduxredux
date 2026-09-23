# Frozen multi-seed synthetic sensitivity protocol

Status: frozen before generation and fitting on 2026-09-23. This is a bounded
numerical sensitivity control, not real-position evidence or an attainable
resolution claim.

## Fixed support and model

- Reuse the object-free direct-SGP4 materialization from
  `2026_09_23_long_position_synthetic_control`: the same first six TRAIN scans,
  476 visibility-qualified tracks, 8,285 timestamps, randomized train/held
  masks, sealed Sacramento candidate identities, direct exact-epoch base
  states, synthetic site (38.0, -122.0, ellipsoidal altitude 0 m), and realized
  per-track CFOs. Bind its NPZ and receipt by SHA-256.
- Do not use measured frequency values, VAL/TEST observations, a full-catalogue
  search, new RF, or a real true position.
- Use exactly 20 independent NumPy `Generator(PCG64(seed))` streams with integer
  seeds 2026092300 through 2026092319 inclusive. No seed may be added, removed,
  rerun selectively, or chosen by its outcome.

## Paired cases

- For each seed, draw 8,285 independent zero-mean Gaussian frequency errors
  with sigma 300 Hz in frozen observation order.
- Case `gaussian_300hz` adds that draw to the frozen direct base signal.
- Then draw one independent zero-mean Gaussian epoch shift with sigma 0.3 s for
  each selected satellite in ascending numeric candidate-ID order and clip it
  to [-1, +1] s. Share that value across every track and scan assigned to the
  satellite. Case `gaussian_300hz_satellite_epoch_0p3s` uses the same frequency
  errors as its paired noise-only case.
- For every seed and retained track, resolve the scan's exact saved causal TLE
  snapshot and run direct SGP4 at every rounded `(observation time + shift)`
  epoch. Convert TEME states to ECEF with the repository implementation and
  generate shifted Doppler directly. Interpolated states are forbidden for
  shifted-signal generation. Record every realized shift and source binding.

## Blinded fitting and post-seal evaluation

- Materialize all paired synthetic frequencies in one object-free NPZ. It must
  not contain the synthetic coordinate. Fit code reads the NPZ once and does no
  propagation or catalogue work.
- Use the unchanged fitter and settings from the corrected single-seed control:
  known generating identities, fixed epoch zero, one analytic training-only CFO
  per track, duration-weighted residuals, the original Sacramento and Reno
  prior disks, one start at each prior centre, and the same least-squares
  tolerances and evaluation cap. Bind the exact fitter source.
- Fit both starts for both paired cases and all 20 seeds, for 80 predeclared
  fits. Do not tune the model or optimizer, discard fits, choose a seed, combine
  the two starts, or select an arm using geography or held frequencies.
- Seal all fitted coordinates, training objectives, and convergence records
  before reading the generator coordinate or calculating held-row metrics.
- Post-seal, report every fit's horizontal error and held residual RMS. For each
  case and start separately, report the median horizontal error, NumPy's default
  linear-interpolation 90th percentile, fraction strictly below 0.300 km,
  maximum error, convergence count, and median train/held uncapped RMS.
- Retain the earlier single shifted-seed result as a separate sensitivity
  control; do not merge it into these 20-seed summaries.

## Interpretation

- The multi-seed distribution measures sensitivity under this shared synthetic
  generator/fitter, fixed support, and stipulated noise/shift distributions.
  It is not calibrated orbit uncertainty, a confidence interval, field
  validation, or evidence that sub-300 m real positioning has been achieved.
