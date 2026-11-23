# Reuse of byte-identical Graph polynomial fits

Caching the complete `_best_piece` selection within one Graph lane saved **0.499 CPU s on DS30-0008** and **0.037 CPU s on DS30-0016**. Both pair orders improved on each recording. Complete prepared Graph evidence matched bitwise, including polynomial coefficients, pieces, signed observations, memberships and curvature. The saved installed decisions, both calibration arms, owner digests, position paths and full numerical grids also matched on both recordings. [Frozen procedure](graph-polynomial-cache-protocol.md) · [Timing, source pins and scientific receipts](measurements/graph-polynomial-cache.json.gz)

## Paired Graph preparation

| Saved installed detections | Stock CPU (s) | `_best_piece` CPU (s) | `_piece` CPU (s) | Both caches CPU (s) | Graph rows / tracks / curved |
|---|---:|---:|---:|---:|---:|
| DS30-0008 | 1.693 | 1.194 | 1.629 | 1.256 | 6,456 / 236 / 111 |
| DS30-0016 | 0.0822 | 0.0448 | 0.0702 | 0.0448 | 374 / 16 / 3 |

Values average the forward and reverse orders on the same low-priority Gauss core. The strongest mode saved 29.5% of dense Graph CPU and 45.5% of weak Graph CPU. Edge construction, original best-path inputs and the installed native recurrence stayed in use. Each run made the same 201 native path calls on dense and 30 on weak, with zero reference fallbacks. The existing degree-preparation experiment shares support and design within a single choice. The canonical alias experiment combines fits whose original lifts can differ slightly. This cache reuses decisions only under exact effective input equality. [Prior degree work](../single-core-2x/graph-degree-and-allocation.md) · [Prior alias study](../single-core-2x/graph-canonical-alias.md)

The dense census found **1,898 hits out of 3,427** `_best_piece` calls, including 355 during finalization on entries populated during refinement. The weak census found **123 of 158**, including 36 across that boundary. Dense original duplicate work measured 0.649 CPU s for `_best_piece`. A direct `_piece` census measured 0.285 s of duplicate calls. Only 0.054 s of that work was outside the already repeated `_best_piece` calls. The disjoint instrumented totals were 0.703 s dense and 0.045 s weak. They include census overhead. The paired clocks, which include lookup, snapshot and owned-result costs, show the net effect. On dense, adding the `_piece` cache on top of `_best_piece` made preparation 0.062 s slower. [Per-mode clocks and refinement-to-finalization hits](measurements/graph-polynomial-cache.json.gz)

## Effective fit inputs and output ownership

The `_best_piece` lookup binds every original lane time and measured value, the full configuration, ordered support indices and exactly the binary lifted response used by the pinned selector. The selector uses its incoming prediction only to compute the lift. `_piece` binds all of its time, lifted response and index inputs, degree and lane configuration. Array keys include dtype, shape, strides and bytes. The prototype checks current snapshots to guard mutation and clears a cache when its lane-wide inputs change. It copies the cached dictionary and arrays on reuse. Caches hold at most 256 entries per function per lane, accept at most 4,096 values per vector and are discarded on lane return. Unsupported inputs use the original operation. Tests exercise a one-ULP change to a lift, signed zero, ordered support, strides, mutated inputs and config, output ownership and lane lifetime. [Adapter](polynomial_fit_cache.py) · [Tests](../../../tests/pipeline_eval/test_polynomial_fit_cache.py)

## Installed saved decisions

The eligible `_best_piece` mode ran once per recording through the original installed numerical solve. Both physical recordings retained their original supplied region and causal TLE archive. The cases share the same surveyed reference. Both kept the same decisions, owner identities, position path, all 179 grid points and zero endpoint objective replay error. [Survey basis](../../2026_11_21_ds30_full/reference-audit.json) · [Exact comparison receipts](measurements/graph-polynomial-cache.json.gz)

| Case | Horizontal error, fixed / fitted (km) | RF RMS, fixed / fitted (Hz) | Owners per arm | Numerical CPU / elapsed (s) |
|---|---:|---:|---:|---:|
| DS30-0008 | 1.639 / 1.512 | 129.703 / 129.663 | 4,472 | 52.247 / 52.711 |
| DS30-0016 | 1.644 / 1.661 | 109.375 / 109.479 | 109 | 3.247 / 4.613 |

These single numerical launches establish parity with the archived decisions. They stop before PNG rendering and filesystem publication. They supply no paired full-solve speed measurement. A separate edge-construction change can be applied in the same lane scope. Its combined runtime needs a matched publication comparison. [Saved numerical trial](polynomial_fit_cache_trial.py)

Use the archived recording-readable account and the installed payload before the checkout on `PYTHONPATH`. Under the same Gauss CPU 2, `gauss.lock`, `nice -n15`, `ionice -c2 -n7` and one-thread controls, run `polynomial_fit_cache_trial.py graph CASE GRAPH_JSON`, then `graph CASE CENSUS_JSON --census-only` for the phase-specific hit count. The command `downstream CASE DENSE_GRAPH_JSON WEAK_GRAPH_JSON RESULT_JSON` verifies exact numerical parity if the frozen stage gate passes. All inputs are saved detector and causal archive products. Nine focused and adjacent tests passed. [Gauss runner](polynomial_fit_cache_trial.py) · [Component tests](../../../tests/pipeline_eval/test_polynomial_fit_cache.py)
