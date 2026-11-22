# Fixed predictive layouts in the event likelihood

Reusing invariant prediction work reduced predictive geometry CPU from **330 to 130 ms** on the physical saved case and from **127 to 47 ms** on the northern containing simulation. The physical selected packet still took **4.43–4.45 CPU seconds**. Both calibration arms reproduced their original positions, RF RMS, owner maps, and all numerical grid values on both inputs. [Paired measurements](measurements/predictive-layout.json)

## Scope of the exact reuse

The earlier dense DS30-0374 profile attributed 4.52 seconds to 360 event-predictive calculations, mostly in the selected grid. That time included 2.47 seconds in the underlying curved fit, 0.38 in predictive geometry, and 0.67 in the predictive Gaussian. Most of the remaining local work gathers the curved rows, applies their updated weight and forms their precision Gram. The conditional grid already deduplicates requested points, and the event model caches repeated exact coordinates. The native curved fit already caches its phase-interpolated states. The separate cavity projection optimizes shared all-catalogue sky evaluation for held families. [Conditional grid](../../../src/leo/analysis/position_grid.py) · [Event model](../../../src/leo/analysis/localization_v3/event_position.py) · [Cavity projection](solver-cavity-projection.md)

The trial prepares the predictive view's position-independent phase states with the existing geometry cache and fills the original phase and orbital columns at each receiver trial point. It keeps the privately owned hardware, smooth receiver coefficients, noise and track-bias columns in the original dimensions and array order. The selected curved rows and their weighted right product use bounded reusable scratch. The curved posterior, full precision product and Gaussian factorizations remain in their original arithmetic order, with their weights recalculated at every point. [Prototype](../../../tools/pipeline_eval/variants/algo08_predictive_layout.py)

The new attachment applies to empty event layouts with up to 16 MiB of dense scratch. Nonempty or oversized layouts use the original arithmetic and allocation. A changed curved mask, noise vector, power or layout sends that Gram evaluation through the release path. The component tests compare exact bytes for both calibration widths, changed phase references, masked and unmasked curved rows, and predictive models with one or several bias columns. They also exercise layout fallback. [Component tests](../../../tests/pipeline_eval/test_algo08_predictive_layout.py)

## Matched saved-input replays

Every pair begins at the same verified saved detections and runs through the complete selected packet and standard grid. Both arms use causal archive reuse and coarse salvage statistics. One low-priority pinned CPU and one numerical thread ran each job. DS30-0374 ran the control first. The northern input ran the prepared variant first. [Trial runner](solver_predictive_layout_trial.py)

| Saved input | Curved subcall CPU (s) | Curved Gram CPU (s) | Predictive geometry CPU (s) | Predictive Gaussian CPU (s) | Selected packet CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0374 | 2.321 → 2.457 | 0.947 → 1.012 | 0.330 → 0.130 | 0.632 → 0.650 | 4.425 → 4.445 | 28.870 → 28.538 |
| North containing | 0.659 → 0.657 | 0.035 → 0.036 | 0.127 → 0.047 | 0.083 → 0.076 | 0.866 → 0.788 | 6.998 → 6.963 |

All 360 physical prediction calls and all 413 northern calls used a prepared layout. The physical case built two layouts and the northern case built twelve. Both runs avoided the fallback paths. Setup consumed under one millisecond per input. Each case completed 179 grid evaluations. All grid fields matched after dropping the elapsed time. Selected trim records and endpoint objective replay matched too.

| Saved input and calibration | Published owners | Horizontal error (km) | Solver RF RMS (Hz) |
|---|---:|---:|---:|
| DS30-0374, `c = 0` | 2,905 | 1.855 | 101.536 |
| DS30-0374, fitted `c` | 2,905 | 1.935 | 101.520 |
| North containing, `c = 0` | 302 | 0.745 | 5.380 |
| North containing, fitted `c` | 302 | 0.711 | 5.173 |

The reference coordinates enter the postfit scoring only. [Physical reference](../location-audit/README.md) · [Simulated reference scores](../regional-release/blind-scores.csv)

The repeated predictive geometry represented 0.33 CPU seconds of the physical control. The weighted Gram and conditional Gaussian accounted for 1.58 CPU seconds together and continue to run at every point. The measured geometry savings are small at the whole-pipeline boundary. The physical selected-packet timing and the complete solver timing from one pair give different directions of change.

## Reproduce

Use the release runtime, the pinned saved detections, a common offer and the original causal archive. The earlier detector digest table identifies both the physical input and the saved Northern simulation detections, which can be replayed with the containing offer. [Saved detector input digests](solver-track-moments.md#reproduce)

```sh
work=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
for mode in control prepared; do
  flock "$work/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_predictive_layout_trial.py \
    "$mode" "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
done
```
