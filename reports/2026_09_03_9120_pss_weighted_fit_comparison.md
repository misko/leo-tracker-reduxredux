# PSS fit-weighting comparison for `9120aba2922e`

## Conclusion

PSS score weighting moves the fitted curves only a few nanoseconds and changes the
phase-derived frequency rate by about +4 Hz/s at every resolution.  It lowers the RMS
measured under its own weighted objective, but slightly increases ordinary unweighted
RMS and does not improve agreement across resolutions or between non-overlapping
parities.  On this strong recording, the current equal-weight fit remains preferable.

The result does not show that weighting is intrinsically wrong.  It shows that the
persisted `robust_z` score is not a calibrated timing-variance estimate.  A production
weight should ultimately be based on a measured phase uncertainty or score-to-error
calibration from a multi-recording cohort.

## Weighting tested

For each already-detected dominant track, the original phase observations were refitted
without rerunning PSS acquisition.

The conservative PSS-quality weight was

`q_i = clip(robust_z_i / median(robust_z), 0.5, 2.0)`, normalized to mean one.

Weighted least squares minimized `sum(q_i * residual_i^2)`.  Because NumPy's `polyfit`
multiplies the unsquared residual by its `w` argument, the implementation passed
`sqrt(q_i)`, not `q_i`.

A second control combined the same quality weight with iterated Huber residual weights:

`q_total = q_i * min(1, 1.345 * MAD_scale / abs(residual_i))`.

`robust_z` was chosen because it is the persisted score closest to normalized detection
salience.  It is still only a heuristic proxy—not a probability, likelihood, or measured
inverse timing variance.

## Results

### PSS-quality weighted least squares

| Window / stride | Equal rate | Weighted rate | Rate shift | Equal ordinary RMS | Weighted-fit ordinary RMS | Weighted-objective RMS | Maximum curve movement |
|---|---:|---:|---:|---:|---:|---:|---:|
| 62.5/31.25 ms | 2.554584 kHz/s | 2.558427 kHz/s | +3.842 Hz/s | 0.037823 µs | 0.037890 µs | 0.037155 µs | 4.22 ns |
| 125/62.5 ms | 2.556487 kHz/s | 2.560976 kHz/s | +4.489 Hz/s | 0.039550 µs | 0.039636 µs | 0.038775 µs | 4.47 ns |
| 250/125 ms | 2.556827 kHz/s | 2.561134 kHz/s | +4.308 Hz/s | 0.038223 µs | 0.038307 µs | 0.037409 µs | 4.59 ns |

The weights are mild because every selected observation is a strong match.  The effective
sample counts change only from 270 to 264.8, 134 to 131.1, and 66 to 64.5.  No observation
receives less than half weight; the actual WLS ranges are approximately 0.73–1.37.

The lower weighted-objective RMS is expected because that is the quantity being optimized.
The independent check is ordinary RMS, which becomes slightly worse at all three
resolutions.  Maximum residuals also do not improve consistently.

### Robust Huber control

| Window / stride | Huber-weighted rate | Shift from equal | Ordinary RMS | Weighted-objective RMS | Maximum curve movement | Points below half weight |
|---|---:|---:|---:|---:|---:|---:|
| 62.5/31.25 ms | 2.561082 kHz/s | +6.497 Hz/s | 0.038016 µs | 0.034856 µs | 8.03 ns | 6 |
| 125/62.5 ms | 2.563353 kHz/s | +6.866 Hz/s | 0.039777 µs | 0.036803 µs | 9.22 ns | 3 |
| 250/125 ms | 2.565175 kHz/s | +8.348 Hz/s | 0.038654 µs | 0.035418 µs | 13.68 ns | 1 |

Huber weighting suppresses a handful of larger residuals and therefore reports a much
smaller weighted RMS.  However, ordinary RMS rises and the rate moves farther from the
equal-weight result.

## Stability checks

| Method | Cross-resolution rate range |
|---|---:|
| Equal weight | **2.242 Hz/s** |
| Robust-z WLS | 2.708 Hz/s |
| Robust-z WLS + Huber | 4.093 Hz/s |

Splitting each 50%-overlapped series into independently refitted, non-overlapping
parities also does not favor score weighting:

| Window / stride | Equal parity spread | Robust-z WLS parity spread | Huber parity spread |
|---|---:|---:|---:|
| 62.5/31.25 ms | **0.072 Hz/s** | 0.684 Hz/s | 0.545 Hz/s |
| 125/62.5 ms | **0.253 Hz/s** | 1.742 Hz/s | 2.706 Hz/s |
| 250/125 ms | 9.758 Hz/s | **9.381 Hz/s** | 12.126 Hz/s |

The association between PSS score and actual timing error is real but weak: correlation of
`robust_z` with absolute equal-fit residual is -0.12, -0.15, and -0.16 for the half,
baseline, and double resolutions.  That weak relationship explains why the weighting has
little useful leverage.

## Recommendation

Keep equal weighting for now.  If weighting is promoted as an experiment, use the bounded
robust-z WLS form rather than unbounded scores or Huber stacking, and judge it on held-out
recordings using ordinary residuals, non-overlap/block bootstrap stability, and external
GLRT agreement—not its self-weighted RMS.

A better long-term weight would be `1 / phase_variance` derived from local peak curvature,
repeat-to-repeat phase dispersion, or an empirical score-to-error calibration.  The
current product contract does not persist such an uncertainty estimate.

## Artifacts

- `weighted-fit-comparison.png`: magnified timing-curve and frequency-rate changes.
- `weighted-fit-comparison.json` and `.csv`: all fit metrics and weights.
- `compare_weighted_fits.py`: reproducible analysis implementation.
