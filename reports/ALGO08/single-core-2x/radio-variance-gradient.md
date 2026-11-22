# Analytic refinement of the released radio variance profile

Analytic refinement substantially reduces sensitivity to the native margin difference and leaves the BIC model choices intact. The complete physical replay still exceeds the strict 10 µm coordinate tolerance in both arms. The southern control matches exactly. [Saved solver evidence](measurements/radio-variance-gradient-solver.json)

The research variant refines the original variance objective with its analytic derivative inside the same grid-selected basin. The released estimator still builds the residual vectors, applies the per-observation variance bounds and decides between constant and margin-dependent noise using BIC. The saved solver replays patch only the profile fit in their isolated process. [Prespecified protocol](radio-variance-gradient-protocol.md) · [Released estimator](../../../src/leo/analysis/localization_v3/noise.py) · [Research variant](../../../tools/pipeline_eval/variants/experimental/analytic_radio_variance.py)

The unconstrained floor at a fixed ratio is the mean of the squared residuals divided by the variance shape. The profile clips this floor to the original bounds. The derivative is the mean of the normalized variance residual times the derivative of log variance. For an interior floor, the contribution of the floor derivative vanishes in the mean. At a fixed clamp the floor derivative is zero. At the moving upper cap, strength is fixed and the variance derivative instead reflects the falling floor. The implementation partitions the basin at both clamp crossings and the upper-cap kink at ratio one. It tests endpoints and solves bracketed stationary minima. The original objective chooses among those candidates in extended precision. The finite bracket mesh preserves the local search scope.

The matched native files used identical selected observations and Graph tracks. Their unrounded fractional margins differ. Both active physical pairs retained the margin-dependent BIC choice and reached absolute profile gradients below 5.0 × 10⁻¹⁷, from stock gradients of 1.7 × 10⁻⁹ to 2.4 × 10⁻⁸. All profiled losses matched or improved within floating-point precision. The southern whole noise record stayed identical, including the constant 40 Hz choice and zero fitted strength. [Matched inputs and analytic fit measurements](measurements/radio-variance-gradient-preparation.json) · [Earlier exact-margin crossover](solver-deployed-margin-recovery.md)

| Saved pair | Largest native margin change | Maximum sigma difference, stock → analytic (Hz) | Median candidate profile CPU, stock → analytic (ms) | BIC selection |
|---|---:|---:|---:|---|
| DS30-0374 | 2.245 × 10⁻¹³ | 8.178 × 10⁻⁶ → 1.881 × 10⁻¹⁰ | 6.075 → 4.827 | Margin-dependent |
| DS30-0008 | 2.336 × 10⁻¹³ | 2.958 × 10⁻⁵ → 2.655 × 10⁻¹⁰ | 7.835 → 6.001 | Margin-dependent |
| South | 2.154 × 10⁻¹⁴ | 0 → 0 | 2.556 → 1.775 | Constant |

The sigma sensitivity fell by about 43,500-fold and 111,400-fold on the two physical inputs. Timing measures just the profile fit with seven alternating repetitions on the same residual and margin vectors. The fit itself saves milliseconds. These tests establish that the original search through nearly equal objective values amplified the tiny margin differences. They also establish that the analytic optimum may differ from the stock answer even on unchanged input.

## Complete saved solves

Both active physical cases passed the preparation thresholds. The prespecified downstream check then ran DS30-0374 and the southern control through their previous frozen solvers, substituting only the analytic profile on the candidate native detections. Both published fixes retained the original owners. The physical snapshot contains 2,905 associated points per arm and the simulation 266. On DS30-0374 both path and grid digests changed. On the southern simulation both digests, coordinates and RF RMS matched deployment exactly. [Full arm comparisons and owner hashes](measurements/radio-variance-gradient-solver.json)

| Saved solve and calibration | Horizontal error, deployed → analytic (km) | RF RMS, deployed → analytic (Hz) | Displacement from deployed |
|---|---:|---:|---:|
| DS30-0374, fixed zero | 1.855441343 → 1.855441293 | 101.535912756 → 101.535912750 | 55.6 µm |
| DS30-0374, fitted | 1.935369631 → 1.935369693 | 101.519802851 → 101.519802857 | 69.8 µm |
| South, fixed zero | 0.816788804 → 0.816788804 | 6.502298682 → 6.502298682 | 0 |
| South, fitted | 1.101408650 → 1.101408650 | 6.391939883 → 6.391939883 | 0 |

The prior physical receiver-margin deviations from deployment were 21.3 and 51.2 µm. The analytic fit removes their numerical amplification and converges to a different optimum from the legacy fit on the deployed margins. On this complete physical replay the exact-margin crossover alone reproduced the original endpoints. Horizontal accuracy was effectively unchanged. The analytic fit improves variance conditioning and fails the strict deployment parity gate.

Whole saved solver CPU and elapsed were 22.251 and 22.472 s on DS30-0374 and 4.545 and 4.609 s on the southern simulation. The instrumented analytic profile contributed 4.923 ms and 1.904 ms, respectively. These are saved-input costs. No new complete timing pair or raw receiver comparison was run.

## Reproduce

Use the original saved pairs and frozen releases referenced by the driver. The parent process uses the checkout storage adapter to read existing receipts. Each complete solver subprocess loads the published research bundle and installed release, checks the fit source pin and uses only candidate detections. The published position references enter scoring after both solves.

~~~bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
trial=$(mktemp -d "$bench/radio-variance-gradient.XXXXXXXX")
module=reports.ALGO08.single-core-2x.radio_variance_gradient_trial
python="$release/venv/bin/python"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD/src:$PWD:$release/src:$release"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" prepare "$bench" "$trial/preparation.json"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" solve "$bench" "$trial/preparation.json" "$trial/solver.json"
~~~

Eleven targeted component tests passed. They cover finite-difference gradients, an interior solution, all clamp regimes, the kink, the ratio endpoints and the original observation matching. [Tests](../../../tests/pipeline_eval/test_analytic_radio_variance.py) · [Saved-input driver](radio_variance_gradient_trial.py)
