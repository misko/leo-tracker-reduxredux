# Fixed-500-ms uncertainty calibration with true sample-clock resampling

Date: 2026-08-26 UTC

Status: **FAIL** for fixed-500 interval calibration; **PASS** for the lean quadratic challenger.

## Bottom line

The combined fixed-500 promotion failed: unchanged_fixed500_point_rmse. The failure is point accuracy, not a missing background or a coverage shortfall: the unchanged point estimate has a primary RMSE of 291.59 Hz/s. Grouped calibration changes no point estimate and uses multiplier 25.725, selected as order 12 from 12 usable whole-scenario scores. It raises evaluation scenario-simultaneous coverage to 100.0%, but only with median half-width 501.14 Hz/s. Inflating covariance therefore does not repair the trailing-linear point error.

The quadratic challenger has RMSE 37.18 Hz/s, a ratio of 0.127 to the unchanged line; the frozen promotion threshold is 0.95. This comparison uses identical even-supported frames and endpoints.

These are component-test results conditional on truth-quantized carrier acquisition and oracle knowledge of the **resampled** frame lattice. They do not establish satellite acquisition yield or separate LNB/transmitter/sample-clock/geometric nuisances.

## Authority and provenance

The [preregistration](2026_08_26_fixed500_calibration_preregistration.md) was committed at `8e6e98e4a3824723b04ef3c9bcb92df3080a7336` before this experiment read IQ. It inherits the exact three-span bindings from the [original polynomial-injection protocol](../config/analysis/polynomial-phase-injection-protocol-v1.json) and the deny-by-default [dataset policy](../config/analysis/doppler-experiment-dataset-policy-v1.json). No new, newer, PRE-FIX, holdout-foundation, 3/5-MS/s, dynamically discovered, or substituted capture was read.

All three recording manifests, analysis manifests, compressed chunks, uncompressed chunks, and extracted spans were digest verified before injection. The run retained all 36 scenarios and finished in 261.9 seconds, below the frozen 20-minute bound. Exact implementation hashes and artifact hashes are in [`metrics.json`](figures/2026_08_26_fixed500_calibration/metrics.json).

The first canonical attempt completed all scientific scenario scoring but failed before writing `metrics.json` or this report because a relative artifact path was resolved against an absolute repository root. The hash-bound execution amendment changes only that serialization call; the rerun preserves every scientific kernel, scenario, mask, estimator, metric, and gate.

After execution, the explicit-lattice evaluator was moved into the fixed-500 component and the historical polynomial-injection kernel was restored byte-for-byte so its older sealed result remains verifiable. The hash-bound [source-layout amendment](../config/analysis/fixed500-calibration-source-layout-amendment-v1.json) records that maintenance; it changed no IQ access, execution artifact, scientific metric, figure, or decision. The implementation hashes above remain the exact execution-time receipt rather than pretending the maintained source tree produced the sealed run.

## Primary evaluation

The primary mask contains 12 smooth strong evaluation scenarios (`SNR ≥ −12 dB`, occupancy ≥0.70), four per background. Each scenario contributes three non-overlapping endpoints; a scenario counts as simultaneously covered only if all three truth rates fall in their intervals.

| Estimator | Scenarios | Bias Hz/s | RMSE Hz/s | Displayed endpoint cov. | Displayed scenario cov. | Median half-width |
|---|---|---|---|---|---|---|
| Fixed 125 ms | 12/12 | -7.85 | 92.71 | 100.0% | 100.0% | 301.42 |
| Unchanged fixed 500 ms | 12/12 | 1.17 | 291.59 | 8.3% | 0.0% | 38.18 |
| Calibrated fixed 500 ms | 12/12 | 1.17 | 291.59 | 100.0% | 100.0% | 501.14 |
| Lean quadratic 500 ms | 12/12 | -1.71 | 37.18 | 100.0% | 100.0% | 152.78 |

Only the green `Calibrated fixed 500 ms` row uses the grouped split-conformal
multiplier. Fixed 125 ms, unchanged fixed 500 ms, and the quadratic show their
legacy residual-chi-square conditional covariance, so their displayed coverage
is descriptive and is **not** evidence that those intervals have been separately
calibrated. Point bias and RMSE do not depend on this interval distinction.

![Primary accuracy and calibration](figures/2026_08_26_fixed500_calibration/01-primary-calibration.png)

| Background | Evaluable | Calibrated RMSE Hz/s | Simultaneous coverage |
|---|---|---|---|
| cap-20260825T062228-886fe2dd9cde | 4/4 | 294.38 | 100.0% |
| cap-20260825T105640-facdadeffb3b | 4/4 | 291.69 | 100.0% |
| cap-20260825T111222-a2d4ce2afb9a | 4/4 | 288.68 | 100.0% |

The old covariance treats dense overlapping frame endpoints too independently.
For the fixed-500 line only, the candidate computes one maximum standardized
endpoint error per whole calibration scenario. There were only 12 usable no-step
calibration scenarios; the frozen finite-sample 95% rule therefore selects the
maximum score (order 12), producing multiplier 25.725. That is conservative but
explicit, and it must not be transferred to fixed 125 ms or the quadratic without
a new frozen calibration. Acceleration and jerk are scored against instantaneous
endpoint rate, so trailing-linear curvature lag remains in the fixed-500
calibration error.

![Legacy and grouped intervals](figures/2026_08_26_fixed500_calibration/02-grouped-intervals.png)

## True sample-clock experiment

For nonzero ppm, the complex Qin waveform is interpolated on the scaled physical timebase and physical frame `k` moves to receiver sample `round(Fs × (1+ppm×10⁻⁶) × k/750)`. At ±50 ppm the final two-second frame is shifted by ±250 samples. This is not the earlier phase-coordinate-only warp.

With the true lattice supplied, mean occupied support for nonzero-ppm evaluation rows is 86.3%. Replaying the same resampled waveform on the nominal fixed lattice yields 2.1%. The nominal result is diagnostic only: it measures what a frame-aligner loses if it refuses accumulated delay; it does not enter rate promotion.

![Physical sample-clock lattice and support](figures/2026_08_26_fixed500_calibration/03-true-sample-clock.png)

## Curvature, nuisance factors, and controls

![Curvature comparison](figures/2026_08_26_fixed500_calibration/04-curvature-comparison.png)

The lean quadratic is a causal 500-ms derivative using the same even-Qin support as the line. Odd-Qin CFO and rolled-control responses remain in [`frame-evidence.csv.gz`](figures/2026_08_26_fixed500_calibration/frame-evidence.csv.gz) but cannot affect support, endpoints, model choice, multiplier, or gates. Alias changes are known labels and canonicalized; step rows are retained as diagnostics and excluded from the smooth primary mask. Every no-result endpoint and every frame rejection remains in the ledgers.

The smooth-primary win does **not** make the quadratic a safe unconditional
tracker. The following scenario-equal diagnostics use the oracle-resampled
lattice. Counts show evaluable/frozen scenarios; factor levels outside the
primary mask are deliberately confounded by the fractional design and therefore
describe stress behavior rather than isolated causal effects.

| Scope | Fixed 125 ms | Fixed 500 ms | Quadratic 500 ms |
|---|---:|---:|---:|
| Primary evaluation: strong, smooth | 12/12; 92.71 Hz/s | 12/12; 291.59 Hz/s | 12/12; **37.18 Hz/s** |
| Strong, smooth; both splits | 18/18; 96.98 | 18/18; 298.78 | 18/18; **36.94** |
| All smooth, including weak | 19/24; 270.59 | 24/24; 332.82 | 24/24; **147.10** |
| Nonzero 400-Hz step | 8/12; **217.90** | 11/12; 322.38 | 11/12; 919.17 |
| Weak −20-dB injection | 3/12; 717.92 | 11/12; **363.29** | 11/12; 709.39 |

Occupied-frame support averaged 45.5% at −20 dB, 99.9% at −12 dB, and
99.9% at −6 dB. The quadratic interprets a discontinuous CFO step as extreme
curvature and is decisively unsafe there. A retrospective prototype therefore
needs sustained past-only change evidence and hysteresis: use the quadratic only
inside stable smooth locklets, then fall back to a shorter/linear history after a
detected step or support collapse. The known ±750-Hz alias labels were supplied
and canonicalized before fitting, so these rows do not test blind alias recovery.

This experiment makes sample-clock timing observable only because injected truth supplies the physical clock map. In retrospective satellite data, sample clock, frame epoch, receiver/LNB drift, transmitter drift, and geometric Doppler still require a downstream nuisance model. The calibrated interval can improve candidate weighting, but it is not itself a satellite identity claim.

## Evidence artifacts

- [`frame-evidence.csv.gz`](figures/2026_08_26_fixed500_calibration/frame-evidence.csv.gz): every frame opportunity, parity response, rolled-control margin, and failure reason for oracle and nominal diagnostic alignments.
- [`frame-summary.csv`](figures/2026_08_26_fixed500_calibration/frame-summary.csv): scenario/alignment support and false-support accounting.
- [`endpoint-estimates.csv`](figures/2026_08_26_fixed500_calibration/endpoint-estimates.csv): all frozen endpoints, no-results, truth, errors, intervals, and odd-Qin held-out error.
- [`scenario-metrics.csv`](figures/2026_08_26_fixed500_calibration/scenario-metrics.csv): scenario-equal point and coverage metrics.
- [`calibration-scores.csv`](figures/2026_08_26_fixed500_calibration/calibration-scores.csv): whole-scenario maximum standardized calibration scores.
- [`injection-ledger.csv`](figures/2026_08_26_fixed500_calibration/injection-ledger.csv): clock scale, waveform length, accumulated lattice shift, occupancy, and background provenance.

## Verification receipt

- Component and adjacent provenance/DSP suite: **95 passed** in 7.05 seconds. This covered the fixed-500 kernels, runner, sealed result, historical polynomial protocol/result, dataset policy, adaptive tracker, and parity-split pilot likelihood.
- Ruff formatting check: **pass** on all seven changed Python implementation, tool, and test files.
- Ruff lint: **pass** on the same seven files.
- Strict mypy: **pass** on the fixed-500 and historical polynomial scientific kernels plus the presentation postprocessor.
- Repository diff whitespace check: **pass**. The historical `polynomial_injection.py` SHA-256 is again `9e5dfc653552bb4bfe0272239fb8f327af045c2b416c982ba3b7c6922ae0934b`, exactly matching its sealed result.

## Decision

The unchanged fixed 500-ms line remains the comparison baseline, but it should not be the next estimator carried into satellite matching on the strength of this experiment: it failed its frozen point-RMSE gate. The lean quadratic **passed** its separate frozen component gate and is now the leading rate candidate for a separately frozen retrospective real-signal evaluation. Fixed 125 ms is the simpler fallback because it also substantially reduced curvature lag.

This does not authorize production promotion. Before satellite association, freeze the quadratic implementation and compare it with fixed 125/500 ms on already opened, source-supported retrospective tracks, using future odd-Qin prediction, rolled controls, and nuisance-aware TLE fits. No result here authorizes opening the sealed holdout.
