# Screened-stock solver profile on the southern portable input

The newly frozen screened-stock launcher reproduced the stored positions, Doppler RMS and owner digests in both calibration arms. Conservative recovery took **34.35 of 61.52 profiled CPU seconds**. Its salvage routine accounted for 31.60 seconds. The original profile arithmetic and noise diagnostics accounted for 15.64 and 9.77 seconds inside salvage. The earlier unprofiled screened-stock solve took 50.89 CPU seconds including the selected evidence packet. [Profile receipt](measurements/screened-stock-profile.json) · [Unprofiled comparison](screened-stock-recovery.md)

The run used the frozen publication module, release interpreter, complete candidate specification and checked source pins. The adapter intercepted its acquisition callback after the frozen lazy startup hook and supplied the released southern detections. The profile begins at those detections and measures `algo08_position.solve` through preparation, cavity, guard and selected packet. `cProfile` used a process CPU timer. The profile recorded 27.60 million calls and spent 61.37 seconds in its reported call accounting. The 61.52-second enclosing process counter includes profiler overhead. [Screened-stock specification](measurements/screened-stock-freeze.json) · [Profiler](screened_stock_profile.py)

| Disjoint solver boundary | Profiled CPU seconds |
|---|---:|
| Native track and causal orbit preparation | 6.455 |
| Initial ranking and screened fit | 6.254 |
| Conservative recovery | 34.348 |
| Family history policy | 3.465 |
| Signed update | 0.991 |
| Complete-family cavity nominations and fit | 5.211 |
| Selected evidence packet | 4.200 |

Within conservative recovery, 65,410 calls to the retained-track profile used 11.551 seconds of self CPU and 15.641 seconds including their callees. The 65,375 noise screens used 3.000 seconds self and 9.770 seconds including their callees. The selected packet included a 3.985-second posterior grid. The recovery cache reused zero pairs and the existing endpoint cache reused 90 evaluations. This is one containing solve with 4,149 final owners per arm. [Profile totals and cumulative subgroups](measurements/screened-stock-profile.json)

## Deferring residual calculations until selection

The deployed coarse salvage loop reads only phase costs. Its fine loop reads every cost, chooses the original visible minimum, and reads residual, alias, bias and RMS from that winning row. The component retains the existing alias rounding, whitening, bias fit, cost reduction, phase penalty and order. It defers RMS and residual calculation to that winner when its array layout preserves the original reduction. For other layouts it keeps the full reduction. This differs from the earlier quadratic coarse-statistics approximation and support or noise-gate pruning. [Deployed salvage](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Previous coarse statistics](solver.md) · [Previous gate pruning](solver-salvage-bound.md)

| Synthetic component workload | Stock → deferred CPU seconds | Reduction |
|---|---:|---:|
| One broad profile, 134,946 satellite-phase rows × 221 points | 0.398 → 0.268 | 33% |
| Two coarse windows, 134,946 satellite-phase rows × 24 points each | 0.0752 → 0.0508 | 32% |
| 4,096 fine profiles, 121 phases × 121 points each | 0.3238 → 0.2663 | 18% |

These are medians of four alternating timings of the frozen release’s numerical kernel and the component prototype on Gauss CPU 2. The fixed synthetic shapes reflect the profiled catalogue and representative support lengths. Every score was bit-identical on those shapes. The fine check also matched the original residual samples, alias, bias and RMS. Five component tests cover layouts, whitening and ties. The fraction of solve time removable by this change depends on the actual dimensions and data layout of each profile and on integration cost. [Component runner](salvage_profile_readout_trial.py) · [Component timings](measurements/salvage-profile-readout.json)

## Scoped saved solve

The optional readout scopes deferred fields to the original released conservative salvage loop, matching the stock salvage and profile source digests. That loop still computes each phase cost and uses its original visibility mask, phase penalty, ordering, eligibility, and gates. A whole-array request, an unsupported input signature or a layout requiring the original reduction invokes the released full calculation. Other track consumers use the regular profile. [Scoped binding](../../../tools/pipeline_eval/variants/algo08_deferred_salvage_readout.py)

One unprofiled southern containing replay with the opt-in took **49.487 solver CPU seconds** against **50.885** in the existing screened-stock receipt, a reduction of **1.398 seconds (2.75%)**. Elapsed time was 54.054 seconds against 55.125 in that receipt. The five archived trim nominations and twenty-two logged alternative scores matched exactly. Both endpoints, RMS values and 4,149-owner maps agreed in both calibration arms. [Unprofiled comparison receipt](measurements/screened-stock-deferred-salvage.json) · [Archived trim and owner reference](portable-south-solver-attribution.md)

| Measured boundary inside the deferred solve | Calls | CPU seconds |
|---|---:|---:|
| Deployed salvage loop with deferred readout | 1 | 24.225 |
| All original phase scores, inside salvage | 65,410 | 13.324 |
| Winning-row residual and RMS, inside salvage | 65,375 | 0.387 |
| Full-array fallback or unsupported profile | 0 | 0 |

One additional test confirms scalar residual and RMS share the same selected row and full-array access replays the released computation once. The saved solve measures the deferred readout in isolation. Other salvage optimizations and full-pipeline performance are separate comparisons. [Readout tests](../../../tests/pipeline_eval/test_salvage_profile_readout_trial.py)

## Reproduction

The solver profiling command performs one saved solve and writes `solver.prof`, its terminal receipt and the checked summary. Use the staged inputs from the geographic replay and a fresh output directory. The component command uses synthetic numbers and the release interpreter with no solver call.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -BPs reports/ALGO08/single-core-2x/screened_stock_profile.py run \
  "$bench/portable-v5-geodiverse" "$bench/integration-screened-stock-finish" \
  "$bench/screened-stock-profile-new"
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH="$release/src" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/single-core-2x/salvage_profile_readout_trial.py \
  "$bench/salvage-readout-new.json"
```

To run one unprofiled solve with deferred readout, substitute `run-lazy` and a fresh output directory in the first command.
