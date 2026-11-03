# Whole-scan transfer with timing marginalized

Tests the small shared candidate-slope prior after its partial whole-receiver
transfer result. Each eight-scan panel is split into two four-scan halves.
Both directions are evaluated: first half predicts last half, then the reverse.
Both receivers are used in each source fit. All target-scan measurements are
withheld from fitting, initialization, candidate grouping, and start selection.

**Decision: retain the baseline.** The shared slope improves source interleaved
prediction in all 18 directions and whole-scan transfer in 12/18, but aggregate
whole-scan score decreases by 53.827 and geographic error improves in only 9/18.
Sub-km source fits fall from 3/18 to 2/18. The earlier partial cross-receiver
benefit does not establish a robust localization improvement.

## Results

All 18 comparisons qualify after the single documented numerical refinement.
These are four-scan source-location errors, distinct from the earlier eight-scan
combined fits and single-receiver results.

| Dataset | Comparisons | Baseline median m | Shared slope median m | Whole-scan wins | Geographic wins | Sub-km baseline → shared |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 6 | 2,413.21 | 2,455.59 | 5/6 | 4/6 | 1 → 1 |
| DS8 | 6 | 2,106.22 | 2,138.10 | 4/6 | 3/6 | 1 → 0 |
| DS9 | 6 | 2,330.93 | 2,402.92 | 3/6 | 2/6 | 1 → 1 |

Median error increases in every dataset. The largest predictive regression is
DS7 late, training on its last half and evaluating its first: -234.786 log-score
units. Its location error also increases from 3,087 m to 3,814 m. Do not discard
that direction to improve the aggregate or select a prior using known errors.
Reciprocal halves are dependent comparisons, not independent significance trials.

![Whole-scan prediction and geographic transfer](transfer.png)

All 18 processes returned zero, taking at most 56.08 seconds per direction
(840.21 summed process wall seconds, excluding numerical refinement). Original
timing audits passed for 143/144 scan/arm integrals. The remaining integral
changed by 0.017906 at the first refinement, then by only 2.91e-11 at 64/128 nodes;
its original failure is preserved. The largest accepted original discrepancy
is 0.005178. Maximum scalar-replay error is 1.82e-11 and fitted-gradient audit
error is 3.06e-6. All final input/source hashes verify; synthetic tests and Ruff
checks pass.

The resulting evaluation infrastructure can test future candidate, orbit,
waveform, or timing models without using target scans to fit location. The
next methodological requirement is evidence that improves geographic transfer,
not another model selected merely for better interleaved residual prediction.

## Why timing must be integrated

The prior model fits a separate timing offset to each recording. A target scan
has no source-fitted timing parameter. Setting it to its previously fitted
value would leak target data; maximizing its score over timing would provide
a target-specific fit. Instead, each target scan receives the normalized
uniform timing prior on the existing [-5,+5]second range:

    log p(target scan | source position)
      = log integral[-5,+5] exp(sum_track log p(track | position,time)) dt / 10.

All tracks share one scan time inside the integral. Integrating tracks separately
would allow incompatible times within the same scan. The original q020
complete-track likelihood is used for both arms. The location remains fixed
at its source estimate, and source parameter uncertainty is not integrated.
This is a plug-in location-transfer test under an explicit working timing
prior, not an independently calibrated clock model.

## Fitting and numerical evidence

The source baseline uses three fixed starts with zero timing offsets; it never
uses the previous combined-panel optimum. The SD0.5 Hz/s slope model is grouped
and initialized only from that source baseline. The larger prior from the
previous experiment is not retested. Source interleaved held score and target
whole-scan marginal score are reported separately.

Timing evaluation batches interpolation and Doppler calculations across
quadrature nodes, using the same banks and mathematical constants as the
original scalar model. Each target scan/arm is replayed against the scalar
model at five times including both endpoints and bank interiors. Composite
Gauss-Legendre integration uses16 nodes per0.25-second bank interval and is
audited at32. The allowed absolute log-integral discrepancy is0.01 per scan;
an arm fails qualification if any target scan exceeds it. Optimization and
source-slope integration retain the previous numerical gates.

The [protocol](PROTOCOL.md) was frozen before outcomes. [Full table](TABLE.md)
reports every direction and qualification. `summary.json` retains missing
directions explicitly and aggregates only qualified pairs. Per-direction JSON
files preserve every baseline start, fitted parameters, source and target
session IDs, scalar-replay and quadrature discrepancies for every target scan,
and input/source SHA-256 bindings. Process receipts preserve exits and failures.

[Numerical refinement](NUMERICAL-REFINEMENT.md) preserves the one original
timing-audit failure and defines a higher-resolution check at 64/128 nodes per
bank interval. It changes no fitted parameter or data split. `refinement.json`
binds the original failed artifact and records both refined scores. The summary
uses a refined score only after checking all original fit gates and all target
scan integration gates; original run artifacts remain unchanged.

Tests cover uniform normalization, an analytic narrow Gaussian timing integral,
the distinction between shared and independently integrated timing, and whole
scan partitioning. The reused fitting and slope likelihood retain their prior
synthetic tests and source bindings. No observations, golden scientific
fixtures, production analyzers, or radio collections are changed.

## Scope

Both directions involve the same exposed site and existing candidate exports.
They are dependent evaluations, and the reverse direction is not a causal
forecast. The candidate banks, visibility gates and geographic origin are
inherited; this is not blind satellite identification. Geographic errors use
the inherited unsurveyed reference. Withholding entire scans removes direct
measurement reuse in the fit, but does not create a new independent site or
guarantee correct association, timing prior, or orbit predictions.

Reports are local; no remote publication is claimed.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_scan_holdout -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120s uv run --no-project --with numpy --with scipy python reports/2026_09_29_scan_holdout/run.py DS7_early_8 0
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_scan_holdout/batch.py
OPENBLAS_NUM_THREADS=1 timeout 120s uv run --no-project --with numpy --with scipy python reports/2026_09_29_scan_holdout/refine.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_scan_holdout/summarize.py
```
