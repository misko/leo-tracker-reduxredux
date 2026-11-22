# Repeated Gamma updates in the full regional likelihood

The saved DS30-0374 profile attributed 9.19 profiled seconds to the complete native likelihood wrapper and 1.78 to paired phase geometry. The geometry path already caches phase-interpolated orbit states at a fixed linearization, including the plus and minus perturbations. Earlier native experiments reduced group residual work or reduced factor width and saved at most 1.1 kernel seconds. Removing repeated variational updates is a distinct opportunity across initial, recovery, family, cavity and grid objectives. [Native Schur measurements](solver-native-family.md) · [Residual contraction measurements](solver-statistics.md) · [Existing phase geometry cache](../../../src/leo/analysis/localization_v3/marginal.py)

Both prototypes retain the original observations, priors, group design, native conditioning checks, iteration cap and `1e−5` stopping rule. The comparison starts at saved detections and uses the exact causal-archive and salvage changes in every run. It uses one pinned low-priority process and records the kernel CPU and whole selected packet separately. The station references enter the score after the solver has returned. [Trial runner](solver_warm_trial.py)

## Carrying rates between calls

The first prototype seeds the rate vectors with the last converged posterior of the same model instance. A changed observation mask or phase geometry snapshot discards the seed. The native code also checks the input dimensions and Gamma prior parameters. The cache holds up to eight models and the two calibration arms have separate instances. A failed or unconverged warm call retries the original cold kernel. [Warm-start implementation](../../../tools/pipeline_eval/variants/algo08_robust_warm.py)

On DS30-0374 the native CPU was 4.680 → 2.819 seconds, variational updates fell from 25,090 to 14,031, and the saved-detection-to-grid CPU was 28.661 → 27.082 seconds. Both arms kept 2,905 owners. On north-far the control completed in 11.463 CPU seconds. The warm path stopped at 8.061 CPU seconds with a cavity replay error, after 26,482 updates. A newly constructed cavity model began cold and exceeded the allowed `1e−5` objective replay difference. The existing repair then rejected an approximately 43 ns mismatch between the recorded expansion and posterior phase where it required equality within `1e−12` seconds. The incomplete warm time and update count cover less work than the 99,007-update control. This rejects carry-over between objective calls under the original publication checks.

On the completed physical trial, the carry-over moved the `c = 0` endpoint by 0.254 m and the fitted-`c` endpoint by 13.893 m. Errors were 1.855 and 1.933 km, and RF RMS was 101.535890 and 101.518475 Hz. Both 179-point grids completed. On the 81 common grid coordinates, the maximum score changes were 0.00986 and 0.35730. The largest selected endpoint replay difference was `8.33e−8`.

## Extrapolating within a single likelihood call

The second prototype starts each fit from the original Gamma rates. After two ordinary rate updates, it estimates an extrapolation of the log-rate vector using bounded SQUAREM with a maximum step factor of four. The kernel checks finite rates and the Gamma rate floors. It resumes from the ordinary successor if the extrapolated point increases the maximum log-rate residual. An accelerated result must satisfy the original fixed-point convergence condition. A native failure or exhausted accelerated budget retries the original cold kernel. Each call depends on its own observations, model and trial point. [Deterministic implementation](../../../tools/pipeline_eval/variants/algo08_robust_accel.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_robust_warm.py)

| Saved input | Native updates, control → accelerated | Native CPU, control → accelerated (s) | Solve and grid CPU, control → accelerated (s) | Owners per arm, control → accelerated |
|---|---:|---:|---:|---:|
| DS30-0374 | 25,090 → 16,823 | 4.680 → 3.430 | 28.661 → 28.204 | 2,905 → 2,905 |
| North far | 99,007 → 30,520 | 4.334 → 1.262 | 11.463 → 8.782 | 228 → 190 |

The physical cases evaluated the same number of native calls and used the original Python fallback for the same 100 calls. The accelerated north-far solve made 1,735 native calls against 2,295 in the control. The control hit its original update cap on 99 calls. The accelerated solve reached the stopping criterion on all calls it made. The changed owner sets and number of model evaluations contribute to the north-far CPU difference.

| Saved input and arm | Endpoint movement | Error, control → accelerated (km) | Solver RF RMS, control → accelerated (Hz) |
|---|---:|---:|---:|
| DS30-0374, `c = 0` | 0.214 mm | 1.855 → 1.855 | 101.535913 → 101.535913 |
| DS30-0374, fitted `c` | 0.130 mm | 1.935 → 1.935 | 101.519803 → 101.519803 |
| North far, `c = 0` | 3.260 km | 52.455 → 52.634 | 37.951 → 21.090 |
| North far, fitted `c` | 10.299 km | 52.491 → 53.047 | 37.533 → 25.266 |

All deterministic acceleration arms replayed their own selected endpoint objective exactly. On DS30-0374 both owner hashes matched. The maximum change over common grid coordinates was 0.00092 for zero calibration and 0.00093 for fitted calibration. North-far kept producing false fixes, and both arms changed their owner hashes. The lower frequency RMS accompanied worse geographic errors. [Physical scoring reference](../location-audit/README.md) · [Wrong-region control scores](../regional-release/blind-scores.csv)

The separate `--audit-fixed` comparison reconstructed the stock-selected north-far models and passed identical 228-observation native inputs to both kernels at the endpoint, center, and a corner in each arm. All six cold and accelerated calls reached the original tolerance. Their combined update count fell from 258 to 125. The maximum conditional residual change was 0.00204 Hz, the maximum Gamma noise-precision change was 0.000144, and the maximum absolute native ELBO change was `1.16e−8`. The Gamma noise term and log-volume moved by up to 0.000823 and 0.000108, respectively. The full north-far divergence appeared during selection of the model and observations. These fixed-label checks do not identify whether a budget-limited fit, an early branch comparison, or a gate first changed that selection.

On the physical recording, even removing the entire measured native kernel would cap this boundary's contribution at about 1.20× for the full solve and grid. The deterministic acceleration saved 0.457 CPU seconds on that input and changed the selected evidence on the wrong-region input. These results do not qualify either update schedule as a compatible substitution.
