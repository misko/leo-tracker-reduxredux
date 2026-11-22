# Exact likelihood work in the publication grid

A triangular solve for the predictive rows did not reduce complete grid CPU on either saved input. DS30-0016 moved from **284.7 to 290.2 ms** and the northern near-edge simulation from **732.1 to 732.4 ms**. The trial evaluated every original point in both calibration arms. Its scores moved by up to **4.55 × 10⁻¹³** from floating-point arithmetic. The publication code and frozen candidates still use the original kernel. [Measurements](measurements/solver-grid-kernel.json)

## The published grid

The sampler fixes satellite ownership and each arm's phase linearization, then re-evaluates the nuisance likelihood at every point it records. It labels cells for which that calculation fails, and publishes an ordered partial grid if the time budget expires. `evaluated_points` counts those actual trials. On a fix, the resulting grid and its recorded optimizer path bind to that publication's terminal and position PNG. An interpolated surface would need its own research product and legend. An interstitial check cannot make interpolated values into evaluations of the original likelihood. [Sampler](../../../src/leo/analysis/position_grid.py) · [Grid contract](../../../src/leo/contracts/position_grid.py) · [Figure labels](../../../src/leo/presentation/fast_standard_analysis.py)

The sampler already deduplicates coordinates, evaluates both arms at every location, and starts with the optimizer endpoints. The selected event likelihood also caches recent exact coordinates per arm. On these inputs the two arms had identical curved observation times and labels. Their stored phase references agreed on **37 of 127** per-observation inputs to the physical geometry and **zero of 285** in the northern geometry. The largest reference difference was **0.042 s** physical and **0.166 s** simulated. The extra fitted RF calibration column was nonzero at every retained curved observation, 90 and 285 respectively. A cache keyed only by receiver position would mix different orbit projections or profiled likelihoods. Reusing geometry on a subset of rows with identical references would still leave separate robust weights, nuisance fits and predictive scores. [Event likelihood](../../../src/leo/analysis/localization_v3/event_position.py) · [History likelihood](../../../src/leo/analysis/localization_v3/history_position.py)

## Native triangular solve

The grid integrates the pending linear tracks against the curved posterior. It factors that posterior's precision as (LL^\top), then computes (L^{-1}U^\top) for every predictive-feature row (U). The stock kernel passes this lower-triangular matrix to a general solve. The trial uses one native triangular solve with the same right-hand sides. The subsequent likelihood, noise and bias priors are unchanged. This path differs from the earlier predictive-layout trial, which reused scratch and geometry and retained the original general solve. [Triangular kernel](../../../tools/pipeline_eval/variants/algo08_grid_triangular.py) · [Earlier predictive layout trial](solver-predictive-layout.md)

Each input used one replay from digest-verified detections and the original causal archive. At the selected callback the stock and triangular methods independently reconstructed the same fixed result, then evaluated its two calibration grids. The trial kernel ran only inside the grid sampler. The order was stock-first on DS30-0016 and triangular-first on the public simulation. Each process used one low-priority pinned CPU. The timing includes matched instrumentation in both arms. [Trial runner](solver_grid_kernel_trial.py)

| Saved input | Grid locations | Predictive calls | Predictive CPU, stock → triangular | Grid CPU, stock → triangular | Selected packet CPU, stock → triangular |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 179 | 356 | 40.86 → 44.16 ms | 284.66 → 290.18 ms | 298.98 → 303.61 ms |
| North near edge | 137 | 272 | 56.61 → 55.43 ms | 732.13 → 732.43 ms | 780.31 → 779.97 ms |

The coordinates, masks, ownership, endpoint objectives and recorded paths matched. DS30 kept 109 owners in each arm and reproduced errors of 1.644 km fixed-zero and 1.662 km fitted. North kept 302 owners in each arm and reproduced 106 m and 141 m. The regional references enter only that assessment. Score changes affected 23 fixed-zero and 34 fitted values on DS30, all within (1.14 × 10^{-13}). On the northern input 21 fixed-zero and 24 fitted values changed, all within (4.55 × 10^{-13}). Neither grid had failed locations. These results measure the same likelihood in different floating-point arithmetic. [Physical reference](../location-audit/README.md) · [Northern reference scores](batch-publication.md)

Even removing the entire measured stock grid would cap saved-detection solver speedup at about **1.06×** on the short physical input and **1.10×** on north near edge. The prior dense DS30-0374 comparison spent 4.43 seconds on its complete selected packet, including 0.63 seconds in the predictive Gaussian. The larger DS30-0008 experiment measured 10.37 elapsed seconds for the full grid and evidence phase. Those earlier measurements use different workloads and delimit the scale of this work. The triangular substitution adds numerical differences and delivers no repeatable speed improvement here. [Dense predictive breakdown](solver-predictive-layout.md) · [Long-recording compute budget](cost-checks.md)

## Reproduce

Use the baseline detection file and the offer and archive in each of the saved pair receipts. The measurements preserve both detection digests. Use `--candidate-first` for the northern input. Eleven component tests passed. [Physical pair](measurements/DS30-0016-conditional-reverse.json) · [Northern pair](measurements/north-edge-conditional.json) · [Kernel tests](../../../tests/pipeline_eval/test_algo08_grid_triangular.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/solver_grid_kernel_trial.py \
  "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detection_sha256"
```
