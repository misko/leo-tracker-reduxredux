# Frozen synthetic position-control protocol

Status: frozen before generation or fitting on 2026-09-23. This report is a
numerical/model control. It is not real-position evidence and cannot satisfy a
sub-300 m field-positioning claim.

## Inputs and selection

- Bind the frozen long-inventory manifest and the sealed fixed-identity
  six-scan result from `2026_09_23_long_training_search_multi`.
- Use exactly the first six TRAIN session IDs, their real track timestamps,
  randomized training masks, and the Sacramento arm's selected candidate ID
  for every track. Do not use measured frequency values.
- The synthetic generator site is latitude 38.0 degrees, longitude -122.0
  degrees, ellipsoidal altitude 0 m. This is deliberately different from the
  receiver reference coordinate and is sequestered from the fit until results
  are sealed.
- Resolve every session's recorded causal snapshot instance and generate TEME
  states with direct SGP4 at the exact rounded observation epoch. Convert those
  states to ECEF with the repository frame implementation. Interpolated cache
  states are forbidden for generation and fitting.
- Retain a track only when its generating satellite is above the geometric
  horizon at every unshifted observation epoch at the generator site. Record
  every included and excluded track, its candidate, and its minimum/maximum
  elevation. This makes the control conditional on the retained support.

## Random generation

- Use NumPy `Generator(PCG64(20260923))` and record all realized nuisance
  values.
- Draw one per-track CFO independently from a uniform distribution on
  [-1,000,000, +1,000,000] Hz. The same CFO is used in all three cases.
- Case `zero_noise` adds no frequency noise and no epoch shift.
- Case `gaussian_300hz` adds independent zero-mean Gaussian frequency noise
  with sigma 300 Hz to each observation and no epoch shift.
- Case `gaussian_300hz_satellite_epoch_0p3s` uses the same frequency-noise
  realization as `gaussian_300hz` and additionally draws one independent epoch
  shift per selected satellite from a zero-mean Gaussian with sigma 0.3 s,
  clipped to [-1, +1] s. That shift is shared by all tracks and scans assigned
  to the satellite. Direct SGP4 is rerun at the shifted epochs.
- Doppler is `-11.2e9 / 299792.458 * dot(satellite-receiver, velocity) /
  range` in Hz, plus the realized per-track CFO and case noise.

## Sealed fits and evaluation

- Before exposing the generator coordinate to fitting code, materialize one
  object-free NPZ containing the retained observations, masks, direct base
  states, shifted generator states, synthetic frequencies, realized nuisance
  variables, and stable string identifiers. The fitter reads this NPZ once and
  does no catalogue search or propagation.
- Fit the known generating identities at fixed epoch zero with one analytic
  training-only CFO per track. Fit latitude/longitude as local east/north
  offsets separately from the original Sacramento and Reno prior centres.
  Constrain each fit to its original 250 km or 500 km prior disk. Start at the
  corresponding prior centre. Use weighted training residuals and report
  capped-800-Hz and uncapped RMS values.
- Run both prior-centre starts for all three cases. Record optimizer success,
  termination message, iterations/evaluations, boundary distance, runtime,
  fitted coordinate, and training residuals before unsealing truth.
- After all fit records are sealed, expose the generator coordinate only in a
  separate evaluation step. Add horizontal error and held-row residual metrics
  without refitting.
- The required noiseless recovery check passes only if both starts converge,
  remain inside their prior disks, recover within 0.3 km, and have training and
  held uncapped RMS below 0.01 Hz.
- The held-frequency invariance check perturbs every held synthetic frequency
  deterministically by large finite offsets, reruns all six fits, and requires
  bit-identical fitted parameters, training objectives, and convergence
  records. This checks that held frequencies cannot affect fitting.

## Bounds and outputs

- Run only the six frozen TRAIN scans. Do not read VAL/TEST observations, run a
  full-catalogue grid, collect RF, deploy, or use a real true position.
- Produce `materialize.py`, `fit.py`, `plot.py`, an executable test, binding
  hashes, `results/inference.json`, post-seal `results/results.json`, checksums,
  one plot, and a concise README. Preserve all referenced reports and caches.
