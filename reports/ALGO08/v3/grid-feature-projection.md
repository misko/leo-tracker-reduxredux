# Exact per-view projection and row packing on the dense map

The fused projection and one-pass row selection reduced the complete DS30-0008 grid from **5.393 to 5.035 CPU seconds**, a **0.358 s** or **6.6%** saving. The surrounding numerical evidence slice fell from **5.461 to 5.107 s**. All 179 locations, every objective value in both calibration arms, and the original checked posterior calls were preserved. The experiment rebuilt the selected context from the authenticated cold witness. Cold discovery, the geographic proof, acquisition, and rendering were outside the measured comparison. [Protocol](grid-feature-projection-protocol.md) · [Exact map, scope, and source receipts](measurements/grid-feature-projection.json.gz)

## Measured scope

The first census charged **1.604 CPU s** to map-point projection and feature work, with roughly 1 ms left for interpolation after the existing phase-state cache. Its grid checker compared a subset of archived point fields with the full returned point object, which already included latitude and longitude. Direct comparison of the saved full point objects succeeded. The following pairs use full-object checks and the final paired control measured **1.464 s** in the same scopes. The checked posterior export took **1.889 s** in the final control, independently of the disjoint scopes below. The final comparison ran each complete selected map in a fresh process on the same low-priority Gauss CPU, incumbent first.

| CPU seconds across all fresh arm-locations | Incumbent | Native projection and selection |
| --- | ---: | ---: |
| Nominal Doppler and elevation | 0.145 | 0.001 |
| Both phase-offset projections | 0.211 | 0.001 |
| Physical mode projection | 0.139 | 0.001 |
| Fused projection, coordinates and cache bookkeeping | 0.032 | 0.136 |
| Curved design allocation and fill | 0.441 | 0.458 |
| Curved design row selection and scaling | 0.335 | 0.179 |
| Predictive design allocation and fill | 0.125 | 0.129 |
| Predictive handoff packing | 0.036 | 0.037 |
| **Disjoint projection and design total** | **1.464** | **0.942** |
| Checked native posterior export | 1.889 | 1.898 |
| Complete map | 5.393 | 5.035 |
| Numerical evidence, selected context | 5.461 | 5.107 |
| Saved-context replay including input verification and reconstruction | 16.737 | 16.477 |

The directly timed projection and selected design saved **0.387 s** and **0.157 s** respectively. Their sum exceeds the observed full-map gain. The rest of the measured map includes Python bookends, checked handoff validation, reduced predictive factor evaluation, and intervening allocation and memory traffic. The paid map difference is the quantity available for a dense solve budget. One saved packet and one full-map pair support this figure. A cumulative whole-solver or live publication replay was outside this experiment.

## What changed

For a fixed phase view, the C kernel uses the existing phase-state cache and the released Python WGS84 and ENU conversions. It forms observer-relative coordinates, range, Doppler, ±0.01-second difference and three physical perturbation modes in one row pass. It omits azimuth and omits elevation for the two offsets whose callers consume frequency alone. The nominal elevation still uses the original NumPy matrix product, hypot, arctangent and degree conversion. The kernel preserves the installed contiguous NumPy three-element einsum reduction order, the separate physical-mode dot order and scale, and the original degree and frequency conventions. The row selection kernel copies the bit-preserving scale-one prefix and multiplies the remaining selected values in a single gather pass. The installed design fill still runs at every node. [C kernel](grid_feature_projection.c) · [Binding and fallback](grid_feature_projection.py)

The experiment uses the pinned Python geometry source, binary64 contiguous aligned states, finite projected outputs and positive finite ranges. Each immutable prepared view must pass a whole-array bitwise comparison on its first use. Unsupported layout, nonfinite results or an exactness disagreement use the incumbent projection. The selected row port also falls back on unsupported layout. The comparison uses the installed NumPy arithmetic on this Gauss host. The saved experiment makes no deployment claim for other platforms or package versions.

An earlier exact variant also prebuilt the fixed design scaffold and checked each immutable input against a snapshot. On its own full-map pair, curved design increased from **0.445 to 0.759 CPU s** and the map increased from **5.441 to 5.788 s**. The simpler final trial removes the scaffold. The earlier code is preserved in research revision `c9e8e43a9` with its own receipts.

## Numerical checks and scope

The sample covered the centre, a refined-grid location and all four corners. All 24 projection bundles, 12 selected curved designs and 12 full predictive designs were checked bit for bit. Each complete map kept the same 356 independent checked posterior calls, 178 per calibration arm. Endpoint reuse accounts for the other two arm-locations. The native candidate performed four initial projection comparisons and 708 further native projections across the distinct curved and predictive views. No fallback fired.

The complete numerical replay matched all ordered coordinates, latitude and longitude values, objectives, failure fields, the published path, and all 4,367 owner and role rows in each arm. Endpoint objective replay differences were zero. RF RMS stayed at **140.961 Hz** for fixed zero and **140.950 Hz** for fitted calibration, with identical endpoints within each arm. The candidate is scoped to the diagnostic sampler. The selected fit and previous position-candidate decisions precede this change. Thirty component and adjacent tests passed. [Component tests](../../../tests/pipeline_eval/test_grid_feature_projection.py) · [Saved reconstruction](grid_neighbor_gamma_trial.py)

## Reproduce

Run the six-node candidate sample first, then run the incumbent and candidate on the saved complete map. Each output is a fresh JSON path with an existing parent directory. The archived assets may require an account with access to the regional qualification archive. Keep `TMPDIR` on tmpfs when space is tight.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
export PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$PWD:$release/src:$release"
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
run_grid() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
    "$release/venv/bin/python" -BPs reports/ALGO08/v3/grid_feature_projection_trial.py "$@"
}
run_grid "$output/edge.json" --candidate --edge-sample
run_grid "$output/control.json"
run_grid "$output/candidate.json" --candidate
```
