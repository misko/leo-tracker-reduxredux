# Exact reuse of track and posterior calculations

Reusing complete endpoint likelihood results saved **0.62 CPU seconds on DS30-0374** and **0.53 seconds on north far** through the selected packet and exact grid. Both calibration arms reproduced their original outputs. Caching fixed Gram entries and precomputing posterior matrix destinations saved much less at their respective boundaries. [Paired receipts](measurements/fixed-gram-readout.json)

The saved DS30-0374 profile attributed 9.19 profiled seconds to the native likelihood wrapper. The earlier family Schur experiment timed about 4.8 CPU seconds inside the C likelihood, including numerical assembly, factorization and repeated robust updates. Even a zero-cost C likelihood would cap the physical saved-detection solver speedup around 1.2×. This trial times three smaller exact opportunities in that boundary. [Native Schur timing](solver-native-family.md) · [Earlier per-call statistics](solver-statistics.md)

## Retain fixed products between likelihood calls

The deployed kernel forms a normalized Gram matrix and right-hand side for each observation group at every trial position. The prototype keeps the last input values, scales and numeric Gram for each existing symbolic layout. A group column is reusable only when every contributing input and noise scale agrees byte for byte. RHS entries always use the current measurements. Changed rows of the Gram accumulate in the original observation order. A cross entry reflected into a fixed row has the same two scalar operands and the same observation order as its counterpart. The original Gamma updates and numerical factorization consume the resulting Gram. [Native prototype](../../../tools/pipeline_eval/variants/algo08_fixed_gram.h)

The numeric workspace is bounded to 8 MiB per layout. Oversized work, allocation failure, a busy layout or values outside the guarded range use the original row contraction. Both paths retain stock numerical and layout fallbacks.

| Saved input | Original → actual tracked Gram products | Gram/RHS CPU (s) | Whole native C CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|
| DS30-0374 | 1,281.5 → 239.0 million | 0.261 → 0.246 | 4.721 → 4.597 | 29.363 → 29.042 |
| North far | 204.1 → 40.1 million | 0.034 → 0.027 | 4.302 → 4.372 | 11.353 → 11.346 |

The original row contraction was already inexpensive. Matching and packing the design for reuse consumed most of the saved arithmetic. Neither saved-input trial reached the additional numeric cache guard. DS30-0374 exercised the same 100 original Python fallbacks for unsupported layouts in both modes. North far had no native fallbacks.

## Reuse the posterior destinations on every robust update

A separate mode precomputes where each group Gram entry contributes to the shared matrix, private block or coupling. It accumulates one triangle of the symmetric part of the shared Gram and copies that triangle before the original Schur and conditioning operations. Destinations and row-product ordering are invariant across changes in the track weights. The release still computes an exact factor and a new variational update with each changed weight. Layouts that exceed the map limit or fail allocation use the original loops.

| Saved input | Mapped assemblies | Posterior assembly CPU (s) | Whole native C CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|
| DS30-0374 | 26,471 of 26,471 | 0.303 → 0.219 | 4.690 → 4.660 | 28.681 → 30.298 |
| North far | 101,302 of 101,302 | 0.256 → 0.177 | 4.447 → 4.335 | 12.203 → 11.968 |

The shared and private destinations can be initialized more cheaply. The already small assembly stage leaves the whole run sensitive to timing variation. This mode exercised the original 100 Python fallbacks on DS30-0374 and no fallback at the mapped boundary.

## Reuse the selected endpoint posterior during readout

The stock regional fitter reads its chosen position after optimization. Then state, retained-track gating and summary can compute that same fixed model again at the same position. A one-entry cache starts at optimizer return and retains the first complete selected endpoint result. It compares the coordinates, observation mask, scales, phase reference, orbits, hardware and smooth feature arrays byte for byte. A changed value or unsupported layout invokes the original calculation. The wrapper supports the direct normal likelihood and releases its active model before any later optimizer invocation, including another fit of the same instance. It also restores the active instance on scope exit. The history and predictive closures retain their previous path, and the event likelihood and publication grid already have their own bounded caches. The older fit-point experiment scoped its cache within one optimizer call. [Endpoint prototype](../../../tools/pipeline_eval/variants/algo08_endpoint_readout.py) · [Earlier fit-point measurement](cost-checks.md)

This comparison wraps both arms with the same endpoint observation logic. The control evaluates every request. The candidate can reuse the original result. Only the individual measurement boundaries in this report have been timed. [Runner](solver_fixed_gram_trial.py) · [Context mutation tests](../../../tests/pipeline_eval/test_algo08_endpoint_readout.py) · [Native exactness tests](../../../tests/pipeline_eval/test_algo08_fixed_gram.py)

| Saved input | Repeated complete endpoint calls avoided | Endpoint readout CPU (s) | Whole native C CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|
| DS30-0374 | 117 | 1.329 → 0.448 | 4.678 → 4.417 | 28.955 → 28.340 |
| North far | 93 | 0.720 → 0.223 | 4.375 → 3.890 | 11.595 → 11.065 |

The physical cache avoided 93 native calls, 24 original Python fallback calls and 1,403 native posterior assemblies across 60 models. The north-far cache avoided 93 native calls and 10,464 assemblies across 50 models. No cached readout request needed a context rebuild or unsupported-layout fallback on either input. The solver calculated each original endpoint once per model before using its result for subsequent readouts.

Elapsed time moved from 29.471 to 32.294 seconds on DS30-0374 and from 11.789 to 11.194 seconds on north far. The physical case ran the observed control first. The simulated case ran the cache first. These are single pairs. The physical elapsed result did not reproduce the CPU reduction.

## Scientific outputs

Each pair used the same verified saved detections, factory calibration settings and matched zero/fitted RF arms, original TLE archive and offered region on one low-priority pinned core. Both complete publication grids and reported paths match after dropping elapsed time. The north-far offer still produced both false fixes. Frequencies below are the solver RF RMS values. The reference coordinates are used only for the postfit error. [Physical reference](../location-audit/README.md) · [Simulation scores](../regional-release/blind-scores.csv)

| Saved input and arm | Owners | Horizontal error (km) | Solver RF RMS (Hz) |
|---|---:|---:|---:|
| DS30-0374, `c = 0` | 2,905 | 1.855 | 101.536 |
| DS30-0374, fitted `c` | 2,905 | 1.935 | 101.520 |
| North far, `c = 0` | 228 | 52.455 | 37.951 |
| North far, fitted `c` | 228 | 52.491 | 37.533 |

## Reproduce

Use the frozen solver assets and the verified detectors from the earlier moment comparison. The runner accepts `control` versus `fixed` for numeric Gram reuse, `control` versus `mapped` for posterior maps, and `observe` versus `readout` for complete endpoint reuse. [Saved detector digests](solver-track-moments.md#reproduce)

For a full experimental launcher, add `--endpoint-reuse` to the paired SHA-256 freezer command. The source is pinned only when the option is selected. An enabled run reports its model and readout counts. [Paired SHA-256 freezer recipe](paired-sha256.md#reproduction)

```sh
work=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock "$work/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$@"
}
lock "$release/venv/bin/python" -B -m tools.pipeline_eval.variants.algo08_fixed_gram "$work/gram.so"
for mode in observe readout; do
  lock "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_fixed_gram_trial.py \
    "$mode" "$native" "$archive" "$release/assets" "$offer" "$work/gram.so" "$native_digest"
done
```
